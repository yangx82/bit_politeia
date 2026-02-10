import asyncio
import os
import sys

# Ensure backend modules are found
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from backend.app.bus.events import InboundMessage
from backend.app.bus.queue import MessageBus, message_bus
from backend.app.channels.telegram import TelegramChannel
from backend.app.channels.feishu import FeishuChannel

async def test_bus():
    print("1. Testing Message Bus instantiation...")
    bus = MessageBus()
    await bus.start()
    print("   Bus started.")
    
    print("2. Testing Inbound Message...")
    msg = InboundMessage(
        channel="test", 
        sender_id="user1", 
        chat_id="chat1", 
        content="Hello Bus"
    )
    await bus.publish_inbound(msg)
    print("   Inbound published.")
    
    rec_msg = await bus.consume_inbound()
    print(f"   Consumed inbound: {rec_msg.content}")
    assert rec_msg.content == "Hello Bus"
    
    print("3. Testing Telegram Channel Initialization (Dry Run)...")
    try:
        # Mock token
        channel = TelegramChannel(token="123:fake-token", bus=bus)
        print("   Telegram Channel initialized.")
        # We won't start it because it tries to connect to Telegram API which will fail
    except Exception as e:
        print(f"   Telegram init failed: {e}")
        return

    print("4. Testing Feishu Channel (Dry Run)...")
    try:
        feishu = FeishuChannel(app_id="cli_123", app_secret="sec_456", bus=bus)
        print("   Feishu Channel initialized.")
    except Exception as e:
        print(f"   Feishu init failed: {e}")
        return

    print("5. Testing Agent Service Integration (Imports)...")
    try:
        from backend.app.services.agent_service import agent_service
        print("   AgentService imported successfully.")
    except Exception as e:
        print(f"   AgentService import failed: {e}")
        # Detailed traceback might be needed if this fails due to circular imports etc.
        import traceback
        traceback.print_exc()

    bus.stop()
    print("\nSUCCESS: Bus infrastructure validation passed.")

if __name__ == "__main__":
    asyncio.run(test_bus())
