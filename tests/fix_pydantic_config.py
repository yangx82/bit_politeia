import re

target_file = r"C:\Users\yangx\AppData\Roaming\Python\Python314\site-packages\chromadb\config.py"

with open(target_file, encoding="utf-8") as f:
    content = f.read()

# Match class Config block
#     class Config:
#         env_file = ".env"
#         env_file_encoding = "utf-8"

pattern = r"(class Config:\s+env_file = \".env\"\s+env_file_encoding = \"utf-8\")"
replacement = r"\1\n        extra = \"ignore\""

new_content = re.sub(pattern, replacement, content)

if 'extra = "ignore"' in new_content:
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Added extra='ignore' to Config")
else:
    print("Failed to find Config block pattern")
