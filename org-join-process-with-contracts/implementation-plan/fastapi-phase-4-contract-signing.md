# FastAPI Phase 4: Contract Signing

## Overview
Sign a contract when the user clicks the sign button in the UI. Execute the nunet CLI command to sign the contract and notify the Organization Manager.

## Current Implementation Analysis

### Existing Code Structure
- **Nunet Actor Commands**: `backend/modules/dms_utils.py`
  - `_run_contract_command()` (line 249) - Runs contract-specific commands
- **API Endpoints**: `backend/nunet_api/routers/organizations.py`
  - Various organization endpoints exist
- **State Management**: `backend/modules/onboarding_manager.py`
  - State tracking in `onboarding_state.json`

### Current Flow
- No contract signing exists

### Required Changes
1. Add endpoint: `POST /organizations/contract/sign`
2. Execute `nunet actor cmd /dms/tokenomics/contract/approve_local --contract-did <did>`
3. Notify Organization Manager via `POST /contract-signed/{id}/`
4. Update state to track contract signing

## Implementation Tasks

### Task 4.1: Create Contract Signing Method
**File**: `backend/modules/onboarding_manager.py`

**Location**: After `api_contract_received()` method

**New Method**:
```python
def sign_contract(self, contract_did: str) -> bool:
    """
    Sign a contract using nunet CLI.
    
    Args:
        contract_did: The DID of the contract to sign
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from .dms_utils import _run_contract_command
        
        self.append_log("contract_signed", f"Signing contract: {contract_did}")
        
        # Execute: nunet actor cmd /dms/tokenomics/contract/approve_local --contract-did <did>
        argv, cp = _run_contract_command(
            "/dms/tokenomics/contract/approve_local",
            extra_args=["--contract-did", contract_did],
            timeout=30
        )
        
        if cp.returncode != 0:
            error_msg = cp.stderr or cp.stdout or "Unknown error"
            logger.error("Contract signing failed: %s", error_msg)
            self.append_log("contract_signed", f"Contract signing failed: {error_msg}")
            return False
        
        output = (cp.stdout or "").strip()
        self.append_log("contract_signed", f"Contract signed successfully. Output: {output}")
        return True
        
    except Exception as exc:
        logger.error("Failed to sign contract: %s", exc)
        self.append_log("contract_signed", f"Contract signing error: {exc}")
        return False
```

**Rationale**: 
- Uses existing `_run_contract_command` helper
- Handles errors gracefully
- Provides logging

---

### Task 4.2: Create api_contract_signed Method
**File**: `backend/modules/onboarding_manager.py`

**Location**: After `api_contract_received()` method

**New Method**:
```python
def api_contract_signed(self, request_id: str, status_token: str) -> Dict[str, Any]:
    """
    Notify Organization Manager that a contract has been signed.
    
    Args:
        request_id: The onboarding request ID
        status_token: The status token for authentication
        
    Returns:
        Response from Organization Manager API
    """
    if self.use_mock_api:
        self.append_log("contract_signed", "Mock contract-signed invoked.")
        return {"status": "success"}
    
    api_url = self.get_onboarding_api_url()
    if not api_url:
        raise RuntimeError("No onboarding API URL configured for the selected organisation.")
    
    endpoint = f"{api_url.rstrip('/')}/contract-signed/{request_id}/"
    params = {"status_token": status_token}
    
    self.append_log("contract_signed", f"Notifying contract signed to {endpoint}")
    
    resp = self.session.post(endpoint, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()
```

---

### Task 4.3: Add Contract Signing Endpoint
**File**: `backend/nunet_api/routers/organizations.py`

**Location**: After `POST /organizations/join/submit` endpoint (around line 900)

**New Endpoint**:
```python
@router.post("/contract/sign")
def sign_contract(
    body: Dict[str, str],  # {"contract_did": "..."}
    mgr: OnboardingManager = Depends(_mgr)
):
    """
    Sign a contract.
    
    Request body:
        {
            "contract_did": "did:key:..."
        }
    """
    contract_did = body.get("contract_did")
    if not contract_did:
        raise HTTPException(status_code=400, detail="contract_did is required")
    
    state = mgr.get_onboarding_status()
    request_id = state.get("request_id")
    status_token = state.get("status_token")
    
    if not request_id or not status_token:
        raise HTTPException(
            status_code=400,
            detail="No active onboarding request. Start onboarding first."
        )
    
    # Verify contract exists in state
    contract_data = state.get("contract_data")
    if not contract_data:
        raise HTTPException(
            status_code=400,
            detail="No contract available. Wait for contract to be received."
        )
    
    # Sign the contract
    success = mgr.sign_contract(contract_did)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to sign contract. Check logs for details."
        )
    
    # Notify Organization Manager
    try:
        mgr.api_contract_signed(request_id, status_token)
    except Exception as exc:
        logger.error("Failed to notify contract signed: %s", exc)
        # Don't fail - contract is signed, notification is secondary
    
    # Update state
    mgr.update_state(
        step="contract_signed",
        contract_signed=True,
        api_status="contract_signed"
    )
    
    return {
        "status": "success",
        "message": "Contract signed successfully",
        "contract_did": contract_did
    }
```

**Rationale**: 
- Validates contract exists
- Signs contract via nunet CLI
- Notifies Organization Manager
- Updates state

---

### Task 4.4: Update State Structure
**File**: `backend/modules/onboarding_manager.py`

**Location**: `_baseline_state()` method

**Change**: Add contract signing tracking:
```python
@staticmethod
def _baseline_state() -> Dict[str, Any]:
    return {
        # ... existing fields ...
        "contract_signed": False,  # ADD THIS
    }
```

---

## Implementation Notes

1. **Contract DID**: The contract DID should come from the contract data stored in state (from contract polling).

2. **Error Handling**: If contract signing fails, return an error. If notification fails, log but don't fail (contract is already signed).

3. **State Validation**: Verify that a contract exists before allowing signing.

4. **Idempotency**: Check if contract is already signed before signing again.

5. **State Transitions**:
   - `contract_received` → `contract_signed` (after signing)

---

## Files to Modify

1. `backend/modules/onboarding_manager.py`
   - Add `sign_contract()` method
   - Add `api_contract_signed()` method
   - Update `_baseline_state()` to include `contract_signed` field

2. `backend/nunet_api/routers/organizations.py`
   - Add `POST /organizations/contract/sign` endpoint

---

## Testing Checklist

- [ ] Endpoint validates contract_did
- [ ] Endpoint validates contract exists
- [ ] Contract signing executes correctly
- [ ] Organization Manager is notified
- [ ] State is updated correctly
- [ ] Error handling works (invalid DID, signing failure, notification failure)
- [ ] Idempotency works (doesn't sign twice)

---

## Dependencies

- Organization Manager API must support `POST /contract-signed/{id}/`
- DMS must support `nunet actor cmd /dms/tokenomics/contract/approve_local`
- Contract must be available in state (from contract polling)

---

## Next Steps

After completing this phase, proceed to **Phase 5: Deployment Capabilities Application**.
