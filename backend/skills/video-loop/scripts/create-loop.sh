#!/bin/bash
#
# create-loop.sh
# Creates a seamless infinite loop from a video using forward-reverse-crossfade technique
#
# Usage: ./create-loop.sh input.mp4 output.mp4 [crossfade_duration]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${RED}Error: ffmpeg is not installed${NC}"
    echo "Install with: brew install ffmpeg"
    exit 1
fi

# Check arguments
if [ $# -lt 2 ]; then
    echo "Usage: $0 input.mp4 output.mp4 [crossfade_duration]"
    echo ""
    echo "Arguments:"
    echo "  input.mp4           Source video file"
    echo "  output.mp4          Output seamless loop file"
    echo "  crossfade_duration  Optional, default 0.5 (seconds)"
    exit 1
fi

INPUT="$1"
OUTPUT="$2"
CROSSFADE="${3:-0.5}"

# Validate input file exists
if [ ! -f "$INPUT" ]; then
    echo -e "${RED}Error: Input file not found: $INPUT${NC}"
    exit 1
fi

# Get input video duration
DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$INPUT")
DURATION_INT=${DURATION%.*}

echo ""
echo -e "${GREEN}Video Loop Creator${NC}"
echo "=================================="
echo "Input:      $INPUT"
echo "Output:     $OUTPUT"
echo "Duration:   ${DURATION}s"
echo "Crossfade:  ${CROSSFADE}s"
echo ""

# Create temp directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

echo -e "${YELLOW}Step 1/3:${NC} Reversing video..."
ffmpeg -y -i "$INPUT" -vf reverse -an "$TEMP_DIR/reversed.mp4" -loglevel warning

# Calculate crossfade offset (duration - crossfade)
OFFSET=$(echo "$DURATION - $CROSSFADE" | bc)

echo -e "${YELLOW}Step 2/3:${NC} Creating forward-reverse with crossfade..."
ffmpeg -y -i "$INPUT" -i "$TEMP_DIR/reversed.mp4" \
    -filter_complex "[0:v][1:v]xfade=transition=fade:duration=$CROSSFADE:offset=$OFFSET[v]" \
    -map "[v]" \
    -an \
    "$TEMP_DIR/forward-reverse.mp4" \
    -loglevel warning

# Get the forward-reverse duration for second crossfade
FR_DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$TEMP_DIR/forward-reverse.mp4")
OFFSET2=$(echo "$FR_DURATION - $CROSSFADE" | bc)

echo -e "${YELLOW}Step 3/3:${NC} Finalizing seamless loop..."

# For a true seamless loop, we need to crossfade the end back to the beginning
# Extract first few frames to crossfade with the end
ffmpeg -y -i "$TEMP_DIR/forward-reverse.mp4" \
    -t "$CROSSFADE" \
    "$TEMP_DIR/start-segment.mp4" \
    -loglevel warning

# Create the final loop by crossfading end into start segment
ffmpeg -y -i "$TEMP_DIR/forward-reverse.mp4" -i "$TEMP_DIR/start-segment.mp4" \
    -filter_complex "[0:v][1:v]xfade=transition=fade:duration=$CROSSFADE:offset=$OFFSET2[v]" \
    -map "[v]" \
    -an \
    -c:v libx264 \
    -preset medium \
    -crf 18 \
    -pix_fmt yuv420p \
    "$OUTPUT" \
    -loglevel warning

# Get output duration
OUTPUT_DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUTPUT")
OUTPUT_SIZE=$(ls -lh "$OUTPUT" | awk '{print $5}')

echo ""
echo "=================================="
echo -e "${GREEN}Seamless loop created!${NC}"
echo "Output:     $OUTPUT"
echo "Duration:   ${OUTPUT_DURATION}s"
echo "Size:       $OUTPUT_SIZE"
echo ""
