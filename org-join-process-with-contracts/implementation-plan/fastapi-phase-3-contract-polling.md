# FastAPI Phase 3: Contract Polling and Detection

## Overview
Poll the DMS for incoming contracts and detect when a contract arrives. When detected, notify the Organization Manager.

## Current Implementation Analysis

### Existing Code Structure
- **Nunet Actor Commands**: `backend/modules/dms_utils.py`
  - `_run_actor_command()` (line 239) - Runs nunet actor commands
  - `_run_contract_command()` (line 249) - Runs contract-specific commands
  - `_run_contracts_command()` (line 267) - Runs contracts list commands
- **Status Polling**: `backend/nunet_api/routers/organizations.py`
  - `GET /organizations/join/poll` (line 904) - Current polling endpoint
- **DMS Utils**: `backend/modules/dms_utils.py` - Has contract command helpers

### Current Flow
- Status polling only checks Organization Manager API
- No contract polling exists

### Required Changes
1. Integrate contract polling into status polling loop
2. Execute `nunet actor cmd /contract/list_incoming`
3. Parse contract list response
4. Detect new contracts
5. Notify Organization Manager via `POST /contract-received/{id}/`

## Implementation Tasks

### Task 3.1: Create Contract Polling Method
**File**: `backend/modules/onboarding_manager.py`

**Location**: After `api_check_status()` method (around line 594)

**New Method**:
```python
def poll_for_contracts(self, request_id: str) -> Optional[Dict[str, Any]]:
    """
    Poll DMS for incoming contracts.
    
    Args:
        request_id: The onboarding request ID (for logging)
        
    Returns:
        Contract data if found, None otherwise
    """
    try:
        from .dms_utils import _run_contract_command
        
        # Execute: nunet actor cmd /contract/list_incoming
        argv, cp = _run_contract_command(
            "/dms/tokenomics/contract/list_incoming",
            timeout=15
        )
        
        if cp.returncode != 0:
            logger.debug("Contract list command failed: %s", cp.stderr or cp.stdout)
            return None
        
        # Parse response - should be JSON array of contracts
        output = (cp.stdout or "").strip()
        if not output:
            return None
        
        try:
            contracts = json.loads(output)
            if not isinstance(contracts, list):
                contracts = [contracts] if contracts else []
        except json.JSONDecodeError:
            logger.warning("Failed to parse contract list response: %s", output)
            return None
        
        # Check for new contracts (compare with previously seen)
        seen_contracts = set(self.state.get("seen_contract_dids", []))
        new_contracts = [
            contract for contract in contracts
            if isinstance(contract, dict) and contract.get("did") not in seen_contracts
        ]
        
        if new_contracts:
            # Store seen contract DIDs
            all_dids = seen_contracts | {c.get("did") for c in new_contracts if c.get("did")}
            self.update_state(seen_contract_dids=list(all_dids))
            
            # Return the first new contract (or all if needed)
            contract = new_contracts[0]
            self.append_log("contract_received", f"Contract detected: {contract.get('did', 'unknown')}")
            return contract
        
        return None
        
    except Exception as exc:
        logger.error("Contract polling failed: %s", exc)
        self.append_log("contract_received", f"Contract polling error: {exc}")
        return None
```

**Rationale**: 
- Uses existing `_run_contract_command` helper
- Parses JSON response
- Tracks seen contracts to avoid duplicates
- Returns contract data when found

---

### Task 3.2: Create api_contract_received Method
**File**: `backend/modules/onboarding_manager.py`

**Location**: After `api_confirm_caps()` method

**New Method**:
```python
def api_contract_received(self, request_id: str, status_token: str) -> Dict[str, Any]:
    """
    Notify Organization Manager that a contract has been received.
    
    Args:
        request_id: The onboarding request ID
        status_token: The status token for authentication
        
    Returns:
        Response from Organization Manager API
    """
    if self.use_mock_api:
        self.append_log("contract_received", "Mock contract-received invoked.")
        return {"status": "success"}
    
    api_url = self.get_onboarding_api_url()
    if not api_url:
        raise RuntimeError("No onboarding API URL configured for the selected organisation.")
    
    endpoint = f"{api_url.rstrip('/')}/contract-received/{request_id}/"
    params = {"status_token": status_token}
    
    self.append_log("contract_received", f"Notifying contract received to {endpoint}")
    
    resp = self.session.post(endpoint, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()
```

---

### Task 3.3: Integrate Contract Polling into Status Polling
**File**: `backend/nunet_api/routers/organizations.py`

**Location**: `GET /organizations/join/poll` endpoint (line 904)

**Change**: Add contract polling after contract_caps_applied status:

```python
@router.get("/join/poll", response_model=PollStatusResponse)
def poll_join(mgr: OnboardingManager = Depends(_mgr), force_check: bool = Query(True)):
    # ... existing code ...
    
    # After contract_caps_applied status check, add contract polling
    if state.get("step") == "contract_caps_applied" or state.get("contract_caps_applied"):
        # Poll for contracts
        contract = mgr.poll_for_contracts(req_id)
        if contract:
            # Contract detected
            try:
                mgr.api_contract_received(req_id, token)
                mgr.update_state(
                    step="contract_received",
                    contract_data=contract,
                    api_status="contract_received"
                )
            except Exception as exc:
                logger.error("Failed to notify contract received: %s", exc)
                # Don't fail the entire process, just log
        
        return PollStatusResponse(
            status="pending",
            api_status=state.get("api_status", "contract_caps_applied"),
            step=state.get("step", "contract_caps_applied"),
            payload_available=False,
            state=mgr.get_onboarding_status(),
        )
    
    # ... rest of existing code ...
```

**Rationale**: 
- Polls for contracts only after contract caps are applied
- Notifies Organization Manager when contract is detected
- Updates state to track contract receipt

---

### Task 3.4: Update State Structure
**File**: `backend/modules/onboarding_manager.py`

**Location**: `_baseline_state()` method

**Change**: Add contract tracking fields:
```python
@staticmethod
def _baseline_state() -> Dict[str, Any]:
    return {
        # ... existing fields ...
        "seen_contract_dids": [],  # ADD THIS
        "contract_data": None,  # ADD THIS
    }
```

---

## Implementation Notes

1. **Polling Frequency**: Contract polling should happen during the status polling loop (every 5 seconds). Don't create a separate polling loop.

2. **Contract Detection**: Track seen contract DIDs to avoid processing the same contract multiple times.

3. **Error Handling**: If contract polling fails, don't fail the entire process. Just log and continue.

4. **Contract Format**: The contract list response should be a JSON array. Each contract should have at least a `did` field.

5. **State Transitions**:
   - `contract_caps_applied` → `contract_received` (when contract detected)

---

## Files to Modify

1. `backend/modules/onboarding_manager.py`
   - Add `poll_for_contracts()` method
   - Add `api_contract_received()` method
   - Update `_baseline_state()` to include contract tracking fields

2. `backend/nunet_api/routers/organizations.py`
   - Update `GET /organizations/join/poll` to include contract polling

---

## Testing Checklist

- [ ] Contract polling executes correctly
- [ ] Contract list response is parsed correctly
- [ ] New contracts are detected
- [ ] Previously seen contracts are ignored
- [ ] Organization Manager is notified when contract detected
- [ ] State is updated correctly
- [ ] Error handling works (failed polling, failed notification)
- [ ] Polling doesn't interfere with status polling

---

## Dependencies

- Organization Manager API must support `POST /contract-received/{id}/`
- DMS must support `nunet actor cmd /dms/tokenomics/contract/list_incoming`
- Contract list response must be JSON format

---

## Next Steps

After completing this phase, proceed to **Phase 4: Contract Signing**.
