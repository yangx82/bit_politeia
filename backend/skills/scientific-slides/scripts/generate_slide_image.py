#!/usr/bin/env python3
"""
Slide image generation using Nano Banana 2 (or Nano Banana Pro).

Generate presentation slides or visuals by describing them in natural language.
The AI handles everything automatically with smart iterative refinement.

Two modes:
- Default (full slide): Generate complete slides with title, content, visuals (for PDF workflow)
- Visual only: Generate just images/figures to place on slides (for PPT workflow)

Supports attaching reference images for context (the AI will see these).

Usage:
    # Generate full slide for PDF workflow
    python generate_slide_image.py "Title: Introduction\\nKey points: AI, ML, Deep Learning" -o slide_01.png

    # Generate visual only for PPT workflow
    python generate_slide_image.py "Neural network diagram" -o figure.png --visual-only

    # With reference images attached
    python generate_slide_image.py "Create a slide about this data" -o slide.png --attach chart.png
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _load_env_file():
    """Load .env file from current directory, parent directories, or package directory.

    Returns True if a .env file was found and loaded, False otherwise.
    Note: This does NOT override existing environment variables.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False  # python-dotenv not installed

    # Try current working directory first
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
        return True

    # Try parent directories (up to 5 levels)
    cwd = Path.cwd()
    for _ in range(5):
        env_path = cwd / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
            return True
        cwd = cwd.parent
        if cwd == cwd.parent:  # Reached root
            break

    # Try the package's parent directory
    script_dir = Path(__file__).resolve().parent
    for _ in range(5):
        env_path = script_dir / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
            return True
        script_dir = script_dir.parent
        if script_dir == script_dir.parent:
            break

    return False


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description="Generate presentation slides or visuals using Google Gemini AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
How it works:
  Describe your slide or visual in natural language.
  The AI generates it automatically with:
  - Smart iteration (only regenerates if quality is below threshold)
  - Quality review by Gemini 3.1 Pro
  - Publication-ready output

Models:
  Nano Banana 2 (default):   Gemini 3.1 Flash Image (fast, resource-efficient)
  Nano Banana Pro:           Gemini 3 Pro Image (highest quality)

Modes:
  Default (full slide):  Generate complete slide with title, content, visuals
                         Use for PDF workflow where each slide is an image
  
  Visual only:           Generate just the image/figure
                         Use for PPT workflow where you add text separately

Attachments:
  Use --attach to provide reference images that the AI will see.
  This allows you to say "create a slide about this chart" and attach the chart.

Examples:
  # Full slide (default) - for PDF workflow
  python generate_slide_image.py "Title: Machine Learning\\nPoints: supervised, unsupervised, reinforcement" -o slide_01.png
  
  # Visual only - for PPT workflow  
  python generate_slide_image.py "Flowchart showing data pipeline" -o figure.png --visual-only
  
  # With reference images attached
  python generate_slide_image.py "Create a slide explaining this chart" -o slide.png --attach chart.png
  python generate_slide_image.py "Combine these into a comparison" -o compare.png --attach before.png --attach after.png
  
  # Using a specific model
  python generate_slide_image.py "Complex architecture" -o arch.png --model nano-banana-pro

Environment Variables:
  GEMINI_API_KEY    Required for AI generation (Google AI Studio)
        """,
    )

    parser.add_argument("prompt", help="Description of the slide or visual to generate")
    parser.add_argument("-o", "--output", required=True, help="Output file path")
    parser.add_argument(
        "--attach",
        action="append",
        dest="attachments",
        metavar="IMAGE",
        help="Attach image file(s) as context (can use multiple times)",
    )
    parser.add_argument(
        "--visual-only",
        action="store_true",
        help="Generate just the visual/figure (for PPT workflow)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=2,
        help="Maximum refinement iterations (default: 2, max: 2)",
    )
    parser.add_argument(
        "--model",
        choices=["nano-banana-pro", "nano-banana-2"],
        default="nano-banana-2",
        help="Image generation model (default: nano-banana-2)",
    )
    parser.add_argument("--api-key", help="Google Gemini API key (or use GEMINI_API_KEY env var)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Load .env file
    _load_env_file()

    # Check for API key
    api_key = args.api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set")
        print("\nFor AI generation, you need a Google Gemini API key.")
        print("Get one at: https://aistudio.google.com/app/apikey")
        print("\nSet it with:")
        print("  export GEMINI_API_KEY='your_api_key'")
        print("\nOr use --api-key flag")
        sys.exit(1)

    # Find AI generation script
    script_dir = Path(__file__).parent
    ai_script = script_dir / "generate_slide_image_ai.py"

    if not ai_script.exists():
        print(f"Error: AI generation script not found: {ai_script}")
        sys.exit(1)

    # Build command
    cmd = [sys.executable, str(ai_script), args.prompt, "-o", args.output]

    # Add attachments
    if args.attachments:
        for att in args.attachments:
            cmd.extend(["--attach", att])

    if args.visual_only:
        cmd.append("--visual-only")

    # Enforce max 2 iterations
    iterations = min(args.iterations, 2)
    if iterations != 2:
        cmd.extend(["--iterations", str(iterations)])

    if api_key:
        cmd.extend(["--api-key", api_key])

    if args.verbose:
        cmd.append("-v")

    if args.model:
        cmd.extend(["--model", args.model])

    # Execute
    try:
        result = subprocess.run(cmd, check=False)
        sys.exit(result.returncode)
    except Exception as e:
        print(f"Error executing AI generation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
