import sys
import site
print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")
print(f"sys.path: {sys.path}")
print(f"User site: {site.getusersitepackages()}")

print("\n--- Trying to import chromadb ---")
try:
    import chromadb
    print("SUCCESS: import chromadb")
except Exception as e:
    print(f"FAILURE: {e}")

print("\n--- Trying to import sentence_transformers ---")
try:
    from sentence_transformers import SentenceTransformer
    print("SUCCESS: from sentence_transformers import SentenceTransformer")
except Exception as e:
    print(f"FAILURE: {e}")
