import asyncio
import logging
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.p2p_community.nat_traversal import nat_manager


async def test_stun():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("STUN_TEST")

    logger.info("Starting STUN test...")

    # Perform STUN discovery for a dummy port
    endpoint = nat_manager.get_stun_endpoint(8000)

    if endpoint:
        ip, port = endpoint
        logger.info(f"SUCCESS: Discovered public endpoint: {ip}:{port}")
    else:
        logger.error("FAILURE: STUN discovery failed.")


if __name__ == "__main__":
    asyncio.run(test_stun())
