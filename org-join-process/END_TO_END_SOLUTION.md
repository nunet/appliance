# Organization Join Process - End-to-End Solution Documentation

## Overview

This document provides a comprehensive view of the complete organization onboarding solution, covering all three components and their interactions:

1. **Appliance**: User-facing application that initiates and monitors onboarding
2. **Organization Manager**: Central coordination service that manages request lifecycle
3. **Onboarding Worker**: Background service that processes requests and generates artifacts

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         APPLIANCE                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Frontend   │  │   Backend    │  │  Onboarding   │         │
│  │   (React)    │→ │   (FastAPI)  │→ │   Manager    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP POST/GET
                              │ /onboarding/submit/
                              │ /onboarding/status/{id}/
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ORGANIZATION MANAGER                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Django     │  │   Request    │  │   Worker     │         │
│  │   REST API   │→ │   Model      │← │   API        │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         │                  │                  │                 │
│         │                  │                  │                 │
│         ▼                  ▼                  ▼                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Email      │  │   GeoIP      │  │   Round-     │         │
│  │   Validator  │  │   Enrichment │  │   Robin      │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP GET/PUT
                              │ /worker/available-requests/
                              │ /worker/claim-request/
                              │ /worker/complete-request/
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ONBOARDING WORKER                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Simple     │  │   Contract   │  │   API         │         │
│  │   Worker     │  │   Worker     │  │   Client     │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         │                  │                  │                 │
│         ▼                  ▼                  ▼                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   NuNet      │  │ Certificate  │  │  Elastic      │         │
│  │  Processor   │  │  Generator   │  │  Generator   │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
    ┌─────────┐        ┌─────────┐        ┌─────────┐
    │  NuNet  │        │ OpenBao │        │Elastic  │
    │   CLI   │        │   PKI   │        │   API   │
    └─────────┘        └─────────┘        └─────────┘
```

---

## Component Responsibilities

### Appliance

**Primary Role**: User interface and local state management

**Responsibilities**:
- Display known organizations to user
- Collect user information and form data
- Validate form inputs (roles, wallet, etc.)
- Capture DMS resource snapshot
- Submit onboarding request to organization manager
- Poll for status updates
- Process approval payload (tokens, certificates, config)
- Apply capabilities and configure local services
- Display progress and completion status

**Key Files**:
- `frontend/src/pages/Organizations.tsx`: Organization selection UI
- `frontend/src/pages/OnboardFlow.tsx`: Onboarding flow UI
- `backend/modules/onboarding_manager.py`: State management and API interaction
- `backend/modules/organizations.py`: FastAPI endpoints

**State Management**:
- Local state file: `~/.nunet/appliance/onboarding_state.json`
- Persists across restarts
- Tracks current step, progress, form data, request ID, status token

---

### Organization Manager

**Primary Role**: Central coordination and request lifecycle management

**Responsibilities**:
- Receive and validate onboarding requests
- Send email verification
- Manage request status lifecycle
- Coordinate worker processing (round-robin)
- Store processed results (tokens, certificates, keys)
- Serve status and results to appliances
- Enrich requests with GeoIP data
- Provide DID lookup services

**Key Files**:
- `onboarding/api/views.py`: Public API endpoints
- `onboarding/api/worker_views.py`: Worker API endpoints
- `onboarding/models.py`: Database models
- `onboarding/workers/email_validator.py`: Email verification

**Database Models**:
- `OnboardingRequest`: Main request record
- `OnboardingWorker`: Worker registration
- `GPU`: Hardware GPU information
- `GeoIPInfo`: Geographic data

**API Endpoints**:
- Public: `/api/onboarding/submit/`, `/api/onboarding/status/{id}/`
- Worker: `/api/onboarding/worker/available-requests/`, `/api/onboarding/worker/claim-request/`, `/api/onboarding/worker/complete-request/`

---

### Onboarding Worker

**Primary Role**: Background processing and artifact generation

**Responsibilities**:
- Poll organization manager for available requests
- Claim requests using round-robin coordination
- Generate capability tokens (NuNet CLI)
- Generate mTLS certificates (OpenBao PKI)
- Generate Elasticsearch API keys
- Create tokenomics contracts (if requested)
- Submit results back to organization manager
- Send heartbeats to maintain health status

**Key Files**:
- `workers/simple_worker.py`: Main onboarding worker
- `workers/contract_worker.py`: Contract creation worker
- `workers/nunet_processor.py`: NuNet capability delegation
- `workers/certificate_generator.py`: Certificate generation
- `workers/secrets.py`: Secrets management

**Worker Types**:
- **SimpleWorker**: Standard onboarding (tokens, certs, keys)
- **ContractWorker**: Tokenomics contract creation

---

## Complete Flow Sequence

### Phase 1: Request Initiation (Appliance)

1. **User selects organization**
   - Frontend loads known organizations from backend
   - User clicks on organization card
   - Backend updates state: `step="collect_join_data"`

2. **User fills join form**
   - Collects: name, email, roles, wallet (if tokenomics), etc.
   - Frontend validates inputs
   - User clicks "Submit"

3. **Backend prepares submission**
   - Validates organization and roles
   - Ensures DMS is onboarded
   - Captures resource snapshot (CPU, RAM, disk, GPUs, IP)
   - Builds submission payload

4. **Backend submits to organization manager**
   - `POST {org_api_url}/onboarding/submit/`
   - Receives: `{id, status_token, status}`
   - Updates state: `step="join_data_sent"`, stores `request_id` and `status_token`

---

### Phase 2: Request Processing (Organization Manager)

1. **Receive request**
   - Creates `OnboardingRequest` record
   - Status: `pending`
   - Extracts hardware data, stores in database
   - Enriches with GeoIP data (if IP provided)

2. **Email verification**
   - Checks spam protection (max 10 requests per email in 24h)
   - Generates verification token
   - Sends verification email
   - Status: `email_sent`

3. **User verifies email**
   - User clicks verification link
   - Organization manager validates token
   - Status: `email_verified`
   - Request becomes available for worker processing

---

### Phase 3: Worker Processing (Onboarding Worker)

1. **Worker polls for requests**
   - `GET /api/onboarding/worker/available-requests/`
   - Organization manager uses round-robin to distribute requests
   - Returns request if it's this worker's turn

2. **Worker claims request**
   - `PUT /api/onboarding/worker/claim-request/{id}/`
   - Organization manager sets: `claimed_by=worker`, `status=processing`, `processing_timeout=now+2min`

3. **Worker processes request**
   - **Delegate capabilities**: `nunet cap delegate` → capability token
   - **Generate certificates**: OpenBao PKI → client.crt, client.key, infra-bundle-ca.crt
   - **Generate Elastic key**: Elastic API → API key
   - **Create contract** (if tokenomics): `nunet actor cmd` → contract ID

4. **Worker completes request**
   - `PUT /api/onboarding/worker/complete-request/{id}/`
   - Submits all generated artifacts
   - Organization manager stores results, status: `ready` (or `contract_pending`)

---

### Phase 4: Status Polling (Appliance)

1. **Frontend polls for updates**
   - `GET /organizations/join/poll` (every 5 seconds)
   - Backend calls: `GET {org_api_url}/onboarding/status/{request_id}/?status_token={token}`

2. **Status transitions**
   - `email_sent` / `pending` → Continue polling
   - `email_verified` → Continue polling (waiting for worker)
   - `processing` → Continue polling (worker processing)
   - `ready` → **Auto-process payload** (see Phase 5)
   - `rejected` → Show rejection message
   - `error` → Show error message

---

### Phase 5: Payload Processing (Appliance)

1. **Backend receives approval payload**
   - Extracts: `capability_token`, `client_crt`, `client_key`, `infra_bundle_crt`, `elastic_api_key`

2. **Generate require token**
   - Loads role profile from known orgs
   - Extracts `require_template` (capabilities, topics)
   - Runs: `nunet cap grant` → require token
   - Anchors: `nunet cap anchor -c dms --require {token}`

3. **Apply provide token**
   - Anchors organization's capability token: `nunet cap anchor -c dms --provide {token}`

4. **Configure observability**
   - Updates nunet config: `observability.elasticsearch_*`
   - Sets logging level and file path

5. **Write mTLS certificates**
   - Creates: `~/.nunet/appliance/ddns-client/certs/certs/`
   - Writes: `client.crt`, `client.key`, `infra-bundle-ca.crt`
   - Sets permissions (chmod 600 for key)

6. **Copy tokens to DMS user**
   - Copies `~/.nunet/dms.cap` → `/home/nunet/.nunet/dms.cap`
   - Sets ownership: `nunet:nunet`

7. **Onboard compute with capabilities**
   - Runs: `dms_manager.onboard_compute()`
   - Refreshes DMS resources with new capabilities

8. **Final state update**
   - Status: `complete`
   - Frontend shows completion message
   - User restarts DMS service

---

## Data Flow

### Request Submission Flow
```
Appliance → Organization Manager
  POST /onboarding/submit/
  {
    dms_did, name, email, roles, resources, ...
  }
  ↓
  {
    id, status_token, status: "email_sent"
  }
```

### Status Polling Flow
```
Appliance → Organization Manager
  GET /onboarding/status/{id}/?status_token={token}
  ↓
  {
    status: "ready",
    capability_token, client_crt, client_key, ...
  }
```

### Worker Processing Flow
```
Worker → Organization Manager
  GET /worker/available-requests/
  ↓
  [request]
  ↓
  PUT /worker/claim-request/{id}/
  ↓
  PUT /worker/complete-request/{id}/
  {
    capability_token, client_crt, client_key, ...
  }
```

---

## State Synchronization

### Appliance State
- **File**: `~/.nunet/appliance/onboarding_state.json`
- **Fields**: `step`, `progress`, `org_data`, `form_data`, `request_id`, `status_token`, `api_status`, `api_payload`
- **Updates**: On every step transition, status change, payload receipt

### Organization Manager State
- **Database**: `OnboardingRequest` model
- **Fields**: `status`, `status_message`, `claimed_by`, `processing_timeout`, `capability_token`, `client_crt`, etc.
- **Updates**: On request creation, email verification, worker claim, worker completion

### Worker State
- **Stateless**: No persistent state
- **Temporary**: Only holds current request being processed
- **Recovery**: Can re-claim expired requests

---

## Error Handling

### Appliance Errors
- **Network errors**: Retry with exponential backoff
- **Validation errors**: Show inline form errors
- **API errors**: Display error message, allow retry
- **Processing errors**: Log error, show error state, allow reset

### Organization Manager Errors
- **Invalid payload**: Return 400 with error details
- **Spam protection**: Return 429, set status to `rejected`
- **Email failure**: Set status to `error`, log error
- **Worker errors**: Preserve error message, set status to `error`

### Worker Errors
- **API errors**: Log error, continue polling
- **Processing errors**: Complete request with `success=false`, include error message
- **Claim timeout**: Another worker can claim expired request
- **NuNet/OpenBao/Elastic errors**: Log error, complete with failure

---

## Security Model

### Authentication

**Appliance → Organization Manager**:
- No authentication (public endpoints)
- `status_token` required for status polling (prevents enumeration)

**Worker → Organization Manager**:
- API key authentication (`X-API-Key` header)
- API keys managed via Django admin
- Workers can be activated/deactivated

### Authorization

**Request Access**:
- Status polling requires valid `status_token`
- Workers can only claim/complete their own requests
- Round-robin prevents request hoarding

**Worker Coordination**:
- Only healthy workers (heartbeat < 60s) participate in round-robin
- Claim timeouts prevent stuck requests
- Historical processing data preserved for audit

### Secrets Management

**Appliance**:
- DMS passphrase: From local config or user input
- Capability tokens: Stored in `dms.cap` file

**Organization Manager**:
- Email service credentials: Django settings
- Database credentials: Django settings

**Worker**:
- DMS passphrase: From OpenBao
- Service provider passphrase: From config
- OpenBao token: From config
- Elastic password: From OpenBao

---

## Scalability Considerations

### Horizontal Scaling

**Appliance**:
- Stateless (state in file system)
- Multiple appliances can onboard simultaneously
- No coordination needed

**Organization Manager**:
- Django application (stateless)
- Can run multiple instances behind load balancer
- Database shared across instances
- Round-robin works across all workers

**Onboarding Worker**:
- Stateless background service
- Multiple workers can run in parallel
- Organization manager handles distribution
- No shared state between workers

### Performance

**Request Throughput**:
- Limited by worker processing time (~10-30 seconds per request)
- Multiple workers increase throughput linearly
- Round-robin ensures fair distribution

**Database Load**:
- Read-heavy (status polling, worker polling)
- Write operations: request creation, status updates, worker completion
- Indexes on: `status`, `email`, `dms_did`, `claimed_by`, `created_at`

**API Load**:
- Status polling: Every 5 seconds per active appliance
- Worker polling: Every 30 seconds per worker
- Heartbeats: Every 30 seconds per worker

---

## Monitoring and Observability

### Metrics to Track

**Organization Manager**:
- Request creation rate
- Email verification rate
- Worker processing time
- Request status distribution
- Error rates by type

**Onboarding Worker**:
- Requests processed per hour
- Processing time per request
- Error rates
- Heartbeat status
- Claim success/failure rate

**Appliance**:
- Onboarding completion rate
- Time to completion
- Error rates
- Step progression

### Logging

**Organization Manager**:
- Request lifecycle events
- Email sending events
- Worker coordination events
- Error events with full context

**Onboarding Worker**:
- Polling cycles
- Request claiming
- Processing steps
- Errors with tracebacks

**Appliance**:
- State transitions
- API calls
- Processing steps
- Errors

---

## Deployment Architecture

### Recommended Deployment

**Organization Manager**:
- Django application on Gunicorn/uWSGI
- PostgreSQL database
- Redis (optional, for caching)
- Nginx reverse proxy
- SSL/TLS termination

**Onboarding Worker**:
- Python service (systemd or Docker)
- Access to NuNet CLI
- Access to OpenBao API
- Access to Elasticsearch API
- Environment variables for configuration

**Appliance**:
- FastAPI backend service
- React frontend (static files)
- Local file system for state
- Access to NuNet CLI
- Access to DMS service

---

## Future Enhancements

### Potential Improvements

1. **Webhook Support**: Push notifications instead of polling
2. **Retry Logic**: Automatic retry for failed processing steps
3. **Batch Processing**: Process multiple requests in parallel
4. **Metrics Dashboard**: Real-time monitoring of onboarding pipeline
5. **Multi-Organization**: Support for multiple organizations per appliance
6. **Role-Based Access**: Different capabilities per role
7. **Contract Templates**: Configurable contract templates per organization
8. **Audit Logging**: Comprehensive audit trail for compliance

---

## Related Documentation

- **[Appliance Documentation](../org-join-process/README.md)**: Detailed appliance-side flow
- **[Organization Manager Documentation](../../organization_manager/org-join-process/README.md)**: Detailed organization manager flow
- **[Onboarding Worker Documentation](../../onboarding-worker/org-join-process/README.md)**: Detailed worker flow

---

## Summary

The organization onboarding solution is a distributed system with three main components:

1. **Appliance**: User-facing application that initiates and monitors onboarding
2. **Organization Manager**: Central coordination service managing request lifecycle
3. **Onboarding Worker**: Background service generating artifacts (tokens, certificates, keys)

The system is designed for:
- **Scalability**: Multiple workers, stateless components
- **Reliability**: Error handling, timeouts, state persistence
- **Security**: API keys, status tokens, secrets management
- **Observability**: Logging, metrics, status tracking

The complete flow takes approximately 1-2 minutes from submission to completion, depending on worker processing time and email verification.
