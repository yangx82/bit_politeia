import re

target_file = r"C:\Users\yangx\AppData\Roaming\Python\Python314\site-packages\chromadb\config.py"

with open(target_file, encoding="utf-8") as f:
    content = f.read()

# Pattern to match: : Optional[...] = None
# We want to replace it with : Any = None
# We need to be careful not to match things that aren't fields, but in this file, it's mostly fields.

# Regex explanation:
# :\s*Optional\[.*?\]  -> Matches ": Optional[...]" non-greedily
# \s*=\s*None          -> Matches " = None"
pattern = r":\s*Optional\[.*?\]\s*=\s*None"
replacement = ": Any = None"

new_content, count = re.subn(pattern, replacement, content)

print(f"Replaced {count} occurrences.")

if count > 0:
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Successfully patched config.py")
else:
    print("No occurrences found or files match.")
