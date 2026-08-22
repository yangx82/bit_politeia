"""
Live Observability & Multi-Agent Topology Canvas Module

Aggregates real-time P2P mesh topology, Matrix Event DAG causality graph,
Neo4j/Semantic memory graph snapshots, and AIP self-evolution Kanban state
for dashboard and frontend visual rendering.
"""

import logging
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any

from app.p2p_community.dag_resolver import dag_resolver
from app.services.evolution_service import evolution_service
from app.services.hot_reload_manager import hot_reload_manager

logger = logging.getLogger(__name__)


class ObservabilityService:
    """
    Service providing live graph feeds and telemetry for multi-agent observability.
    """

    def __init__(self, agent_service: Any = None):
        self.agent_service = agent_service

    def get_p2p_topology(self, p2p_service: Any = None) -> dict[str, Any]:
        """
        Exports P2P network mesh topology (nodes & links) for D3/ECharts rendering.
        """
        nodes = []
        links = []

        local_node_id = "local_resident"
        if p2p_service and getattr(p2p_service, "local_node", None):
            local_node_id = p2p_service.local_node.node_id

        nodes.append({
            "id": local_node_id,
            "label": "Local Agent Node",
            "type": "local",
            "status": "online",
            "reputation": 100,
        })

        if p2p_service and getattr(p2p_service, "network_manager", None):
            peers = getattr(p2p_service.network_manager, "connected_peers", {})
            for peer_id, peer_info in peers.items():
                nodes.append({
                    "id": peer_id,
                    "label": f"Peer {peer_id[:8]}",
                    "type": "peer",
                    "status": "online" if peer_info.get("connected") else "offline",
                    "reputation": peer_info.get("reputation", 50),
                })
                links.append({
                    "source": local_node_id,
                    "target": peer_id,
                    "latency_ms": peer_info.get("latency_ms", 25),
                    "protocol": peer_info.get("protocol", "WebRTC"),
                })

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "node_count": len(nodes),
            "nodes": nodes,
            "links": links,
        }

    def get_event_dag(self, limit: int = 50) -> dict[str, Any]:
        """
        Exports Matrix-style Event DAG causality tree.
        """
        events = dag_resolver.get_all_events(limit=limit)
        dag_nodes = []
        dag_edges = []

        for evt in events:
            m_type = evt.message_type.value if hasattr(evt.message_type, "value") else str(evt.message_type)
            ts_str = evt.timestamp.isoformat() if hasattr(evt.timestamp, "isoformat") else str(evt.timestamp)
            dag_nodes.append({
                "id": evt.message_id,
                "sender": evt.sender_id,
                "seq_id": getattr(evt, "seq_id", 0),
                "type": m_type,
                "timestamp": ts_str,
            })
            for parent_id in (evt.parents or []):
                dag_edges.append({
                    "source": parent_id,
                    "target": evt.message_id,
                    "relation": "CAUSED_BY",
                })

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_count": len(dag_nodes),
            "nodes": dag_nodes,
            "edges": dag_edges,
        }

    def get_memory_graph_snapshot(self, resident_memory: Any = None) -> dict[str, Any]:
        """
        Exports semantic memory facts, distilled concepts, and social edges as a force-directed graph.
        """
        nodes = []
        edges = []

        nodes.append({"id": "resident_self", "label": "Resident Self", "category": "agent"})

        if resident_memory:
            profile = getattr(resident_memory, "_semantic_profile", {})
            facts = profile.get("facts", [])
            for i, fact in enumerate(facts[-30:]):
                f_id = f"fact_{i}"
                nodes.append({"id": f_id, "label": fact[:40], "full_text": fact, "category": "fact"})
                edges.append({"source": "resident_self", "target": f_id, "relation": "KNOWS_FACT"})

            concepts = profile.get("distilled_concepts", [])
            for i, concept in enumerate(concepts[-20:]):
                c_id = f"concept_{i}"
                nodes.append({
                    "id": c_id,
                    "label": concept.get("concept", "")[:40],
                    "category": "concept",
                    "confidence": concept.get("confidence", 1.0),
                })
                edges.append({"source": "resident_self", "target": c_id, "relation": "DISTILLED_CONCEPT"})

            social_graph = getattr(resident_memory, "_social_graph", {})
            for peer_id, edge_data in social_graph.items():
                p_node_id = f"social_{peer_id[:8]}"
                nodes.append({
                    "id": p_node_id,
                    "label": edge_data.get("name") or f"Peer {peer_id[:8]}",
                    "category": "social_peer",
                    "trust": edge_data.get("trust", 0),
                })
                edges.append({
                    "source": "resident_self",
                    "target": p_node_id,
                    "relation": edge_data.get("rel_type", "contact"),
                    "weight": edge_data.get("trust", 0),
                })

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "nodes": nodes,
            "edges": edges,
        }

    def get_evolution_kanban(self) -> dict[str, Any]:
        """
        Exports AIP self-evolution Kanban state columns (Draft, Proposed, Auditing, Canary, Applied, Rejected).
        """
        all_aips = evolution_service.list_aips()
        columns: dict[str, list[dict[str, Any]]] = {
            "draft": [],
            "proposed": [],
            "audited": [],
            "canary": [],
            "applied": [],
            "rejected": [],
        }

        for aip in all_aips:
            status = aip.get("status", "draft")
            if status in columns:
                columns[status].append(aip)
            else:
                columns["draft"].append(aip)

        reload_history = hot_reload_manager.get_history()

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "columns": columns,
            "total_aips": len(all_aips),
            "recent_canary_reloads": reload_history[-10:],
        }


# Singleton instance
observability_service = ObservabilityService()
