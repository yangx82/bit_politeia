import sqlite3
import threading

import uvicorn
from fastapi import FastAPI

app = FastAPI()


@app.on_event("startup")
def startup_event():
    print("FastAPI Startup Event Fired!")
    try:
        print("Attempting to connect to SQLite...")
        conn = sqlite3.connect("bootstrap_test.db", timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY)")
        conn.close()
        print("SQLite connection successful!")
    except Exception as e:
        print(f"SQLite Connection Failed: {e}")


@app.get("/")
def read_root():
    return {"Hello": "World"}


if __name__ == "__main__":
    print(f"Starting minimal Uvicorn server on thread {threading.get_ident()}...")
    uvicorn.run(app, host="0.0.0.0", port=8088, log_level="debug")
