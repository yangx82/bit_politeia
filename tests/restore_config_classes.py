import re

target_file = r"C:\Users\yangx\AppData\Roaming\Python\Python314\site-packages\chromadb\config.py"

missing_block = """
DEFAULT_TENANT = "default_tenant"
DEFAULT_DATABASE = "default_database"


class APIVersion(str, Enum):
    V1 = "/api/v1"
    V2 = "/api/v2"


# NOTE(hammadb) 1/13/2024 - This has to be in config.py instead of being localized to the module
# that uses it because of a circular import issue. This is a temporary solution until we can
# refactor the code to remove the circular import.
class RoutingMode(Enum):
    \"\"\"
    Routing mode for the segment directory

    node - Assign based on the node name, used in production with multi-node settings with the assumption that
    there is one query service pod per node. This is useful for when there is a disk based cache on the
    node that we want to route to.

    id - Assign based on the member id, used in development and testing environments where the node name is not
    guaranteed to be unique. (I.e a local development kubernetes env). Or when there are multiple query service
    pods per node.
    \"\"\"

    NODE = "node"
    ID = "id"
"""

with open(target_file, "r", encoding="utf-8") as f:
    content = f.read()

# Insert before class Settings if not present
if "class APIVersion" not in content:
    # Use simple string replacement or regex
    # We replaced imports up to class Settings, so class Settings should be there
    content = content.replace("class Settings", missing_block + "\n\nclass Settings")
    
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    print("Restored APIVersion and RoutingMode")
else:
    print("APIVersion already present")
