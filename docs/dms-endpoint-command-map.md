# DMS Endpoint -> Function -> CLI Command Map

This document maps the DMS endpoints used by the frontend to:

1. The backend router/function chain that serves them
2. The exact `nunet` CLI commands executed under the hood
3. Cache behavior that affects command frequency

## Scope

This focuses on the endpoints used by `allInfo()` in the frontend:

- `GET /dms/status`
- `GET /dms/status/resources` (legacy alias: `/dms/status/full`)
- `GET /dms/peers/self`

## Endpoint Mapping Table

| Endpoint | Frontend caller | Router function | Backend function chain | CLI commands executed |
|---|---|---|---|---|
| `GET /dms/status` | `getDmsStatus()` (`frontend/src/api/api.ts`) | `status()` in `backend/nunet_api/routers/dms.py` | `get_cached_dms_status_info(force_refresh=fresh)` -> `get_dms_status_info()` -> `normalize_dms_status()` | 1) `nunet version`  2) `nunet -c dms actor cmd /dms/node/peers/self`  3) `nunet key did dms` *(only if peers/self succeeds)* |
| `GET /dms/status/resources` | `getDmsFullStatus()` (`frontend/src/api/api.ts`) | `status_resources()` in `backend/nunet_api/routers/dms.py` | `get_cached_dms_resource_info(force_refresh=fresh)` -> `get_dms_resource_info()` | Always: 1) `nunet -c dms actor cmd /dms/node/onboarding/status`  If onboarded: 2) `nunet -c dms actor cmd /dms/node/resources/free`  3) `nunet -c dms actor cmd /dms/node/resources/allocated`  4) `nunet -c dms actor cmd /dms/node/resources/onboarded`  5) `nunet -c dms actor cmd /dms/node/hardware/spec` |
| `GET /dms/peers/self` | `getSelfPeers()` (`frontend/src/api/api.ts`) | `self_peer()` in `backend/nunet_api/routers/dms.py` | `DMSManager.get_self_peer_info()` | 1) `nunet -c dms actor cmd /dms/node/peers/self`  2) `nunet key did dms` |

## Composite Frontend Call (`allInfo`)

`allInfo()` runs these three requests in parallel:

- `getDmsStatus()` -> `/dms/status`
- `getDmsFullStatus()` -> `/dms/status/resources` (legacy alias still available)
- `getSelfPeers()` -> `/dms/peers/self`

So a single `allInfo()` fetch can trigger multiple backend commands, depending on onboarding status.

## Cache Behavior

| Layer | Cached item | Current cache duration |
|---|---|---|
| Backend (`backend/modules/dms_utils.py`) | DMS status and resource snapshots | `30s` default TTL (`_CACHE_TTL_DEFAULT = 30.0`) |
| Frontend React Query | Depends on query key/config by page | Varies by page/query settings |

### Notes

- `/dms/status` and `/dms/status/resources` have a `refresh` query param; when `refresh=true`, backend bypasses cache (`force_refresh=True`).
- `/dms/peers/self` currently goes through `DMSManager` and does not use the `dms_utils` cache helper path used by `/dms/status`.

## Dashboard Field-Level Mapping

Dashboard card data in `frontend/src/components/dashboard/section-cards.tsx` is read from:

- `info` (query key `["apiData"]`, query fn `allInfo()`)
- `sysinfo` (query key `["sysInfo"]`, query fn `allSysInfo()`)

### Fields from `info` (`allInfo`)

| Dashboard field used | Source in merged payload | API call | Backend endpoint | Underlying CLI command(s) |
|---|---|---|---|---|
| `info.dms_status` | `dms_status` | `getDmsStatus()` | `GET /dms/status` | `nunet version`; `nunet -c dms actor cmd /dms/node/peers/self`; `nunet key did dms` |
| `info.dms_version` | `dms_version` | `getDmsStatus()` | `GET /dms/status` | `nunet version`; `nunet -c dms actor cmd /dms/node/peers/self`; `nunet key did dms` |
| `info.dms_running` | `dms_running` | `getDmsStatus()` | `GET /dms/status` | `nunet version`; `nunet -c dms actor cmd /dms/node/peers/self`; `nunet key did dms` |
| `info.dms_did` | `dms_did` | `getDmsStatus()` | `GET /dms/status` | `nunet version`; `nunet -c dms actor cmd /dms/node/peers/self`; `nunet key did dms` |
| `info.dms_peer_id` | `dms_peer_id` | `getDmsStatus()` | `GET /dms/status` | `nunet version`; `nunet -c dms actor cmd /dms/node/peers/self`; `nunet key did dms` |
| `info.dms_is_relayed` | `dms_is_relayed` | `getDmsStatus()` | `GET /dms/status` | `nunet version`; `nunet -c dms actor cmd /dms/node/peers/self`; `nunet key did dms` |
| `info.onboarding_status` | `onboarding_status` | `getDmsFullStatus()` | `GET /dms/status/resources` | `nunet -c dms actor cmd /dms/node/onboarding/status`; plus resource commands when onboarded |
| `info.free_resources` | `free_resources` | `getDmsFullStatus()` | `GET /dms/status/resources` | `/dms/node/resources/free` command (if onboarded) |
| `info.allocated_resources` | `allocated_resources` | `getDmsFullStatus()` | `GET /dms/status/resources` | `/dms/node/resources/allocated` command (if onboarded) |
| `info.onboarded_resources` | `onboarded_resources` | `getDmsFullStatus()` | `GET /dms/status/resources` | `/dms/node/resources/onboarded` command (if onboarded) |

Additional values also returned by `allInfo()` (from `getSelfPeers()`), but not primary dashboard badges:
`peer_id`, `context`, `did`, `local_addrs`, `public_addrs`, `relay_addrs`, `is_relayed`.

### Fields from `sysinfo` (`allSysInfo`)

| Dashboard field used | Source function | API endpoint |
|---|---|---|
| `sysinfo.publicIp` | `getPublicIp()` | `GET /sys/public-ip` |
| `sysinfo.localIp` | `getLocalIp()` | `GET /sys/local-ip` |
| `sysinfo.applianceVersion` | `getApplianceVersion()` | `GET /sys/appliance-version` |
| `sysinfo.sshStatus.running` | `getSshStatus()` | `GET /sys/ssh-status` |
| `sysinfo.sshStatus.authorized_keys` | `getSshStatus()` | `GET /sys/ssh-status` |
| `sysinfo.updateInfo.*` | `checkUpdates()` | `GET /sys/check-updates` |
| `sysinfo.dmsUpdateInfo.*` | `checkDmsUpdates()` | `GET /dms/check-updates` |

