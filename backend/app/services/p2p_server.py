from fastapi import FastAPI, HTTPException, Body, status
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional
import uvicorn
import logging
import os

from .bootstrap_service import bootstrap_service
from ..p2p_community.bootstrap_client import NodeRegistration

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BootstrapServer")

app = FastAPI(title="Bit-Politeia Bootstrap Server")

# Global safety toggle for node removal
ALLOW_NODE_REMOVAL = os.getenv("BOOTSTRAP_ALLOW_NODE_REMOVAL", "false").lower() == "true"

from contextlib import asynccontextmanager

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the bootstrap service on startup
    logger.info("Initializing BootstrapService...")
    try:
        bootstrap_service.initialize()
        logger.info("BootstrapService initialization complete.")
    except Exception as e:
        logger.error(f"FATAL: Failed to initialize BootstrapService: {e}")
        import traceback
        logger.error(traceback.format_exc())
    yield
    # Cleanup on shutdown (if needed)
    logger.info("Shutting down BootstrapServer...")

app.router.lifespan_context = lifespan

@app.get("/")
async def root():
    return {"status": "running", "service": "Bit-Politeia Bootstrap"}

@app.get("/topology")
async def get_topology(node_id: Optional[str] = None) -> Dict:
    """Get full network topology and optionally update heartbeat."""
    return bootstrap_service.get_topology_info(node_id=node_id)

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
             group_id=registration.get("group_id"),
             name=registration.get("name")
        )
        
        success = bootstrap_service.register_node(reg_obj)
        return {"success": success}
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/nodes/{node_id}")
async def unregister_node(node_id: str) -> Dict[str, bool]:
    """Manually unregister a node from the bootstrap server."""
    allow_removal = os.getenv("BOOTSTRAP_ALLOW_NODE_REMOVAL", "false").lower() == "true"
    
    if not allow_removal:
        raise HTTPException(
            status_code=403, 
            detail="Node removal is disabled. Set BOOTSTRAP_ALLOW_NODE_REMOVAL=true to enable."
        )
        
    success = bootstrap_service.unregister_node(node_id)
    if not success:
        raise HTTPException(status_code=404, detail="Node not found.")
        
    return {"success": success}

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

@app.get("/nodes")
async def list_nodes() -> Dict[str, Any]:
    """List all currently registered nodes (for debugging)."""
    topology = bootstrap_service.get_topology_info()
    return {"nodes": topology.get("nodes", {})}

@app.delete("/nodes/{node_id}")
async def remove_node(node_id: str) -> Dict[str, bool]:
    """Manually remove a node from the topology (Safety Toggle required)."""
    logger.info(f"Received request to delete node: {node_id}")
    if not ALLOW_NODE_REMOVAL:
         logger.warning("Node removal blocked: Safety toggle BOOTSTRAP_ALLOW_NODE_REMOVAL=true not set.")
         raise HTTPException(
             status_code=status.HTTP_403_FORBIDDEN, 
             detail="Manual node removal is disabled on this server. Enable via BOOTSTRAP_ALLOW_NODE_REMOVAL=true"
         )
    
    success = bootstrap_service.unregister_node(node_id)
    if not success:
        logger.warning(f"Node removal failed: Node {node_id} not found.")
        # We explicitly return "Node not found." to distinguish from FastAPI 404
        raise HTTPException(status_code=404, detail="Node not found.")
        
    return {"success": True}

from fastapi import WebSocket, WebSocketDisconnect
from .relay_manager import relay_manager
import json

@app.websocket("/ws/relay/{node_id}")
async def websocket_relay(websocket: WebSocket, node_id: str):
    """
    WebSocket endpoint for P2P relay.
    Nodes connect here to receive messages when they are behind NAT.
    """
    await relay_manager.connect(node_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Parse message to determine target
            try:
                message = json.loads(data)
                
                # Handle PING/Heartbeat
                if message.get("type") == "PING":
                    await websocket.send_text(json.dumps({"type": "PONG"}))
                    continue

                # Check for standard SignedMessage format or specific relay envelope
                # Expecting SignedMessage which has 'recipient_id'
                target_id = message.get("recipient_id")
                msg_type = message.get("message_type")
                
                if target_id:
                     if msg_type == "group":
                         # Group Broadcast
                         success = await relay_manager.broadcast_to_group(node_id, target_id, message)
                     else:
                         # Direct Relay to target
                         success = await relay_manager.route_message(node_id, target_id, message)
                         
                     if not success:
                         # Send error back to sender
                         error_msg = {
                             "type": "SYSTEM_ERROR",
                             "error_code": "DELIVERY_FAILED",
                             "recipient_id": target_id,
                             "content": f"Target {target_id} not reachable via relay."
                         }
                         await websocket.send_text(json.dumps(error_msg))
                else:
                    logger.warning(f"Relay: Received malformed message from {node_id} (No recipient_id or type)")
                    
            except json.JSONDecodeError:
                logger.warning(f"Relay: Received invalid JSON from {node_id}")
                
    except WebSocketDisconnect:
        relay_manager.disconnect(node_id)
    except Exception as e:
        logger.error(f"Relay Error for {node_id}: {e}")
        relay_manager.disconnect(node_id)

def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the server programmatically."""
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    run_server()
