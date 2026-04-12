#!/usr/bin/env python
"""
Bootstrap Server Connection Diagnostic Tool
Run this on the LAN node to diagnose connectivity issues.
"""

import socket
import sys

import httpx


def test_bootstrap_connection(bootstrap_url: str):
    """Test connection to bootstrap server with detailed diagnostics."""

    print("=" * 70)
    print("Bootstrap Server Connection Diagnostic")
    print("=" * 70)
    print(f"Target URL: {bootstrap_url}")
    print()

    # Step 1: Parse URL
    try:
        from urllib.parse import urlparse

        parsed = urlparse(bootstrap_url)
        host = parsed.hostname
        port = parsed.port or 8000
        print("✓ URL parsed successfully")
        print(f"  Host: {host}")
        print(f"  Port: {port}")
        print()
    except Exception as e:
        print(f"✗ Failed to parse URL: {e}")
        return False

    # Step 2: DNS Resolution
    try:
        ip = socket.gethostbyname(host)
        print("✓ DNS resolution successful")
        print(f"  {host} -> {ip}")
        print()
    except Exception as e:
        print(f"✗ DNS resolution failed: {e}")
        print(f"  Suggestion: Check if '{host}' is the correct hostname/IP")
        return False

    # Step 3: TCP Connection Test
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((ip, port))
        sock.close()

        if result == 0:
            print("✓ TCP connection successful")
            print(f"  Port {port} is open and reachable")
            print()
        else:
            print(f"✗ TCP connection failed (error code: {result})")
            print("  Suggestions:")
            print("    1. Check if bootstrap server is running")
            print("    2. Check firewall rules on server machine")
            print("    3. Verify server is bound to 0.0.0.0, not 127.0.0.1")
            return False
    except Exception as e:
        print(f"✗ TCP connection test failed: {e}")
        return False

    # Step 4: HTTP GET Test
    try:
        client = httpx.Client(timeout=15.0)
        resp = client.get(f"{bootstrap_url}/")

        if resp.status_code == 200:
            print("✓ HTTP GET request successful")
            print(f"  Status: {resp.status_code}")
            print(f"  Response: {resp.json()}")
            print()
        else:
            print(f"✗ HTTP request failed with status {resp.status_code}")
            return False
    except httpx.ConnectError as e:
        print(f"✗ HTTP connection error: {e}")
        print("  Suggestion: Server may not be listening on the correct interface")
        return False
    except httpx.TimeoutException:
        print("✗ HTTP request timed out")
        print("  Suggestion: Network latency too high or server overloaded")
        return False
    except Exception as e:
        print(f"✗ HTTP request failed: {e}")
        return False

    # Step 5: Topology Endpoint Test
    try:
        resp = client.get(f"{bootstrap_url}/topology")

        if resp.status_code == 200:
            data = resp.json()
            node_count = data.get("stats", {}).get("total_nodes", 0)
            group_count = data.get("stats", {}).get("total_groups", 0)

            print("✓ Topology endpoint accessible")
            print(f"  Total nodes: {node_count}")
            print(f"  Total groups: {group_count}")
            print()
        else:
            print(f"✗ Topology endpoint returned status {resp.status_code}")
            return False
    except Exception as e:
        print(f"✗ Topology endpoint test failed: {e}")
        return False

    print("=" * 70)
    print("✓ ALL TESTS PASSED - Bootstrap server is accessible")
    print("=" * 70)
    return True


if __name__ == "__main__":
    # Default to localhost, or accept command line argument
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        print("Usage: python test_bootstrap_connection.py <bootstrap_url>")
        print("Example: python test_bootstrap_connection.py http://192.168.1.100:8000")
        print()
        url = input("Enter bootstrap server URL (or press Enter for localhost:8000): ").strip()
        if not url:
            url = "http://localhost:8000"

    success = test_bootstrap_connection(url)
    sys.exit(0 if success else 1)
