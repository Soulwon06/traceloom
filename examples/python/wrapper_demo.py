"""Example: a script with no TraceLoom import, designed to run via `traceloom run`.

Notice there is no `import traceloom` and no `traceloom.init()` anywhere below.
This script is meant to demonstrate the `traceloom run` wrapper, which activates
TraceLoom in the wrapped process before user code runs. The wrapper sets
PYTHONPATH so Python's site startup imports a TraceLoom bootstrap module,
which in turn calls traceloom.init() using TRACELOOM_* env vars.

Run it like this (server must be running at http://localhost:5110):

    traceloom run examples/python/wrapper_demo.py

Or against a different server:

    traceloom run --server http://localhost:5110 examples/python/wrapper_demo.py

Or capture only specific hosts:

    traceloom run --capture-host httpbin.org examples/python/wrapper_demo.py

`traceloom run` detects `.py` files and runs them with the current Python.
For console scripts (uvicorn, pytest, gunicorn) just pass the command directly:

    traceloom run uvicorn app:app
    traceloom run pytest tests/

After it finishes, browse captured traffic at http://localhost:5110.
"""

import httpx
import requests


def fetch_with_requests() -> None:
    print("--- requests ---")
    resp = requests.get("https://httpbin.org/get", params={"client": "requests"})
    print(f"GET  /get          -> {resp.status_code}")

    resp = requests.post(
        "https://httpbin.org/post",
        json={"hello": "from requests", "via": "traceloom run"},
    )
    print(f"POST /post         -> {resp.status_code}")

    resp = requests.get(
        "https://httpbin.org/headers",
        headers={"Authorization": "Bearer sk-redacted-by-default"},
    )
    print(f"GET  /headers      -> {resp.status_code}  (Authorization redacted)")


def fetch_with_httpx() -> None:
    print("--- httpx ---")
    with httpx.Client(timeout=10) as client:
        resp = client.get("https://httpbin.org/get", params={"client": "httpx"})
        print(f"GET  /get          -> {resp.status_code}")

        resp = client.put("https://httpbin.org/put", json={"updated": True})
        print(f"PUT  /put          -> {resp.status_code}")


def status_codes() -> None:
    print("--- status codes ---")
    for code in [200, 201, 404, 418, 500]:
        resp = requests.get(f"https://httpbin.org/status/{code}")
        print(f"GET  /status/{code:<3}  -> {resp.status_code}")


def main() -> None:
    fetch_with_requests()
    fetch_with_httpx()
    status_codes()

    print("\nDone. Open http://localhost:5110 to browse captured requests.")


if __name__ == "__main__":
    main()
