from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Body, Depends, Query
from pydantic import BaseModel, EmailStr, Field

from modules.onboarding_manager import OnboardingManager
from modules.organization_manager import OrganizationManager
from modules.org_utils import load_known_organizations, get_joined_organizations_with_names
from modules.dms_utils import get_dms_status_info, get_dms_resource_info

router = APIRouter()  # main.py already applies prefix="/organizations" and tags

# Reuse single instances so in-memory state persists
_onboarding = OnboardingManager()
_org_mgr = OrganizationManager()

STEP_DEFS = [
    {"id": "init",                   "label": "Init"},
    {"id": "select_org",             "label": "Select Organization"},
    {"id": "collect_join_data",      "label": "Fill Join Form"},
    {"id": "submit_data",            "label": "Submit Data"},
    {"id": "join_data_sent",         "label": "Data Sent"},
    {"id": "email_verified",         "label": "Email Verified", "virtual": True},  # virtual step (driven by api_status)
    {"id": "pending_authorization",  "label": "Pending Authorization"},
    {"id": "join_data_received",     "label": "Join Data Received"},
    {"id": "capabilities_applied",   "label": "Capabilities Applied"},
    {"id": "telemetry_configured",   "label": "Telemetry Configured"},
    {"id": "mtls_certs_saved",       "label": "mTLS Certs Saved"},
    {"id": "complete",               "label": "Complete"},
    {"id": "rejected",               "label": "Rejected"},
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
    "telemetry_configured": 85,
    "mtls_certs_saved": 90,
    "complete": 100,
    "rejected": 100,
}

ANSI_RE = re.compile(r'\x1B\[[0-9;]*m')

def _ensure_state_file(mgr: OnboardingManager):
    """
    If the legacy systemd web service didn't create the onboarding state file,
    create a minimal one so mgr.save_state() can persist logs/state.
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
                "logs": []
            }
            p.write_text(json.dumps(initial, indent=2))
            mgr.state = initial
    except Exception:
        # Non-fatal; we can proceed with in-memory state only.
        pass

def _mgr() -> OnboardingManager:
    _ensure_state_file(_onboarding)
    return _onboarding

# ---------- Schemas (no roles field for compatibility) ----------

class SelectOrgRequest(BaseModel):
    org_did: str = Field(..., description="Organization DID to join")

class WormholeResponse(BaseModel):
    status: str
    wormhole_code: Optional[str] = None
    message: Optional[str] = None
    output: Optional[str] = None

class JoinSubmitRequest(BaseModel):
    # org_did is optional if already selected via /organizations/select
    org_did: Optional[str] = Field(None, description="Organization DID (optional if already selected)")
    name: str
    email: EmailStr
    why_join: Optional[str] = None
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
    status: str
    api_status: Optional[str] = None
    step: str
    payload_available: bool
    state: Dict[str, Any]

class ProcessResponse(BaseModel):
    status: str
    step: str
    message: Optional[str] = None
    state: Dict[str, Any]


class SelectOrgIn(BaseModel):
    org_did: str
# ---------- Helpers to gather runtime info (match the old flow) ----------

def _collect_runtime_info(mgr: OnboardingManager) -> Dict[str, Any]:
    """
    Collect the same runtime data the old web flow attached or displayed:
    - DMS status (includes DID/Peer ID, version, etc. if available)
    - Peer info (public/local addrs, context)
    - Onboarded resources (boolean + cleaned string)
    - dms_resources (raw snapshot)
    """
    runtime: Dict[str, Any] = {}

    # DMS status (contains DMS DID / Peer ID and possibly more fields)
    dms_info = get_dms_status_info() or {}
    runtime["dms_status"] = dms_info

    # Peer info (local/public IPs, context)
    try:
        peer_info = mgr.dms_manager.get_self_peer_info() or {}
        runtime["peer_info"] = {
            "did":            peer_info.get("did"),
            "peer_id":        peer_info.get("peer_id"),
            "context":        peer_info.get("context"),
            "public_addrs":   peer_info.get("public_addrs"),
            "local_addrs":    peer_info.get("local_addrs"),
        }
    except Exception:
        runtime["peer_info"] = {}

    # Onboarded resources + raw dms_resources block
    try:
        res_info = get_dms_resource_info() or {}
        onboarding_status = res_info.get("onboarding_status", "Unknown")
        onboarded_resources = res_info.get("onboarded_resources", "Unknown")
        clean_resources = onboarded_resources
        if isinstance(clean_resources, str):
            clean_resources = ANSI_RE.sub("", clean_resources)

        runtime["resources"] = {
            "onboarding_status": ("ONBOARDED" in onboarding_status),
            "onboarded_resources": clean_resources
        }
        runtime["dms_resources"] = res_info.get("dms_resources", {})
    except Exception:
        runtime["resources"] = {
            "onboarding_status": False,
            "onboarded_resources": "Unknown (collection failed)"
        }
        runtime["dms_resources"] = {}

    return runtime

# ---------- Endpoints ----------

@router.get("/known")
def get_known():
    """Known orgs from org_utils.load_known_organizations()."""
    return load_known_organizations()

@router.get("/joined")
def get_joined():
    """Already joined orgs with names."""
    return get_joined_organizations_with_names()

@router.get("/status")
def status(mgr: OnboardingManager = Depends(_mgr)):
    """
    Return enriched, UI-friendly onboarding status:
    - current_step, step_states (done/active/todo), progress
    - api_status, ui_state/ui_message
    - logs
    - raw state (for debugging)
    """
    state = mgr.get_onboarding_status()
    return _enrich_status_for_ui(state)

@router.get("/steps")
def steps():
    return {
        "steps": [{"id": s["id"], "label": s["label"], "virtual": s.get("virtual", False)} for s in STEP_DEFS],
        "progress_map": PROGRESS_MAP
    }



@router.post("/select")
def select_org(body: SelectOrgIn):
    om = OnboardingManager()

    # Resolve org name from known orgs (fallback = DID)
    known = load_known_organizations() or {}
    org_entry = known.get(body.org_did, {})
    org_name = org_entry["name"] if isinstance(org_entry, dict) and "name" in org_entry else body.org_did

    # Save org_data
    om.update_state(org_data={"did": body.org_did, "name": org_name})

    om.update_state(step="collect_join_data")

    state = om.get_onboarding_status()
    return {
        "status": "success",
        "message": f"Selected organization {org_name}",
        "state": state,
    }

@router.post("/wormhole", response_model=WormholeResponse)
def generate_wormhole():
    """
    Optional: for orgs that still use the wormhole pairing script (join-org-web.sh).
    """
    return WormholeResponse(**_org_mgr.join_organization(step="generate"))

@router.post("/join/submit", response_model=JoinSubmitResponse)
def submit_join(
    body: JoinSubmitRequest,
    mgr: OnboardingManager = Depends(_mgr)
):
    # Allow org selection here too (single-call UX)
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

    # DMS identifiers are required
    dms_info = get_dms_status_info() or {}
    dms_did = dms_info.get("dms_did")
    dms_peer_id = dms_info.get("dms_peer_id")
    if not dms_did or not dms_peer_id:
        raise HTTPException(status_code=400, detail="DMS not ready (missing DID or Peer ID). Start DMS first.")

    # Collect runtime info 
    runtime = _collect_runtime_info(mgr)

    # Build payload :
    payload: Dict[str, Any] = {
        # ---- required org + dms context ----
        "organization_name": org_data.get("name"),
        "organization_did":  org_data.get("did"),
        "dms_did":           dms_did,
        "peer_id":           dms_peer_id,

        # ---- user inputs ----
        "name":     body.name,
        "email":    str(body.email),
        "why_join": body.why_join,
        "location": body.location,
        "discord":  body.discord,
        "wormhole": body.wormhole,

        # ---- runtime (for parity & richer telemetry at the API) ----
        # These two keys are *also* added inside api_submit_join(); sending them
        "resources":     runtime.get("resources", {}),
        "dms_resources": runtime.get("dms_resources", {}),

        # Extra context
        "peer_info":     runtime.get("peer_info", {}),
        "dms_status":    runtime.get("dms_status", {}),
    }

    # Persist the same style of state
    form_state = {
        "name": body.name,
        "email": str(body.email),
        "why_join": body.why_join,
        "location": body.location,
        "discord": body.discord,
        "wormhole": body.wormhole,
        "dms_did": dms_did,
        "dms_peer_id": dms_peer_id,
        "resources": runtime.get("resources", {}),
    }
    mgr.update_state(step="submit_data", form_data=form_state)

    try:
        api_res = mgr.api_submit_join(payload)
    except Exception as e:
        # Keep state consistent on error
        mgr.update_state(step="rejected", rejection_reason=str(e), last_step="submit_data")
        raise HTTPException(status_code=502, detail=f"onboarding submit failed: {e}")

    request_id = api_res.get("id") or api_res.get("request_id")
    status_token = api_res.get("status_token")
    api_status = api_res.get("status")
    mgr.update_state(step="join_data_sent", request_id=request_id, status_token=status_token, api_status=api_status)

    return JoinSubmitResponse(
        status="success",
        request_id=request_id,
        status_token=status_token,
        api_status=api_status,
        step="join_data_sent",
        state=mgr.get_onboarding_status()
    )

@router.get("/join/poll", response_model=PollStatusResponse)
def poll_join(mgr: OnboardingManager = Depends(_mgr), force_check: bool = Query(True)):
    state = mgr.get_onboarding_status()
    req_id = state.get("request_id")
    token = state.get("status_token")

    if not req_id or not token:
        return PollStatusResponse(
            status="idle",
            api_status=state.get("api_status"),
            step=state.get("step", "init"),
            payload_available=bool(state.get("api_payload")),
            state=state
        )

    result = None
    try:
        if force_check:
            result = mgr.api_check_status(req_id, token)
    except Exception as e:
        mgr.update_state(step="rejected", rejection_reason=str(e), last_step="join_data_sent")
        raise HTTPException(status_code=502, detail=f"status polling failed: {e}")

    api_status = (result or {}).get("status") or state.get("api_status")

    if api_status in ["ready", "approved", "error", "rejected"]:
        payload = (result or {}).get("payload") or result or {}
        mgr.update_state(step="join_data_received", api_status=api_status, api_payload=payload, last_step="join_data_sent")
        state = mgr.get_onboarding_status()
        return PollStatusResponse(
            status="success",
            api_status=api_status,
            step="join_data_received",
            payload_available=True,
            state=state
        )

    # still pending
    mgr.update_state(api_status=api_status)
    state = mgr.get_onboarding_status()
    return PollStatusResponse(
        status="pending",
        api_status=api_status,
        step=state.get("step", "join_data_sent"),
        payload_available=bool(state.get("api_payload")),
        state=state
    )

@router.post("/join/process", response_model=ProcessResponse)
def process_join(mgr: OnboardingManager = Depends(_mgr), restart_dms: bool = Body(True)):
    state = mgr.get_onboarding_status()
    payload = state.get("api_payload")
    if not payload:
        raise HTTPException(status_code=400, detail="No onboarding payload available yet. Keep polling until 'join_data_received'.")

    ok = mgr.process_post_approval_payload(payload)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to process onboarding payload")

    if restart_dms:
        ok = mgr.restart_dms_service()
        if not ok:
            raise HTTPException(status_code=500, detail="Processed OK, but failed to restart DMS")

    mgr.update_state(step="complete", status="complete", completed=True)

    return ProcessResponse(
        status="success",
        step="complete",
        message="Onboarding complete.",
        state=mgr.get_onboarding_status()
    )

@router.post("/onboarding/reset")
def reset_onboarding(mgr: OnboardingManager = Depends(_mgr)):
    mgr.clear_state()
    _ensure_state_file(mgr)
    return {"status": "success", "state": mgr.get_onboarding_status()}


def _resolve_current_step_from_state(state: dict) -> str:
    """
    Decide which step is 'current' using:
    - explicit 'step'
    - last log's step
    - api_status 'email_verified' as a virtual step when applicable
    """
    step = state.get("step")
    logs = state.get("logs") or []
    api_status = state.get("api_status")

    # If logs carry a more recent step, prefer it
    if logs:
        last = logs[-1]
        if isinstance(last, dict) and "step" in last and last["step"]:
            step = last["step"]

    # Promote to virtual 'email_verified' when API says so
    if api_status == "email_verified":
        return "email_verified"

    # Fall back safely
    ids = [s["id"] for s in STEP_DEFS]
    return step if step in ids else "init"

def _compute_step_states(current_step: str) -> dict:
    """
    Build a step timeline with 'done'/'active'/'todo' flags.
    """
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
        step_states.append({
            "id": s["id"],
            "label": s["label"],
            "virtual": s.get("virtual", False),
            "state": state
        })
    return {
        "current_step": current_step,
        "current_index": current_index,
        "step_states": step_states,
    }

def _get_onboarding_ui_state_and_message(onboarding_status: dict) -> tuple[str, str]:
    """
    Port of the old get_onboarding_ui_state() logic, simplified for API.
    Returns (ui_state, ui_message)
    """
    step = onboarding_status.get('step')
    api_status = onboarding_status.get('api_status')
    rejection_reason = onboarding_status.get('rejection_reason', '')
    error = onboarding_status.get('error')
    org_name = onboarding_status.get('org_data', {}).get('name', 'the organization')

    # Data ready
    if step == 'collect_join_data' and onboarding_status.get('form_data'):
        return ('data_ready', "Your join data is ready. Preparing to submit to the organization's onboarding service...")
    # Waiting for API available
    if step == 'submit_data' and not api_status:
        return ('waiting_api', "Waiting for the organization's onboarding service to become available...")
    # Data submitted
    if step == 'join_data_sent' and api_status in [None, '', 'pending', 'processing', 'email_sent']:
        return ('data_submitted', 'Your join data has been submitted to the organization. Awaiting further instructions...')
    # Email verified
    if api_status == 'email_verified':
        return ('email_verified', 'Your email has been verified! Waiting for organization approval...')
    # Waiting for approval
    if step == 'join_data_sent' and api_status in ['pending', 'processing']:
        return ('waiting_approval', 'Your request is being reviewed by the organization. Please wait for approval.')
    # Approved / Payload ready
    if step in ['pending_authorization', 'join_data_received'] or (step == 'join_data_sent' and api_status in ['approved', 'ready']):
        return ('approved', 'Your request has been approved! Finalizing onboarding...')
    # Capabilities applied
    if step == 'capabilities_applied':
        return ('capabilities_applied', 'Applying organization capabilities...')
    # Telemetry configured
    if step == 'telemetry_configured':
        return ('telemetry_configured', 'Configuring telemetry...')
    # mTLS certs saved
    if step == 'mtls_certs_saved':
        return ('mtls_certs_saved', 'Saving mTLS certificates...')
    # Complete
    if step == 'complete':
        return ('complete', f'Onboarding complete! You are now a member of {org_name}.')
    # Rejected
    if step == 'rejected' and rejection_reason:
        return ('rejected', f'Your onboarding request was rejected. Reason: {rejection_reason}')
    # Error
    if error:
        return ('error', f'An error occurred: {error}')
    # Default
    return (step or 'init', f'Current step: {step or "init"}')

def _enrich_status_for_ui(state: dict) -> dict:
    """
    Compose a UI-friendly JSON with timeline, progress, messages, plus raw state.
    """
    current_step = _resolve_current_step_from_state(state)
    timeline = _compute_step_states(current_step)
    ui_state, ui_message = _get_onboarding_ui_state_and_message(state)

    # prefer state.progress if provided; else map from current step
    progress = state.get("progress")
    if progress is None:
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
        # Keep the raw state for debugging/advanced UI needs
        "raw": state,
    }
