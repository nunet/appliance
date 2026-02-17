# Unified Implementation Phases - All Repositories

This document defines the synchronized phases across all three repositories (appliance, organization_manager, onboarding-worker) for the contract-enabled organization join process.

## Phase Overview

| Phase | Appliance | Organization Manager | Onboarding Worker | Description |
|-------|-----------|---------------------|-------------------|-------------|
| **Phase 1** | ✅ Frontend + Backend | ⏭️ No changes | ⏭️ No changes | Warning Dialog |
| **Phase 2** | ✅ Backend | ✅ API + DB | ✅ Worker | Contract Capabilities |
| **Phase 3** | ✅ Backend | ✅ API + DB | ✅ Worker | Contract Creation & Polling |
| **Phase 4** | ✅ Frontend + Backend | ✅ API + DB | ✅ Worker | Contract Signing |
| **Phase 5** | ✅ Backend | ✅ API + DB | ✅ Worker | Deployment Capabilities |
| **Phase 6** | ⏭️ No changes | ✅ API + DB | ✅ Worker | Deployment Test |
| **Phase 7** | ✅ Frontend + Backend | ✅ API | ⏭️ No changes | Status Polling Updates |

---

## Phase 1: Warning Dialog

**Purpose**: Inform users about DMS restarts before starting onboarding

### Appliance
- **Frontend**: Create WarningDialog component, integrate into OnboardFlow
- **Backend**: Add warning_acknowledged state field (optional)

### Organization Manager
- **Status**: ⏭️ No changes required

### Onboarding Worker
- **Status**: ⏭️ No changes required

---

## Phase 2: Contract Capabilities Generation & Application

**Purpose**: Generate and apply contract capabilities (first phase of two-phase granting)

### Appliance
- **Backend**: 
  - Detect `contract_caps_ready` status in polling
  - Generate require token from known orgs file
  - Apply contract provide token from Organization Manager
  - Restart DMS service
  - Notify Organization Manager via `POST /confirm-caps/{id}/?cap_type=contract`

### Organization Manager
- **API Endpoints**:
  - Return `contract_caps_ready` status with `contract_caps` field
  - Add `POST /confirm-caps/{id}/?cap_type=contract` endpoint
- **Database**:
  - Store `contract_caps` in OnboardingRequest
  - Update status to `contract_caps_ready` when worker completes
  - Update status to `contract_caps_confirmed` when appliance confirms

### Onboarding Worker
- **Worker Logic**:
  - Poll for available requests
  - Claim request
  - Generate contract capabilities via `nunet cap delegate`
  - Send contract_caps to Organization Manager via `PUT /worker/complete-request/`
  - Update status to `contract_caps_ready`

---

## Phase 3: Contract Creation & Polling

**Purpose**: Create contract and detect when it arrives at appliance

### Appliance
- **Backend**:
  - Poll DMS for incoming contracts via `nunet actor cmd /contract/list_incoming`
  - Detect new contracts
  - Notify Organization Manager via `POST /contract-received/{id}/`

### Organization Manager
- **API Endpoints**:
  - Add `POST /contract-received/{id}/` endpoint
  - Update status to `contract_received`
  - Store `contract_did` when worker reports contract created
- **Database**:
  - Update status to `contract_created` when worker reports
  - Update status to `contract_received` when appliance reports

### Onboarding Worker
- **Worker Logic**:
  - Poll for `contract_caps_confirmed` status
  - Create contract JSON
  - Send contract via WorkerDMS: `nunet actor cmd /contract/create`
  - Contract sent to ContractHost via nuactor
  - Update Organization Manager via `PUT /worker/update-status/` with `contract_created`
  - Store `contract_did` in status update

---

## Phase 4: Contract Signing

**Purpose**: User signs contract, worker verifies signing

### Appliance
- **Frontend**: 
  - Create ContractSigningDialog component
  - Display contract information
  - Add "Sign Contract" button
- **Backend**:
  - Add `POST /organizations/contract/sign` endpoint
  - Execute `nunet actor cmd /dms/tokenomics/contract/approve_local --contract-did <did>`
  - Notify Organization Manager via `POST /contract-signed/{id}/`

### Organization Manager
- **API Endpoints**:
  - Add `POST /contract-signed/{id}/` endpoint
  - Update status to `contract_signed`
- **Database**:
  - Update status to `contract_signed` when appliance reports

### Onboarding Worker
- **Worker Logic**:
  - Poll for `contract_signed` status
  - Check nuactor for contract signing confirmation
  - Verify contract signed via WorkerDMS
  - Proceed to deployment capabilities generation

---

## Phase 5: Deployment Capabilities Generation & Application

**Purpose**: Generate and apply deployment capabilities, certificates, and API key

### Appliance
- **Backend**:
  - Detect `deployment_caps_ready` status in polling
  - Read capabilities from known orgs file
  - Generate require token from known orgs (deployment caps)
  - Apply deployment provide token from Organization Manager
  - Write mTLS certificates
  - Configure Elastic API key
  - Restart DMS service
  - Notify Organization Manager via `POST /confirm-caps/{id}/?cap_type=deployment`

### Organization Manager
- **API Endpoints**:
  - Return `deployment_caps_ready` status with `deployment_caps`, `certificates`, `api_key`
  - Add `POST /confirm-caps/{id}/?cap_type=deployment` endpoint
- **Database**:
  - Store `deployment_caps`, `certificates`, `api_key` in OnboardingRequest
  - Update status to `deployment_caps_ready` when worker completes
  - Update status to `deployment_caps_confirmed` when appliance confirms

### Onboarding Worker
- **Worker Logic**:
  - Poll for `contract_signed` status (verified via nuactor)
  - Generate deployment capabilities via `nunet cap delegate`
  - Generate mTLS certificates via OpenBao
  - Generate Elastic API key
  - Send all to Organization Manager via `PUT /worker/complete-request/`
  - Update status to `deployment_caps_ready`

---

## Phase 6: Deployment Test

**Purpose**: Test deployment capabilities by deploying hello world ensemble

### Appliance
- **Status**: ⏭️ No changes required (just polls for status)

### Organization Manager
- **API Endpoints**:
  - Handle `PUT /worker/update-status/` with `deployment_test_complete` or `deployment_failed`
  - Store `deployment_logs` in database
  - Update status to `deployment_test_complete` or `deployment_failed`
- **Database**:
  - Add `deployment_logs` field to OnboardingRequest
  - Update status based on deployment test result

### Onboarding Worker
- **Worker Logic**:
  - Poll for `deployment_caps_confirmed` status
  - Create hello world ensemble
  - Deploy ensemble via WorkerDMS using deployment caps
  - If successful: Retrieve deployment logs, update status to `deployment_test_complete`
  - If failed: Retry up to 5 times (1 minute intervals)
  - If all retries fail: Update status to `deployment_failed`
  - Store deployment logs in status update

---

## Phase 7: Status Polling Updates

**Purpose**: Update status polling logic to handle all new statuses

### Appliance
- **Frontend**:
  - Update step states array with new phases
  - Update polling logic for new statuses
  - Update status display messages
- **Backend**:
  - Update status polling to handle all new statuses
  - Integrate contract polling
  - Integrate capability application logic

### Organization Manager
- **API Endpoints**:
  - Update status endpoint to return all new statuses
  - Ensure proper status transitions
- **Database**:
  - Ensure all new status fields are supported

### Onboarding Worker
- **Status**: ⏭️ No changes required (worker already handles status polling)

---

## Implementation Order Recommendation

1. **Phase 1** (Warning Dialog) - Simple, low risk, independent
2. **Phase 2** (Contract Capabilities) - Foundation for contract flow
3. **Phase 3** (Contract Creation) - Depends on Phase 2
4. **Phase 4** (Contract Signing) - Depends on Phase 3
5. **Phase 5** (Deployment Capabilities) - Depends on Phase 4
6. **Phase 6** (Deployment Test) - Depends on Phase 5
7. **Phase 7** (Status Polling) - Integrates all previous phases

---

## Cross-Repository Dependencies

### Phase 2 Dependencies
- Organization Manager must support `contract_caps_ready` status
- Organization Manager must support `POST /confirm-caps/{id}/?cap_type=contract`
- Worker must generate contract caps correctly
- Appliance must apply caps and restart DMS

### Phase 3 Dependencies
- Worker must create contract and send to ContractHost
- Organization Manager must track `contract_created` status
- Appliance must poll DMS for contracts

### Phase 4 Dependencies
- Appliance must sign contract via nunet CLI
- Organization Manager must track `contract_signed` status
- Worker must verify contract signing via nuactor

### Phase 5 Dependencies
- Organization Manager must support `deployment_caps_ready` status
- Organization Manager must support `POST /confirm-caps/{id}/?cap_type=deployment`
- Worker must generate deployment caps, certs, API key
- Appliance must apply all and restart DMS

### Phase 6 Dependencies
- Worker must deploy hello world ensemble
- Worker must implement retry logic
- Organization Manager must store deployment logs

### Phase 7 Dependencies
- All previous phases must be complete
- All statuses must be properly handled

---

## Notes

- **Placeholder Phases**: If a repo doesn't need changes for a phase, the detailed prompt will indicate "No changes required" with a brief explanation
- **Synchronization**: Phases are designed to be implemented in parallel across repos where possible
- **Testing**: Each phase should be tested end-to-end across all affected repos before moving to the next phase
