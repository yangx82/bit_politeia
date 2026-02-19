import re

target_file = r"C:\Users\yangx\AppData\Roaming\Python\Python314\site-packages\chromadb\config.py"

with open(target_file, "r", encoding="utf-8") as f:
    content = f.read()

# Fix 1: chroma_coordinator_host
# content = re.sub(r"chroma_coordinator_host\s*=\s*", "chroma_coordinator_host: str = ", content)
# To be safe and avoid matching partial words, use \b or look at indentation
content = re.sub(r"(\s+)chroma_coordinator_host\s*=\s*", r"\1chroma_coordinator_host: str = ", content)

# Fix 2: chroma_logservice_host
content = re.sub(r"(\s+)chroma_logservice_host\s*=\s*", r"\1chroma_logservice_host: str = ", content)

# Fix 3: chroma_logservice_port
content = re.sub(r"(\s+)chroma_logservice_port\s*=\s*", r"\1chroma_logservice_port: int = ", content)

with open(target_file, "w", encoding="utf-8") as f:
    f.write(content)

print("Applied annotations info fix.")
