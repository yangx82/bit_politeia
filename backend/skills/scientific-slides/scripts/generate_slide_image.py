#!/usr/bin/env python3
"""
Slide image generation using Nano Banana Pro.

Generate presentation slides or visuals by describing them in natural language.
Nano Banana Pro handles everything automatically with smart iterative refinement.

Two modes:
- Default (full slide): Generate complete slides with title, content, visuals (for PDF workflow)
- Visual only: Generate just images/figures to place on slides (for PPT workflow)

Supports attaching reference images for context (Nano Banana Pro will see these).

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
    """Load .env file from skill directory, current directory, parent directories, or package directory.
    
    Priority: skill directory > current working directory > parent directories > package directory
    """
    def parse_env_content(content):
        """Simple manual parser for .env files."""
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = value

    try:
        from dotenv import load_dotenv
        has_dotenv = True
    except ImportError:
        has_dotenv = False

    # Priority 1: Skill directory (highest priority)
    skill_dir = Path(__file__).resolve().parent.parent  # scripts/ -> scientific-slides/
    env_path = skill_dir / ".env"
    if env_path.exists():
        if has_dotenv:
            load_dotenv(dotenv_path=env_path, override=False)
        else:
            try:
                with open(env_path, "r", encoding="utf-8", errors="replace") as f:
                    parse_env_content(f.read())
            except Exception:
                pass
        return True

    # Priority 2: Current working directory
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        if has_dotenv:
            load_dotenv(dotenv_path=env_path, override=False)
        else:
            try:
                with open(env_path, "r", encoding="utf-8", errors="replace") as f:
                    parse_env_content(f.read())
            except Exception:
                pass
        return True

    # Priority 3: Parent directories (up to 5 levels)
    cwd = Path.cwd()
    for _ in range(5):
        cwd = cwd.parent
        env_path = cwd / ".env"
        if env_path.exists():
            if has_dotenv:
                load_dotenv(dotenv_path=env_path, override=False)
            else:
                try:
                    with open(env_path, "r", encoding="utf-8", errors="replace") as f:
                        parse_env_content(f.read())
                except Exception:
                    pass
            return True
        if cwd == cwd.parent:
            break

    # Priority 4: Package parent directory
    script_dir = Path(__file__).resolve().parent
    for _ in range(5):
        env_path = script_dir / ".env"
        if env_path.exists():
            if has_dotenv:
                load_dotenv(dotenv_path=env_path, override=False)
            else:
                try:
                    with open(env_path, "r", encoding="utf-8", errors="replace") as f:
                        parse_env_content(f.read())
                except Exception:
                    pass
            return True
        script_dir = script_dir.parent
        if script_dir == script_dir.parent:
            break

    return False


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description="Generate presentation slides or visuals using Nano Banana Pro AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
How it works:
  Describe your slide or visual in natural language.
  Nano Banana Pro generates it automatically with:
  - Smart iteration (only regenerates if quality is below threshold)
  - Quality review by Gemini 3 Pro
  - Publication-ready output

Modes:
  Default (full slide):  Generate complete slide with title, content, visuals
                         Use for PDF workflow where each slide is an image
  
  Visual only:           Generate just the image/figure
                         Use for PPT workflow where you add text separately

Attachments:
  Use --attach to provide reference images that Nano Banana Pro will see.
  This allows you to say "create a slide about this chart" and attach the chart.

Examples:
  # Full slide (default) - for PDF workflow
  python generate_slide_image.py "Title: Machine Learning\\nPoints: supervised, unsupervised, reinforcement" -o slide_01.png
  
  # Visual only - for PPT workflow  
  python generate_slide_image.py "Flowchart showing data pipeline" -o figure.png --visual-only
  
  # With reference images attached
  python generate_slide_image.py "Create a slide explaining this chart" -o slide.png --attach chart.png
  python generate_slide_image.py "Combine these into a comparison" -o compare.png --attach before.png --attach after.png
  
  # Multiple slides for PDF
  python generate_slide_image.py "Title slide: AI Conference 2025" -o slides/01_title.png
  python generate_slide_image.py "Title: Introduction\\nOverview of deep learning" -o slides/02_intro.png

Environment Variables:
  OPENROUTER_API_KEY    Required for OpenRouter mode
  GOOGLE_CLOUD_PROJECT  Required for Vertex AI (Gemini Enterprise Agent Platform)
  GOOGLE_CLOUD_LOCATION Location for Vertex AI (default: global)
  GOOGLE_GENAI_USE_ENTERPRISE  Set to 'true' for Vertex AI mode
        """
    )
    
    parser.add_argument("prompt", help="Description of the slide or visual to generate")
    parser.add_argument("-o", "--output", required=True, help="Output file path")
    parser.add_argument("--attach", action="append", dest="attachments", metavar="IMAGE",
                       help="Attach image file(s) as context (can use multiple times)")
    parser.add_argument("--visual-only", action="store_true",
                       help="Generate just the visual/figure (for PPT workflow)")
    parser.add_argument("--iterations", type=int, default=2,
                       help="Maximum refinement iterations (default: 2, max: 2)")
    parser.add_argument("--api-key", help="OpenRouter API key (or use OPENROUTER_API_KEY env var)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Load .env file first (priority: skill directory)
    _load_env_file()
    
    # Check if using Vertex AI (Gemini Enterprise Agent Platform)
    use_vertex = os.getenv("GOOGLE_GENAI_USE_ENTERPRISE", "").lower() in ("true", "1", "yes")
    
    # Check for API key (only needed for OpenRouter, not Vertex AI)
    api_key = args.api_key or os.getenv("OPENROUTER_API_KEY")
    if not api_key and not use_vertex:
        print("Error: OPENROUTER_API_KEY environment variable not set")
        print("\nFor OpenRouter mode, you need an OpenRouter API key.")
        print("Get one at: https://openrouter.ai/keys")
        print("\nSet it with:")
        print("  export OPENROUTER_API_KEY='your_api_key'")
        print("\nOr use --api-key flag")
        print("\nOr use Vertex AI (Gemini Enterprise Agent Platform) by setting:")
        print("  export GOOGLE_CLOUD_PROJECT=your-project-id")
        print("  export GOOGLE_CLOUD_LOCATION=global")
        print("  export GOOGLE_GENAI_USE_ENTERPRISE=true")
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
    
    # Execute
    try:
        result = subprocess.run(cmd, check=False)
        sys.exit(result.returncode)
    except Exception as e:
        print(f"Error executing AI generation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
