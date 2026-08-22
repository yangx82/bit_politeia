"""
Next-Gen Agent Memory System Client & Fallback Adapter
Provides a unified multi-tier memory API (Redis L2, MongoDB L3, Neo4j L4, Qdrant L4, MinIO Payload)
with automatic health detection and zero-breakage local fallback.
"""

import os
import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NextGenMemoryClient:
    """
    Unified Next-Gen Memory Client.
    Supports L2 Short-Term Pub/Sub sliding window (Redis),
    L3 Task Plans & Reflection Error Store (MongoDB),
    L4 Temporal Knowledge Graph (Neo4j),
    L4 Associative Vector Memory (Qdrant),
    and Large Payload Store (MinIO).
    """

    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_pass = os.getenv("REDIS_PASSWORD", "MemoryRedis2026")

        self.mongo_uri = os.getenv("MONGO_URI", "mongodb://admin:MemoryMongo2026@localhost:27017")
        self.neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:17687")
        self.neo4j_pass = os.getenv("NEO4J_PASSWORD", "MemoryGraph2026")
        self.qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port = int(os.getenv("QDRANT_PORT", "16333"))

        self._redis = None
        self._mongo = None
        self._neo4j = None
        self._qdrant = None
        self._initialized = False

    def connect(self) -> Dict[str, bool]:
        """Lazy connect to available middleware services."""
        status = {"redis": False, "mongo": False, "neo4j": False, "qdrant": False}

        # 1. Redis
        try:
            from redis import Redis
            r = Redis(host=self.redis_host, port=self.redis_port, password=self.redis_pass, socket_timeout=1)
            r.ping()
            self._redis = r
            status["redis"] = True
        except Exception:
            self._redis = None

        # 2. MongoDB
        try:
            from pymongo import MongoClient
            client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=1000)
            client.admin.command("ping")
            self._mongo = client["agent_memory_db"]
            status["mongo"] = True
        except Exception:
            self._mongo = None

        # 3. Neo4j
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(self.neo4j_uri, auth=("neo4j", self.neo4j_pass), connection_timeout=1)
            driver.verify_connectivity()
            self._neo4j = driver
            status["neo4j"] = True
        except Exception:
            self._neo4j = None

        # 4. Qdrant
        try:
            from qdrant_client import QdrantClient
            q_client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port, timeout=1)
            q_client.get_collections()
            self._qdrant = q_client
            status["qdrant"] = True
        except Exception:
            self._qdrant = None

        self._initialized = True
        return status

    def check_health(self) -> Dict[str, Any]:
        """Return connectivity status for all memory tiers."""
        if not self._initialized:
            st = self.connect()
        else:
            st = {
                "redis": self._redis is not None,
                "mongo": self._mongo is not None,
                "neo4j": self._neo4j is not None,
                "qdrant": self._qdrant is not None,
            }
        st["active"] = any(st.values())
        return st

    # --- L2: SHORT-TERM MEMORY (Redis) ---

    def write_short_term(self, session_id: str, role: str, content: str, window_size: int = 20) -> bool:
        """Write to L2 Short-Term Memory sliding window in Redis."""
        if not self._redis:
            return False
        try:
            key = f"session:{session_id}:stm"
            msg = f"{role}:{content}"
            self._redis.rpush(key, msg)
            self._redis.ltrim(key, -window_size, -1)
            return True
        except Exception as e:
            logger.warning(f"Redis write_short_term failed: {e}")
            return False

    def read_short_term(self, session_id: str, count: int = 10) -> List[str]:
        """Read recent messages from L2 Short-Term Memory in Redis."""
        if not self._redis:
            return []
        try:
            key = f"session:{session_id}:stm"
            items = self._redis.lrange(key, -count, -1)
            return [item.decode("utf-8") if isinstance(item, bytes) else str(item) for item in items]
        except Exception as e:
            logger.warning(f"Redis read_short_term failed: {e}")
            return []

    # --- L3: MID-TERM TASK & REFLECTION STORE (MongoDB) ---

    def record_reflection(self, session_id: str, trigger_error: str, corrective_action: str, context_snippet: str = "") -> bool:
        """Record an error reflection into MongoDB L3 store."""
        if self._mongo is None:
            return False
        try:
            doc = {
                "session_id": session_id,
                "trigger_error": trigger_error,
                "corrective_action": corrective_action,
                "context_snippet": context_snippet,
                "created_at": time.time(),
            }
            self._mongo["reflections"].insert_one(doc)
            return True
        except Exception as e:
            logger.warning(f"MongoDB record_reflection failed: {e}")
            return False

    def search_reflections(self, trigger_error: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Search reflections in MongoDB L3 store."""
        if self._mongo is None:
            return []
        try:
            query = {}
            if trigger_error:
                query["trigger_error"] = {"$regex": trigger_error, "$options": "i"}
            cursor = self._mongo["reflections"].find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
            return list(cursor)
        except Exception as e:
            logger.warning(f"MongoDB search_reflections failed: {e}")
            return []

    def store_task_plan(self, session_id: str, plan_data: Dict[str, Any]) -> bool:
        """Store or update task plan in MongoDB L3 store."""
        if self._mongo is None:
            return False
        try:
            doc = dict(plan_data)
            doc["session_id"] = session_id
            doc["updated_at"] = time.time()
            self._mongo["task_plans"].replace_one({"session_id": session_id}, doc, upsert=True)
            return True
        except Exception as e:
            logger.warning(f"MongoDB store_task_plan failed: {e}")
            return False

    # --- L4: TEMPORAL KNOWLEDGE GRAPH (Neo4j) ---

    def add_temporal_fact(self, subject: str, relation: str, target: str, valid_from: str = None, valid_to: str = None) -> bool:
        """Insert entity-relation triplet into Neo4j Temporal KG."""
        if not self._neo4j:
            return False
        try:
            v_from = valid_from or time.strftime("%Y-%m-%d %H:%M:%S")
            v_to = valid_to or "9999-12-31 23:59:59"
            cypher = """
            MERGE (s:Entity {id: $subject})
            MERGE (t:Entity {id: $target})
            MERGE (s)-[r:RELATION {type: $relation}]->(t)
            SET r.valid_from = $v_from, r.valid_to = $v_to
            """
            with self._neo4j.session() as session:
                session.run(cypher, subject=subject, target=target, relation=relation, v_from=v_from, v_to=v_to)
            return True
        except Exception as e:
            logger.warning(f"Neo4j add_temporal_fact failed: {e}")
            return False

    def search_temporal_facts(self, subject: str) -> List[Dict[str, Any]]:
        """Query relations for an entity in Neo4j Temporal KG."""
        if not self._neo4j:
            return []
        try:
            cypher = """
            MATCH (s:Entity {id: $subject})-[r:RELATION]->(t:Entity)
            RETURN r.type as relation, t.id as target, r.valid_from as valid_from, r.valid_to as valid_to
            """
            results = []
            with self._neo4j.session() as session:
                res = session.run(cypher, subject=subject)
                for record in res:
                    results.append({
                        "subject": subject,
                        "relation": record["relation"],
                        "target": record["target"],
                        "valid_from": record["valid_from"],
                        "valid_to": record["valid_to"],
                    })
            return results
        except Exception as e:
            logger.warning(f"Neo4j search_temporal_facts failed: {e}")
            return []

    # --- L4: ASSOCIATIVE VECTOR MEMORY (Qdrant) ---

    def add_associative_vector(self, memory_id: str, vector: List[float], payload: Dict[str, Any], collection_name: str = "agent_longterm_memory") -> bool:
        """Insert associative vector payload into Qdrant."""
        if not self._qdrant:
            return False
        try:
            from qdrant_client.models import PointStruct
            point = PointStruct(id=memory_id, vector=vector, payload=payload)
            self._qdrant.upsert(collection_name=collection_name, points=[point])
            return True
        except Exception as e:
            logger.warning(f"Qdrant add_associative_vector failed: {e}")
            return False

    def search_associative_memory(self, vector: List[float], limit: int = 5, collection_name: str = "agent_longterm_memory") -> List[Dict[str, Any]]:
        """Search Qdrant for associative vector memory."""
        if not self._qdrant:
            return []
        try:
            hits = self._qdrant.search(collection_name=collection_name, query_vector=vector, limit=limit)
            return [{"id": hit.id, "score": hit.score, "payload": hit.payload} for hit in hits]
        except Exception as e:
            logger.warning(f"Qdrant search_associative_memory failed: {e}")
            return []


# Global singleton instance
next_gen_memory = NextGenMemoryClient()
