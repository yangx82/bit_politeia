import sys
import json
import argparse
import io
import shlex
from pypdf import PdfReader

# Force UTF-8 output for Windows compatibility
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def read_pdf(file_path, start_page=None, end_page=None):
    try:
        # Strip quotes if present
        if file_path.startswith('"') and file_path.endswith('"'):
            file_path = file_path[1:-1]
            
        reader = PdfReader(file_path)
        text = ""
        
        # Convert 1-based to 0-based
        total_pages = len(reader.pages)
        start_idx = (start_page - 1) if start_page else 0
        end_idx = end_page if end_page else total_pages
        
        # Bounds checking
        if start_idx < 0: start_idx = 0
        if end_idx > total_pages: end_idx = total_pages
        
        pages_to_read = reader.pages[start_idx:end_idx]
        
        if not pages_to_read:
            print(f"Warning: No pages found in range {start_page}-{end_page} (Total: {total_pages})", file=sys.stderr)
            return

        for i, page in enumerate(pages_to_read):
            page_num = start_idx + i + 1
            content = page.extract_text()
            if content:
                text += f"--- Page {page_num} ---\n{content}\n"
        
        # Truncate to avoid LLM context overflow (approx 128k input limit)
        max_chars = 50000 
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[WARNING: Content truncated. Original length: {len(text)} chars. Showing first {max_chars} chars.]"
            
        print(text)
    except Exception as e:
        print(f"Error reading PDF: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract text from PDF")
    parser.add_argument("file_path", help="Path to the PDF file")
    parser.add_argument("--start", type=int, help="Start page (1-based, inclusive)")
    parser.add_argument("--end", type=int, help="End page (1-based, inclusive)")
    
    # Custom parsing logic for SkillManager which passes args as a single string
    # E.g., sys.argv = ['script.py', 'file.pdf --start 1']
    args_to_parse = sys.argv[1:]
    
    if len(sys.argv) == 2 and (" " in sys.argv[1]):
        # Attempt to split the single argument string
        try:
            # posix=False for Windows path compatibility
            args_to_parse = shlex.split(sys.argv[1], posix=False)
        except Exception:
            # Fallback to default if split fails
            pass
            
    try:
        args = parser.parse_args(args_to_parse)
        read_pdf(args.file_path, args.start, args.end)
    except SystemExit:
        # argparse calls sys.exit() on error, which we catch to print customized error if needed
        # But for agent tool, standard stderr output is fine.
        sys.exit(1)
