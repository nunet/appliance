import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, AsyncGenerator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import StreamingResponse

from modules.ensemble_manager_v2 import EnsembleManagerV2
from ..security import is_password_set, validate_token



router = APIRouter()

DMS_LOG_PATH = Path("/home/nunet/logs/nunet-dms.log")

# ---------- auth helpers ----------

def _extract_token_from_ws(ws: WebSocket) -> Optional[str]:
    # Prefer query param in browsers; headers also possible
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
    token = _extract_token_from_ws(ws)
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

# ---------- line helpers ----------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

async def _readlines(proc: asyncio.subprocess.Process):
    """
    Async line-by-line reader for a process' stdout.
    """
    while True:
        line = await proc.stdout.readline()
        if not line:
            # process ended or no more data currently
            await asyncio.sleep(0.05)
            continue
        yield line.decode(errors="ignore").rstrip("\n")

# ---------- tail helpers ----------

async def _tail_file_via_proc(path: Path, n: int) -> asyncio.subprocess.Process:
    """
    Spawn `sudo tail -n {n} -F path` as an async process.
    Requires sudoers permission for tail without password.
    """
    return await asyncio.create_subprocess_exec(
        "sudo", "tail", "-n", str(n), "-F", str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

async def _pump_tail_ws(ws: WebSocket, label: str, proc: asyncio.subprocess.Process, grep: Optional[str], json_mode: bool):
    """
    Send lines from a 'tail' process to a WebSocket.
    """
    try:
        async for line in _readlines(proc):
            if grep and grep not in line:
                continue
            if json_mode:
                await ws.send_json({"source": label, "line": line, "ts": _now_iso()})
            else:
                await ws.send_text(line)
    except WebSocketDisconnect:
        # client disconnected
        pass
    except Exception as e:
        # best-effort notify
        try:
            await ws.send_json({"source": label, "error": str(e), "ts": _now_iso()})
        except Exception:
            pass

async def _cancel_process(proc: asyncio.subprocess.Process):
    if proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            proc.kill()

# ============================================================
# WebSocket streams
# ============================================================
@router.websocket("/ws/dms/logs")
async def ws_dms_logs(ws: WebSocket):
    """
    Stream DMS logs in realtime over WebSocket.
    - Query params:
      n:      initial lines to include (default 200)
      grep:   optional substring filter
      json_mode: true => send JSON objects per line; false => plain text lines
    """
    if not await _ws_auth_or_close(ws):
        return
    qp = ws.query_params
    try:
        n = int(qp.get("n", "200"))
    except Exception:
        n = 200
    grep = qp.get("grep")
    json_mode = qp.get("json_mode", "true").lower() == "true"
    proc = await _tail_file_via_proc(DMS_LOG_PATH, n)

    try:
        await _pump_tail_ws(ws, "dms", proc, grep, json_mode)
    finally:
        await _cancel_process(proc)

@router.websocket("/ws/ensemble/deployments/{deployment_id}/logs")
async def ws_ensemble_logs(ws: WebSocket, deployment_id: str):
    """
    Stream an ensemble's stdout/stderr logs over WebSocket.
    - If multiple allocations exist and none specified, connection will be closed with a hint.
    """
    if not await _ws_auth_or_close(ws):
        return
    qp = ws.query_params
    allocation = qp.get("allocation")
    include = qp.get("include", "both")
    try:
        n = int(qp.get("n", "200"))
    except Exception:
        n = 200
    grep = qp.get("grep")
    json_mode = qp.get("json_mode", "true").lower() == "true"
    mgr = EnsembleManagerV2()
    allocs = mgr.get_deployment_allocations(deployment_id)

    if not allocs:
        await ws.send_json({"error": "no_allocations_found", "deployment_id": deployment_id})
        await ws.close(code=4404)
        return

    if allocation is None:
        if len(allocs) > 1:
            await ws.send_json({"error": "multiple_allocations", "allocations": allocs})
            await ws.close(code=4400)
            return
        allocation = allocs[0]

    deployment_dir = Path(f"/home/nunet/nunet/deployments/{deployment_id}/{allocation}")
    tails: List[asyncio.subprocess.Process] = []

    # choose which files to stream
    to_stream: List[tuple[str, Path]] = []
    if include in ("stdout", "both"):
        to_stream.append(("stdout", deployment_dir / "stdout.logs"))
    if include in ("stderr", "both"):
        to_stream.append(("stderr", deployment_dir / "stderr.logs"))

    try:
        # start all tail processes
        for label, path in to_stream:
            proc = await _tail_file_via_proc(path, n)
            tails.append(proc)

        # pump all concurrently
        tasks = [
            asyncio.create_task(_pump_tail_ws(ws, label, proc, grep, json_mode))
            for (label, _), proc in zip(to_stream, tails)
        ]
        await asyncio.gather(*tasks)
    finally:
        # teardown
        await asyncio.gather(*[ _cancel_process(p) for p in tails ], return_exceptions=True)

# ============================================================
# SSE streams (one-way, HTTP-friendly)
# ============================================================

async def _sse_sender(gen: AsyncGenerator[str, None]):
    """
    Convert an async generator of text lines to an SSE stream.
    """
    async for line in gen:
        yield f"data: {line}\n\n"

@router.get("/stream/dms/logs")
async def sse_dms_logs(
    token: Optional[str] = None,
    n: int = 200,
    grep: Optional[str] = None,
    json_mode: bool = True,
):
    """
    SSE stream of DMS logs. Client receives a never-ending text/event-stream.
    """
    try:
        _check_http_token(token)
    except PermissionError:
        return StreamingResponse(iter(["event: error\ndata: unauthorized\n\n"]), media_type="text/event-stream")

    async def gen():
        proc = await _tail_file_via_proc(DMS_LOG_PATH, n)
        try:
            async for line in _readlines(proc):
                if grep and grep not in line:
                    continue
                payload = (
                    json.dumps({"source": "dms", "line": line, "ts": _now_iso()})
                    if json_mode else line
                )
                yield payload
        finally:
            await _cancel_process(proc)

    return StreamingResponse(_sse_sender(gen()), media_type="text/event-stream")

@router.get("/stream/ensemble/deployments/{deployment_id}/logs")
async def sse_ensemble_logs(
    deployment_id: str,
    token: Optional[str] = None,
    allocation: Optional[str] = None,
    include: str = "both",
    n: int = 200,
    grep: Optional[str] = None,
    json_mode: bool = True,
):
    """
    SSE stream of an ensemble's logs (stdout/stderr).
    """
    try:
        _check_http_token(token)
    except PermissionError:
        return StreamingResponse(iter(["event: error\ndata: unauthorized\n\n"]), media_type="text/event-stream")

    mgr = EnsembleManagerV2()
    allocs = mgr.get_deployment_allocations(deployment_id)
    if not allocs:
        return StreamingResponse(iter([f"event: error\ndata: {json.dumps({'error':'no_allocations_found'})}\n\n"]), media_type="text/event-stream")

    if allocation is None:
        if len(allocs) > 1:
            return StreamingResponse(
                iter([f"event: error\ndata: {json.dumps({'error':'multiple_allocations','allocations':allocs})}\n\n"]),
                media_type="text/event-stream",
            )
        allocation = allocs[0]

    deployment_dir = Path(f"/home/nunet/nunet/deployments/{deployment_id}/{allocation}")
    to_stream: List[tuple[str, Path]] = []
    if include in ("stdout", "both"):
        to_stream.append(("stdout", deployment_dir / "stdout.logs"))
    if include in ("stderr", "both"):
        to_stream.append(("stderr", deployment_dir / "stderr.logs"))

    async def gen():
        procs: List[asyncio.subprocess.Process] = []
        try:
            for _, path in to_stream:
                procs.append(await _tail_file_via_proc(path, n))

            # multiplex: interleave lines as they arrive
            tasks = []
            for (label, _), proc in zip(to_stream, procs):
                async def pump(lbl=label, p=proc):
                    async for line in _readlines(p):
                        if grep and grep not in line:
                            continue
                        payload = (
                            json.dumps({"source": lbl, "line": line, "ts": _now_iso()})
                            if json_mode else line
                        )
                        yield payload
                tasks.append(pump())

            # Merge async generators
            done = False
            while not done:
                gen_tasks = [asyncio.create_task(t.__anext__()) for t in tasks]
                try:
                    done_idx, pending = await asyncio.wait(gen_tasks, return_when=asyncio.FIRST_COMPLETED)
                except StopAsyncIteration:
                    break
                for task in gen_tasks:
                    if task.done() and not task.cancelled():
                        try:
                            yield task.result()
                        except StopAsyncIteration:
                            done = True
                for task in gen_tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.sleep(0.01)
        finally:
            await asyncio.gather(*[ _cancel_process(p) for p in procs ], return_exceptions=True)

    return StreamingResponse(_sse_sender(gen()), media_type="text/event-stream")
