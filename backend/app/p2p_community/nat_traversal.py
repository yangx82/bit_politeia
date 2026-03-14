
import logging
import threading
import time
from typing import Optional, Tuple
import upnpy

logger = logging.getLogger(__name__)

class NATManager:
    """
    Manages NAT traversal using UPnP/IGD.
    Tries to map internal ports to external ports on the gateway.
    """
    def __init__(self):
        self.upnp = upnpy.UPnP()
        self.device = None
        self.service = None
        self.public_ip = None
        self.mapped_ports = set() # Set of (external_port, proto)
        self._lock = threading.Lock()

    def discover_gateway(self) -> bool:
        """Discover IGD (Internet Gateway Device) with WANIPConnection service."""
        try:
            logger.info("Discovering UPnP devices...")
            devices = self.upnp.discover()
            
            if not devices:
                logger.warning("No UPnP devices found.")
                return False

            # Select device with WANIPConnection service
            for device in devices:
                # Most routers expose WANIPConnection or WANPPPConnection
                service = device.get_service_by_id("WANIPConnection") or \
                          device.get_service_by_id("WANPPPConnection")
                
                if service:
                    self.device = device
                    self.service = service
                    logger.info(f"Found UPnP Gateway: {device.friendly_name}")
                    return True
            
            logger.warning("No suitable UPnP Gateway found (missing WANIP/WANPPP service).")
            return False
            
        except Exception as e:
            # Downgrade to warning as UPnP is often disabled or unreliable on consumer routers
            # and we use STUN/TURN as a primary traversal mechanism for WebRTC.
            logger.warning(f"UPnP discovery skipped or failed (Typical for many routers): {e}")
            return False

    def get_external_ip(self) -> Optional[str]:
        """Fetch external IP address from the gateway."""
        if not self.service:
            return None
        
        try:
            # Different devices might have different action names, but GetExternalIPAddress is standard
            action = self.service.get_action("GetExternalIPAddress")
            if action:
                response = action.invoke()
                # upnpy returns a dict-like object
                ip = response.get("NewExternalIPAddress")
                self.public_ip = ip
                return ip
        except Exception as e:
            logger.error(f"Failed to get external IP: {e}")
            return None

    def add_port_mapping(self, internal_port: int, external_port: int, protocol: str = "TCP", description: str = "BitPoliteia P2P") -> bool:
        """
        Add a port mapping (External -> Internal).
        protocol: TCP or UDP
        """
        if not self.service:
            if not self.discover_gateway():
                return False

        try:
            import socket
            # Get local internal IP
            # We connect to a dummy address to see which interface is used
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # doesn't even have to be reachable
                s.connect(('10.255.255.255', 1))
                internal_client = s.getsockname()[0]
            except Exception:
                internal_client = '127.0.0.1'
            finally:
                s.close()
            
            logger.info(f"Attempting UPnP mapping: {self.public_ip}:{external_port} -> {internal_client}:{internal_port} ({protocol})")

            # Standard UPnP action for adding port mapping
            # AddPortMapping(
            #    NewRemoteHost="", 
            #    NewExternalPort=external_port, 
            #    NewProtocol=protocol, 
            #    NewInternalPort=internal_port, 
            #    NewInternalClient=internal_client, 
            #    NewEnabled=1, 
            #    NewPortMappingDescription=description, 
            #    NewLeaseDuration=0
            # )
            
            self.service.AddPortMapping(
                NewRemoteHost="",
                NewExternalPort=external_port,
                NewProtocol=protocol,
                NewInternalPort=internal_port,
                NewInternalClient=internal_client,
                NewEnabled=1,
                NewPortMappingDescription=description,
                NewLeaseDuration=0
            )

            with self._lock:
                self.mapped_ports.add((external_port, protocol))
            
            logger.info(f"UPnP mapping successful: {external_port} -> {internal_client}:{internal_port}")
            return True

        except Exception as e:
            logger.error(f"Failed to add port mapping: {e}")
            return False

    def delete_port_mapping(self, external_port: int, protocol: str = "TCP") -> bool:
        """Delete a port mapping."""
        if not self.service:
            return False
            
        try:
            self.service.DeletePortMapping(
                NewRemoteHost="",
                NewExternalPort=external_port,
                NewProtocol=protocol
            )
            with self._lock:
                self.mapped_ports.discard((external_port, protocol))
            logger.info(f"UPnP mapping deleted: {external_port} ({protocol})")
            return True
        except Exception as e:
            logger.error(f"Failed to delete port mapping: {e}")
            return False

    def close(self):
        """Cleanup all mapped ports on shutdown."""
        with self._lock:
            for port, proto in list(self.mapped_ports):
                self.delete_port_mapping(port, proto)

nat_manager = NATManager()
