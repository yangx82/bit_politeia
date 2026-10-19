import os
import sys
import site

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

# Critical for China: Set HuggingFace Mirror before any imports that might use it
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

import warnings
from fastapi import FastAPI

# Suppress pkg_resources deprecation warning from lark-oapi and other legacy packages
warnings.filterwarnings("ignore", category=UserWarning, module="lark_oapi")
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

import asyncio
import logging
from contextlib import asynccontextmanager

from app.utils.env_utils import load_dotenv_safe, sanitize_proxy_env

# Load env vars & sanitize proxy settings before any service imports
load_dotenv_safe()
sanitize_proxy_env()

from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import router as api_router

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.bus.queue import message_bus
from app.channels.feishu import FeishuChannel
from app.channels.telegram import TelegramChannel

logger = logging.getLogger(__name__)

telegram_channel = None
feishu_channel = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global telegram_channel, feishu_channel
    print("[*] Lifespan startup: initializing message bus and channels...", flush=True)

    # 0. Start Message Bus dispatcher
    await message_bus.start()
    print("[*] Message bus started.", flush=True)

    # 1. Telegram
    token = os.getenv("TELEGRAM_TOKEN")
    if token:
        logger.info("Initializing Telegram Channel...")
        telegram_channel = TelegramChannel(token=token, bus=message_bus)
        message_bus.subscribe_outbound("telegram", telegram_channel.send)
        asyncio.create_task(telegram_channel.start())
        print("[*] Telegram channel initialized.", flush=True)
    else:
        logger.warning("TELEGRAM_TOKEN not found, Telegram channel disabled.")

    # 2. Feishu
    feishu_app_id = os.getenv("FEISHU_APP_ID")
    feishu_app_secret = os.getenv("FEISHU_APP_SECRET")

    if feishu_app_id and feishu_app_secret:
        logger.info("Initializing Feishu Channel...")
        feishu_channel = FeishuChannel(
            app_id=feishu_app_id, app_secret=feishu_app_secret, bus=message_bus
        )
        message_bus.subscribe_outbound("feishu", feishu_channel.send)
        asyncio.create_task(feishu_channel.start())
        print("[*] Feishu channel initialized.", flush=True)
    else:
        logger.warning("FEISHU_APP_ID/SECRET not found, Feishu channel disabled.")

    # 3. Auto-configure Agent if .env exists
    from app.services.agent_service import agent_service

    env_config = agent_service.load_config_from_env()
    if env_config:
        agent_name = env_config.get("name", "Agent")
        logger.info("Found persisted configuration in .env, auto-configuring Agent...")
        # configure_agent is async
        asyncio.create_task(agent_service.configure_agent(**env_config))
        print(f"[*] Agent auto-configuration initiated for '{agent_name}'.", flush=True)

    # 4. Start Scheduler
    # Must be done after loop is running
    agent_service.start_scheduler()
    print("[*] Background scheduler started.", flush=True)
    print("\n" + "=" * 60, flush=True)
    print("  Bit Politeia Agent Node is READY and LISTENING", flush=True)
    print("  API Docs: http://0.0.0.0:8100/docs", flush=True)
    print("  Health:   http://0.0.0.0:8100/", flush=True)
    print("=" * 60 + "\n", flush=True)

    yield

    # Shutdown
    print("[*] Lifespan shutdown: stopping channels...", flush=True)
    if telegram_channel:
        await telegram_channel.stop()
    if feishu_channel:
        await feishu_channel.stop()
    print("[*] Backend shutdown complete.", flush=True)


# Ensure log directory exists (anchor to backend directory to avoid nested backend/backend/data/logs)
backend_base_dir = os.path.dirname(os.path.abspath(__file__))
log_dir = os.path.join(backend_base_dir, "data", "logs")
os.makedirs(log_dir, exist_ok=True)

# Configure logging
console_handler = logging.StreamHandler()
log_format = "%(asctime)s - %(levelname)s:    %(name)s - %(message)s"
console_handler.setFormatter(logging.Formatter(log_format))
handlers = [console_handler]

# Feature: Conditional Debug File Logging
ENABLE_DEBUG_LOG = os.getenv("ENABLE_DEBUG_LOGGING", "true").lower() == "true"
if ENABLE_DEBUG_LOG:
    file_handler = logging.FileHandler(os.path.join(log_dir, "p2p_network.log"), encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(log_format))

    # Optional filter based on DEBUG_MODULES
    debug_modules = os.getenv("DEBUG_MODULES", "")
    if debug_modules:
        allowed_modules = [m.strip() for m in debug_modules.split(",")]
        allowed_modules.append("p2p_network")  # Always allow P2P Network logs to this file

        class ModuleFilter(logging.Filter):
            def filter(self, record):
                return any(record.name.startswith(m) for m in allowed_modules)

        file_handler.addFilter(ModuleFilter())

    handlers.append(file_handler)

logging.basicConfig(level=logging.INFO, handlers=handlers)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

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
from app.api.gateway import router as gateway_router

app.include_router(gateway_router)


@app.get("/")
async def root():
    return {"message": "Agent Node is Running"}


if __name__ == "__main__":
    import uvicorn
    import os

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.join(backend_dir, "app")

    # Smart Reload Detection:
    # On WSL2 DrvFs mounts (/mnt/c, /mnt/d) or active sync disks (BaiduSyncdisk),
    # uvicorn's watchfiles reloader frequently deadlocks or freezes during inotify recursive scanning.
    # Default to False unless explicitly enabled via UVICORN_RELOAD=true
    is_wsl_mnt = sys.platform.startswith("linux") and os.path.abspath(__file__).startswith("/mnt/")
    default_reload = "false" if is_wsl_mnt else os.getenv("UVICORN_RELOAD", "false")
    reload_enabled = os.getenv("UVICORN_RELOAD", default_reload).lower() in ("true", "1", "yes")

    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8100"))

    print(f"[*] Launching Bit Politeia Node on http://{host}:{port} (reload={reload_enabled})...", flush=True)

    if reload_enabled:
        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            reload=True,
            app_dir=backend_dir,
            reload_dirs=[app_dir],
            reload_excludes=[
                "data",
                "data/*",
                "data/**",
                "backend/data",
                "backend/data/*",
                "backend/data/**",
                "*.csv",
                "*.json",
                "*.png",
                "*.jpg",
                "*.fig",
            ],
        )
    else:
        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=False,
            log_level="info",
        )

