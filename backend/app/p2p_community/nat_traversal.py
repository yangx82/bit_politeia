import logging
import random
import socket
import struct
import threading

import upnpy

# STUN Protocol Constants
STUN_BINDING_REQUEST = 0x0001
STUN_BINDING_RESPONSE = 0x0101
STUN_MAGIC_COOKIE = 0x2112A442
STUN_ATTR_MAPPED_ADDRESS = 0x0001
STUN_ATTR_XOR_MAPPED_ADDRESS = 0x0020

# Reliable Public STUN Servers
DEFAULT_STUN_SERVERS = [
    "stun.l.google.com:19302",
    "stun1.l.google.com:19302",
    "stun2.l.google.com:19302",
    "stun.cloudflare.com:3478",
    "stun.mixminion.net:3478",
]

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
        self.public_port = None
        self.mapped_ports = set()  # Set of (external_port, proto)
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
                service = device.get_service_by_id("WANIPConnection") or device.get_service_by_id(
                    "WANPPPConnection"
                )

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

    def get_external_ip(self) -> str | None:
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

    def add_port_mapping(
        self,
        internal_port: int,
        external_port: int,
        protocol: str = "TCP",
        description: str = "BitPoliteia P2P",
    ) -> bool:
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
                s.connect(("10.255.255.255", 1))
                internal_client = s.getsockname()[0]
            except Exception:
                internal_client = "127.0.0.1"
            finally:
                s.close()

            logger.info(
                f"Attempting UPnP mapping: {self.public_ip}:{external_port} -> {internal_client}:{internal_port} ({protocol})"
            )

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
                NewLeaseDuration=0,
            )

            with self._lock:
                self.mapped_ports.add((external_port, protocol))

            logger.info(
                f"UPnP mapping successful: {external_port} -> {internal_client}:{internal_port}"
            )
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
                NewRemoteHost="", NewExternalPort=external_port, NewProtocol=protocol
            )
            with self._lock:
                self.mapped_ports.discard((external_port, protocol))
            logger.info(f"UPnP mapping deleted: {external_port} ({protocol})")
            return True
        except Exception as e:
            logger.error(f"Failed to delete port mapping: {e}")
            return False

    def get_stun_endpoint(
        self, local_port: int, servers: list[str] = None
    ) -> tuple[str, int] | None:
        """
        Discover public IP and port using STUN protocol.
        Tries multiple servers until success.
        """
        if not servers:
            servers = DEFAULT_STUN_SERVERS

        logger.info(f"Attempting STUN discovery for local port {local_port}...")

        for server_addr in servers:
            try:
                host, port_str = server_addr.split(":")
                port = int(port_str)

                # Perform a single STUN Binding Request
                endpoint = self._query_stun(local_port, host, port)
                if endpoint:
                    public_ip, public_port = endpoint
                    logger.info(
                        f"STUN Discovery Successful via {server_addr}. Public Endpoint: {public_ip}:{public_port}"
                    )
                    self.public_ip = public_ip
                    self.public_port = public_port
                    return public_ip, public_port
            except Exception as e:
                logger.debug(f"STUN server {server_addr} failed: {e}")
                continue

        logger.warning("STUN Discovery failed for all servers.")
        return None

    def _query_stun(
        self, local_port: int, stun_host: str, stun_port: int
    ) -> tuple[str, int] | None:
        """Internal: Send STUN Binding Request and parse response."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            # Bind to same local port as the P2P service to ensure symmetric mapping (if any)
            # Use '0.0.0.0' to bind to all interfaces
            try:
                sock.bind(("0.0.0.0", local_port))
            except Exception as e:
                # If already bound, we might need SO_REUSEPORT on Linux/Mac
                # On Windows, SO_REUSEADDR is usually enough
                logger.debug(
                    f"STUN socket bind failed on {local_port}: {e}. Retrying without bind (limited NAT info)."
                )
                pass

            sock.settimeout(2.5)

            # Transaction ID: 12 random bytes
            transaction_id = bytes(random.getrandbits(8) for _ in range(12))

            # Header: Type (2), Length (2), Cookie (4), ID (12)
            header = struct.pack(
                "!HHI12s", STUN_BINDING_REQUEST, 0, STUN_MAGIC_COOKIE, transaction_id
            )

            sock.sendto(header, (stun_host, stun_port))

            data, addr = sock.recvfrom(2048)

            if len(data) < 20:
                return None

            res_type, res_len, res_cookie, res_id = struct.unpack("!HHI12s", data[:20])

            if res_type != STUN_BINDING_RESPONSE or res_id != transaction_id:
                return None

            # Parse STUN Attributes
            pos = 20
            while pos + 4 <= len(data):
                attr_type, attr_len = struct.unpack("!HH", data[pos : pos + 4])
                pos += 4

                # XOR-MAPPED-ADDRESS (Preferred)
                if attr_type == STUN_ATTR_XOR_MAPPED_ADDRESS:
                    if pos + 8 <= len(data):
                        # Pad (1), Family (1), X-Port (2), X-Address (4)
                        _, family, x_port = struct.unpack("!BBH", data[pos : pos + 4])
                        if family == 0x01:  # IPv4
                            # Port: XOR with top 16 bits of magic cookie
                            public_port = x_port ^ (STUN_MAGIC_COOKIE >> 16)
                            # Address: XOR with magic cookie
                            x_addr = struct.unpack("!I", data[pos + 4 : pos + 8])[0]
                            public_ip_int = x_addr ^ STUN_MAGIC_COOKIE
                            public_ip = socket.inet_ntoa(struct.pack("!I", public_ip_int))
                            return public_ip, public_port

                # MAPPED-ADDRESS (Fallback)
                elif attr_type == STUN_ATTR_MAPPED_ADDRESS:
                    if pos + 8 <= len(data):
                        _, family, port = struct.unpack("!BBH", data[pos : pos + 4])
                        if family == 0x01:
                            addr_int = struct.unpack("!I", data[pos + 4 : pos + 8])[0]
                            public_ip = socket.inet_ntoa(struct.pack("!I", addr_int))
                            return public_ip, port

                # Move to next attribute (padded to 4 bytes)
                pos += (attr_len + 3) & ~3

            return None
        except Exception:
            return None
        finally:
            sock.close()

    def close(self):
        """Cleanup all mapped ports on shutdown."""
        with self._lock:
            for port, proto in list(self.mapped_ports):
                self.delete_port_mapping(port, proto)


nat_manager = NATManager()
