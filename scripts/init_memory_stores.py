#!/usr/bin/env python3
"""
Next-Gen Agent Memory System - DB Schema & Index Initializer
Reads environment variables and safely initializes Redis, MongoDB, Neo4j, Qdrant, and MinIO.
"""

import os
import sys
import time

def init_redis():
    print("[1/5] Checking Redis L2 Short-Term Memory...")
    try:
        from redis import Redis
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_pass = os.getenv("REDIS_PASSWORD", "MemoryRedis2026")
        
        r = Redis(host=redis_host, port=redis_port, password=redis_pass, socket_timeout=3)
        r.ping()
        print("  ✓ Redis L2 connection successful.")
        return True
    except Exception as e:
        print(f"  ⚠️ Redis not reachable ({e}). Skipping Redis indexing.")
        return False

def init_mongo():
    print("[2/5] Initializing MongoDB L3 Task & Reflexion Store...")
    try:
        from pymongo import MongoClient
        mongo_uri = os.getenv("MONGO_URI", "mongodb://admin:MemoryMongo2026@localhost:27017")
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        db = client["agent_memory_db"]
        
        # Create task_plans index
        db["task_plans"].create_index("session_id", unique=True)
        # Create reflections index
        db["reflections"].create_index([("trigger_error", 1), ("session_id", 1)])
        print("  ✓ MongoDB collections and indexes created successfully.")
        return True
    except Exception as e:
        print(f"  ⚠️ MongoDB not reachable ({e}). Skipping MongoDB indexing.")
        return False

def init_neo4j():
    print("[3/5] Initializing Neo4j L4 Temporal Knowledge Graph...")
    try:
        from neo4j import GraphDatabase
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_pass = os.getenv("NEO4J_PASSWORD", "MemoryGraph2026")
        
        driver = None
        last_err = None
        for attempt in range(6):
            try:
                driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass), connection_timeout=5)
                driver.verify_connectivity()
                break
            except Exception as conn_err:
                last_err = conn_err
                if attempt < 5:
                    time.sleep(3)
                else:
                    raise last_err

        with driver.session() as session:
            session.run("CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE")
            session.run("CREATE INDEX edge_valid_from IF NOT EXISTS FOR ()-[r:RELATION]-() ON (r.valid_from)")
            session.run("CREATE INDEX edge_valid_to IF NOT EXISTS FOR ()-[r:RELATION]-() ON (r.valid_to)")
        driver.close()
        print("  ✓ Neo4j Temporal Graph constraints and indexes created successfully.")
        return True
    except Exception as e:
        print(f"  ⚠️ Neo4j not reachable ({e}). Skipping Neo4j indexing.")
        return False

def init_qdrant():
    print("[4/5] Initializing Qdrant L4 Long-Term Associative Vector Memory...")
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import VectorParams, Distance
        
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
        client = QdrantClient(host=qdrant_host, port=qdrant_port, timeout=3)
        
        collection_name = "agent_longterm_memory"
        collections = [c.name for c in client.get_collections().collections]
        if collection_name not in collections:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
            )
            print(f"  ✓ Qdrant Collection '{collection_name}' created successfully.")
        else:
            print(f"  ✓ Qdrant Collection '{collection_name}' already exists.")
        return True
    except Exception as e:
        print(f"  ⚠️ Qdrant not reachable ({e}). Skipping Qdrant indexing.")
        return False

def init_minio():
    print("[5/5] Checking MinIO Large Payload Storage...")
    try:
        import urllib.request
        minio_url = os.getenv("MINIO_URL", "http://localhost:19000")
        req = urllib.request.Request(f"{minio_url}/minio/health/live", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                print("  ✓ MinIO Large Payload Storage live.")
                return True
        return False
    except Exception as e:
        print(f"  ⚠️ MinIO not reachable ({e}). Skipping MinIO check.")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Starting Next-Gen Agent Memory System Infrastructure Initializer...")
    print("=" * 60)
    results = [init_redis(), init_mongo(), init_neo4j(), init_qdrant(), init_minio()]
    active_count = sum(1 for r in results if r)
    print("=" * 60)
    print(f"Initialization Summary: {active_count}/5 Services Ready.")
    if active_count == 0:
        print("💡 Note: Operating in Local Lightweight Memory Mode (JSONL + SQLite FTS + ChromaDB).")
    else:
        print("🚀 Enterprise Next-Gen Memory Stack Activated!")
    print("=" * 60)
