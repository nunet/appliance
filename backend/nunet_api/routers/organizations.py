from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Body, Depends, Query
from pydantic import BaseModel, EmailStr, Field

from modules.onboarding_manager import OnboardingManager
from modules.organization_manager import OrganizationManager
from modules.org_utils import (
    load_known_organizations,
    get_joined_organizations_with_details,
)
from modules.dms_utils import get_dms_status_info, get_dms_resource_info

router = APIRouter()

# ---------------------------------------------------------------------------
# Globals / singletons
# ---------------------------------------------------------------------------

log = logging.getLogger(__name__)
_onboarding = OnboardingManager()
_org_mgr = OrganizationManager()

ANSI_RE = re.compile(r"\x1B\[[0-9;]*m")


def _ensure_state_file(mgr: OnboardingManager) -> None:
    """
    The legacy service used a state file; create a minimal one if missing so
    mgr.save_state() can persist logs/state reliably.
    """
    try:
        p: Path = mgr.STATE_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            initial = {
                "step": "init",
                "progress": 0,
                "wormhole_code": None,
                "form_data": {},
                "error": None,
                "logs": [],
            }
            p.write_text(json.dumps(initial, indent=2))
            mgr.state = initial
    except Exception as e:
        # Non-fatal; operate with in-memory state
        log.warning("Could not ensure onboarding state file: %s", e)


def _mgr() -> OnboardingManager:
    _ensure_state_file(_onboarding)
    return _onboarding


# ---------------------------------------------------------------------------
# Step model / progress mapping (UI timeline)
# ---------------------------------------------------------------------------

STEP_DEFS = [
    {"id": "init", "label": "Init"},
    {"id": "select_org", "label": "Select Organization"},
    {"id": "collect_join_data", "label": "Fill Join Form"},
    {"id": "submit_data", "label": "Submit Data"},
    {"id": "join_data_sent", "label": "Data Sent"},
    {"id": "email_verified", "label": "Email Verified", "virtual": True},
    {"id": "pending_authorization", "label": "Pending Authorization"},
    {"id": "join_data_received", "label": "Join Data Received"},
    {"id": "capabilities_applied", "label": "Capabilities Applied"},
    {"id": "capabilities_onboarded", "label": "Capabilities Onboarded"},
    {"id": "telemetry_configured", "label": "Telemetry Configured"},
    {"id": "mtls_certs_saved", "label": "mTLS Certs Saved"},
    {"id": "complete", "label": "Complete"},
    {"id": "rejected", "label": "Rejected"},
]

PROGRESS_MAP = {
    "init": 0,
    "select_org": 10,
    "collect_join_data": 20,
    "submit_data": 30,
    "join_data_sent": 40,
    "email_verified": 50,
    "pending_authorization": 60,
    "join_data_received": 70,
    "capabilities_applied": 80,
    "capabilities_onboarded": 83,
    "telemetry_configured": 85,
    "mtls_certs_saved": 90,
    "complete": 100,
    "rejected": 100,
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SelectOrgRequest(BaseModel):
    org_did: str = Field(..., description="Organization DID to join")


class WormholeResponse(BaseModel):
    status: str
    wormhole_code: Optional[str] = None
    message: Optional[str] = None
    output: Optional[str] = None


class JoinSubmitRequest(BaseModel):
    # org_did optional if /select was already called
    org_did: Optional[str] = Field(None, description="Organization DID (optional if already selected)")
    name: str
    email: EmailStr
    why_join: Optional[str] = None  # "provide" | "access" | "both"
    location: Optional[str] = None
    discord: Optional[str] = None
    wormhole: Optional[str] = Field(None, description="Wormhole code if required by the org")


class JoinSubmitResponse(BaseModel):
    status: str
    request_id: Optional[str] = None
    status_token: Optional[str] = None
    api_status: Optional[str] = None
    step: Optional[str] = None
    state: Dict[str, Any]


class PollStatusResponse(BaseModel):
    status: str  # "pending" | "processing" | "success" | "idle" | "error"
    api_status: Optional[str] = None
    step: str
    payload_available: bool
    state: Dict[str, Any]


class ProcessResponse(BaseModel):
    status: str
    step: str
    message: Optional[str] = None
    state: Dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_runtime_info(mgr: OnboardingManager) -> Dict[str, Any]:
    """
    Collect runtime metadata similar to the old UI:
    - dms_status (DID/Peer ID etc.)
    - peer_info (public/local addrs, context)
    - resources onboarding flags and raw dms_resources snapshot
    """
    runtime: Dict[str, Any] = {}

    dms_info = get_dms_status_info() or {}
    runtime["dms_status"] = dms_info

    try:
        peer_info = mgr.dms_manager.get_self_peer_info() or {}
        runtime["peer_info"] = {
            "did": peer_info.get("did"),
            "peer_id": peer_info.get("peer_id"),
            "context": peer_info.get("context"),
            "public_addrs": peer_info.get("public_addrs"),
            "local_addrs": peer_info.get("local_addrs"),
        }
    except Exception:
        runtime["peer_info"] = {}

    try:
        res_info = get_dms_resource_info() or {}
        onboarding_status = res_info.get("onboarding_status", "Unknown")
        onboarded_resources = res_info.get("onboarded_resources", "Unknown")
        if isinstance(onboarded_resources, str):
            onboarded_resources = ANSI_RE.sub("", onboarded_resources)
        runtime["resources"] = {
            "onboarding_status": ("ONBOARDED" in str(onboarding_status)),
            "onboarded_resources": onboarded_resources,
        }
        runtime["dms_resources"] = res_info.get("dms_resources", {})
    except Exception:
        runtime["resources"] = {
            "onboarding_status": False,
            "onboarded_resources": "Unknown (collection failed)",
        }
        runtime["dms_resources"] = {}

    return runtime


def _resolve_current_step_from_state(state: dict) -> str:
    """
    Prefer sticky terminal states; otherwise derive from logs/state/api_status.
    """
    step = state.get("step")
    logs = state.get("logs") or []
    api_status = state.get("api_status")

    # Sticky terminal states
    if state.get("status") == "complete" or state.get("completed"):
        return "complete"
    if step == "rejected":
        return "rejected"

    # Prefer most recent logged step
    if logs:
        last = logs[-1]
        if isinstance(last, dict) and last.get("step"):
            step = last["step"]

    # Virtual step for UX
    if api_status == "email_verified":
        return "email_verified"

    ids = [s["id"] for s in STEP_DEFS]
    return step if step in ids else "init"


def _compute_step_states(current_step: str) -> dict:
    ids = [s["id"] for s in STEP_DEFS]
    if current_step not in ids:
        current_step = "init"
    current_index = ids.index(current_step)

    step_states = []
    for i, s in enumerate(STEP_DEFS):
        if i < current_index:
            state = "done"
        elif i == current_index:
            state = "active"
        else:
            state = "todo"
        step_states.append(
            {
                "id": s["id"],
                "label": s["label"],
                "virtual": s.get("virtual", False),
                "state": state,
            }
        )
    return {
        "current_step": current_step,
        "current_index": current_index,
        "step_states": step_states,
    }


def _get_onboarding_ui_state_and_message(onboarding_status: dict) -> tuple[str, str]:
    step = onboarding_status.get("step")
    api_status = onboarding_status.get("api_status")
    rejection_reason = onboarding_status.get("rejection_reason", "")
    error = onboarding_status.get("error")
    org_name = onboarding_status.get("org_data", {}).get("name", "the organization")

    if step == "collect_join_data" and onboarding_status.get("form_data"):
        return ("data_ready", "Your join data is ready. Preparing to submit to the organization's onboarding service...")
    if step == "submit_data" and not api_status:
        return ("waiting_api", "Waiting for the organization's onboarding service to become available...")
    if step == "join_data_sent" and api_status in [None, "", "pending", "processing", "email_sent"]:
        return ("data_submitted", "Your join data has been submitted to the organization. Awaiting further instructions...")
    if api_status == "email_verified":
        return ("email_verified", "Your email has been verified! Waiting for organization approval...")
    if step == "join_data_sent" and api_status in ["pending", "processing"]:
        return ("waiting_approval", "Your request is being reviewed by the organization. Please wait for approval...")
    if step == 'join_data_received' or (step == 'join_data_sent' and api_status in ['approved', 'ready']) or api_status in ['approved', 'ready']:
        return ('approved', 'Your request has been approved! Finalizing onboarding...')
    if step == 'pending_authorization':
        return ('waiting_approval', 'Your request is being reviewed by the organization. Please wait for approval...')
    if step == "capabilities_applied":
        return ("capabilities_applied", "Applying organization capabilities...")
    if step == "capabilities_onboarded":
        return ("capabilities_onboarded", "Onboarding compute resources with organization capabilities...")
    if step == "telemetry_configured":
        return ("telemetry_configured", "Configuring telemetry...")
    if step == "mtls_certs_saved":
        return ("mtls_certs_saved", "Saving mTLS certificates...")
    if step == "complete":
        return ("complete", f"Onboarding complete! You are now a member of {org_name}.")
    if step == "rejected" and rejection_reason:
        return ("rejected", f"Your onboarding request was rejected. Reason: {rejection_reason}")
    if error:
        return ("error", f"An error occurred: {error}")
    return (step or "init", f"Current step: {step or 'init'}")


def _redact_state_for_ui(state: dict) -> dict:
    """
    Deep-copy and redact sensitive values before returning to UI.
    """
    s = deepcopy(state)
    if "status_token" in s and s["status_token"]:
        s["status_token"] = "***"
    payload = s.get("api_payload")
    if isinstance(payload, dict):
        for k in list(payload.keys()):
            k_low = str(k).lower()
            if "token" in k_low or "key" in k_low or "secret" in k_low:
                payload[k] = "***"
    return s


def _enrich_status_for_ui(state: dict) -> dict:
    current_step = _resolve_current_step_from_state(state)
    timeline = _compute_step_states(current_step)
    ui_state, ui_message = _get_onboarding_ui_state_and_message(state)
    progress = state.get("progress")
    if progress is None or progress == 0:
        progress = PROGRESS_MAP.get(current_step, 0)


    return {
        "current_step": timeline["current_step"],
        "current_index": timeline["current_index"],
        "progress": progress,
        "api_status": state.get("api_status"),
        "ui_state": ui_state,
        "ui_message": ui_message,
        "step_order": [{"id": s["id"], "label": s["label"], "virtual": s.get("virtual", False)} for s in STEP_DEFS],
        "step_states": timeline["step_states"],
        "rejection_reason": state.get("rejection_reason"),
        "logs": state.get("logs", []),
        "raw": _redact_state_for_ui(state),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/known")
def get_known():
    """Known orgs (name + API + join_fields)."""
    return load_known_organizations()


@router.get("/joined")
def get_joined():
    """
    Already joined organizations with details (capabilities, expiry).
    - FE expects fields: did, capabilities[], expiry (ISO)
    """
    return get_joined_organizations_with_details()


@router.get("/steps")
def steps():
    return {
        "steps": [{"id": s["id"], "label": s["label"], "virtual": s.get("virtual", False)} for s in STEP_DEFS],
        "progress_map": PROGRESS_MAP,
    }


@router.get("/status")
def status(mgr: OnboardingManager = Depends(_mgr)):
    state = mgr.get_onboarding_status()
    return _enrich_status_for_ui(state)


@router.post("/select")
def select_org(body: SelectOrgRequest, mgr: OnboardingManager = Depends(_mgr)):
    """
    Select an organization and advance to collect_join_data immediately.
    Clears any previous request ids or processing flags.
    """
    known = load_known_organizations() or {}
    org_entry = known.get(body.org_did, {})
    org_name = org_entry["name"] if isinstance(org_entry, dict) and "name" in org_entry else body.org_did

    mgr.update_state(
        org_data={"did": body.org_did, "name": org_name},
        step="collect_join_data",
        request_id=None,
        status_token=None,
        api_status=None,
        api_payload=None,
        rejection_reason=None,
        processing=False,
        processed_ok=False,
    )

    return {
        "status": "success",
        "message": f"Selected organization {org_name}",
        "state": mgr.get_onboarding_status(),
    }


@router.post("/wormhole", response_model=WormholeResponse)
def generate_wormhole():
    """
    Optional: for orgs that still use the wormhole pairing script (join-org-web.sh).
    """
    try:
        result = _org_mgr.join_organization(step="generate")
        return WormholeResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"wormhole generation failed: {e}")


@router.post("/join/submit", response_model=JoinSubmitResponse)
def submit_join(body: JoinSubmitRequest, mgr: OnboardingManager = Depends(_mgr)):
    """
    Submit join data. If org_did is included, it also selects the org.
    Moves to join_data_sent with request_id / status_token if submit succeeds.
    """
    # Allow select here for single-call UX
    if body.org_did:
        known = load_known_organizations() or {}
        entry = known.get(body.org_did)
        if not entry:
            raise HTTPException(status_code=404, detail="Unknown organization DID")
        org_name = entry["name"] if isinstance(entry, dict) and "name" in entry else str(entry)
        mgr.update_state(step="select_org", org_data={"did": body.org_did, "name": org_name})

    state = mgr.get_onboarding_status()
    org_data = (state or {}).get("org_data") or {}
    if not org_data.get("did"):
        raise HTTPException(status_code=400, detail="No organization selected. Call /organizations/select or include org_did.")

    dms_info = get_dms_status_info() or {}
    dms_did = dms_info.get("dms_did")
    dms_peer_id = dms_info.get("dms_peer_id")
    if not dms_did or not dms_peer_id:
        raise HTTPException(status_code=400, detail="DMS not ready (missing DID or Peer ID). Start DMS first.")

    runtime = _collect_runtime_info(mgr)

    payload: Dict[str, Any] = {
        "organization_name": org_data.get("name"),
        "organization_did": org_data.get("did"),
        "dms_did": dms_did,
        "peer_id": dms_peer_id,
        "name": body.name,
        "email": str(body.email),
        "why_join": body.why_join,
        "location": body.location,
        "discord": body.discord,
        "wormhole": body.wormhole,
        # runtime context
        "resources": runtime.get("resources", {}),
        "dms_resources": runtime.get("dms_resources", {}),
        "peer_info": runtime.get("peer_info", {}),
        "dms_status": runtime.get("dms_status", {}),
    }

    # Persist form data
    mgr.update_state(
        step="submit_data",
        form_data={
            "name": body.name,
            "email": str(body.email),
            "why_join": body.why_join,
            "location": body.location,
            "discord": body.discord,
            "wormhole": body.wormhole,
            "dms_did": dms_did,
            "dms_peer_id": dms_peer_id,
            "resources": runtime.get("resources", {}),
        },
    )

    # Submit to org onboarding API
    try:
        api_res = mgr.api_submit_join(payload)
    except Exception as e:
        mgr.update_state(step="rejected", rejection_reason=str(e), last_step="submit_data")
        raise HTTPException(status_code=502, detail=f"onboarding submit failed: {e}")

    request_id = api_res.get("id") or api_res.get("request_id")
    status_token = api_res.get("status_token")
    api_status = api_res.get("status")

    mgr.update_state(
        step="join_data_sent",
        request_id=request_id,
        status_token=status_token,
        api_status=api_status,
        processing=False,
        processed_ok=False,
    )

    return JoinSubmitResponse(
        status="success",
        request_id=request_id,
        status_token=status_token,
        api_status=api_status,
        step="join_data_sent",
        state=mgr.get_onboarding_status(),
    )


@router.get("/join/poll", response_model=PollStatusResponse)
def poll_join(mgr: OnboardingManager = Depends(_mgr), force_check: bool = Query(True)):
    """
    Polls the remote onboarding status. Handles three phases:
      - email_sent / pending -> keeps waiting (advances to pending_authorization after email_verified)
      - ready / approved -> auto-process (exactly once)
      - error / rejected -> marks rejected
    """
    state = mgr.get_onboarding_status()
    req_id = state.get("request_id")
    token = state.get("status_token")

    if state.get("processing"):
        return PollStatusResponse(
            status="processing",
            api_status=state.get("api_status"),
            step=state.get("step", "init"),
            payload_available=bool(state.get("api_payload")),
            state=state,
        )

    if not req_id or not token:
        return PollStatusResponse(
            status="idle",
            api_status=state.get("api_status"),
            step=state.get("step", "init"),
            payload_available=bool(state.get("api_payload")),
            state=state,
        )

    try:
        result = mgr.api_check_status(req_id, token) if force_check else None
    except Exception as e:
        mgr.update_state(step="rejected", rejection_reason=str(e), last_step=state.get("step", "join_data_sent"))
        raise HTTPException(status_code=502, detail=f"status polling failed: {e}")

    api_status = (result or {}).get("status") or state.get("api_status")
    mgr.update_state(api_status=api_status)

    # 1) Email verified -> show pending_authorization
    if api_status == "email_verified":
        if state.get("step") != "pending_authorization":
            mgr.update_state(step="pending_authorization")
        return PollStatusResponse(
            status="pending",
            api_status=api_status,
            step="pending_authorization",
            payload_available=False,
            state=mgr.get_onboarding_status(),
        )

    # 2) Still waiting (pending/processing/email_sent/None)
    if api_status in ("pending", "processing", "email_sent", None, ""):
        next_step = "pending_authorization" if state.get("step") == "pending_authorization" else "join_data_sent"
        if state.get("step") != next_step:
            mgr.update_state(step=next_step)
        return PollStatusResponse(
            status="pending",
            api_status=api_status,
            step=next_step,
            payload_available=bool(state.get("api_payload")),
            state=mgr.get_onboarding_status(),
        )

    # 3) Approved/ready -> auto-process exactly once
    if api_status in ("ready", "approved"):
        if state.get("processed_ok"):
            mgr.update_state(step="complete", status="complete", completed=True)
            return PollStatusResponse(
                status="success",
                api_status=api_status,
                step="complete",
                payload_available=True,
                state=mgr.get_onboarding_status(),
            )

        payload = (result or {}).get("payload") or state.get("api_payload") or (result or {})
        mgr.update_state(processing=True, api_payload=payload, step="join_data_received")

        try:
            ok = mgr.process_post_approval_payload(payload)
            if ok:
                # Do NOT restart DMS automatically; FE has a button for that.
                mgr.update_state(step="complete", status="complete", completed=True, processed_ok=True)
            else:
                mgr.update_state(step="rejected", rejection_reason="post-approval processing failed")
        finally:
            mgr.update_state(processing=False)

        return PollStatusResponse(
            status="success",
            api_status=api_status,
            step=mgr.get_onboarding_status().get("step", "complete"),
            payload_available=True,
            state=mgr.get_onboarding_status(),
        )

    # 4) Error / rejected
    mgr.update_state(
        step="rejected",
        rejection_reason=(result or {}).get("rejection_reason") or (result or {}).get("reason") or "rejected by remote",
    )
    return PollStatusResponse(
        status="error",
        api_status=api_status,
        step="rejected",
        payload_available=bool(state.get("api_payload")),
        state=mgr.get_onboarding_status(),
    )


@router.post("/join/process", response_model=ProcessResponse)
def process_join(mgr: OnboardingManager = Depends(_mgr), restart_dms: bool = Body(True)):
    """
    Back-compat finalize endpoint. Idempotent.
    If already processed, returns success immediately.
    """
    state = mgr.get_onboarding_status()
    if state.get("processed_ok"):
        return ProcessResponse(
            status="success",
            step="complete",
            message="Already processed.",
            state=state,
        )

    payload = state.get("api_payload")
    if not payload:
        raise HTTPException(status_code=400, detail="No onboarding payload available yet. Keep polling until 'join_data_received'.")

    ok = mgr.process_post_approval_payload(payload)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to process onboarding payload")

    if restart_dms:
        mgr.restart_dms_service()

    mgr.update_state(step="complete", status="complete", completed=True, processed_ok=True)
    return ProcessResponse(status="success", step="complete", message="Onboarding complete.", state=mgr.get_onboarding_status())


@router.post("/onboarding/reset")
def reset_onboarding(mgr: OnboardingManager = Depends(_mgr)):
    """
    Cancel/Reset the flow: clears state and re-creates a fresh file with 'init'.
    """
    mgr.clear_state()
    _ensure_state_file(mgr)
    return {"status": "success", "state": mgr.get_onboarding_status()}
