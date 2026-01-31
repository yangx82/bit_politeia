from fastapi import FastAPI
import sys
print("\n[!!!] STARTING main.py from " + __file__ + " [!!!]\n", flush=True)
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import router as api_router
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:    %(name)s - %(message)s"
)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

app = FastAPI(title="Bit Politeia Agent Node", version="0.1.0")

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
