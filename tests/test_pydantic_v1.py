try:
    from pydantic.v1 import BaseSettings
    print("SUCCESS: from pydantic.v1 import BaseSettings")
except Exception as e:
    print(f"FAILURE: {e}")

try:
    import chromadb
    print("SUCCESS: import chromadb")
except Exception as e:
    print(f"FAILURE: {e}")
