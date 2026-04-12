import logging
import os
import subprocess
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TunnelClient:
    """
    Manages the frpc process for an agent node.
    Requests tunnel allocation from the Bootstrap Server and maintains the tunnel.
    """

    def __init__(self, bootstrap_url: str, node_id: str, local_port: int = 8000):
        self.bootstrap_url = bootstrap_url.rstrip("/")
        self.node_id = node_id
        self.local_port = local_port
        self.process: subprocess.Popen | None = None
        self.config: dict[str, Any] | None = None

    async def request_tunnel(self) -> bool:
        """Request a tunnel from the Bootstrap Server."""
        logger.info(f"[Tunnel] Requesting tunnel for node {self.node_id} from {self.bootstrap_url}")

        # Respect AGENT_BOOTSTRAP_VERIFY setting
        import os

        verify_ssl = os.getenv("AGENT_BOOTSTRAP_VERIFY", "true").lower() == "true"

        try:
            async with httpx.AsyncClient(timeout=10.0, verify=verify_ssl) as client:
                resp = await client.post(
                    f"{self.bootstrap_url}/tunnel/v1/request", json={"node_id": self.node_id}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        self.config = data.get("config")
                        logger.info(
                            f"[Tunnel] Tunnel allocated: Remote Port {self.config.get('remote_port')}"
                        )
                        return True
                logger.error(f"[Tunnel] Request failed with status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"[Tunnel] Connection error while requesting tunnel: {e}")
        return False

    def get_frpc_path(self) -> str | None:
        # Check project bin directory
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        bin_dir = os.path.join(base_dir, "bin")

        # Platform dependent extension
        ext = ".exe" if os.name == "nt" else ""
        path = os.path.join(bin_dir, f"frpc{ext}")

        if os.path.exists(path):
            return path

        # Fallback to PATH
        import shutil

        return shutil.which(f"frpc{ext}")

    def generate_config(self) -> str:
        if not self.config:
            raise ValueError("Tunnel config not available. Call request_tunnel first.")

        config_content = f"""
serverAddr = "{self.config["server_addr"]}"
serverPort = {self.config["server_port"]}
auth.token = "{self.config["token"]}"

[[proxies]]
name = "p2p-{self.node_id[:8]}"
type = "tcp"
localIP = "127.0.0.1"
localPort = {self.local_port}
remotePort = {self.config["remote_port"]}
"""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(base_dir, f"frpc_{self.node_id[:8]}.toml")
        with open(config_path, "w") as f:
            f.write(config_content)
        return config_path

    async def start(self) -> str | None:
        """Start the frpc process and return the public endpoint."""
        if not self.config and not await self.request_tunnel():
            return None

        frpc_path = self.get_frpc_path()
        if not frpc_path:
            logger.warning("[Tunnel] frpc binary not found. Cannot start tunnel.")
            return None

        config_path = self.generate_config()
        logger.info(f"[Tunnel] Starting frpc using {frpc_path} with config {config_path}")

        try:
            self.process = subprocess.Popen(
                [frpc_path, "-c", config_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            public_endpoint = f"http://{self.config['server_addr']}:{self.config['remote_port']}"
            logger.info(f"[Tunnel] frpc started. Public Endpoint: {public_endpoint}")
            return public_endpoint
        except Exception as e:
            logger.error(f"[Tunnel] Failed to start frpc: {e}")
            return None

    def stop(self):
        if self.process:
            logger.info(f"[Tunnel] Stopping frpc (PID: {self.process.pid})...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            logger.info("[Tunnel] frpc stopped.")
