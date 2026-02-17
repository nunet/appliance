# FastAPI Phase 2: Contract Capabilities Application

## Overview
Apply contract capabilities when `contract_caps_ready` status is received, then restart the nunet DMS service. This is the first phase of the two-phase capability granting process.

## Current Implementation Analysis

### Existing Code Structure
- **Capability Application**: `backend/modules/onboarding_manager.py`
  - `generate_and_apply_require_token()` (line 600) - Generates and anchors require tokens
  - `_apply_provide_token()` (line 715) - Anchors provide tokens
  - `process_post_approval_payload()` (line 817) - Currently handles single-phase capability application
- **DMS Restart**: `backend/modules/onboarding_manager.py`
  - `restart_dms_service()` (line 982) - Restarts nunetdms service
- **Status Polling**: `backend/nunet_api/routers/organizations.py`
  - `GET /organizations/join/poll` (line 904) - Polls for status updates
- **Nunet CLI**: `backend/modules/dms_utils.py`
  - `run_dms_command_with_passphrase()` - Executes nunet commands

### Current Flow
1. Status polling receives `ready` or `approved`
2. `process_post_approval_payload()` applies all capabilities at once
3. User manually restarts DMS via button

### Required Changes
1. Detect `contract_caps_ready` status in polling
2. Apply contract capabilities (provide/require tokens)
3. Restart DMS service automatically
4. Notify Organization Manager via `POST /confirm-caps/{id}/?cap_type=contract`

## Implementation Tasks

### Task 2.1: Update Status Polling to Handle contract_caps_ready
**File**: `backend/nunet_api/routers/organizations.py`

**Location**: `GET /organizations/join/poll` endpoint (line 904)

**Change**: Add handling for `contract_caps_ready` status before the `ready/approved` check:

```python
@router.get("/join/poll", response_model=PollStatusResponse)
def poll_join(mgr: OnboardingManager = Depends(_mgr), force_check: bool = Query(True)):
    """
    Polls the remote onboarding status. Handles multiple phases:
      - email_sent / pending -> keeps waiting
      - contract_caps_ready -> apply contract capabilities and restart DMS
      - ready / approved -> auto-process (exactly once)
      - error / rejected -> marks rejected
    """
    state = mgr.get_onboarding_status()
    req_id = state.get("request_id")
    token = state.get("status_token")

    # ... existing early return checks ...

    try:
        result = mgr.api_check_status(req_id, token) if force_check else None
    except Exception as e:
        mgr.update_state(step="rejected", rejection_reason=str(e), last_step=state.get("step", "join_data_sent"))
        raise HTTPException(status_code=502, detail=f"status polling failed: {e}")

    api_status = (result or {}).get("status") or state.get("api_status")
    mgr.update_state(api_status=api_status)

    # NEW: Handle contract_caps_ready status
    if api_status == "contract_caps_ready":
        contract_caps = (result or {}).get("contract_caps") or (result or {}).get("capability_token")
        if contract_caps and not state.get("contract_caps_applied"):
            # Apply contract capabilities
            try:
                success = mgr.apply_contract_capabilities(contract_caps)
                if success:
                    mgr.update_state(
                        step="contract_caps_applied",
                        contract_caps_applied=True,
                        api_status=api_status
                    )
                    # Notify Organization Manager
                    mgr.api_confirm_caps(req_id, token, cap_type="contract")
                else:
                    mgr.update_state(
                        step="rejected",
                        rejection_reason="Failed to apply contract capabilities"
                    )
            except Exception as exc:
                logger.error("Contract capabilities application failed: %s", exc)
                mgr.update_state(
                    step="rejected",
                    rejection_reason=f"Contract capabilities application failed: {exc}"
                )
        
        return PollStatusResponse(
            status="pending",
            api_status=api_status,
            step=state.get("step", "contract_caps_applied"),
            payload_available=False,
            state=mgr.get_onboarding_status(),
        )

    # ... rest of existing status handling ...
```

---

### Task 2.2: Create apply_contract_capabilities Method
**File**: `backend/modules/onboarding_manager.py`

**Location**: After `_apply_provide_token()` method (around line 722)

**New Method**:
```python
def apply_contract_capabilities(self, contract_caps: str) -> bool:
    """
    Apply contract capabilities (require token from known orgs + provide token from org manager) and restart DMS service.
    
    Args:
        contract_caps: The provide capability token for contract interaction from Organization Manager
        
    Returns:
        True if successful, False otherwise
    """
    try:
        self.append_log("contract_caps_applied", "Applying contract capabilities...")
        
        # Get organization DID and role
        org_data = self.state.get("org_data") or {}
        org_did = org_data.get("did") if isinstance(org_data, dict) else None
        if not org_did:
            raise RuntimeError("No organization DID available")
        
        role_id = self.get_selected_role_id()
        
        # Generate and apply require token from known orgs file
        # This generates a require token based on the role's require_template in known_organizations.json
        # The require_template includes caps like /dms/tokenomics/contract, /dms/deployment, /broadcast, /public
        require_success = False
        try:
            self.append_log("contract_caps_applied", "Generating require token from known orgs file...")
            require_success = self.generate_and_apply_require_token(org_did, role_id=role_id)
            if require_success:
                self.append_log("contract_caps_applied", "Require token generated and anchored successfully.")
        except Exception as exc:
            logger.warning("Require token generation failed: %s", exc)
            self.append_log("contract_caps_applied", f"Require token generation failed: {exc}")
            # Continue anyway - provide token might be sufficient
        
        # Anchor the provide token (from Organization Manager)
        self.append_log("contract_caps_applied", "Anchoring contract provide token...")
        self._apply_provide_token(contract_caps)
        self.append_log("contract_caps_applied", "Contract provide token anchored successfully.")
        
        # Restart DMS service
        self.append_log("contract_caps_applied", "Restarting nunet DMS service...")
        restart_success = self.restart_dms_service()
        
        if restart_success:
            self.append_log("contract_caps_applied", "DMS service restarted successfully.")
            return True
        else:
            self.append_log("contract_caps_applied", "DMS service restart failed.")
            return False
            
    except Exception as exc:
        logger.error("Failed to apply contract capabilities: %s", exc)
        self.append_log("contract_caps_applied", f"Failed to apply contract capabilities: {exc}")
        return False
```

**Rationale**: 
- Generates require token from known orgs file using existing `generate_and_apply_require_token()` method
- The require_template in known orgs includes all caps (contract, deployment, broadcast, public)
- Anchors the provide token from Organization Manager
- Restarts DMS service automatically
- Provides logging for debugging
- Handles require token generation failure gracefully (provide token might still work)

---

### Task 2.3: Create api_confirm_caps Method
**File**: `backend/modules/onboarding_manager.py`

**Location**: After `api_check_status()` method (around line 594)

**New Method**:
```python
def api_confirm_caps(self, request_id: str, status_token: str, cap_type: str) -> Dict[str, Any]:
    """
    Notify Organization Manager that capabilities have been applied.
    
    Args:
        request_id: The onboarding request ID
        status_token: The status token for authentication
        cap_type: Either "contract" or "deployment"
        
    Returns:
        Response from Organization Manager API
    """
    if self.use_mock_api:
        self.append_log("capabilities_applied", f"Mock confirm-caps invoked for {cap_type} capabilities.")
        return {"status": "success"}
    
    api_url = self.get_onboarding_api_url()
    if not api_url:
        raise RuntimeError("No onboarding API URL configured for the selected organisation.")
    
    endpoint = f"{api_url.rstrip('/')}/confirm-caps/{request_id}/"
    params = {"status_token": status_token, "cap_type": cap_type}
    
    self.append_log("capabilities_applied", f"Confirming {cap_type} capabilities to {endpoint}")
    
    resp = self.session.post(endpoint, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()
```

**Rationale**: 
- Notifies Organization Manager when capabilities are applied
- Supports both contract and deployment capability types
- Follows existing API interaction patterns

---

### Task 2.4: Update State Structure
**File**: `backend/modules/onboarding_manager.py`

**Location**: `_baseline_state()` method (around line 70)

**Change**: Add contract caps tracking:
```python
@staticmethod
def _baseline_state() -> Dict[str, Any]:
    return {
        # ... existing fields ...
        "contract_caps_applied": False,  # ADD THIS
        "contract_caps": None,  # ADD THIS - store the token
    }
```

---

## Implementation Notes

1. **Require Token Generation**: 
   - Uses existing `generate_and_apply_require_token()` method which reads from `known_organizations.json`
   - The require_template in known orgs includes all caps: `/dms/deployment`, `/dms/tokenomics/contract`, `/broadcast`, `/public`
   - The require token is generated using `nunet cap grant` with these caps and topics
   - The require token is then anchored using `nunet cap anchor --require <token>`
   - This happens BEFORE anchoring the provide token

2. **Provide Token Format**: The `contract_caps` will be a provide token string from the Organization Manager. It should be anchored using `nunet cap anchor -c dms --provide <token>`.

3. **Capability Flow**:
   - **Require token**: Generated locally from known orgs file (what the CP needs from the org)
   - **Provide token**: Received from Organization Manager (what the org grants to the CP)
   - Both are anchored to enable bidirectional contract interaction

4. **DMS Restart Timing**: The DMS must be restarted after anchoring capabilities so the DMS picks up the new capabilities. This is critical for contract interaction to work.

5. **Error Handling**: 
   - If require token generation fails, log warning but continue (provide token might still work)
   - If provide token anchoring fails, mark as rejected
   - If DMS restart fails, log the error but don't necessarily fail the entire process (DMS might still be functional)

6. **Idempotency**: The `contract_caps_applied` flag ensures we don't apply contract capabilities multiple times.

7. **State Transitions**: 
   - `join_data_sent` → `contract_caps_ready` (from API)
   - `contract_caps_ready` → `contract_caps_applied` (after applying)
   - `contract_caps_applied` → wait for contract

---

## Files to Modify

1. `backend/modules/onboarding_manager.py`
   - Add `apply_contract_capabilities()` method
   - Add `api_confirm_caps()` method
   - Update `_baseline_state()` to include contract caps fields

2. `backend/nunet_api/routers/organizations.py`
   - Update `GET /organizations/join/poll` to handle `contract_caps_ready` status

---

## Testing Checklist

- [ ] Status polling detects `contract_caps_ready`
- [ ] Contract capabilities are applied correctly
- [ ] DMS service restarts successfully
- [ ] Organization Manager is notified via confirm-caps endpoint
- [ ] State is updated correctly
- [ ] Error handling works (failed capability application, failed restart)
- [ ] Idempotency works (doesn't apply twice)
- [ ] Logging is comprehensive

---

## Dependencies

- Organization Manager API must support `POST /confirm-caps/{id}/?cap_type=contract`
- Organization Manager API must return `contract_caps_ready` status with `contract_caps` field
- `known_organizations.json` file must exist and contain role profiles with `require_template` for the selected organization and role
- The require_template must include contract-related caps (at minimum `/dms/tokenomics/contract`)

---

## Next Steps

After completing this phase, proceed to **Phase 3: Contract Polling and Detection**.
