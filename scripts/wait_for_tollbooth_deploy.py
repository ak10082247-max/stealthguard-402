import time
import urllib.request
import json
import sys

URL = "https://x402-agent-tollbooth.onrender.com/health"
print(f"Monitoring {URL} for version 2.1.0 deployment...")

start_time = time.time()
while time.time() - start_time < 180:
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "DeployWatcher/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode("utf-8")
            data = json.loads(body)
            # Check if version is 2.1.0
            version = data.get("version") or data.get("serverInfo", {}).get("version")
            print(f"[{int(time.time() - start_time)}s] Live version: {version}")
            if version == "2.1.0":
                print("SUCCESS: x402-agent-tollbooth version 2.1.0 is live on Render!")
                sys.exit(0)
    except Exception as e:
        print(f"[{int(time.time() - start_time)}s] Error: {e}")
    time.sleep(10)

print("Timed out waiting for deploy after 180 seconds.")
sys.exit(1)
