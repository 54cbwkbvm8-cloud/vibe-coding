"""测试专用本地 DeepSeek 兼容服务器；不会访问外网。"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time


RESPONSE_MARKDOWN = """## 思路
先把问题拆成已知条件和目标，再选择合适的方法。

## 步骤
1. 识别变量和关系。
2. 按顺序推导。

```python
value = 2 + 3
print(value)
```

公式：$x^2 + y^2 = z^2$

## 答案
结果是 5。
"""


class MockDeepSeekServer:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
        )

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def recorded_requests(self) -> list[dict]:
        with self._lock:
            return [request.copy() for request in self.requests]

    def _handler_class(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:
                if self.path != "/chat/completions":
                    self._send_json(404, {"error": {"message": "not found"}})
                    return

                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                with owner._lock:
                    owner.requests.append(payload)

                authorization = self.headers.get("Authorization", "")
                token = authorization.removeprefix("Bearer ").strip()
                if token == "fake-401":
                    self._send_json(
                        401,
                        {"error": {"message": "mock authentication failed"}},
                    )
                    return
                if token == "fake-402":
                    self._send_json(
                        402,
                        {"error": {"message": "mock insufficient balance"}},
                    )
                    return
                if token == "fake-429":
                    self._send_json(
                        429,
                        {"error": {"message": "mock rate limit"}},
                    )
                    return
                if token == "fake-timeout":
                    time.sleep(3)
                    self._send_json(
                        200,
                        {"error": {"message": "late response"}},
                    )
                    return
                if token not in {"fake-ok", "fake-stop"}:
                    self._send_json(
                        401,
                        {"error": {"message": "fake key rejected"}},
                    )
                    return

                self._stream_markdown(slow=token == "fake-stop")

            def log_message(self, format, *args) -> None:
                return

            def _send_json(self, status: int, value: dict) -> None:
                body = json.dumps(value, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (
                    BrokenPipeError,
                    ConnectionResetError,
                    ConnectionAbortedError,
                    OSError,
                ):
                    return

            def _stream_markdown(self, slow: bool) -> None:
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "text/event-stream; charset=utf-8",
                )
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                chunks = [
                    RESPONSE_MARKDOWN[index : index + 10]
                    for index in range(0, len(RESPONSE_MARKDOWN), 10)
                ]
                try:
                    for chunk in chunks:
                        data = {
                            "id": "mock-completion",
                            "object": "chat.completion.chunk",
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": chunk},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        encoded = json.dumps(data, ensure_ascii=False)
                        self.wfile.write(f"data: {encoded}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        time.sleep(0.08 if slow else 0.025)
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return

        return Handler
