import httpx


def check_server():
    print("Testing Bootstrap Server Endpoints...")
    print("--------------------------------------")

    # Disable SSL verify for local testing
    client = httpx.Client(verify=False)

    base_url = "http://127.0.0.1:8000"

    # Test Root
    try:
        r = client.get(f"{base_url}/")
        print(f"GET / -> Status: {r.status_code}, Body: {r.text}")
    except Exception as e:
        print(f"GET / -> Request Failed: {e}")

    # Test GET /nodes
    try:
        r = client.get(f"{base_url}/nodes")
        print(f"GET /nodes -> Status: {r.status_code}, Body: {r.text[:200]}...")
    except Exception as e:
        print(f"GET /nodes -> Request Failed: {e}")

    # Test DELETE /nodes/dummy_id
    try:
        r = client.delete(f"{base_url}/nodes/dummy_id")
        print(f"DELETE /nodes/dummy_id -> Status: {r.status_code}, Body: {r.text}")
    except Exception as e:
        print(f"DELETE /nodes/dummy_id -> Request Failed: {e}")


if __name__ == "__main__":
    check_server()
