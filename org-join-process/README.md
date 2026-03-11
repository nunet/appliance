# Organization Join Process - Complete Flow Analysis

## Overview

This document describes the complete organization onboarding flow in the NuNet Appliance application, covering the interaction between the React frontend, FastAPI backend, and external organization onboarding APIs.

> **📚 For complete end-to-end solution documentation**, see [END_TO_END_SOLUTION.md](END_TO_END_SOLUTION.md) which covers all three components (Appliance, Organization Manager, and Onboarding Worker) and their interactions.

## Architecture Components

1. **Frontend (React/TypeScript)**: `Organizations.tsx` and `OnboardFlow.tsx`
2. **Backend FastAPI Service**: `nunet-appliance-web.service` (runs the FastAPI app)
3. **Onboarding Manager**: `onboarding_manager.py` - Core state and API interaction logic
4. **Organization Router**: `organizations.py` - FastAPI endpoints
5. **External Organization APIs**: Remote onboarding services (e.g., `https://spo.parallelvector.com/api`)

---

## Process Diagrams

Visual diagrams of the organization join process are available as separate Mermaid files:

1. **[State Machine Diagram](01-state-machine.mmd)** - Shows all states and transitions
2. **[Sequence Diagram](02-sequence-diagram.mmd)** - Detailed interaction sequence between components
3. **[Process Flowchart](03-process-flowchart.mmd)** - Complete decision tree and process flow
4. **[Component Interaction Diagram](04-component-interaction.mmd)** - Architecture overview

---

## Complete State Machine / Steps

### Step Definitions (from `organizations.py`)

| Step ID | Label | Progress | Description |
|---------|-------|----------|-------------|
| `init` | Init | 0% | Initial state, no onboarding started |
| `select_org` | Select Organization | 10% | User selects an organization to join |
| `collect_join_data` | Fill Join Form | 20% | User fills out the join form |
| `submit_data` | Submit Data | 30% | Form data being prepared and submitted |
| `join_data_sent` | Data Sent | 40% | Data successfully sent to organization API |
| `email_verified` | Email Verified | 50% | Virtual step - email verification completed |
| `pending_authorization` | Pending Authorization | 60% | Waiting for organization approval |
| `join_data_received` | Join Data Received | 70% | Approval payload received from organization |
| `capabilities_applied` | Capabilities Applied | 80% | Capability tokens generated and anchored |
| `capabilities_onboarded` | Capabilities Onboarded | 83% | Compute resources onboarded with new capabilities |
| `telemetry_configured` | Telemetry Configured | 85% | Observability/telemetry configured |
| `mtls_certs_saved` | mTLS Certs Saved | 90% | Mutual TLS certificates written |
| `complete` | Complete | 100% | Onboarding fully completed |
| `rejected` | Rejected | 100% | Request was rejected by organization |

---

## Detailed Flow Process

### Phase 1: Initialization & Organization Selection

#### 1.1 Frontend Loads Known Organizations
- **UI Action**: User navigates to `/organizations` page
- **Frontend**: `Organizations.tsx` calls `organizationsApi.getKnownOrgs()`
- **API Call**: `GET /organizations/known`
- **Backend**: `organizations.py::get_known()` → `load_known_organizations()`
- **Data Source**: Reads `known_orgs/known_organizations.json`
- **Response**: Returns organization metadata including:
  - `name`: Organization display name
  - `onboarding_api_url`: External API endpoint
  - `join_fields`: Required form fields
  - `roles`: Available roles with `require_template` (capabilities)
  - `tokenomics`: Wallet requirements (if any)

#### 1.2 User Selects Organization
- **UI Action**: User clicks on an organization card
- **Frontend**: `OnboardFlow.tsx` calls `selectMutation.mutate(org_did)`
- **API Call**: `POST /organizations/select` with `{ org_did: string }`
- **Backend**: `organizations.py::select_org()`
  - Loads organization entry from known orgs
  - Extracts roles, role profiles, tokenomics config
  - Updates onboarding state:
    ```python
    mgr.update_state(
        org_data={
            "did": org_did,
            "name": org_name,
            "roles": roles,
            "role_profiles": role_profiles,
            "selected_role": default_role,
            "tokenomics": tokenomics,
        },
        step="collect_join_data",
        # Clear previous request data
        request_id=None,
        status_token=None,
        api_status=None,
    )
    ```
- **State File**: Persisted to `~/.nunet/appliance/onboarding_state.json`

---

### Phase 2: Form Collection & Validation

#### 2.1 User Fills Join Form
- **UI Component**: `JoinForm.tsx` displays form fields
- **Fields Collected**:
  - `name`: User's name
  - `email`: Email address (required)
  - `roles`: Selected role(s) from organization's available roles
  - `why_join`: Optional reason for joining
  - `location`: City, Country (if required by org)
  - `discord`: Discord username (optional)
  - `wormhole`: Wormhole code (if required by org)
  - `wallet_address`: Blockchain wallet (if tokenomics enabled)
  - `wallet_chain`: "cardano" | "ethereum" (if wallet required)

#### 2.2 Frontend Validates Form
- Validates required fields based on `join_fields` from org config
- Validates role selection against allowed roles
- Validates wallet requirements if `tokenomics.enabled === true`
- Validates wallet chain is in allowlist: `["cardano", "ethereum"]`

---

### Phase 3: Data Submission

#### 3.1 Frontend Submits Join Request
- **UI Action**: User clicks "Submit" button
- **Frontend**: `OnboardFlow.tsx` calls `joinMutation.mutate(formData)`
- **API Call**: `POST /organizations/join/submit` with `JoinSubmitRequest`

#### 3.2 Backend Validates & Prepares Payload
- **Endpoint**: `organizations.py::submit_join()`
- **Validation Steps**:
  1. Verifies organization is known
  2. Validates role selection against org's allowed roles
  3. Validates wallet requirements if tokenomics enabled
  4. Ensures DMS is ready (has DID and Peer ID)

#### 3.3 Backend Captures Compute Resources
- **Action**: `mgr.ensure_pre_onboarding()`
- **Process**:
  1. Checks if DMS reports `ONBOARDED` status
  2. If not, runs `dms_manager.onboard_compute()` script
  3. Polls DMS (up to 6 attempts, 5s delay) until `ONBOARDED`
  4. Collects resource snapshot:
     - `onboarding_status`: Boolean flag
     - `onboarded_resources`: Hardware summary string
     - `dms_resources`: Detailed hardware dict (CPU, RAM, disk, GPUs)
     - `free_resources`: Available resources
     - `allocated_resources`: Currently allocated resources

#### 3.4 Backend Builds Submission Payload
- **Payload Structure**:
  ```python
  {
      "organization_name": org_name,
      "organization_did": org_did,
      "dms_did": dms_did,
      "peer_id": dms_peer_id,
      "name": user_name,
      "email": user_email,
      "roles": selected_roles,
      "why_join": why_join,
      "location": location,
      "discord": discord,
      "wormhole": wormhole_code,
      "wallet_address": wallet_address,
      "wallet_chain": wallet_chain,
      "tokenomics": tokenomics_config,
      "is_renewal": renewal_flag,
      "renewing_previous": previous_request_id,
      # Runtime context
      "resources": {
          "onboarding_status": bool,
          "onboarded_resources": str,
      },
      "dms_resources": {...},
      "peer_info": {...},
      "dms_status": {...},
  }
  ```

#### 3.5 Backend Submits to Organization API
- **Action**: `mgr.api_submit_join(payload, resource_snapshot)`
- **Process**:
  1. Resolves organization's `onboarding_api_url` from known orgs
  2. Constructs endpoint: `{api_url}/onboarding/submit/`
  3. Makes HTTP POST request with JSON payload (30s timeout)
  4. Handles response:
     ```python
     {
         "id": request_id,  # or "request_id"
         "status_token": status_token,
         "status": api_status,  # "pending", "email_sent", etc.
     }
     ```
- **State Update**:
  ```python
  mgr.update_state(
      step="join_data_sent",
      request_id=request_id,
      status_token=status_token,
      api_status=api_status,
      form_data={...},  # Persist form data
  )
  ```

---

### Phase 4: Polling & Status Updates

#### 4.1 Frontend Starts Polling
- **Trigger**: When `currentStep === "join_data_sent"` or `apiStatus` indicates waiting
- **Frontend**: `OnboardFlow.tsx` uses React Query with:
  ```typescript
  useQuery({
      queryKey: ["email-poll", currentStep, apiStatus],
      queryFn: () => organizationsApi.poll(),
      refetchInterval: 5000,  // Every 5 seconds
      enabled: shouldPoll && !complete && !rejected,
  })
  ```

#### 4.2 Backend Polls Organization API
- **Endpoint**: `GET /organizations/join/poll`
- **Backend**: `organizations.py::poll_join()`
- **Process**:
  1. Checks if already processing (prevents duplicate processing)
  2. Retrieves `request_id` and `status_token` from state
  3. Calls `mgr.api_check_status(request_id, status_token)`
     - Endpoint: `{api_url}/onboarding/status/{request_id}/?status_token={token}`
     - Timeout: 15 seconds
  4. Updates state with `api_status` from response

#### 4.3 Status State Machine (Backend)
- **Status: `email_sent` / `pending` / `processing`**
  - Updates step to `pending_authorization` (if not already)
  - Returns `status="pending"` to frontend
  - Continues polling

- **Status: `email_verified`**
  - Updates step to `pending_authorization`
  - Returns `status="pending"` to frontend
  - Continues polling

- **Status: `ready` / `approved`**
  - **Auto-processing** (if not already processed):
    1. Sets `processing=True` in state
    2. Extracts `payload` from API response
    3. Updates state: `step="join_data_received"`, `api_payload=payload`
    4. Calls `mgr.process_post_approval_payload(payload)` (see Phase 5)
    5. On success: `step="complete"`, `processed_ok=True`
    6. Sets `processing=False`
  - Returns `status="success"` to frontend

- **Status: `error` / `rejected`**
  - Updates state: `step="rejected"`, `rejection_reason=...`
  - Returns `status="error"` to frontend
  - Stops polling

---

### Phase 5: Post-Approval Processing

#### 5.1 Process Approval Payload
- **Method**: `onboarding_manager.py::process_post_approval_payload()`
- **Payload Contains**:
  - `capability_token` / `provide_token`: Token from organization
  - `client_crt`, `client_key`, `infra_bundle_crt`: mTLS certificates
  - `elasticsearch_api_key`, `elasticsearch_url`: Telemetry config
  - `organization_did`: Organization identifier

#### 5.2 Generate Require Token
- **Action**: `mgr.generate_and_apply_require_token(org_did, role_id)`
- **Process**:
  1. Loads role profile from state or known orgs
  2. Extracts `require_template`:
     - `context`: Usually "dms"
     - `caps`: Capability paths (e.g., `["/dms/deployment", "/dms/tokenomics/contract"]`)
     - `topics`: Topic subscriptions (e.g., `["/nunet"]`)
  3. Calculates expiry (default: 30 days from now)
  4. Runs `nunet cap grant` command:
     ```bash
     nunet cap grant \
         --context dms \
         --cap /dms/deployment \
         --cap /dms/tokenomics/contract \
         --topic /nunet \
         --expiry 2024-02-15T12:00:00Z \
         {org_did}
     ```
  5. Anchors token: `nunet cap anchor -c dms --require {token}`
  6. Logs success to onboarding state

#### 5.3 Apply Provide Token
- **Action**: `mgr._apply_provide_token(provide_token)`
- **Process**:
  - Runs: `nunet cap anchor -c dms --provide {provide_token}`
  - Anchors the organization's capability token

#### 5.4 Configure Observability
- **Action**: `mgr._configure_observability(payload)`
- **Process**:
  - Extracts `elasticsearch_api_key` and `elasticsearch_url` from payload
  - Updates `nunet` config file via `nunet config set` commands:
    - `observability.elasticsearch_api_key`
    - `observability.elasticsearch_enabled: true`
    - `observability.elasticsearch_url`
    - `observability.elasticsearch_index: nunet-dms`
    - `observability.logging.level: DEBUG`
    - `observability.logging.file: /home/nunet/logs/nunet-dms.log`
  - Runs as `nunet` user to preserve permissions

#### 5.5 Write mTLS Certificates
- **Action**: `mgr._write_certificates(payload)`
- **Process**:
  1. Creates directory: `~/.nunet/appliance/ddns-client/certs/certs/`
  2. Writes files:
     - `client.crt`: Client certificate
     - `client.key`: Client private key (chmod 600)
     - `infra-bundle-ca.crt`: CA bundle
  3. Logs written files

#### 5.6 Enable Caddy Proxy (if certificates available)
- **Action**: Checks if all 3 certificates are present
- **Process**:
  - Calls `caddy_proxy_manager.get_caddy_proxy_status()`
  - Service is installed via `nunet-appliance-web` deb package
  - Logs service status

#### 5.7 Copy Capability Tokens to DMS User
- **Action**: `mgr.copy_capability_tokens_to_dms_user()`
- **Process**:
  1. Copies `~/.nunet/dms.cap` → `/home/nunet/.nunet/dms.cap`
  2. Sets ownership: `nunet:nunet`
  3. Sets permissions: `640`
  - Allows DMS service to access capability tokens

#### 5.8 Onboard Compute with New Capabilities
- **Action**: `mgr.dms_manager.onboard_compute()`
- **Process**:
  - Runs compute onboarding script with new capability tokens
  - Refreshes DMS resources with organization capabilities
  - Updates state: `step="capabilities_onboarded"`

#### 5.9 Final State Update
- **State**:
  ```python
  {
      "step": "complete",
      "status": "complete",
      "completed": True,
      "processed_ok": True,
      "processing": False,
  }
  ```

---

### Phase 6: Completion & DMS Restart

#### 6.1 Frontend Shows Completion
- **UI**: `OnboardFlow.tsx` displays completion card
- **Message**: "Onboarding complete! Restart DMS to apply the new configuration."
- **Action**: Shows `RestartDmsButton` component

#### 6.2 User Restarts DMS (Manual)
- **UI Action**: User clicks "Restart DMS" button
- **Frontend**: Calls DMS restart endpoint (separate from onboarding)
- **Backend**: `mgr.restart_dms_service()`
  - Runs: `sudo systemctl restart nunetdms`
  - Waits 2 seconds
  - Verifies: `sudo systemctl is-active nunetdms`
  - Returns success/failure

---

## Data Flow Diagram

```
┌─────────────────┐
│  React Frontend  │
│  Organizations   │
│     .tsx         │
└────────┬─────────┘
         │ HTTP REST API
         │ (FastAPI)
         ▼
┌─────────────────────────┐
│  FastAPI Backend         │
│  nunet-appliance-web     │
│  .service                │
│                          │
│  ┌────────────────────┐ │
│  │ organizations.py   │ │
│  │ (Router)            │ │
│  └──────────┬─────────┘ │
│             │            │
│  ┌──────────▼─────────┐ │
│  │ OnboardingManager   │ │
│  │ (State Management)  │ │
│  └──────────┬─────────┘ │
└─────────────┼────────────┘
              │
              │ HTTP POST/GET
              │ (requests.Session)
              ▼
┌─────────────────────────────┐
│  External Organization API   │
│  e.g., spo.parallelvector   │
│  .com/api                    │
│                              │
│  /onboarding/submit/         │
│  /onboarding/status/{id}/   │
└─────────────────────────────┘
```

---

## State Persistence

### State File Location
- **Path**: `~/.nunet/appliance/onboarding_state.json`
- **Format**: JSON with structure:
  ```json
  {
      "step": "join_data_sent",
      "progress": 40,
      "org_data": {
          "did": "did:key:...",
          "name": "Organization Name",
          "roles": ["compute_provider"],
          "role_profiles": {...},
          "tokenomics": {...}
      },
      "form_data": {
          "name": "User Name",
          "email": "user@example.com",
          "roles": ["compute_provider"],
          ...
      },
      "request_id": "abc123",
      "status_token": "xyz789",
      "api_status": "pending",
      "api_payload": {...},
      "processing": false,
      "processed_ok": false,
      "completed": false,
      "logs": [
          {
              "timestamp": "2024-01-15 10:30:00",
              "step": "submit_data",
              "message": "Submitting onboarding payload..."
          }
      ]
  }
  ```

### Log File
- **Path**: `~/.nunet/appliance/onboarding_log.txt`
- **Format**: Plain text with timestamps
- **Purpose**: Human-readable audit trail

---

## Key API Endpoints

### Frontend → Backend (FastAPI)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/organizations/known` | Get list of known organizations |
| `POST` | `/organizations/select` | Select an organization |
| `POST` | `/organizations/join/submit` | Submit join request |
| `GET` | `/organizations/join/poll` | Poll for status updates |
| `GET` | `/organizations/status` | Get current onboarding status |
| `POST` | `/organizations/onboarding/reset` | Reset/cancel onboarding |
| `POST` | `/organizations/renew/start` | Start renewal process |
| `DELETE` | `/organizations/join/{org_did}` | Leave an organization |

### Backend → External Organization API

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `{org_api_url}/onboarding/submit/` | Submit join request |
| `GET` | `{org_api_url}/onboarding/status/{request_id}/` | Check request status |

---

## Error Handling

### Frontend Error States
- **Network Errors**: Displayed via toast notifications
- **Validation Errors**: Shown inline in form
- **Rejection**: Shows rejection card with reason and retry option

### Backend Error Handling
- **API Failures**: Caught and logged, state updated with error
- **DMS Not Ready**: Returns 400 error with message
- **Invalid Roles**: Returns 400 with list of allowed roles
- **Missing Wallet**: Returns 400 if tokenomics requires wallet

### State Recovery
- State persists across service restarts
- Frontend polls status on page load
- Can resume from any step if state is valid

---

## Renewal Process

### Renewal Flow
1. User clicks "Renew" on a joined organization
2. Frontend calls `POST /organizations/renew/start` with `org_did`
3. Backend:
   - Loads cached join payload from `role_metadata`
   - Falls back to state `form_data` if metadata missing
   - Constructs `JoinSubmitRequest` with `renewal=True`
   - Includes `renewing_previous` (last request ID)
4. Follows same submission flow as new join
5. Organization API handles renewal logic

---

## Capability Token System

### Require Token (Generated Locally)
- **Purpose**: Grants permissions to the local DMS node
- **Source**: Role profile's `require_template`
- **Contains**:
  - Capabilities: `["/dms/deployment", "/dms/tokenomics/contract"]`
  - Topics: `["/nunet"]`
  - Context: `"dms"`
  - Expiry: 30 days (default)
  - Subject: Organization DID

### Provide Token (From Organization)
- **Purpose**: Organization grants capabilities to the node
- **Source**: Received in approval payload
- **Anchored**: Stored in `dms.cap` file under `provide.tok[]`

### Token Storage
- **Location**: `~/.nunet/dms.cap` (ubuntu user)
- **Service Copy**: `/home/nunet/.nunet/dms.cap` (nunet service user)
- **Format**: JSON with `provide` and `require` sections

---

## Summary

The organization join process is a multi-phase state machine that:

1. **Collects** user information and organization selection
2. **Validates** inputs against organization requirements
3. **Submits** join request to external organization API
4. **Polls** for approval status
5. **Processes** approval payload (tokens, certificates, config)
6. **Applies** capabilities and configures services
7. **Completes** when all steps are done

The system uses persistent state files to survive restarts and provides real-time status updates via polling. The frontend automatically advances through steps based on backend state, with manual intervention only required for DMS restart at the end.
