from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List
import uvicorn
import logging

from .bootstrap_service import bootstrap_service
from ..p2p_community.bootstrap_client import NodeRegistration

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BootstrapServer")

app = FastAPI(title="Bit-Politeia Bootstrap Server")

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "running", "service": "Bit-Politeia Bootstrap"}

@app.get("/topology")
async def get_topology() -> Dict[str, Any]:
    """Get full network topology and node list."""
    return bootstrap_service.get_topology_info()

@app.get("/rules")
async def get_rules() -> Dict[str, Any]:
    """Get community rules/constitution."""
    return bootstrap_service.get_community_rules()

@app.post("/register")
async def register_node(registration: dict = Body(...)) -> Dict[str, bool]:
    """Register a new node."""
    try:
        # Convert dict to NodeRegistration dataclass
        reg_obj = NodeRegistration(
             node_id=registration.get("node_id"),
             public_key=registration.get("public_key"),
             ip_address=registration.get("ip_address"),
             port=registration.get("port"),
             group_id=registration.get("group_id")
        )
        
        success = bootstrap_service.register_node(reg_obj)
        return {"success": success}
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/groups/{group_id}/pending")
async def get_pending_joins(group_id: str) -> Dict[str, Any]:
    """Get pending join requests for a group."""
    pending = bootstrap_service.get_pending_joins(group_id)
    return {"pending": [r.to_dict() for r in pending]}

@app.post("/groups/{group_id}/approve")
async def approve_node(group_id: str, payload: dict = Body(...)) -> Dict[str, bool]:
    """Approve a node's join request."""
    node_id = payload.get("node_id")
    approver_id = payload.get("approver_id")
    if not node_id or not approver_id:
        raise HTTPException(status_code=400, detail="node_id and approver_id required")
    
    success = bootstrap_service.approve_node_join(group_id, node_id, approver_id)
    return {"success": success}

@app.post("/groups/{group_id}/rankings")
async def set_rankings(group_id: str, payload: dict = Body(...)) -> Dict[str, bool]:
    """Set node rankings for a group."""
    rankings = payload.get("rankings")
    requester_id = payload.get("requester_id")
    if rankings is None or not requester_id:
        raise HTTPException(status_code=400, detail="rankings and requester_id required")
    
    success = bootstrap_service.set_group_rankings(group_id, rankings, requester_id)
    return {"success": success}

@app.post("/groups/{group_id}/core-nodes")
async def set_core_nodes(group_id: str, payload: dict = Body(...)) -> Dict[str, bool]:
    """Update core nodes for a group."""
    core_nodes = payload.get("core_nodes")
    requester_id = payload.get("requester_id")
    if core_nodes is None or not requester_id:
        raise HTTPException(status_code=400, detail="core_nodes and requester_id required")
    
    success = bootstrap_service.update_group_core_nodes(group_id, core_nodes, requester_id)
    return {"success": success}

@app.get("/groups/{group_id}/candidates")
async def get_candidates(group_id: str) -> Dict[str, List[str]]:
    """Get candidate suggestions for a core node election based on reputation."""
    candidates = bootstrap_service.get_election_candidates(group_id)
    return {"candidates": candidates}

def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the server programmatically."""
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    run_server()
