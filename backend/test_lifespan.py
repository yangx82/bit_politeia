import asyncio

from app.services.p2p_server import app, lifespan


async def test_startup():
    print("Testing Lifespan Startup...")
    try:
        async with lifespan(app):
            print("Lifespan started successfully.")
    except Exception as e:
        print(f"Caught exception during lifespan: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_startup())
