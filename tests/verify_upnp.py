
import asyncio
import logging
import sys
import os

# Ensure backend module is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(project_root, 'backend'))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from app.p2p_community.nat_traversal import nat_manager

def main():
    logger.info("Starting UPnP Verification...")
    
    # 1. Discover Gateway
    if not nat_manager.discover_gateway():
        logger.error("FAILED: No UPnP Gateway found.")
        return

    logger.info(f"SUCCESS: Found Gateway '{nat_manager.device.friendly_name}'")

    # 2. Get External IP
    external_ip = nat_manager.get_external_ip()
    if external_ip:
        logger.info(f"SUCCESS: External IP is {external_ip}")
    else:
        logger.warning("WARNING: Could not fetch External IP.")

    # 3. Add Port Mapping
    test_port = 18000
    logger.info(f"Attempting to map external port {test_port} to internal...")
    
    if nat_manager.add_port_mapping(test_port, test_port, "TCP", "BitPoliteia Verification"):
        logger.info(f"SUCCESS: Mapped TCP port {test_port}")
    else:
        logger.error("FAILED: Port mapping failed.")
        return

    # 4. Clean up
    logger.info("Cleaning up...")
    if nat_manager.delete_port_mapping(test_port, "TCP"):
        logger.info("SUCCESS: Deleted port mapping.")
    else:
        logger.error("FAILED: Could not delete port mapping.")

if __name__ == "__main__":
    main()
