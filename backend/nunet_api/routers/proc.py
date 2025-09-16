from __future__ import annotations
import asyncio
import json
import os
import pty
import re
import subprocess
import tty
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..security import is_password_set, validate_token
from ..utils.pty_bridge import run_pty_ws

router = APIRouter()

HOME = Path.home()

# -------------------------
# Auth helpers (same pattern as we used for stream.py)
# -------------------------
def _extract_ws_token(ws: WebSocket) -> Optional[str]:
    token = ws.query_params.get("token")
    if token:
        return token
    auth = ws.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1]
    return None

async def _ws_auth_or_close(ws: WebSocket) -> bool:
    if not is_password_set():
        await ws.close(code=4401)
        return False
    token = _extract_ws_token(ws)
    if token and validate_token(token):
        await ws.accept()
        return True
    await ws.close(code=4401)
    return False


def _check_http_token(token: Optional[str]) -> None:
    if token is None:
        return
    if validate_token(token):
        return
    raise PermissionError("Invalid token")

# -------------------------
# DMS passphrase helper
# -------------------------
def _get_dms_passphrase() -> Optional[str]:
    try:
        key_id = subprocess.run(
            ["keyctl", "request", "user", "dms_passphrase"],
            text=True, capture_output=True, check=True
        ).stdout.strip()
        if not key_id:
            return None
        return subprocess.run(
            ["keyctl", "pipe", key_id],
            text=True, capture_output=True, check=True
        ).stdout.strip() or None
    except Exception:
        return None

# -------------------------
# Whitelist: define safe commands to expose
# -------------------------
@dataclass
class CmdSpec:
    argv: List[str]                         # Base argv (no user input)
    needs_passphrase: bool = False          # Auto-inject DMS_PASSPHRASE
    allow_args: bool = False                # Whether to allow user-supplied args
    arg_regex: Optional[str] = None         # If allow_args, validate each arg by regex
    allow_cwd_within_home: bool = True      # Restrict cwd to HOME (for safety)
    allowed_env_keys: Optional[set] = None  # Extra env keys user can set (whitelisted)

UPDATE_SCRIPT = r'''
set -euo pipefail
arch="$(uname -m | tr '[:upper:]' '[:lower:]')"
echo "Detected arch: $arch"
if echo "$arch" | grep -qi 'arm\|aarch'; then
  url="https://d.nunet.io/nunet-dms-arm64-latest.deb"
elif echo "$arch" | grep -qi 'x86_64\|amd64\|amd'; then
  url="https://d.nunet.io/nunet-dms-amd64-latest.deb"
else
  echo "Unsupported architecture: $arch" >&2; exit 2
fi
echo "Downloading $url ..."
wget -N "$url" -O dms-latest.deb
echo "Installing ..."
sudo apt install ./dms-latest.deb -y --allow-downgrades
echo "Cleaning up ..."
rm -f dms-latest.deb || true
echo "✅ Update complete."
'''

COMMAND_WHITELIST: Dict[str, CmdSpec] = {
    # mirror specific tasks (you also have dedicated routers; this is generic)
    "dms_init": CmdSpec(
        argv=["sudo", "-u", "ubuntu", "/home/ubuntu/menu/scripts/configure-dms.sh"],
        needs_passphrase=True,
    ),
    "dms_onboard": CmdSpec(
        argv=[str(HOME / "menu" / "scripts" / "onboard-max.sh")],
        needs_passphrase=True,
    ),
    "dms_update": CmdSpec(
        argv=["bash", "-lc", UPDATE_SCRIPT],
        needs_passphrase=False,
        allowed_env_keys={"DEBIAN_FRONTEND"},  # will default to noninteractive in your UI typically
    ),
    # tail DMS log (args allowed but constrained)
    "tail_dms": CmdSpec(
        argv=["sudo", "tail"],
        allow_args=True,
        arg_regex=r"^(-n|\-F|[0-9]+|/home/nunet/logs/nunet-dms\.log)$",
    ),
    # generic nunet invocations; restrict to subcommand + safe flags (example)
    # You can extend this with more precise arg_regex per flag if needed.
    "nunet_version": CmdSpec(argv=["nunet", "version"]),
}

# -------------------------
# Helpers to build the final argv/env/cwd safely
# -------------------------
def _build_argv(name: str, args: List[str]) -> List[str]:
    spec = COMMAND_WHITELIST.get(name)
    if not spec:
        raise ValueError(f"Command '{name}' is not allowed")
    argv = list(spec.argv)
    if args:
        if not spec.allow_args:
            raise ValueError(f"Command '{name}' does not accept user arguments")
        pattern = re.compile(spec.arg_regex or r"^[\w\-./:=]+$")
        for a in args:
            if not pattern.match(a):
                raise ValueError(f"Argument not allowed: {a!r}")
        argv.extend(args)
    return argv

def _build_env_for(name: str, user_env: Dict[str, str] | None) -> Dict[str, str]:
    spec = COMMAND_WHITELIST[name]
    env = os.environ.copy()
    if spec.needs_passphrase:
        pw = _get_dms_passphrase()
        if pw:
            env["DMS_PASSPHRASE"] = pw
    allowed = set(spec.allowed_env_keys or set())
    if user_env:
        for k, v in user_env.items():
            if k in allowed:
                env[k] = v
    return env

def _sanitize_cwd(name: str, cwd: Optional[str]) -> Optional[str]:
    spec = COMMAND_WHITELIST[name]
    if not cwd:
        return None
    p = Path(cwd).expanduser().resolve()
    if spec.allow_cwd_within_home and not str(p).startswith(str(HOME)):
        raise ValueError("cwd must be within the user's home directory")
    if not p.exists() or not p.is_dir():
        raise ValueError("cwd is not a directory")
    return str(p)

# -------------------------
# WebSocket: interactive PTY runner
# -------------------------
@router.websocket("/ws/{name}")
async def ws_exec(
    ws: WebSocket,
    name: str,
):
    """
    WebSocket interactive runner for whitelisted commands.

    Connect with query params:
      arg        : repeatable, e.g. ?arg=-n&arg=200&arg=/home/nunet/logs/nunet-dms.log
      cwd        : optional working directory (must be under $HOME by default)
      env        : optional JSON object, keys must be whitelisted per command
    Send input as:
      - plain text (treated as keystrokes)
      - or JSON: {"type":"stdin","data":"y\\n"}

    Server sends:
      {"type":"stdout","source":name,"data":"..."}
      {"type":"exit","code":0}
      {"type":"error","message":"..."}
    """
    if not await _ws_auth_or_close(ws):
        return

    # Parse query
    args = ws.query_params.getlist("arg")
    cwd = ws.query_params.get("cwd")
    env_json = ws.query_params.get("env")

    try:
        user_env = json.loads(env_json) if env_json else None
        argv = _build_argv(name, args)
        env = _build_env_for(name, user_env)
        cwd_s = _sanitize_cwd(name, cwd)
    except Exception as e:
        await ws.send_json({"type": "error", "message": str(e)})
        await ws.close(code=4400)
        return

    await run_pty_ws(ws, argv, env=env, cwd=cwd_s, label=name)

# -------------------------
# SSE: one-way PTY streaming
# -------------------------
async def _pty_to_sse(argv: List[str], env: Optional[Dict[str, str]], cwd: Optional[str], auto_stdin: Optional[str]):
    """
    Async generator that spawns a PTY, yields lines as SSE data frames.
    Sends a final 'event: exit' with the return code.
    """
    # Create PTY
    master_fd, slave_fd = pty.openpty()
    tty.setraw(master_fd)

    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        cwd=cwd, env=env, start_new_session=True
    )
    os.close(slave_fd)

    if auto_stdin:
        try:
            os.write(master_fd, auto_stdin.encode())
        except Exception:
            pass

    loop = asyncio.get_running_loop()
    buf = b""
    try:
        while True:
            chunk = await loop.run_in_executor(None, os.read, master_fd, 4096)
            if not chunk:
                # brief wait; if process is done, break
                await asyncio.sleep(0.05)
                if proc.returncode is not None:
                    break
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode(errors="ignore")
                yield f"data: {text}\n\n"
    finally:
        try:
            os.close(master_fd)
        except Exception:
            pass
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                proc.kill()
        # exit event
        code = proc.returncode if proc.returncode is not None else -1
        yield f"event: exit\ndata: {code}\n\n"

@router.get("/stream/{name}")
async def sse_exec(
    name: str,
    token: Optional[str] = None,
    arg: List[str] = Query(default=[]),            # repeatable
    cwd: Optional[str] = None,
    env: Optional[str] = None,                     # JSON {"KEY":"VALUE"}; only allowed keys applied
    stdin: Optional[str] = None,                   # optional one-shot stdin on start (e.g., "y\\n")
):
    """
    SSE (Server-Sent Events) one-way streaming of a whitelisted command under a PTY.
    WARNING: If the command expects additional input after start and you don't provide it,
    it may block. Use the WebSocket endpoint for fully interactive sessions.

    Server emits 'data: <line>' frames and a final 'event: exit' with the code.
    """
    try:
        _check_http_token(token)
    except PermissionError:
        return StreamingResponse(iter(["event: error\ndata: unauthorized\n\n"]), media_type="text/event-stream")

    try:
        user_env = json.loads(env) if env else None
        argv = _build_argv(name, arg)
        env_full = _build_env_for(name, user_env)
        cwd_s = _sanitize_cwd(name, cwd)
    except Exception as e:
        return StreamingResponse(iter([f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"]), media_type="text/event-stream")

    return StreamingResponse(
        _pty_to_sse(argv, env_full, cwd_s, auto_stdin=stdin),
        media_type="text/event-stream"
    )
