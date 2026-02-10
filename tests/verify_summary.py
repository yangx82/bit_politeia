
import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Analyze paths
project_root = Path(__file__).resolve().parent.parent
summarize_script = project_root / "backend" / "skills" / "long-doc-analyzer" / "scripts" / "summarize.py"

# Try loading .env from current or backend dir
load_dotenv()
load_dotenv(project_root / ".env")

api_key = os.environ.get("OPENAI_API_KEY")
base_url = os.environ.get("OPENAI_BASE_URL")

if not api_key:
    # Try one more location: user home .env
    load_dotenv(Path.home() / ".env")
    api_key = os.environ.get("OPENAI_API_KEY")

if not api_key:
    # Final fallback for verification in this specific environment if known
    # But usually we fail here.
    print("Skipping test: No API Key found in env vars or .env files.")
    print("Please ensure OPENAI_API_KEY is set.")
    sys.exit(0)

# Generate dummy long file
long_text = "This is a test sentence for summarization. " * 2000 # Approx 80k chars
test_file = "test_long_doc.txt"
with open(test_file, "w", encoding="utf-8") as f:
    f.write(long_text)

print(f"Created {test_file} with size {len(long_text)}")

# Run summarize.py
cmd = [
    "python",
    str(summarize_script),
    test_file,
    "--api_key", api_key,
    "--chunk_size", "10000"
]

if base_url:
    cmd.extend(["--base_url", base_url])

print(f"Running command: {' '.join(cmd)}")

# We use shell=True on Windows sometimes if python is not in path correctly, 
# but list args are safer.
result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)

if result.returncode == 0:
    print("SUCCESS")
    # Clean up
    if os.path.exists(test_file):
        os.remove(test_file)
else:
    print("FAILURE")
