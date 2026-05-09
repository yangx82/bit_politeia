#!/usr/bin/env python3
"""
AI-powered scientific schematic generation using Google Gemini models.

This script uses a smart iterative refinement approach:
1. Generate initial image with Nano Banana Pro or Nano Banana 2 via Google API
2. AI quality review using Gemini for scientific critique
3. Only regenerate if quality is below threshold for document type
4. Repeat until quality meets standards (max iterations)

Requirements:
    - GEMINI_API_KEY environment variable (Google AI Studio API key)
    - requests library

Usage:
    python generate_schematic_ai.py "Create a flowchart showing CONSORT participant flow" -o flowchart.png
    python generate_schematic_ai.py "Neural network architecture diagram" -o architecture.png --iterations 2
    python generate_schematic_ai.py "Simple block diagram" -o diagram.png --doc-type poster
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("Error: requests library not found. Install with: pip install requests")
    sys.exit(1)


# Try to load .env file from multiple potential locations
def _load_env_file():
    """Load .env file from current directory, parent directories, or package directory.
    Supports manual parsing if python-dotenv is not installed.
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

    # Potential locations to check
    search_dirs = [Path.cwd()]
    
    # Add parent directories of CWD
    cwd = Path.cwd()
    for _ in range(5):
        cwd = cwd.parent
        search_dirs.append(cwd)
        if cwd == cwd.parent: break

    # Add parent directories of the script itself
    script_dir = Path(__file__).resolve().parent
    for _ in range(5):
        search_dirs.append(script_dir)
        script_dir = script_dir.parent
        if script_dir == script_dir.parent: break

    # Remove duplicates while preserving order
    unique_dirs = []
    seen = set()
    for d in search_dirs:
        if d not in seen:
            unique_dirs.append(d)
            seen.add(d)

    for d in unique_dirs:
        env_path = d / ".env"
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
    return False


class ScientificSchematicGenerator:
    """Generate scientific schematics using AI with smart iterative refinement.

    Uses Google Gemini API for both image generation (Nano Banana Pro/2) and quality review.
    Multiple passes only occur if the generated schematic doesn't meet the
    quality threshold for the target document type.
    """

    # Quality thresholds by document type (score out of 10)
    # Higher thresholds for more formal publications
    QUALITY_THRESHOLDS = {
        "journal": 8.5,  # Nature, Science, etc. - highest standards
        "conference": 8.0,  # Conference papers - high standards
        "poster": 7.0,  # Academic posters - good quality
        "presentation": 6.5,  # Slides/talks - clear but less formal
        "report": 7.5,  # Technical reports - professional
        "grant": 8.0,  # Grant proposals - must be compelling
        "thesis": 8.0,  # Dissertations - formal academic
        "preprint": 7.5,  # arXiv, etc. - good quality
        "default": 7.5,  # Default threshold
    }
    
    # Available image generation models via Google Gemini API
    IMAGE_GENERATION_MODELS = {
        "nano-banana-pro": "gemini-3-pro-image-preview",  # Nano Banana Pro (Gemini 3 Pro)
        "nano-banana-2": "gemini-3.1-flash-image-preview",  # Nano Banana 2 (Gemini 3.1 Flash)
    }
    
    # Review model for quality evaluation
    REVIEW_MODEL = "gemini-3.1-pro-preview"  # Gemini 3.1 Pro for quality review

    # Scientific diagram best practices prompt template
    SCIENTIFIC_DIAGRAM_GUIDELINES = """
Create a high-quality scientific diagram with these requirements:

VISUAL QUALITY:
- Clean white or light background (no textures or gradients)
- High contrast for readability and printing
- Professional, publication-ready appearance
- Sharp, clear lines and text
- Adequate spacing between elements to prevent crowding

TYPOGRAPHY:
- Clear, readable sans-serif fonts (Arial, Helvetica style)
- Minimum 10pt font size for all labels
- Consistent font sizes throughout
- All text horizontal or clearly readable
- No overlapping text

SCIENTIFIC STANDARDS:
- Accurate representation of concepts
- Clear labels for all components
- Include scale bars, legends, or axes where appropriate
- Use standard scientific notation and symbols
- Include units where applicable

ACCESSIBILITY:
- Colorblind-friendly color palette (use Okabe-Ito colors if using color)
- High contrast between elements
- Redundant encoding (shapes + colors, not just colors)
- Works well in grayscale

LAYOUT:
- Logical flow (left-to-right or top-to-bottom)
- Clear visual hierarchy
- Balanced composition
- Appropriate use of whitespace
- No clutter or unnecessary decorative elements

IMPORTANT - NO FIGURE NUMBERS:
- Do NOT include "Figure 1:", "Fig. 1", or any figure numbering in the image
- Do NOT add captions or titles like "Figure: ..." at the top or bottom
- Figure numbers and captions are added separately in the document/LaTeX
- The diagram should contain only the visual content itself
"""

    def __init__(self, api_key: str | None = None, verbose: bool = False, image_model: str = "nano-banana-2"):
        """
        Initialize the generator.

        Args:
            api_key: Google Gemini API key (or use GEMINI_API_KEY env var)
            verbose: Print detailed progress information
            image_model: Image generation model to use ("nano-banana-pro" or "nano-banana-2")
        """
        # Priority: 1) explicit api_key param, 2) environment variable, 3) .env file
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

        # If not found in environment, try loading from .env file
        if not self.api_key:
            _load_env_file()
            self.api_key = os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY not found. Please either:\n"
                "  1. Set the GEMINI_API_KEY environment variable\n"
                "  2. Add GEMINI_API_KEY to your .env file\n"
                "  3. Pass api_key parameter to the constructor\n"
                "Get your API key from: https://aistudio.google.com/app/apikey"
            )

        self.verbose = verbose
        self._last_error = None  # Track last error for better reporting
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        
        # Select image generation model
        if image_model in self.IMAGE_GENERATION_MODELS:
            self.image_model = self.IMAGE_GENERATION_MODELS[image_model]
        else:
            self.image_model = self.IMAGE_GENERATION_MODELS["nano-banana-2"]
        
        # Gemini 2.0 Flash for quality review
        self.review_model = self.REVIEW_MODEL

    def _log(self, message: str):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] {message}")

    def _make_request(
        self, model: str, contents: list[dict[str, Any]], generation_config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Make a request to Google Gemini API.

        Args:
            model: Model identifier (e.g., "gemini-2.0-flash-exp-image-generation")
            contents: List of content dictionaries (Gemini format)
            generation_config: Optional generation configuration

        Returns:
            API response as dictionary
        """
        headers = {
            "Content-Type": "application/json",
        }

        payload = {
            "contents": contents,
        }
        
        if generation_config:
            payload["generationConfig"] = generation_config

        self._log(f"Making request to {model}...")

        try:
            # Google Gemini API format: POST /models/{model}:generateContent?key={api_key}
            url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
            
            response = requests.post(
                url, headers=headers, json=payload, timeout=120
            )

            # Try to get response body even on error
            try:
                response_json = response.json()
            except json.JSONDecodeError:
                response_json = {"raw_text": response.text[:500]}

            # Check for HTTP errors but include response body in error message
            if response.status_code != 200:
                error_detail = response_json.get("error", response_json)
                self._log(f"HTTP {response.status_code}: {error_detail}")
                raise RuntimeError(
                    f"API request failed (HTTP {response.status_code}): {error_detail}"
                )

            return response_json
        except requests.exceptions.Timeout:
            raise RuntimeError("API request timed out after 120 seconds")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API request failed: {e!s}")

    def _extract_image_from_response(self, response: dict[str, Any]) -> bytes | None:
        """
        Extract base64-encoded image from Google Gemini API response.

        For Gemini image generation models, images are returned in the 'parts' field
        with 'inlineData' containing mimeType and data.

        Args:
            response: API response dictionary

        Returns:
            Image bytes or None if not found
        """
        try:
            # Gemini API response format: {"candidates": [{"content": {"parts": [...]}}]}
            candidates = response.get("candidates", [])
            if not candidates:
                self._log("No candidates in response")
                return None

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            
            if not parts:
                self._log("No parts in response content")
                return None

            # Look for image data in parts
            for part in parts:
                # Gemini returns images as inlineData
                if "inlineData" in part:
                    inline_data = part["inlineData"]
                    mime_type = inline_data.get("mimeType", "image/png")
                    base64_str = inline_data.get("data", "")
                    
                    if base64_str:
                        self._log(f"Found image in inlineData (mimeType: {mime_type}, length: {len(base64_str)})")
                        return base64.b64decode(base64_str)
                
                # Also check for text response (for debugging)
                if "text" in part and self.verbose:
                    self._log(f"Text response: {part['text'][:200]}...")

            self._log("No image data found in response")
            return None

        except Exception as e:
            self._log(f"Error extracting image: {e!s}")
            import traceback

            if self.verbose:
                traceback.print_exc()
            return None

    def _image_to_base64(self, image_path: str) -> str:
        """
        Convert image file to base64 data URL.

        Args:
            image_path: Path to image file

        Returns:
            Base64 data URL string
        """
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Determine image type from extension
        ext = Path(image_path).suffix.lower()
        mime_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(ext, "image/png")

        base64_data = base64.b64encode(image_data).decode("utf-8")
        return f"data:{mime_type};base64,{base64_data}"

    def generate_image(self, prompt: str) -> bytes | None:
        """
        Generate an image using Google Gemini image generation model.

        Args:
            prompt: Description of the diagram to generate

        Returns:
            Image bytes or None if generation failed
        """
        self._last_error = None  # Reset error

        # Gemini API content format
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        
        # Generation config for image generation
        generation_config = {
            "responseModalities": ["image", "text"],  # Request image output
        }

        try:
            response = self._make_request(
                model=self.image_model, 
                contents=contents, 
                generation_config=generation_config
            )

            # Debug: print response structure if verbose
            if self.verbose:
                self._log(f"Response keys: {response.keys()}")
                if "error" in response:
                    self._log(f"API Error: {response['error']}")
                if response.get("candidates"):
                    candidate = response["candidates"][0]
                    self._log(f"Candidate keys: {candidate.keys()}")
                    content = candidate.get("content", {})
                    self._log(f"Content keys: {content.keys()}")
                    parts = content.get("parts", [])
                    self._log(f"Parts count: {len(parts)}")
                    for i, part in enumerate(parts[:3]):
                        if isinstance(part, dict):
                            self._log(f"  Part {i}: keys={list(part.keys())}")

            # Check for API errors in response
            if "error" in response:
                error_msg = response["error"]
                if isinstance(error_msg, dict):
                    error_msg = error_msg.get("message", str(error_msg))
                self._last_error = f"API Error: {error_msg}"
                print(f"✗ {self._last_error}")
                return None

            image_data = self._extract_image_from_response(response)
            if image_data:
                self._log(f"✓ Generated image ({len(image_data)} bytes)")
            else:
                self._last_error = (
                    "No image data in API response - model may not support image generation"
                )
                self._log(f"✗ {self._last_error}")

            return image_data
        except RuntimeError as e:
            self._last_error = str(e)
            self._log(f"✗ Generation failed: {self._last_error}")
            return None
        except Exception as e:
            self._last_error = f"Unexpected error: {e!s}"
            self._log(f"✗ Generation failed: {self._last_error}")
            import traceback

            if self.verbose:
                traceback.print_exc()
            return None

    def review_image(
        self,
        image_path: str,
        original_prompt: str,
        iteration: int,
        doc_type: str = "default",
        max_iterations: int = 2,
    ) -> tuple[str, float, bool]:
        """
        Review generated image using Gemini for quality analysis.

        Uses Gemini's vision capabilities to evaluate the schematic quality
        and determine if regeneration is needed.

        Args:
            image_path: Path to the generated image
            original_prompt: Original user prompt
            iteration: Current iteration number
            doc_type: Document type (journal, poster, presentation, etc.)
            max_iterations: Maximum iterations allowed

        Returns:
            Tuple of (critique text, quality score 0-10, needs_improvement bool)
        """
        # Convert image to base64
        image_data_url = self._image_to_base64(image_path)
        
        # Extract base64 data from data URL
        if "," in image_data_url:
            base64_data = image_data_url.split(",", 1)[1]
        else:
            base64_data = image_data_url
        
        # Determine mime type
        ext = Path(image_path).suffix.lower()
        mime_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(ext, "image/png")

        # Get quality threshold for this document type
        threshold = self.QUALITY_THRESHOLDS.get(
            doc_type.lower(), self.QUALITY_THRESHOLDS["default"]
        )

        review_prompt = f"""You are an expert reviewer evaluating a scientific diagram for publication quality.

ORIGINAL REQUEST: {original_prompt}

DOCUMENT TYPE: {doc_type} (quality threshold: {threshold}/10)
ITERATION: {iteration}/{max_iterations}

Carefully evaluate this diagram on these criteria:

1. **Scientific Accuracy** (0-2 points)
   - Correct representation of concepts
   - Proper notation and symbols
   - Accurate relationships shown

2. **Clarity and Readability** (0-2 points)
   - Easy to understand at a glance
   - Clear visual hierarchy
   - No ambiguous elements

3. **Label Quality** (0-2 points)
   - All important elements labeled
   - Labels are readable (appropriate font size)
   - Consistent labeling style

4. **Layout and Composition** (0-2 points)
   - Logical flow (top-to-bottom or left-to-right)
   - Balanced use of space
   - No overlapping elements

5. **Professional Appearance** (0-2 points)
   - Publication-ready quality
   - Clean, crisp lines and shapes
   - Appropriate colors/contrast

RESPOND IN THIS EXACT FORMAT:
SCORE: [total score 0-10]

STRENGTHS:
- [strength 1]
- [strength 2]

ISSUES:
- [issue 1 if any]
- [issue 2 if any]

VERDICT: [ACCEPTABLE or NEEDS_IMPROVEMENT]

If score >= {threshold}, the diagram is ACCEPTABLE for {doc_type} publication.
If score < {threshold}, mark as NEEDS_IMPROVEMENT with specific suggestions."""

        # Gemini content format with image
        contents = [
            {
                "role": "user",
                "parts": [
                    {"text": review_prompt},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": base64_data
                        }
                    }
                ]
            }
        ]

        try:
            # Use Gemini for review
            response = self._make_request(model=self.review_model, contents=contents)

            # Extract text response from Gemini format
            candidates = response.get("candidates", [])
            if not candidates:
                return "Image generated successfully", 8.0, False

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            
            # Extract text from parts
            text_parts = []
            for part in parts:
                if "text" in part:
                    text_parts.append(part["text"])
            
            critique_text = "\n".join(text_parts) if text_parts else "Image generated successfully"

            # Try to extract score
            score = 7.5  # Default score if extraction fails
            import re

            # Look for SCORE: X or SCORE: X/10 format
            score_match = re.search(r"SCORE:\s*(\d+(?:\.\d+)?)", critique_text, re.IGNORECASE)
            if score_match:
                score = float(score_match.group(1))
            else:
                # Fallback: look for any score pattern
                score_match = re.search(
                    r"(?:score|rating|quality)[:\s]+(\d+(?:\.\d+)?)\s*(?:/\s*10)?",
                    critique_text,
                    re.IGNORECASE,
                )
                if score_match:
                    score = float(score_match.group(1))

            # Determine if improvement is needed based on verdict or score
            needs_improvement = False
            if "NEEDS_IMPROVEMENT" in critique_text.upper() or score < threshold:
                needs_improvement = True

            self._log(f"✓ Review complete (Score: {score}/10, Threshold: {threshold}/10)")
            self._log(f"  Verdict: {'Needs improvement' if needs_improvement else 'Acceptable'}")

            return (
                critique_text if critique_text else "Image generated successfully",
                score,
                needs_improvement,
            )
        except Exception as e:
            self._log(f"Review skipped: {e!s}")
            # Don't fail the whole process if review fails - assume acceptable
            return "Image generated successfully (review skipped)", 7.5, False

    def improve_prompt(self, original_prompt: str, critique: str, iteration: int) -> str:
        """
        Improve the generation prompt based on critique.

        Args:
            original_prompt: Original user prompt
            critique: Review critique from previous iteration
            iteration: Current iteration number

        Returns:
            Improved prompt for next generation
        """
        improved_prompt = f"""{self.SCIENTIFIC_DIAGRAM_GUIDELINES}

USER REQUEST: {original_prompt}

ITERATION {iteration}: Based on previous feedback, address these specific improvements:
{critique}

Generate an improved version that addresses all the critique points while maintaining scientific accuracy and professional quality."""

        return improved_prompt

    def generate_iterative(
        self, user_prompt: str, output_path: str, iterations: int = 2, doc_type: str = "default"
    ) -> dict[str, Any]:
        """
        Generate scientific schematic with smart iterative refinement.

        Only regenerates if the quality score is below the threshold for the
        specified document type. This saves API calls and time when the first
        generation is already good enough.

        Args:
            user_prompt: User's description of desired diagram
            output_path: Path to save final image
            iterations: Maximum refinement iterations (default: 2, max: 2)
            doc_type: Document type for quality threshold (journal, poster, etc.)

        Returns:
            Dictionary with generation results and metadata
        """
        output_path = Path(output_path)
        output_dir = output_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        base_name = output_path.stem
        extension = output_path.suffix or ".png"

        # Get quality threshold for this document type
        threshold = self.QUALITY_THRESHOLDS.get(
            doc_type.lower(), self.QUALITY_THRESHOLDS["default"]
        )

        results = {
            "user_prompt": user_prompt,
            "doc_type": doc_type,
            "quality_threshold": threshold,
            "iterations": [],
            "final_image": None,
            "final_score": 0.0,
            "success": False,
            "early_stop": False,
            "early_stop_reason": None,
        }

        current_prompt = f"""{self.SCIENTIFIC_DIAGRAM_GUIDELINES}

USER REQUEST: {user_prompt}

Generate a publication-quality scientific diagram that meets all the guidelines above."""

        print(f"\n{'=' * 60}")
        print("Generating Scientific Schematic")
        print(f"{'=' * 60}")
        print(f"Description: {user_prompt}")
        print(f"Document Type: {doc_type}")
        print(f"Quality Threshold: {threshold}/10")
        print(f"Max Iterations: {iterations}")
        print(f"Output: {output_path}")
        print(f"{'=' * 60}\n")

        for i in range(1, iterations + 1):
            print(f"\n[Iteration {i}/{iterations}]")
            print("-" * 40)

            # Generate image
            print("Generating image...")
            image_data = self.generate_image(current_prompt)

            if not image_data:
                error_msg = getattr(
                    self, "_last_error", "Image generation failed - no image data returned"
                )
                print(f"✗ Generation failed: {error_msg}")
                results["iterations"].append({"iteration": i, "success": False, "error": error_msg})
                continue

            # Save iteration image
            iter_path = output_dir / f"{base_name}_v{i}{extension}"
            with open(iter_path, "wb") as f:
                f.write(image_data)
            print(f"✓ Saved: {iter_path}")

            # Review image using Gemini 3.1 Pro
            print("Reviewing image with Gemini 3.1 Pro...")
            critique, score, needs_improvement = self.review_image(
                str(iter_path), user_prompt, i, doc_type, iterations
            )
            print(f"✓ Score: {score}/10 (threshold: {threshold}/10)")

            # Save iteration results
            iteration_result = {
                "iteration": i,
                "image_path": str(iter_path),
                "prompt": current_prompt,
                "critique": critique,
                "score": score,
                "needs_improvement": needs_improvement,
                "success": True,
            }
            results["iterations"].append(iteration_result)

            # Check if quality is acceptable - STOP EARLY if so
            if not needs_improvement:
                print(f"\n✓ Quality meets {doc_type} threshold ({score} >= {threshold})")
                print("  No further iterations needed!")
                results["final_image"] = str(iter_path)
                results["final_score"] = score
                results["success"] = True
                results["early_stop"] = True
                results["early_stop_reason"] = (
                    f"Quality score {score} meets threshold {threshold} for {doc_type}"
                )
                break

            # If this is the last iteration, we're done regardless
            if i == iterations:
                print("\n⚠ Maximum iterations reached")
                results["final_image"] = str(iter_path)
                results["final_score"] = score
                results["success"] = True
                break

            # Quality below threshold - improve prompt for next iteration
            print(f"\n⚠ Quality below threshold ({score} < {threshold})")
            print("Improving prompt based on feedback...")
            current_prompt = self.improve_prompt(user_prompt, critique, i + 1)

        # Copy final version to output path
        if results["success"] and results["final_image"]:
            final_iter_path = Path(results["final_image"])
            if final_iter_path != output_path:
                import shutil

                shutil.copy(final_iter_path, output_path)
                print(f"\n✓ Final image: {output_path}")

        # Save review log
        log_path = output_dir / f"{base_name}_review_log.json"
        with open(log_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"✓ Review log: {log_path}")

        print(f"\n{'=' * 60}")
        print("Generation Complete!")
        print(f"Final Score: {results['final_score']}/10")
        if results["early_stop"]:
            print(
                f"Iterations Used: {len([r for r in results['iterations'] if r.get('success')])}/{iterations} (early stop)"
            )
        print(f"{'=' * 60}\n")

        return results


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description="Generate scientific schematics using Google Gemini AI with smart iterative refinement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate a flowchart for a journal paper
  python generate_schematic_ai.py "CONSORT participant flow diagram" -o flowchart.png --doc-type journal
  
  # Generate neural network architecture for presentation (lower threshold)
  python generate_schematic_ai.py "Transformer encoder-decoder architecture" -o transformer.png --doc-type presentation
  
  # Generate with Nano Banana 2 model
  python generate_schematic_ai.py "Biological signaling pathway" -o pathway.png --model nano-banana-2
  
  # Verbose output
  python generate_schematic_ai.py "Circuit diagram" -o circuit.png -v

Document Types (quality thresholds):
  journal      8.5/10  - Nature, Science, peer-reviewed journals
  conference   8.0/10  - Conference papers
  thesis       8.0/10  - Dissertations, theses
  grant        8.0/10  - Grant proposals
  preprint     7.5/10  - arXiv, bioRxiv, etc.
  report       7.5/10  - Technical reports
  poster       7.0/10  - Academic posters
  presentation 6.5/10  - Slides, talks
  default      7.5/10  - General purpose

Image Generation Models:
  nano-banana-pro  - Gemini 2.0 Flash (fast, default)
  nano-banana-2    - Gemini 2.0 Flash Preview (preview version)

Note: Multiple iterations only occur if quality is BELOW the threshold.
      If the first generation meets the threshold, no extra API calls are made.

Environment:
  GEMINI_API_KEY    Google Gemini API key (required)
                   Get from: https://aistudio.google.com/app/apikey
        """,
    )

    parser.add_argument("prompt", help="Description of the diagram to generate")
    parser.add_argument(
        "-o", "--output", required=True, help="Output image path (e.g., diagram.png)"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=2,
        help="Maximum refinement iterations (default: 2, max: 2)",
    )
    parser.add_argument(
        "--doc-type",
        default="default",
        choices=[
            "journal",
            "conference",
            "poster",
            "presentation",
            "report",
            "grant",
            "thesis",
            "preprint",
            "default",
        ],
        help="Document type for quality threshold (default: default)",
    )
    parser.add_argument(
        "--model",
        default="nano-banana-pro",
        choices=["nano-banana-pro", "nano-banana-2"],
        help="Image generation model to use (default: nano-banana-pro)",
    )
    parser.add_argument("--api-key", help="Google Gemini API key (or set GEMINI_API_KEY)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Check for API key
    api_key = args.api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set")
        print("\nSet it with:")
        print("  export GEMINI_API_KEY='your_api_key'")
        print("\nOr provide via --api-key flag")
        print("\nGet your API key from: https://aistudio.google.com/app/apikey")
        sys.exit(1)

    # Validate iterations - enforce max of 2
    if args.iterations < 1 or args.iterations > 2:
        print("Error: Iterations must be between 1 and 2")
        sys.exit(1)

    try:
        generator = ScientificSchematicGenerator(
            api_key=api_key, 
            verbose=args.verbose, 
            image_model=args.model
        )
        results = generator.generate_iterative(
            user_prompt=args.prompt,
            output_path=args.output,
            iterations=args.iterations,
            doc_type=args.doc_type,
        )

        if results["success"]:
            print(f"\n✓ Success! Image saved to: {args.output}")
            if results.get("early_stop"):
                print(
                    f"  (Completed in {len([r for r in results['iterations'] if r.get('success')])} iteration(s) - quality threshold met)"
                )
            sys.exit(0)
        else:
            print("\n✗ Generation failed. Check review log for details.")
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e!s}")
        sys.exit(1)


if __name__ == "__main__":
    main()
