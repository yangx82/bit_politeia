# Bootstrap Server LAN Connection Troubleshooting Guide

## Problem: LAN Node Shows "bootstrap topology fetch error"

### Quick Diagnosis

Run the diagnostic script on your **LAN node** (the one that's failing):

```bash
cd backend
python test_bootstrap_connection.py http://YOUR_BOOTSTRAP_IP:8000
```

Replace `YOUR_BOOTSTRAP_IP` with the actual IP address of your bootstrap server.

---

## Common Issues and Solutions

### 1. Server Not Bound to Network Interface

**Symptom**: Local node works, LAN node fails

**Cause**: Bootstrap server is bound to `127.0.0.1` instead of `0.0.0.0`

**Solution**: Verify `run_bootstrap.py` uses `host="0.0.0.0"`:

```python
uvicorn.run(
    app,
    host="0.0.0.0",  # Must be 0.0.0.0, NOT 127.0.0.1
    port=8000,
    log_level="info"
)
```

**Verification**: On the bootstrap server machine, run:
```bash
netstat -an | findstr :8000
```

You should see: `0.0.0.0:8000` or `*:8000`, NOT `127.0.0.1:8000`

---

### 2. Firewall Blocking Port 8000

**Symptom**: TCP connection test fails in diagnostic script

**Solution (Windows)**:
```powershell
# Allow inbound on port 8000
netsh advfirewall firewall add rule name="Bootstrap Server" dir=in action=allow protocol=TCP localport=8000

# Verify rule was added
netsh advfirewall firewall show rule name="Bootstrap Server"
```

**Solution (Linux)**:
```bash
# UFW
sudo ufw allow 8000/tcp

# iptables
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
```

---

### 3. Incorrect Bootstrap URL Configuration

**Symptom**: DNS resolution fails or wrong IP

**Cause**: LAN node is configured with wrong bootstrap URL

**Solution**: On the LAN node, verify the bootstrap URL in frontend configuration:

1. Open frontend config page
2. Check "Bootstrap Server URL" field
3. Should be: `http://192.168.X.X:8000` (actual LAN IP)
4. Should NOT be: `http://localhost:8000` or `http://127.0.0.1:8000`

**Find Bootstrap Server IP**:
```bash
# Windows
ipconfig

# Linux/Mac
ifconfig
# or
ip addr show
```

Look for the IP in your LAN subnet (usually `192.168.x.x` or `10.x.x.x`)

---

### 4. Network Isolation / Different Subnets

**Symptom**: All tests fail, cannot ping bootstrap server

**Cause**: LAN node and bootstrap server are on different network segments

**Verification**:
```bash
# From LAN node, ping bootstrap server
ping 192.168.X.X
```

**Solution**:
- Ensure both machines are on the same WiFi/LAN network
- Check router settings for AP isolation (disable it)
- Verify no VPN is interfering

---

### 5. Antivirus/Security Software

**Symptom**: Intermittent failures or timeout errors

**Cause**: Antivirus blocking Python network connections

**Solution**:
- Temporarily disable antivirus and test
- Add Python.exe to antivirus whitelist
- Add exception for port 8000

---

## Step-by-Step Debugging Process

### On Bootstrap Server Machine:

1. **Verify server is running**:
   ```bash
   # You should see startup messages
   cd backend
   python run_bootstrap.py
   ```

2. **Test locally**:
   ```bash
   # In another terminal
   curl http://localhost:8000/
   # Should return: {"status":"running","service":"Bit-Politeia Bootstrap"}
   ```

3. **Get server's LAN IP**:
   ```bash
   ipconfig  # Windows
   # Look for IPv4 Address under your active network adapter
   ```

4. **Test from server using LAN IP**:
   ```bash
   curl http://YOUR_LAN_IP:8000/
   # Should work if firewall is configured correctly
   ```

### On LAN Node Machine:

1. **Verify network connectivity**:
   ```bash
   ping YOUR_BOOTSTRAP_IP
   # Should get replies
   ```

2. **Test TCP port**:
   ```bash
   # Windows
   Test-NetConnection -ComputerName YOUR_BOOTSTRAP_IP -Port 8000
   
   # Linux/Mac
   telnet YOUR_BOOTSTRAP_IP 8000
   # or
   nc -zv YOUR_BOOTSTRAP_IP 8000
   ```

3. **Test HTTP endpoint**:
   ```bash
   curl http://YOUR_BOOTSTRAP_IP:8000/
   ```

4. **Run full diagnostic**:
   ```bash
   cd backend
   python test_bootstrap_connection.py http://YOUR_BOOTSTRAP_IP:8000
   ```

5. **Check agent node logs**:
   - Look for the exact error message
   - Note the bootstrap URL being used
   - Check for timeout values

---

## Expected Diagnostic Output (Success)

```
======================================================================
Bootstrap Server Connection Diagnostic
======================================================================
Target URL: http://192.168.1.100:8000

✓ URL parsed successfully
  Host: 192.168.1.100
  Port: 8000

✓ DNS resolution successful
  192.168.1.100 -> 192.168.1.100

✓ TCP connection successful
  Port 8000 is open and reachable

✓ HTTP GET request successful
  Status: 200
  Response: {'status': 'running', 'service': 'Bit-Politeia Bootstrap'}

✓ Topology endpoint accessible
  Total nodes: 1
  Total groups: 1

======================================================================
✓ ALL TESTS PASSED - Bootstrap server is accessible
======================================================================
```

---

## Still Not Working?

If you've tried all the above and it still fails, please provide:

1. Output of the diagnostic script
2. Bootstrap server startup logs
3. LAN node error logs
4. Network topology (same WiFi? router model? VPN?)
5. Operating systems of both machines

This will help identify more specific issues.
