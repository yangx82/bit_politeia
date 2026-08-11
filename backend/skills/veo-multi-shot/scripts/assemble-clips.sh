#!/bin/bash
#
# assemble-clips.sh
# Concatenates multiple video clips with optional transitions using FFmpeg
#
# Usage:
#   ./assemble-clips.sh --clips clip1.mp4,clip2.mp4,clip3.mp4 --output assembled.mp4
#   ./assemble-clips.sh --clips clip1.mp4,clip2.mp4 --transition crossfade --transition-duration 0.5 --output assembled.mp4
#
# Transitions:
#   cut         - Hard cut (no transition)
#   crossfade   - Smooth dissolve between clips
#   fade-black  - Fade to black between clips
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
TRANSITION="cut"
TRANSITION_DURATION="0.5"
OUTPUT=""
CLIPS=""
AUDIO_TRACK=""

# ============================================================================
# Help
# ============================================================================

print_usage() {
    echo ""
    echo -e "${GREEN}Clip Assembly Tool${NC}"
    echo ""
    echo "Concatenates multiple video clips with optional transitions."
    echo ""
    echo "Usage:"
    echo "  $0 --clips <files> --output <file> [options]"
    echo ""
    echo "Required:"
    echo "  --clips, -c           Comma-separated list of input clip paths"
    echo "  --output, -o          Output file path"
    echo ""
    echo "Options:"
    echo "  --transition, -t      Transition type: cut, crossfade, fade-black (default: cut)"
    echo "  --transition-duration Duration of transition in seconds (default: 0.5)"
    echo "  --audio               Path to audio track to overlay"
    echo "  --help, -h            Show this help message"
    echo ""
    echo "Examples:"
    echo "  # Simple concatenation (hard cuts)"
    echo "  $0 --clips shot1.mp4,shot2.mp4,shot3.mp4 --output final.mp4"
    echo ""
    echo "  # With crossfade transitions"
    echo "  $0 --clips shot1.mp4,shot2.mp4,shot3.mp4 \\"
    echo "     --transition crossfade \\"
    echo "     --transition-duration 0.5 \\"
    echo "     --output final.mp4"
    echo ""
    echo "  # With audio overlay"
    echo "  $0 --clips shot1.mp4,shot2.mp4 \\"
    echo "     --audio music.mp3 \\"
    echo "     --output final.mp4"
    echo ""
}

# ============================================================================
# Argument Parsing
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --clips|-c)
            CLIPS="$2"
            shift 2
            ;;
        --output|-o)
            OUTPUT="$2"
            shift 2
            ;;
        --transition|-t)
            TRANSITION="$2"
            shift 2
            ;;
        --transition-duration)
            TRANSITION_DURATION="$2"
            shift 2
            ;;
        --audio)
            AUDIO_TRACK="$2"
            shift 2
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            print_usage
            exit 1
            ;;
    esac
done

# ============================================================================
# Validation
# ============================================================================

# Check for ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${RED}Error: ffmpeg is not installed${NC}"
    echo "Install with: brew install ffmpeg"
    exit 1
fi

# Check required arguments
if [ -z "$CLIPS" ]; then
    echo -e "${RED}Error: --clips is required${NC}"
    print_usage
    exit 1
fi

if [ -z "$OUTPUT" ]; then
    echo -e "${RED}Error: --output is required${NC}"
    print_usage
    exit 1
fi

# Validate transition type
case $TRANSITION in
    cut|crossfade|fade-black)
        ;;
    *)
        echo -e "${RED}Error: Invalid transition type '$TRANSITION'${NC}"
        echo "Valid options: cut, crossfade, fade-black"
        exit 1
        ;;
esac

# Parse clips into array
IFS=',' read -ra CLIP_ARRAY <<< "$CLIPS"
CLIP_COUNT=${#CLIP_ARRAY[@]}

if [ $CLIP_COUNT -lt 2 ]; then
    echo -e "${RED}Error: At least 2 clips required for assembly${NC}"
    exit 1
fi

# Validate all clips exist
for clip in "${CLIP_ARRAY[@]}"; do
    if [ ! -f "$clip" ]; then
        echo -e "${RED}Error: Clip not found: $clip${NC}"
        exit 1
    fi
done

# ============================================================================
# Assembly Functions
# ============================================================================

# Get video duration using ffprobe
get_duration() {
    ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$1"
}

# Assemble with hard cuts (concat demuxer)
assemble_cut() {
    echo -e "${YELLOW}Assembling with hard cuts...${NC}"

    # Create concat file
    CONCAT_FILE=$(mktemp)
    for clip in "${CLIP_ARRAY[@]}"; do
        echo "file '$(realpath "$clip")'" >> "$CONCAT_FILE"
    done

    ffmpeg -y -f concat -safe 0 -i "$CONCAT_FILE" \
        -c:v libx264 \
        -preset medium \
        -crf 18 \
        -pix_fmt yuv420p \
        -an \
        "$OUTPUT" \
        -loglevel warning

    rm -f "$CONCAT_FILE"
}

# Assemble with crossfade transitions
assemble_crossfade() {
    echo -e "${YELLOW}Assembling with crossfade transitions (${TRANSITION_DURATION}s)...${NC}"

    # Build complex filter for xfade
    # For N clips, we need N-1 xfade filters

    # First, get all durations
    DURATIONS=()
    for clip in "${CLIP_ARRAY[@]}"; do
        dur=$(get_duration "$clip")
        DURATIONS+=("$dur")
    done

    # Build input arguments
    INPUTS=""
    for clip in "${CLIP_ARRAY[@]}"; do
        INPUTS="$INPUTS -i \"$clip\""
    done

    # Build filter complex
    FILTER=""
    OFFSET=0
    CURRENT_LABEL="[0:v]"

    for ((i=1; i<CLIP_COUNT; i++)); do
        NEXT_LABEL="[$i:v]"

        # Calculate offset: sum of previous durations minus transition overlaps
        if [ $i -eq 1 ]; then
            OFFSET=$(echo "${DURATIONS[0]} - $TRANSITION_DURATION" | bc)
        else
            PREV_DUR=$(echo "${DURATIONS[$i-1]} - $TRANSITION_DURATION" | bc)
            OFFSET=$(echo "$OFFSET + $PREV_DUR" | bc)
        fi

        # Create xfade filter
        if [ $i -eq $((CLIP_COUNT - 1)) ]; then
            # Last transition - output to [v]
            FILTER="${FILTER}${CURRENT_LABEL}${NEXT_LABEL}xfade=transition=fade:duration=$TRANSITION_DURATION:offset=$OFFSET[v]"
        else
            # Intermediate - output to temp label
            OUT_LABEL="[v$i]"
            FILTER="${FILTER}${CURRENT_LABEL}${NEXT_LABEL}xfade=transition=fade:duration=$TRANSITION_DURATION:offset=$OFFSET${OUT_LABEL};"
            CURRENT_LABEL="$OUT_LABEL"
        fi
    done

    # Execute ffmpeg
    eval "ffmpeg -y $INPUTS \
        -filter_complex \"$FILTER\" \
        -map \"[v]\" \
        -c:v libx264 \
        -preset medium \
        -crf 18 \
        -pix_fmt yuv420p \
        -an \
        \"$OUTPUT\" \
        -loglevel warning"
}

# Assemble with fade-to-black transitions
assemble_fade_black() {
    echo -e "${YELLOW}Assembling with fade-to-black transitions (${TRANSITION_DURATION}s)...${NC}"

    # Create temp directory
    TEMP_DIR=$(mktemp -d)
    trap "rm -rf $TEMP_DIR" EXIT

    HALF_DUR=$(echo "$TRANSITION_DURATION / 2" | bc -l)

    # Process each clip: add fade out at end (except last), fade in at start (except first)
    PROCESSED_CLIPS=()
    for ((i=0; i<CLIP_COUNT; i++)); do
        clip="${CLIP_ARRAY[$i]}"
        dur=$(get_duration "$clip")
        out_file="$TEMP_DIR/clip_$i.mp4"

        FILTER=""

        if [ $i -eq 0 ]; then
            # First clip: fade out only
            FADE_START=$(echo "$dur - $HALF_DUR" | bc)
            FILTER="fade=t=out:st=$FADE_START:d=$HALF_DUR"
        elif [ $i -eq $((CLIP_COUNT - 1)) ]; then
            # Last clip: fade in only
            FILTER="fade=t=in:st=0:d=$HALF_DUR"
        else
            # Middle clips: fade in and out
            FADE_START=$(echo "$dur - $HALF_DUR" | bc)
            FILTER="fade=t=in:st=0:d=$HALF_DUR,fade=t=out:st=$FADE_START:d=$HALF_DUR"
        fi

        ffmpeg -y -i "$clip" \
            -vf "$FILTER" \
            -c:v libx264 \
            -preset medium \
            -crf 18 \
            -pix_fmt yuv420p \
            -an \
            "$out_file" \
            -loglevel warning

        PROCESSED_CLIPS+=("$out_file")
    done

    # Concatenate processed clips
    CONCAT_FILE="$TEMP_DIR/concat.txt"
    for pclip in "${PROCESSED_CLIPS[@]}"; do
        echo "file '$pclip'" >> "$CONCAT_FILE"
    done

    ffmpeg -y -f concat -safe 0 -i "$CONCAT_FILE" \
        -c copy \
        "$OUTPUT" \
        -loglevel warning
}

# Add audio track overlay
add_audio() {
    if [ -n "$AUDIO_TRACK" ] && [ -f "$AUDIO_TRACK" ]; then
        echo -e "${YELLOW}Adding audio track...${NC}"

        TEMP_OUTPUT=$(mktemp).mp4
        VIDEO_DUR=$(get_duration "$OUTPUT")

        ffmpeg -y -i "$OUTPUT" -i "$AUDIO_TRACK" \
            -c:v copy \
            -c:a aac \
            -b:a 192k \
            -t "$VIDEO_DUR" \
            -map 0:v:0 \
            -map 1:a:0 \
            -shortest \
            "$TEMP_OUTPUT" \
            -loglevel warning

        mv "$TEMP_OUTPUT" "$OUTPUT"
    fi
}

# ============================================================================
# Main Execution
# ============================================================================

echo ""
echo -e "${GREEN}Clip Assembly Tool${NC}"
echo "=================================="
echo "Clips: ${CLIP_COUNT}"
for ((i=0; i<CLIP_COUNT; i++)); do
    dur=$(get_duration "${CLIP_ARRAY[$i]}")
    echo "  $((i+1)). ${CLIP_ARRAY[$i]} (${dur}s)"
done
echo "Transition: ${TRANSITION}"
if [ "$TRANSITION" != "cut" ]; then
    echo "Transition duration: ${TRANSITION_DURATION}s"
fi
echo "Output: ${OUTPUT}"
echo ""

# Execute appropriate assembly
case $TRANSITION in
    cut)
        assemble_cut
        ;;
    crossfade)
        assemble_crossfade
        ;;
    fade-black)
        assemble_fade_black
        ;;
esac

# Add audio if specified
add_audio

# Report results
if [ -f "$OUTPUT" ]; then
    OUTPUT_DUR=$(get_duration "$OUTPUT")
    OUTPUT_SIZE=$(ls -lh "$OUTPUT" | awk '{print $5}')

    echo ""
    echo "=================================="
    echo -e "${GREEN}Assembly complete!${NC}"
    echo "Output:     $OUTPUT"
    echo "Duration:   ${OUTPUT_DUR}s"
    echo "Size:       $OUTPUT_SIZE"
    echo ""
else
    echo -e "${RED}Assembly failed - output file not created${NC}"
    exit 1
fi
