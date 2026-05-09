try:
    print("SUCCESS: from pydantic_settings import BaseSettings")
except Exception as e:
    print(f"FAILURE: {e}")

try:
    import chromadb.config

    print("SUCCESS: import chromadb.config")
    # Verify Settings class inherits from BaseSettings (V2)
    print(f"Settings bases: {chromadb.config.Settings.__bases__}")
except Exception as e:
    print(f"FAILURE: {e}")

try:
    import chromadb

    print("SUCCESS: import chromadb")
except Exception as e:
    print(f"FAILURE: {e}")
