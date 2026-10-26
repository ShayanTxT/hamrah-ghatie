"""مرحلهٔ ۴ — اجرای مدل GGUF با llama.cpp بهصورت کاملاً محلی.

فقط ارتباط loopback (127.0.0.1) با ``llama-server.exe`` برقرار میشود؛ این
ارتباط توسط NetworkGuard با هدف ``LOCAL_AI`` مجاز شمرده میشود و هرگز به
اینترنت نمیرود. پاسخها بهصورت SSE کلمهبهکلمه (stream) دریافت میشوند.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .db import Database
from .errors import AppError
from .http import HttpClient
from .netpolicy import NetworkGuard, Purpose
from .persian import truncate

DEFAULT_SYSTEM = (
    "تو «همراه قطعی» هستی، یک دستیار آفلاین فارسیزبان که روی کامپیوتر کاربر و بدون اینترنت اجرا میشوی. "
    "پاسخها را به فارسی روان، دقیق و کوتاه بده. اگر پاسخی را نمیدانی صادقانه بگو نمیدانم. "
    "هرگز وانمود نکن که به اینترنت دسترسی داری."
)

PROMPT_START = "<|im_start|>"
PROMPT_END = "<|im_end|>"


@dataclass
class ChatMessage:
    id: int
    chat_id: int
    role: str
    content: str
    sources: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "role": self.role, "content": self.content,
                "sources": self.sources}


class LlamaEngine:
    def __init__(
        self,
        db: Database,
        cfg: dict[str, Any],
        paths: Any,
        *,
        guard: NetworkGuard | None = None,
    ) -> None:
        self.db = db
        self.cfg = cfg
        self.paths = paths
        self.guard = guard or NetworkGuard()
        self.http = HttpClient(self.guard)
        self.port = int(cfg.get("llama_port", 18081))
        self.process: subprocess.Popen | None = None
        self.model_path: Path | None = None
        self._lock = threading.Lock()
        self._log_handle: Any = None

    # ---------- پیدا کردن فایلها ----------
    def server_path(self) -> Path | None:
        local = self.paths.bin_dir / ("llama-server.exe" if os.name == "nt" else "llama-server")
        if local.is_file():
            return local
        found = shutil.which("llama-server")
        return Path(found) if found else None

    def models(self) -> list[Path]:
        return sorted(self.paths.models.glob("*.gguf"))

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # ---------- اجرا ----------
    def is_running(self) -> bool:
        try:
            with self.http.open(self.base_url + "/health", Purpose.LOCAL_AI, timeout=1.5) as resp:
                return getattr(resp, "status", 200) == 200
        except Exception:
            return False

    def start(self, model: Path | None = None, *, gpu_layers: int | None = None,
              ctx: int | None = None, timeout: float = 120.0) -> dict[str, Any]:
        """شروع llama-server. خطاها با پیام فارسی برگردانده میشوند."""
        if self.is_running():
            return {"ok": True, "already": True, "model": str(self.model_path or "")}
        server = self.server_path()
        if not server:
            raise AppError(
                "فایل llama-server.exe پیدا نشد. آن را در پوشهٔ data/bin کنار برنامه قرار بده "
                "(راهنمای README، بخش «فایلهایی که قبل از قطعی دانلود کنی»).",
                code="llama_missing",
            )
        model_path = Path(model) if model else (self.models()[0] if self.models() else None)
        if not model_path or not model_path.is_file():
            raise AppError(
                "هیچ مدل GGUF در پوشهٔ data/models پیدا نشد. فایل مدل را از فلش وارد کن.",
                code="model_missing",
            )
        self.model_path = model_path
        profile = self.cfg.get("_model_profile") or {}
        ngl = int(gpu_layers if gpu_layers is not None else self.cfg.get("llama_gpu_layers", -1))
        if ngl < 0:
            from .sysinfo import detect, recommend
            rec = recommend(detect())
            ngl = int(rec["gpu_layers"])
        ctx_size = int(ctx or profile.get("ctx") or self.cfg.get("llama_ctx", 4096))
        threads = int(self.cfg.get("llama_threads", 0)) or max(2, min(8, (os.cpu_count() or 4) // 2))

        cmd = [
            str(server), "-m", str(model_path),
            "--host", "127.0.0.1", "--port", str(self.port),
            "-c", str(ctx_size), "-ngl", str(ngl), "-t", str(threads),
        ]
        log_path = self.paths.logs / "llama.log"
        self._log_handle = log_path.open("ab", buffering=0)
        kwargs: dict[str, Any] = {
            "stdout": self._log_handle,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        try:
            self.process = subprocess.Popen(cmd, **kwargs)
        except Exception as exc:
            raise AppError("اجرای مدل ممکن نشد. فایل llama-server.exe را بررسی کن.",
                           detail=str(exc), code="llama_start") from exc

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_running():
                return {"ok": True, "model": str(model_path), "gpu_layers": ngl, "ctx": ctx_size}
            if self.process.poll() is not None:
                tail = self._log_tail()
                raise AppError("مدل اجرا نشد و برنامهٔ llama-server بسته شد. " + tail,
                               detail=tail, code="llama_exit")
            time.sleep(0.7)
        self.stop()
        raise AppError(
            "مدل در زمان تعیینشده آماده نشد. شاید فایل مدل خیلی بزرگ است یا نسخهٔ CPU/CUDA اشتباه است.",
            code="llama_timeout",
        )

    def _log_tail(self, lines: int = 8) -> str:
        try:
            text = (self.paths.logs / "llama.log").read_text("utf-8", "ignore")
            tail = " | ".join(text.splitlines()[-lines:])
            return truncate(tail, 300)
        except Exception:
            return ""

    def stop(self) -> None:
        with self._lock:
            proc = self.process
            self.process = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self._log_handle:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None

    def __del__(self) -> None:  # pragma: no cover - بهترین تلاش هنگام خروج
        try:
            self.stop()
        except Exception:
            pass

    # ---------- ساخت prompt ----------
    @staticmethod
    def build_prompt(messages: list[dict[str, str]], *, system: str = DEFAULT_SYSTEM,
                     context: str = "") -> str:
        sys_text = system + ("\n\n" + context if context else "")
        parts = [f"{PROMPT_START}system\n{sys_text}{PROMPT_END}\n"]
        for msg in messages:
            role = msg.get("role", "user")
            if role not in ("user", "assistant"):
                continue
            parts.append(f"{PROMPT_START}{role}\n{msg.get('content', '')}{PROMPT_END}\n")
        parts.append(f"{PROMPT_START}assistant\n")
        return "".join(parts)

    def make_context(self, question: str, library: Any | None, *, limit: int = 3) -> tuple[str, list[str]]:
        """RAG اختیاری: چند سند مرتبط از کتابخانهٔ آفلاین + فهرست منابع."""
        if not library or not self.cfg.get("ai_use_library", True):
            return "", []
        try:
            hits = library.search(question, limit=limit)
        except Exception:
            return "", []
        if not hits:
            return "", []
        blocks, sources = [], []
        for i, hit in enumerate(hits, 1):
            blocks.append(f"[{i}] {hit.title} ({hit.source_label})\n{truncate(hit.content, 1200)}")
            sources.append(f"{i}. {hit.title} — {hit.source_label}")
        context = (
            "از منابع آفلاین زیر برای پاسخ استفاده کن و شمارهٔ منبع را داخل متن ذکر کن "
            "مثلاً [1]. اگر منابع کافی نبودند، از دانش خودت استفاده کن ولی بگو که منبعی پیدا نشد.\n\n"
            + "\n\n".join(blocks)
        )
        return context, sources

    # ---------- چت استریمینگ ----------
    def stream_chat(
        self,
        messages: list[dict[str, str]],
        on_token: Callable[[str], None],
        *,
        context: str = "",
        stop_event: threading.Event | None = None,
        system: str = DEFAULT_SYSTEM,
        max_tokens: int | None = None,
    ) -> str:
        """ارسال گفتگو به llama-server و دریافت پاسخ کلمهبهکلمه."""
        if not self.is_running():
            raise AppError("مدل هنوز اجرا نشده است. از تب دستیار دکمهٔ «اجرای مدل» را بزن.")
        prompt = self.build_prompt(messages, system=system, context=context)
        payload = {
            "prompt": prompt,
            "stream": True,
            "n_predict": int(max_tokens or self.cfg.get("llama_max_tokens", 512)),
            "temperature": float(self.cfg.get("llama_temperature", 0.7)),
            "stop": [PROMPT_END, "<|im_start|>", "\nuser:", "\nUser:"],
            "cache_prompt": True,
        }
        url = self.base_url + "/completion"
        full: list[str] = []
        try:
            resp = self.http.open(
                url, Purpose.LOCAL_AI, method="POST",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
                timeout=300.0,
            )
            with resp:
                for raw_line in resp:
                    if stop_event and stop_event.is_set():
                        break
                    line = raw_line.decode("utf-8", "ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data in ("[DONE]", ""):
                        continue
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    token = obj.get("content", "")
                    if token:
                        full.append(token)
                        try:
                            on_token(token)
                        except Exception:
                            pass
                    if obj.get("stop"):
                        break
        except AppError:
            raise
        except Exception as exc:
            raise AppError("ارتباط با مدل محلی قطع شد. دوباره امتحان کن.",
                           detail=str(exc), code="llama_stream") from exc
        return "".join(full).strip()

    # ---------- تاریخچهٔ گفتگوها ----------
    def list_chats(self) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT c.*, (SELECT COUNT(*) FROM chat_messages m WHERE m.chat_id=c.id) AS n "
            "FROM chats c ORDER BY c.updated_at DESC"
        )
        return [dict(r) for r in rows]

    def create_chat(self, title: str = "گفتگوی جدید", model: str = "") -> int:
        now = time.time()
        return self.db.execute(
            "INSERT INTO chats(title, model, created_at, updated_at) VALUES(?, ?, ?, ?)",
            (title, model, now, now),
        )

    def add_message(self, chat_id: int, role: str, content: str, sources: str = "") -> int:
        now = time.time()
        msg_id = self.db.execute(
            "INSERT INTO chat_messages(chat_id, role, content, sources, ts) VALUES(?, ?, ?, ?, ?)",
            (chat_id, role, content, sources, now),
        )
        self.db.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
        return msg_id

    def messages(self, chat_id: int) -> list[ChatMessage]:
        rows = self.db.query("SELECT * FROM chat_messages WHERE chat_id = ? ORDER BY id", (chat_id,))
        return [ChatMessage(r["id"], r["chat_id"], r["role"], r["content"], r["sources"])
                for r in rows]

    def rename_chat(self, chat_id: int, title: str) -> None:
        self.db.execute("UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
                        (title[:80], time.time(), chat_id))

    def delete_chat(self, chat_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM chat_messages WHERE chat_id = ?", (chat_id,))
            conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
