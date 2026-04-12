import re

target_file = r"C:\Users\yangx\AppData\Roaming\Python\Python314\site-packages\chromadb\config.py"

with open(target_file, encoding="utf-8") as f:
    content = f.read()

# Replace imports
# Match the block that tries to import BaseSettings
pattern_imports = r"(in_pydantic_v2 = False.*?)class Settings"
replacement_imports = """try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings

def validator(*args, **kwargs):
    def decorator(f):
        return f
    return decorator

class Settings"""

# regex flag DOTALL to match newlines
new_content = re.sub(pattern_imports, replacement_imports, content, flags=re.DOTALL)

# Ensure BaseSettings is strictly from pydantic_settings if possible
if "pydantic.v1" in new_content:
    new_content = new_content.replace(
        "from pydantic.v1 import BaseSettings", "from pydantic_settings import BaseSettings"
    )
    new_content = new_content.replace(
        "from pydantic.v1 import validator", "# from pydantic.v1 import validator"
    )

with open(target_file, "w", encoding="utf-8") as f:
    f.write(new_content)

print("Forced Pydantic V2 in config.py")
