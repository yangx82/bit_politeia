import argparse
import io
import shlex
import sys
from pathlib import Path

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Dependencies
try:
    from openai import OpenAI
    from pypdf import PdfReader
except ImportError:
    print("Error: Missing dependencies. Please install `pypdf` and `openai`.", file=sys.stderr)
    sys.exit(1)


def extract_text(file_path):
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    else:
        # Assume text file
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()


def split_text(text, chunk_size=10000, overlap=500):
    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap

    return chunks


def summarize_chunk(client, text_chunk, model):
    prompt = f"""
    Please summarize the following text. Capture the main points, key arguments, and any significant details.
    
    TEXT:
    {text_chunk}
    
    SUMMARY:
    """

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes text."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error summarizing chunk: {e}", file=sys.stderr)
        return "[Error in summarization]"


def summarize_final(client, summaries, model):
    combined_text = "\n\n".join(summaries)
    prompt = f"""
    Here are summaries of different parts of a document. Please combine them into a single, coherent, and comprehensive summary of the entire document. structure it with appropriate headings if necessary.
    
    SUMMARIES:
    {combined_text}
    
    FINAL SUMMARY:
    """

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that creates comprehensive summaries.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error creating final summary: {e}", file=sys.stderr)
        return "[Error in final summarization]"


def main():
    parser = argparse.ArgumentParser(description="Summarize long documents.")
    parser.add_argument("file_path", help="Path to the file (.pdf or .txt)")
    parser.add_argument("--api_key", required=True, help="LLM API Key")
    parser.add_argument("--base_url", help="LLM Base URL")
    parser.add_argument("--model", default="gpt-4o", help="LLM Model")
    parser.add_argument("--chunk_size", type=int, default=10000, help="Chunk size in characters")

    # Custom parsing logic for SkillManager which passes args as a single string
    args_to_parse = sys.argv[1:]
    if len(sys.argv) == 2 and (" " in sys.argv[1]):
        try:
            args_to_parse = shlex.split(sys.argv[1], posix=False)
        except Exception:
            pass

    args = parser.parse_args(args_to_parse)

    # Initialize Client
    client = OpenAI(api_key=args.api_key, base_url=args.base_url)

    try:
        # 1. Read
        print(f"Reading {args.file_path}...")
        text = extract_text(args.file_path)
        print(f"Total length: {len(text)} characters.")

        if len(text) < args.chunk_size:
            print("Document is short enough for direct summarization.")
            # Direct summary
            chunks = [text]
        else:
            # 2. Split
            chunks = split_text(text, chunk_size=args.chunk_size)
            print(f"Split into {len(chunks)} chunks.")

        # 3. Map (Summarize Chunks)
        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            print(f"Summarizing chunk {i + 1}/{len(chunks)}...")
            summary = summarize_chunk(client, chunk, args.model)
            chunk_summaries.append(summary)

        # 4. Reduce (Final Summary)
        if len(chunk_summaries) == 1:
            final_summary = chunk_summaries[0]
        else:
            print("Generating final summary...")
            final_summary = summarize_final(client, chunk_summaries, args.model)

        print("\n" + "=" * 20 + " FINAL SUMMARY " + "=" * 20 + "\n")
        print(final_summary)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
