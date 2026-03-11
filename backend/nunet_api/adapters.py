# nunet_api/app/adapters.py
import json
import re
from typing import Dict, Any, List

ANSI = re.compile(r"\x1b\[[0-9;]*m")

def strip_ansi(s: str) -> str:
    return ANSI.sub("", s or "")

def normalize_dms_status(status_dict: Dict[str, Any]) -> Dict[str, Any]:
    # Input may have colorized strings; normalize to clean JSON
    running_str = strip_ansi(status_dict.get("dms_running", "Not Running"))
    running = running_str.lower().startswith("running")
    return {
        "dms_status": status_dict.get("dms_status", "Unknown"),
        "dms_version": status_dict.get("dms_version", "Unknown"),
        "dms_running": running,
        "dms_context": status_dict.get("dms_context", "Unknown"),
        "dms_did": status_dict.get("dms_did", "Unknown"),
        "dms_peer_id": status_dict.get("dms_peer_id", "Unknown"),
        "dms_is_relayed": status_dict.get("dms_is_relayed"),
    }

def parse_ssh_status(colored_line: str) -> Dict[str, Any]:
    # Example input: "\x1b[92mSSH: Running | Authorized Keys: 2\x1b[0m"
    text = strip_ansi(colored_line)
    running = "Running" in text and "Stopped" not in text
    # naive parse; adjust if you change the format
    try:
        after_pipe = text.split("|", 1)[1]
        key_part = after_pipe.split(":")[1].strip()
        key_count = int(key_part)
    except Exception:
        key_count = 0
    return {"running": running, "authorized_keys": key_count}


_PRIVATE_IPV4 = re.compile(
    r"/ip4/(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.)"
)
def _ensure_list(val) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        # split common list-like strings
        if s.startswith("[") and s.endswith("]"):
            try:
                arr = json.loads(s)
                return [str(x).strip() for x in arr if str(x).strip()]
            except Exception:
                pass
        # comma/space separated
        parts = [p.strip() for p in re.split(r"[,\s]+", s) if p.strip()]
        return parts
    return []

def _categorize_addr(addr: str) -> str:
    a = addr or ""
    if "p2p-circuit" in a or "/circuit/" in a or "/relay" in a:
        return "relay"
    if _PRIVATE_IPV4.search(a) or "/ip6/::1" in a:
        return "local"
    return "public"

def _normalize_peer_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    # Accept many possible keys and normalize
    peer_id = d.get("peer_id") or d.get("peerId") or d.get("id") or d.get("peer") or d.get("PeerID")
    did = d.get("did") or d.get("DID") or d.get("did_key") or d.get("didKey")
    context = d.get("context") or d.get("Context")
    is_relayed = d.get("is_relayed")
    if is_relayed is None:
        is_relayed = d.get("isRelayed")
    # addresses possibly split or single list
    local_addrs = _ensure_list(d.get("local_addrs") or d.get("local") or d.get("localAddresses") or d.get("localAddrs"))
    public_addrs = _ensure_list(d.get("public_addrs") or d.get("public") or d.get("publicAddresses") or d.get("publicAddrs"))
    relay_addrs = _ensure_list(d.get("relay_addrs") or d.get("relay") or d.get("relayAddresses") or d.get("relayAddrs"))
    # generic bucket
    generic_addrs = _ensure_list(d.get("addresses") or d.get("addrs"))

    for a in generic_addrs:
        kind = _categorize_addr(a)
        if kind == "relay":
            relay_addrs.append(a)
        elif kind == "local":
            local_addrs.append(a)
        else:
            public_addrs.append(a)

    # infer relayed if not provided
    if is_relayed is None:
        is_relayed = len(relay_addrs) > 0

    return {
        "peer_id": peer_id or "",
        "did": did,
        "context": context,
        "local_addrs": local_addrs,
        "public_addrs": public_addrs,
        "relay_addrs": relay_addrs,
        "is_relayed": is_relayed,
    }

def parse_connected_peers(stdout: str) -> List[Dict[str, Any]]:
    """
    Try to parse `nunet -c dms actor cmd /dms/node/peers/list` output into a list of peers.
    - If stdout is JSON (list or {"peers":[...]}) -> normalize each dict entry
    - Otherwise, fall back to a forgiving line-based parser
    """
    s = strip_ansi(stdout or "").strip()
    if not s:
        return []

    # JSON path first
    try:
        data = json.loads(s)
        items = None
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for key in ("peers", "result", "data"):
                if isinstance(data.get(key), list):
                    items = data[key]
                    break
            # sometimes it's a mapping { peer_id: { ... } }
            if items is None and isinstance(data.get("peers"), dict):
                items = []
                for pid, meta in data["peers"].items():
                    md = dict(meta or {})
                    md.setdefault("peer_id", pid)
                    items.append(md)
        if items is not None:
            peers: List[Dict[str, Any]] = []
            for it in items:
                if isinstance(it, dict):
                    peers.append(_normalize_peer_dict(it))
                elif isinstance(it, str):
                    # best effort for string-only entries (treat like peer id)
                    peers.append(_normalize_peer_dict({"peer_id": it}))
            return [p for p in peers if p.get("peer_id")]
    except Exception:
        pass

    # Line / table parsing (best-effort)
    peers: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {"local_addrs": [], "public_addrs": [], "relay_addrs": []}

    def _flush():
        nonlocal current
        if current.get("peer_id") or any(current[k] for k in ("local_addrs", "public_addrs", "relay_addrs")):
            # infer relayed
            if "is_relayed" not in current:
                current["is_relayed"] = len(current.get("relay_addrs", [])) > 0
            peers.append({
                "peer_id": current.get("peer_id", ""),
                "did": current.get("did"),
                "context": current.get("context"),
                "local_addrs": current.get("local_addrs", []),
                "public_addrs": current.get("public_addrs", []),
                "relay_addrs": current.get("relay_addrs", []),
                "is_relayed": current.get("is_relayed"),
            })
        current = {"local_addrs": [], "public_addrs": [], "relay_addrs": []}

    for raw in s.splitlines():
        line = raw.strip()
        if not line or set(line) <= {"-", "="}:
            _flush()
            continue

        m = re.search(r"(peer\s*id|peerid|id)\s*[:=]\s*([^\s,;]+)", line, re.I)
        if m:
            if current.get("peer_id"):
                _flush()
            current["peer_id"] = m.group(2)
            continue

        m = re.search(r"\bdid\b\s*[:=]\s*([^\s,;]+)", line, re.I)
        if m:
            current["did"] = m.group(1)
            continue

        m = re.search(r"\bcontext\b\s*[:=]\s*(.+)$", line, re.I)
        if m:
            current["context"] = m.group(1).strip()
            continue

        m = re.search(r"(local|public|relay)\s*(addrs|addresses)?\s*[:=]\s*(.+)$", line, re.I)
        if m:
            kind = m.group(1).lower()
            addr_part = m.group(3)
            for a in _ensure_list(addr_part):
                if not a.startswith("/"):
                    # free text? still try to categorize
                    kind2 = _categorize_addr(a)
                else:
                    kind2 = kind
                bucket = f"{kind2}_addrs"
                current.setdefault(bucket, []).append(a.strip())
            continue

        # bullet or raw multiaddrs
        if line.startswith(("-", "/")):
            addr = line.lstrip("- ").strip()
            kind2 = _categorize_addr(addr)
            bucket = f"{kind2}_addrs"
            current.setdefault(bucket, []).append(addr)
            continue

    _flush()
    # keep only entries with a peer_id if any exist; otherwise keep address-only entries
    if any(p.get("peer_id") for p in peers):
        peers = [p for p in peers if p.get("peer_id")]
    return peers

def build_full_status_summary(info: Dict[str, Any]) -> str:
    """
    Produce a color-free, human-readable summary like show_full_status().
    `info` is expected to contain both resource and DMS fields.
    """
    lines = []
    lines.append("=== DMS Full Status ===")
    lines.append(f"Onboarding Status: {info.get('onboarding_status', 'Unknown')}")
    lines.append(f"Free Resources: {info.get('free_resources', 'Unknown')}")
    lines.append(f"Allocated Resources: {info.get('allocated_resources', 'Unknown')}")
    lines.append(f"Onboarded Resources: {info.get('onboarded_resources', 'Unknown')}")
    running_str = "Running" if info.get("dms_running") else "Not Running"
    lines.append(
        f"DMS Status: {info.get('dms_status', 'Unknown')} (v{info.get('dms_version', 'Unknown')}) "
        f"{running_str} Context: {info.get('dms_context', 'Unknown')}"
    )
    if info.get("dms_peer_id") and info.get("dms_peer_id") != "Unknown":
        lines.append(f"DMS DID: {info.get('dms_did', 'Unknown')}")
        lines.append(f"DMS Peer ID: {info.get('dms_peer_id')}")
        is_rel = info.get("dms_is_relayed")
        if is_rel is not None:
            relay_status = "Using relay" if is_rel else "Direct connection"
            lines.append(f"NuNet Network Connection Type: {relay_status}")
    return "\n".join(lines)