# nunet_api/app/utils/pty_bridge.py
from __future__ import annotations
import asyncio
import json
import os
import pty
import signal
import tty
from typing import Dict, List, Optional
from fastapi import WebSocket
import contextlib

async def _read_pty(master_fd: int, ws: WebSocket, label: str = "proc"):
    loop = asyncio.get_running_loop()
    try:
        while True:
            # read up to 4096 bytes without blocking
            data: bytes = await loop.run_in_executor(None, os.read, master_fd, 4096)
            if not data:
                await asyncio.sleep(0.03)
                continue
            # send as text (keep raw bytes printable; UTF-8 fallback)
            try:
                await ws.send_json({"type": "stdout", "source": label, "data": data.decode(errors="ignore")})
            except Exception:
                break
    except Exception:
        # connection might be closed
        pass

async def _write_pty(master_fd: int, ws: WebSocket):
    try:
        while True:
            msg = await ws.receive_text()
            # support raw text as stdin, and also a small JSON protocol {type:"stdin", data:"y\n"}
            try:
                obj = json.loads(msg)
                if isinstance(obj, dict) and obj.get("type") == "stdin":
                    payload = obj.get("data", "")
                else:
                    payload = msg
            except Exception:
                payload = msg
            os.write(master_fd, payload.encode())
    except Exception:
        # client closed or error: stop writing
        pass

async def run_pty_ws(
    ws: WebSocket,
    argv: List[str],
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[str] = None,
    label: str = "proc",
):
    """
    Bridge a subprocess with a pseudo-TTY to a WebSocket.
    - Sends: {"type":"stdout","source":label,"data":"..."}
    - On exit: {"type":"exit","code":int}
    - Receives stdin: either plain text (treated as keystrokes) or {"type":"stdin","data":"..."}
    """
    # create PTY
    master_fd, slave_fd = pty.openpty()
    tty.setraw(master_fd)

    # start subprocess attached to the PTY
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=cwd,
        env=env,
        start_new_session=True,  # own process group for signals
    )

    # close slave in parent
    os.close(slave_fd)

    # pump data both ways
    reader = asyncio.create_task(_read_pty(master_fd, ws, label=label))
    writer = asyncio.create_task(_write_pty(master_fd, ws))

    # wait for process to finish
    return_code = await proc.wait()

    # cleanup tasks
    for t in (reader, writer):
        if not t.done():
            t.cancel()
            with contextlib.suppress(Exception):
                await t

    # close master fd
    try:
        os.close(master_fd)
    except Exception:
        pass

    # notify client
    try:
        await ws.send_json({"type": "exit", "code": return_code})
    except Exception:
        pass

    return return_code
