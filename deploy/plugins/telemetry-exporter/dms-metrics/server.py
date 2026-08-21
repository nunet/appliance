#!/usr/bin/env python3
"""Always-on DMS Prometheus metrics exporter (stdlib only).

Queries only the three DMS capacity snapshots:

  /dms/node/resources/onboarded
  /dms/node/resources/free        (available / headroom)
  /dms/node/resources/allocated

No GPU inventory, hardware/spec, onboarding status, peers, or deployments.
Those extra actor calls are I/O-blocking and too expensive for a 60s scrape.

Serves ``/metrics`` for Grafana Alloy to scrape into Mimir.

Environment:
  NUNET_DMS_METRICS_LISTEN   default ``127.0.0.1:9105``
  NUNET_DMS_METRICS_TTL      cache TTL seconds (default ``15``)
  NUNET_DMS_CONTEXT          nunet context (default ``dms``)
  NUNET_DMS_PASSPHRASE_FILE  optional passphrase file override
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

ANSI_RE = re.compile(r"\u001b\[[0-9;]*m")

DEFAULT_LISTEN = "127.0.0.1:9105"
DEFAULT_TTL = 15.0
DEFAULT_CONTEXT = "dms"
DEFAULT_TIMEOUT = 20

# DMS names these snapshots onboarded / free / allocated. "free" is available capacity.
RESOURCE_STATES = ("onboarded", "free", "allocated")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _coerce_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _prom_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(**kwargs: Any) -> str:
    parts: List[str] = []
    for key, value in kwargs.items():
        if value is None:
            continue
        text = _coerce_text(value)
        if text is None:
            continue
        parts.append(f'{key}="{_prom_escape(text)}"')
    if not parts:
        return ""
    return "{" + ",".join(parts) + "}"


def _metric(name: str, value: float, **labels: Any) -> str:
    return f"{name}{_labels(**labels)} {value}"


def _load_passphrase() -> Optional[str]:
    override = os.environ.get("NUNET_DMS_PASSPHRASE_FILE")
    candidates: List[Path] = []
    if override:
        candidates.append(Path(override))
    candidates.append(Path.home() / ".secrets" / "dms_passphrase")

    try:
        key_id_cp = subprocess.run(
            ["keyctl", "request", "user", "dms_passphrase"],
            capture_output=True,
            text=True,
            check=False,
        )
        if key_id_cp.returncode == 0 and key_id_cp.stdout.strip():
            pipe_cp = subprocess.run(
                ["keyctl", "pipe", key_id_cp.stdout.strip()],
                capture_output=True,
                text=True,
                check=False,
            )
            if pipe_cp.returncode == 0 and pipe_cp.stdout.strip():
                return pipe_cp.stdout.strip()
    except FileNotFoundError:
        pass

    for path in candidates:
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            continue
    return None


def _merge_env() -> Dict[str, str]:
    env = os.environ.copy()
    passphrase = _load_passphrase()
    if passphrase:
        env["DMS_PASSPHRASE"] = passphrase
    return env


class DmsClient:
    def __init__(self, context: str = DEFAULT_CONTEXT, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.context = context
        self.timeout = timeout

    def run(self, argv: Sequence[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            check=False,
            timeout=self.timeout,
            env=_merge_env(),
        )

    def actor_json(self, endpoint: str, *extra: str) -> Tuple[bool, Any, str]:
        argv = ["nunet", "-c", self.context, "actor", "cmd", endpoint, *extra]
        try:
            cp = self.run(argv)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return False, None, str(exc)

        raw = ANSI_RE.sub("", (cp.stdout or "").strip())
        if cp.returncode != 0:
            err = (cp.stderr or raw or f"rc={cp.returncode}").strip()
            return False, None, err
        if not raw:
            return True, None, ""
        try:
            return True, json.loads(raw), ""
        except json.JSONDecodeError:
            return True, raw, ""


def _resources_block(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    resources = payload.get("Resources")
    if isinstance(resources, dict):
        return resources
    return payload


def _resource_totals(payload: Any) -> Dict[str, Optional[float]]:
    resources = _resources_block(payload)
    cpu = resources.get("cpu") if isinstance(resources.get("cpu"), dict) else {}
    ram = resources.get("ram") if isinstance(resources.get("ram"), dict) else {}
    disk = resources.get("disk") if isinstance(resources.get("disk"), dict) else {}
    return {
        "cores": _coerce_float(cpu.get("cores")),
        "ram_bytes": _coerce_float(ram.get("size")),
        "disk_bytes": _coerce_float(disk.get("size")),
    }


def _append_resource_metrics(lines: List[str], state: str, payload: Any) -> None:
    totals = _resource_totals(payload)
    if totals["cores"] is not None:
        lines.append(_metric("nunet_dms_resource_cores", totals["cores"], state=state))
    if totals["ram_bytes"] is not None:
        lines.append(_metric("nunet_dms_resource_ram_bytes", totals["ram_bytes"], state=state))
    if totals["disk_bytes"] is not None:
        lines.append(_metric("nunet_dms_resource_disk_bytes", totals["disk_bytes"], state=state))


class MetricsCollector:
    def __init__(self, client: DmsClient, ttl: float) -> None:
        self.client = client
        self.ttl = ttl
        self._lock = threading.Lock()
        self._cached_text = ""
        self._cached_at = 0.0

    def render(self) -> str:
        now = time.monotonic()
        with self._lock:
            if self._cached_text and now - self._cached_at < self.ttl:
                return self._cached_text
        text = self._collect()
        with self._lock:
            self._cached_text = text
            self._cached_at = time.monotonic()
        return text

    def _query_state(self, state: str) -> Tuple[str, bool, Any, str]:
        endpoint = f"/dms/node/resources/{state}"
        ok, payload, err = self.client.actor_json(endpoint)
        return endpoint, ok, payload, err

    def _collect(self) -> str:
        started = time.perf_counter()
        lines: List[str] = [
            "# HELP nunet_dms_resource_cores CPU cores by capacity state",
            "# TYPE nunet_dms_resource_cores gauge",
            "# HELP nunet_dms_resource_ram_bytes RAM bytes by capacity state",
            "# TYPE nunet_dms_resource_ram_bytes gauge",
            "# HELP nunet_dms_resource_disk_bytes Disk bytes by capacity state",
            "# TYPE nunet_dms_resource_disk_bytes gauge",
        ]
        query_ok: Dict[str, int] = {}
        results: Dict[str, Tuple[str, bool, Any, str]] = {}

        # Parallel actor cmds so scrape latency is ~one query, not three serial waits.
        with ThreadPoolExecutor(max_workers=len(RESOURCE_STATES)) as pool:
            futures = {state: pool.submit(self._query_state, state) for state in RESOURCE_STATES}
            for state in RESOURCE_STATES:
                results[state] = futures[state].result()

        for state in RESOURCE_STATES:
            endpoint, ok, payload, err = results[state]
            query_ok[endpoint] = 1 if ok else 0
            if not ok:
                if err:
                    lines.append(f"# {endpoint} error: {_prom_escape(err)[:200]}")
                continue
            _append_resource_metrics(lines, state, payload)

        lines.extend(
            [
                "# HELP nunet_dms_actor_query_success 1 if the named DMS query succeeded",
                "# TYPE nunet_dms_actor_query_success gauge",
            ]
        )
        for endpoint, value in sorted(query_ok.items()):
            lines.append(_metric("nunet_dms_actor_query_success", float(value), endpoint=endpoint))

        duration = time.perf_counter() - started
        success = 1.0 if all(query_ok.get(f"/dms/node/resources/{state}", 0) for state in RESOURCE_STATES) else 0.0
        lines.extend(
            [
                "# HELP nunet_dms_up 1 if onboarded, free, and allocated resource queries succeeded",
                "# TYPE nunet_dms_up gauge",
                _metric("nunet_dms_up", success),
                "# HELP nunet_dms_scrape_success 1 if onboarded, free, and allocated resource queries succeeded",
                "# TYPE nunet_dms_scrape_success gauge",
                _metric("nunet_dms_scrape_success", success),
                "# HELP nunet_dms_scrape_duration_seconds Time spent collecting DMS metrics",
                "# TYPE nunet_dms_scrape_duration_seconds gauge",
                _metric("nunet_dms_scrape_duration_seconds", duration),
                "# HELP nunet_dms_scrape_timestamp_seconds Unix time of last successful metrics build",
                "# TYPE nunet_dms_scrape_timestamp_seconds gauge",
                _metric("nunet_dms_scrape_timestamp_seconds", time.time()),
            ]
        )
        lines.append("")
        return "\n".join(lines)


class MetricsHandler(BaseHTTPRequestHandler):
    collector: MetricsCollector

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/healthz", "/readyz"):
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path != "/metrics":
            body = b"not found\n"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        try:
            text = self.collector.render()
            body = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001 - keep exporter alive
            body = f"# exporter error: {exc}\n".encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def _parse_listen(value: str) -> Tuple[str, int]:
    if ":" not in value:
        raise ValueError(f"listen address must be host:port, got {value!r}")
    host, port_s = value.rsplit(":", 1)
    return host, int(port_s)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="NuNet DMS Prometheus metrics exporter")
    parser.add_argument(
        "--listen",
        default=os.environ.get("NUNET_DMS_METRICS_LISTEN", DEFAULT_LISTEN),
        help=f"host:port to bind (default {DEFAULT_LISTEN})",
    )
    parser.add_argument(
        "--ttl",
        type=float,
        default=_env_float("NUNET_DMS_METRICS_TTL", DEFAULT_TTL),
        help="cache TTL seconds between DMS collections",
    )
    parser.add_argument(
        "--context",
        default=os.environ.get("NUNET_DMS_CONTEXT", DEFAULT_CONTEXT),
        help="nunet DMS context name",
    )
    args = parser.parse_args(argv)

    host, port = _parse_listen(args.listen)
    collector = MetricsCollector(DmsClient(context=args.context), ttl=max(0.0, args.ttl))
    MetricsHandler.collector = collector
    server = ThreadingHTTPServer((host, port), MetricsHandler)
    print(f"nunet-dms-metrics listening on http://{host}:{port}/metrics", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
