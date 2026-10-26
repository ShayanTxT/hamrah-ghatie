"""تست استریم پاسخ مدل با یک llama-server قلابی روی 127.0.0.1 (بدون مدل واقعی)."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from hamrah.core.llama import LlamaEngine
from hamrah.core.sysinfo import PROFILES, SystemInfo, recommend


class FakeLlamaHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        assert payload.get("stream") is True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for token in ["سلام", "! ", "من ", "آفلاین", " هستم."]:
            chunk = json.dumps({"content": token, "stop": False}, ensure_ascii=False)
            self.wfile.write(f"data: {chunk}\n\n".encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b'data: {"content":"","stop":true}\n\n')
        self.wfile.flush()


def test_streaming_and_prompt(db, settings, paths):
    server = HTTPServer(("127.0.0.1", 0), FakeLlamaHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        settings["llama_port"] = port
        engine = LlamaEngine(db, settings, paths)
        assert engine.is_running()
        tokens: list[str] = []
        answer = engine.stream_chat(
            [{"role": "user", "content": "تو کیستی؟"}],
            on_token=tokens.append,
            context="[1] منبع تست",
        )
        assert answer == "سلام! من آفلاین هستم."
        assert "".join(tokens) == answer
        assert "<|im_start|>system" in engine.build_prompt([])
    finally:
        server.shutdown()
        server.server_close()


def test_chat_history(db, settings, paths):
    engine = LlamaEngine(db, settings, paths)
    chat_id = engine.create_chat("تست", "model.gguf")
    engine.add_message(chat_id, "user", "سلام")
    engine.add_message(chat_id, "assistant", "درود", "منبع ۱")
    msgs = engine.messages(chat_id)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[-1].sources == "منبع ۱"
    assert engine.list_chats()[0]["n"] == 2
    engine.delete_chat(chat_id)
    assert engine.messages(chat_id) == []


def test_model_recommendation():
    assert PROFILES["light"].size_gb < PROFILES["balanced"].size_gb < PROFILES["quality"].size_gb
    weak = SystemInfo(ram_gb=8, vram_gb=0, cores=4, gpu="")
    assert recommend(weak)["primary"]["key"] == "light"
    strong = SystemInfo(ram_gb=32, vram_gb=8, cores=12, gpu="RTX", has_nvidia=True)
    rec = recommend(strong)
    assert rec["primary"]["key"] == "balanced"
    assert "گیگ" in rec["note"] or "32" in rec["note"]
    assert any(a["key"] == "quality" for a in rec["alternatives"])
