# Onboarding flow and disk calculation

## What runs when you press "Onboard" on the dashboard

1. **Frontend**: The dashboard calls `POST /dms/onboard` (see `frontend/src/api/api.ts`).
2. **API**: `nunet_api/routers/dms.py` → `onboard()` → `mgr.onboard_compute()`.
3. **Backend**: `backend/modules/dms_manager.py`:
   - `onboard_compute()` (entry point) calls `_calculate_onboard_resources()` then runs:
     `nunet -c dms actor cmd /dms/node/onboarding/onboard --disk <disk_gb> --ram <ram_gb> --cpu <cpu>`

The same `dms_manager.onboard_compute()` is used from:
- **Dashboard "Onboard" button** → `POST /dms/onboard` (DMS router).
- **Org join flow** → `onboarding_manager.py` (e.g. `ensure_pre_onboarding()`, and after approval in `process_post_approval_payload()`).

So the single place that calculates and runs onboarding is **`DMSManager.onboard_compute()`** in `backend/modules/dms_manager.py`.

---

## How disk is calculated today

- **CPU**: From DMS hardware spec `Resources.cpu.cores` (or `os.cpu_count()`), then `max(1, cores - 1)`.
- **RAM**: From hardware spec total RAM and `free -k` used; onboard = min(floored free RAM, 89% of total).
- **Disk**: From **`df -k --total`**:
  - The **last line** of the output is treated as the "total" row.
  - Column index **3** is used as "free space" (Available, in KiB).
  - Formula: `disk_onboard_gb = max(0, free_disk_gb - 5.0)` (reserve 5 GiB).

So disk is **not** taken from the hardware spec; it is intended to be **free space** from `df`. The hardware spec is only used for CPU, RAM total, and GPUs.

---

## Why you can see "not enough free Disk" even with 45 GiB onboard

The problem is **`df -k --total`**:

- The **total** row is an **aggregate** over all mounted filesystems: it **sums** 1K-blocks, Used, and **Available**.
- So "total available" can be the **sum** of free space on many mounts (e.g. 20 + 15 + 10 = 45 GB).
- You cannot actually allocate 45 GB on a **single** filesystem from that number.
- DMS (device-management-service) checks free space on **one** path (typically the partition where it stores data). If that partition has e.g. 30 GB free, it will reject "45 GB" with "not enough free Disk available".

So the appliance is using **aggregate** free space, while DMS validates against **one** filesystem, which causes the mismatch.

---

## Fix: use free space on a single filesystem

We should compute disk from the **same** filesystem DMS uses (e.g. root `/` or the DMS data directory), not from `df --total`. That way we never offer more than the free space on that one partition.

See the code change in `dms_manager.py`: use `df -k <path>` for a specific path (e.g. `/` or the backend root) and take Available from that line, then `max(0, free_gb - 5.0)`.
