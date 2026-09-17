import os
import sys
import time
import json
import socket
import urllib.request
import urllib.error
import subprocess

print("=== STARTING SECURITY VERIFICATION TESTS ===\n")

env = os.environ.copy()
env["PYTHONPATH"] = os.path.abspath("backend")

# Start uvicorn server process on port 8008
server_process = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8008"],
    cwd=os.path.abspath("backend"),
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

# Wait for server readiness
ready = False
for _ in range(30):
    try:
        s = socket.create_connection(("127.0.0.1", 8008), timeout=1)
        s.close()
        ready = True
        break
    except OSError:
        time.sleep(0.5)

if not ready:
    stdout, stderr = server_process.communicate()
    print("Server failed to start!")
    print("STDOUT:", stdout.decode())
    print("STDERR:", stderr.decode())
    sys.exit(1)

print("Server is listening on http://127.0.0.1:8008\n")

base_url = "http://127.0.0.1:8008"
auth_token = None

try:
    # -------------------------------------------------------------
    # TEST 1: Unauthenticated Request
    # -------------------------------------------------------------
    print("--- TEST 1: Unauthenticated Request ---")
    req = urllib.request.Request(f"{base_url}/api/vehicles", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Status Code: {resp.status}")
            print(f"Response: {resp.read().decode('utf-8')}")
    except urllib.error.HTTPError as e:
        print(f"Status Code: {e.code}")
        print(f"Response Body: {e.read().decode('utf-8')}")
    print()

    # -------------------------------------------------------------
    # TEST 2: Invalid Login Request
    # -------------------------------------------------------------
    print("--- TEST 2: Invalid Login Request ---")
    bad_login_data = json.dumps({"username": "admin", "password": "wrongpassword"}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/auth/login",
        data=bad_login_data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Status Code: {resp.status}")
            print(f"Response: {resp.read().decode('utf-8')}")
    except urllib.error.HTTPError as e:
        print(f"Status Code: {e.code}")
        print(f"Response Body: {e.read().decode('utf-8')}")
    print()

    # -------------------------------------------------------------
    # TEST 3: Valid Login Request
    # -------------------------------------------------------------
    print("--- TEST 3: Valid Login Request ---")
    valid_login_data = json.dumps({"username": "admin", "password": "admin123"}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/auth/login",
        data=valid_login_data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Status Code: {resp.status}")
            body = resp.read().decode("utf-8")
            print(f"Response: {body}")
            parsed = json.loads(body)
            auth_token = parsed.get("access_token")
    except urllib.error.HTTPError as e:
        print(f"Status Code: {e.code}")
        print(f"Response Body: {e.read().decode('utf-8')}")
    print()

    # -------------------------------------------------------------
    # TEST 4: Authenticated Request
    # -------------------------------------------------------------
    print("--- TEST 4: Authenticated Request ---")
    if auth_token:
        req = urllib.request.Request(
            f"{base_url}/api/vehicles",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {auth_token}"
            }
        )
        try:
            with urllib.request.urlopen(req) as resp:
                print(f"Status Code: {resp.status}")
                body = resp.read().decode("utf-8")
                print(f"Response (Preview): {body[:200]}...")
        except urllib.error.HTTPError as e:
            print(f"Status Code: {e.code}")
            print(f"Response Body: {e.read().decode('utf-8')}")
    else:
        print("ERROR: Token not acquired from Test 3.")
    print()

    # -------------------------------------------------------------
    # TEST 5: CORS Restriction Check
    # -------------------------------------------------------------
    print("--- TEST 5: CORS Restriction Check ---")
    # 5a. Allowed origin preflight
    print("[5a] Testing Allowed Origin (http://localhost:3000)...")
    req = urllib.request.Request(
        f"{base_url}/api/vehicles",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        },
        method="OPTIONS"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Status Code: {resp.status}")
            print(f"Access-Control-Allow-Origin Header: {resp.headers.get('Access-Control-Allow-Origin')}")
    except urllib.error.HTTPError as e:
        print(f"Status Code: {e.code}")

    # 5b. Unallowed origin preflight
    print("\n[5b] Testing Unallowed Origin (http://unauthorized-attacker.com)...")
    req = urllib.request.Request(
        f"{base_url}/api/vehicles",
        headers={
            "Origin": "http://unauthorized-attacker.com",
            "Access-Control-Request-Method": "GET"
        },
        method="OPTIONS"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Status Code: {resp.status}")
            print(f"Access-Control-Allow-Origin Header: {resp.headers.get('Access-Control-Allow-Origin')}")
    except urllib.error.HTTPError as e:
        print(f"Status Code: {e.code}")
        print(f"Response Body: {e.read().decode('utf-8')}")
    print()

finally:
    print("Terminating test server...")
    server_process.terminate()
    try:
        server_process.wait(timeout=3)
    except Exception:
        server_process.kill()
    print("Test server terminated.")

print("\n=== ALL VERIFICATION TESTS COMPLETED ===")