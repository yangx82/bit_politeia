#!/usr/bin/env python3
"""
PDF Reader with Intelligent Chunked Reading
===========================================
Enhanced PDF reader that prevents API timeout on large documents.

Features:
- Auto-detect document size and switch to chunked mode
- Configurable chunk sizes for large PDFs
- Output to file or stdout
- PDF metadata extraction
"""

import argparse
import io
import shlex
import sys
from pathlib import Path

from pypdf import PdfReader

# Force UTF-8 output for Windows compatibility
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Constants
MAX_CHARS_PER_CHUNK = 30000  # Safe limit per chunk for LLM
DEFAULT_CHUNK_SIZE = 10  # Default pages per chunk
AUTO_CHUNK_THRESHOLD = 30  # Auto-switch to chunked if pages > this


def get_pdf_info(file_path):
    """Extract PDF metadata and recommend reading mode."""
    try:
        if file_path.startswith('"') and file_path.endswith('"'):
            file_path = file_path[1:-1]

        reader = PdfReader(file_path)
        total_pages = len(reader.pages)

        # Extract metadata
        meta = reader.metadata
        info = {
            "file": file_path,
            "total_pages": total_pages,
            "title": meta.title if meta else None,
            "author": meta.author if meta else None,
            "creator": meta.creator if meta else None,
            "producer": meta.producer if meta else None,
            "created": str(meta.creation_date) if meta and meta.creation_date else None,
        }

        # Recommend mode
        recommended_mode = "chunked" if total_pages > AUTO_CHUNK_THRESHOLD else "full"
        info["recommended_mode"] = recommended_mode

        print("=== PDF Metadata ===")
        for key, val in info.items():
            if val:
                print(f"{key}: {val}")

        if recommended_mode == "chunked":
            print(f"\n⚠️ Large document ({total_pages} pages). Recommended: --mode chunked")

        return info

    except Exception as e:
        print(f"Error reading PDF info: {e}", file=sys.stderr)
        sys.exit(1)


def read_page_range(reader, start_idx, end_idx, show_page_nums=True):
    """Extract text from a specific page range."""
    text = ""
    pages_to_read = reader.pages[start_idx:end_idx]

    for i, page in enumerate(pages_to_read):
        page_num = start_idx + i + 1
        content = page.extract_text()
        if content:
            if show_page_nums:
                text += f"--- Page {page_num} ---\n"
            text += content + "\n"

    return text


def read_pdf_chunked(file_path, chunk_size=DEFAULT_CHUNK_SIZE, output_file=None):
    """
    Read PDF in chunks, processing each chunk separately.
    Outputs chunk summaries and optionally saves to file.
    """
    try:
        if file_path.startswith('"') and file_path.endswith('"'):
            file_path = file_path[1:-1]

        reader = PdfReader(file_path)
        total_pages = len(reader.pages)

        print("\n=== Chunked Reading Mode ===")
        print(f"Total pages: {total_pages}")
        print(f"Chunk size: {chunk_size} pages")
        print(f"Estimated chunks: {(total_pages // chunk_size) + 1}")
        print("=" * 40)

        all_chunks = []

        # Process each chunk
        for chunk_start in range(0, total_pages, chunk_size):
            chunk_end = min(chunk_start + chunk_size, total_pages)
            chunk_num = (chunk_start // chunk_size) + 1

            print(f"\n--- Chunk {chunk_num}: Pages {chunk_start + 1}-{chunk_end} ---")

            chunk_text = read_page_range(reader, chunk_start, chunk_end)

            # Truncate chunk if too large
            if len(chunk_text) > MAX_CHARS_PER_CHUNK:
                chunk_text = chunk_text[:MAX_CHARS_PER_CHUNK]
                print(f"[Chunk truncated to {MAX_CHARS_PER_CHUNK} chars]", file=sys.stderr)

            # Store chunk info
            chunk_info = {
                "chunk_num": chunk_num,
                "pages": f"{chunk_start + 1}-{chunk_end}",
                "char_count": len(chunk_text),
            }
            all_chunks.append(chunk_info)

            # Print chunk content
            print(chunk_text)

        # Summary
        print("\n=== Reading Summary ===")
        print(f"Total chunks processed: {len(all_chunks)}")
        for chunk in all_chunks:
            print(f"  Chunk {chunk['chunk_num']}: {chunk['pages']} ({chunk['char_count']} chars)")

        # Save to output file if specified
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write("# PDF Chunked Reading Summary\n")
                f.write(f"Source: {file_path}\n")
                f.write(f"Total pages: {total_pages}\n")
                f.write(f"Chunks: {len(all_chunks)}\n\n")
                for chunk in all_chunks:
                    f.write(f"## Chunk {chunk['chunk_num']} (Pages {chunk['pages']})\n")
                    f.write(f"Characters: {chunk['char_count']}\n\n")

            print(f"\n✅ Summary saved to: {output_file}")

        return all_chunks

    except Exception as e:
        print(f"Error in chunked reading: {e}", file=sys.stderr)
        sys.exit(1)


def read_pdf(
    file_path,
    start_page=None,
    end_page=None,
    mode="auto",
    chunk_size=DEFAULT_CHUNK_SIZE,
    output_file=None,
    info_only=False,
):
    """
    Main reading function with intelligent mode selection.

    Args:
        file_path: Path to PDF file
        start_page: Start page (1-based)
        end_page: End page (1-based)
        mode: Reading mode ('full', 'chunked', 'auto')
        chunk_size: Pages per chunk for chunked mode
        output_file: Output file path (optional)
        info_only: Only show metadata
    """
    try:
        # Strip quotes if present
        if file_path.startswith('"') and file_path.endswith('"'):
            file_path = file_path[1:-1]

        # Info mode: just show metadata
        if info_only:
            return get_pdf_info(file_path)

        reader = PdfReader(file_path)
        total_pages = len(reader.pages)

        # Auto mode: decide based on size
        if mode == "auto":
            if total_pages > AUTO_CHUNK_THRESHOLD:
                mode = "chunked"
                print(
                    f"⚠️ Auto-switching to chunked mode ({total_pages} pages > {AUTO_CHUNK_THRESHOLD} threshold)"
                )
            else:
                mode = "full"

        # Chunked mode
        if mode == "chunked":
            return read_pdf_chunked(file_path, chunk_size, output_file)

        # Full mode (or page range)
        start_idx = (start_page - 1) if start_page else 0
        end_idx = end_page if end_page else total_pages

        # Bounds checking
        if start_idx < 0:
            start_idx = 0
        if end_idx > total_pages:
            end_idx = total_pages

        text = read_page_range(reader, start_idx, end_idx)

        if not text:
            print(
                f"Warning: No pages found in range {start_page}-{end_page} (Total: {total_pages})",
                file=sys.stderr,
            )
            return

        # Truncate to avoid LLM context overflow
        max_chars = 50000
        if len(text) > max_chars:
            text = text[:max_chars]
            print(
                f"\n⚠️ Content truncated to {max_chars} chars. Original: {len(text)} chars.",
                file=sys.stderr,
            )
            print("💡 Tip: Use --mode chunked for full document.", file=sys.stderr)

        # Output to file or stdout
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"✅ Content saved to: {output_file}")
        else:
            print(text)

    except Exception as e:
        print(f"Error reading PDF: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract text from PDF with intelligent chunked reading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s file.pdf                     # Auto mode (chunked if >30 pages)
  %(prog)s file.pdf --mode chunked      # Force chunked mode
  %(prog)s file.pdf --start 1 --end 10  # Read specific pages
  %(prog)s file.pdf --info              # Show metadata only
  %(prog)s file.pdf --mode chunked --output temp/summary.md
        """,
    )

    parser.add_argument("file_path", help="Path to the PDF file")
    parser.add_argument("--start", type=int, help="Start page (1-based, inclusive)")
    parser.add_argument("--end", type=int, help="End page (1-based, inclusive)")
    parser.add_argument(
        "--mode",
        choices=["full", "chunked", "auto"],
        default="auto",
        help="Reading mode: full (single read), chunked (split), auto (detect)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"Pages per chunk (default: {DEFAULT_CHUNK_SIZE})",
    )
    parser.add_argument("--output", type=str, help="Output file path (optional)")
    parser.add_argument("--info", action="store_true", help="Show PDF metadata only")

    # Custom parsing for SkillManager (single string argument)
    args_to_parse = sys.argv[1:]

    if len(sys.argv) == 2 and (" " in sys.argv[1]):
        try:
            args_to_parse = shlex.split(sys.argv[1], posix=False)
        except Exception:
            pass

    try:
        args = parser.parse_args(args_to_parse)
        read_pdf(
            args.file_path, args.start, args.end, args.mode, args.chunk_size, args.output, args.info
        )
    except SystemExit:
        sys.exit(1)
