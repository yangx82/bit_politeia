from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
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

def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the server programmatically."""
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    run_server()
