from fastapi import FastAPI
import sys
print("\n[!!!] STARTING main.py from " + __file__ + " [!!!]\n", flush=True)
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import router as api_router
import logging
import os
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load env vars
load_dotenv()

from app.bus.queue import message_bus
from app.channels.telegram import TelegramChannel
from app.channels.feishu import FeishuChannel

logger = logging.getLogger(__name__)

telegram_channel = None
feishu_channel = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global telegram_channel, feishu_channel
    
    # 1. Telegram
    token = os.getenv("TELEGRAM_TOKEN")
    if token:
        logger.info("Initializing Telegram Channel...")
        telegram_channel = TelegramChannel(token=token, bus=message_bus)
        message_bus.subscribe_outbound("telegram", telegram_channel.send)
        asyncio.create_task(telegram_channel.start())
    else:
        logger.warning("TELEGRAM_TOKEN not found, Telegram channel disabled.")
        
    # 2. Feishu
    feishu_app_id = os.getenv("FEISHU_APP_ID")
    feishu_app_secret = os.getenv("FEISHU_APP_SECRET")
    
    if feishu_app_id and feishu_app_secret:
        logger.info("Initializing Feishu Channel...")
        feishu_channel = FeishuChannel(
            app_id=feishu_app_id, 
            app_secret=feishu_app_secret, 
            bus=message_bus
        )
        message_bus.subscribe_outbound("feishu", feishu_channel.send)
        asyncio.create_task(feishu_channel.start())
    else:
        logger.warning("FEISHU_APP_ID/SECRET not found, Feishu channel disabled.")
        
    # 3. Auto-configure Agent if .env exists
    from app.services.agent_service import agent_service
    env_config = agent_service.load_config_from_env()
    if env_config:
        logger.info("Found persisted configuration in .env, auto-configuring Agent...")
        # configure_agent is async
        asyncio.create_task(agent_service.configure_agent(**env_config))

    yield
    
    # Shutdown
    if telegram_channel:
        await telegram_channel.stop()
    if feishu_channel:
        await feishu_channel.stop()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:    %(name)s - %(message)s"
)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

app = FastAPI(title="Bit Politeia Agent Node", version="0.1.0", lifespan=lifespan)

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Agent Node is Running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
