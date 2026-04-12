import asyncio
import logging
import os
import sys

# Add current directory to path so 'app' can be found
sys.path.append(os.getcwd())

from app.bus.events import OutboundMessage
from app.bus.queue import MessageBus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_queue_size():
    bus = MessageBus(maxsize=2)
    msg = OutboundMessage(channel="test", session_id="1", content="hello")

    await bus.publish_outbound(msg)
    await bus.publish_outbound(msg)

    logger.info("Current queue size: %d", bus.outbound_size)

    # This should block or we can check full()
    if bus.outbound.full():
        logger.info("SUCCESS: Queue is full as expected (size=2)")
    else:
        logger.error("FAILURE: Queue should be full")


async def test_concurrent_dispatch():
    bus = MessageBus()
    results = []

    async def slow_subscriber(msg):
        logger.info("Slow subscriber started for %s", msg.content)
        await asyncio.sleep(1)
        results.append(f"slow_{msg.content}")
        logger.info("Slow subscriber finished for %s", msg.content)

    async def fast_subscriber(msg):
        logger.info("Fast subscriber started for %s", msg.content)
        results.append(f"fast_{msg.content}")
        logger.info("Fast subscriber finished for %s", msg.content)

    bus.subscribe_outbound("chat", slow_subscriber)
    bus.subscribe_outbound("chat", fast_subscriber)

    await bus.start()

    msg = OutboundMessage(channel="chat", session_id="1", content="msg1")
    await bus.publish_outbound(msg)

    # Wait a bit to let the fast one finish
    await asyncio.sleep(0.1)

    if "fast_msg1" in results and "slow_msg1" not in results:
        logger.info(
            "SUCCESS: Fast subscriber received message while slow one is still sleeping (Concurrent Dispatch Works!)"
        )
    else:
        logger.error(
            "FAILURE: Order was not as expected or fast subscriber was blocked. Results: %s",
            results,
        )

    await bus.stop()


async def main():
    logger.info("Running Queue Size Test...")
    await test_queue_size()

    logger.info("\nRunning Concurrent Dispatch Test...")
    await test_concurrent_dispatch()


if __name__ == "__main__":
    asyncio.run(main())
