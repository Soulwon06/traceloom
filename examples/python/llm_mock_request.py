"""Send one OpenAI-style chat completion request to a local mock server."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests


HOST = "127.0.0.1"
PORT = 8008
URL = f"http://{HOST}:{PORT}/v1/chat/completions"


class MockLLMHandler(BaseHTTPRequestHandler):
    """Handle the small subset of the OpenAI Chat Completions API we need."""

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        json.loads(self.rfile.read(content_length))

        response_body = {
            "id": "chatcmpl-demo123",
            "object": "chat.completion",
            "model": "gpt-demo",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "你好！这是一个模拟的 LLM 回复。",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 12,
                "total_tokens": 32,
            },
        }
        encoded_response = json.dumps(response_body, ensure_ascii=False).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded_response)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded_response)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the example output focused on the client response."""


def main() -> None:
    server = HTTPServer((HOST, PORT), MockLLMHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    request_body = {
        "model": "gpt-demo",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "请简单解释什么是 TCP 三次握手。"},
        ],
    }

    try:
        response = requests.post(URL, json=request_body, timeout=10)
        response_json = response.json()
        print(f"HTTP 状态码: {response.status_code}")
        print("返回的 JSON:")
        print(json.dumps(response_json, ensure_ascii=False, indent=2))
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)


if __name__ == "__main__":
    main()
