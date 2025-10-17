# modules/org_utils.py

import json
import os
import re
import stat
from pathlib import Path
from typing import Dict

from .path_constants import KNOWN_ORGS_FILE

# Use JSON for known organizations for extensibility

TRUSTED_ORGS = [
    {
        "did": "did:key:z6MkkXnNzxFryuL9aeH7K8o8jxhtc5pGs8YKrUqipvK943bJ",
        "name": "NuNet Compute Testnet"
    },
]

# Remove or comment out ensure_known_orgs_file and .txt logic
# def ensure_known_orgs_file():
#     """
#     Ensure the known_orgs.txt file exists.
#     If not, create it with the default trusted orgs and set secure permissions.
#     """
#     if KNOWN_ORGS_FILE.exists():
#         return
#
#     # Ensure directory exists
#     KNOWN_ORGS_FILE.parent.mkdir(parents=True, exist_ok=True)
#
#     # Write the file
#     with open(KNOWN_ORGS_FILE, 'w') as f:
#         f.write("# Known Organizations\n")
#         for org in TRUSTED_ORGS:
#             f.write(f"{org['did']}:{org['name']}\n")
#
#     # Set ownership and permissions
#     try:
#         os.chown(KNOWN_ORGS_FILE, 0, 0)  # root:root
#     except PermissionError:
#         pass  # Skip if not running as root
#
#     os.chmod(KNOWN_ORGS_FILE, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # Read-only for all
#
#     # Optional: Make immutable using chattr (Linux only). This keeps failing because of the platform. Fix later
#     # import sys
#     # if sys.platform == "linux":
#     #     try:
#     #         import subprocess
#     #         subprocess.run(["chattr", "+i", str(KNOWN_ORGS_FILE)], check=True)
#     #     except (FileNotFoundError, subprocess.CalledProcessError):
#     #         print("[*] chattr not available or failed. Skipping immutability.")

def load_known_organizations():
    """
    Load known organizations from known_organizations.json
    Returns:
        dict: {did: name} or {did: {name: ..., ...}} for future extensibility
    """
    if not KNOWN_ORGS_FILE.exists():
        return {}
    with open(KNOWN_ORGS_FILE, 'r') as f:
        return json.load(f)

def is_organization_known(org_did):
    """
    Check if an organization DID is in the known list
    Args:
        org_did (str): Organization DID to check
    Returns:
        bool: True if known
    """
    known = load_known_organizations()
    return org_did in known

def get_root_issuer(capability):
    """
    Traverse the capability chain to find the ultimate issuer (the organization)
    Args:
        capability (dict): A single capability token under 'provide'
    Returns:
        str: The DID of the ultimate issuer (organization)
    """
    dms_cap = capability.get('dms', {})
    if not isinstance(dms_cap, dict):
        print(" Warning: 'dms cap' is not a dictionary")
        return None
    while True:
        if 'chain' in dms_cap:
            dms_cap = dms_cap['chain']

            # If chain is not a dict, break
            if not isinstance(dms_cap, dict):
                print("Chain is not a dictionary anymore.")
                break

            # If chain has a 'dms' key, dig into it
            if 'dms' in dms_cap:
                dms_cap = dms_cap['dms']
                if not isinstance(dms_cap, dict):
                    print("Warning 'dms cap' inside chain is not a dictionary")
                    break
        else:
            break

    issuer = dms_cap.get('iss', {}).get('uri')
    return issuer

def get_joined_organizations() -> list:
    """
    Extract unique organization DIDs from provide tokens in dms.cap
    Returns:
        list: List of unique organization DIDs
    """
    cap_file = Path("/home/ubuntu/.nunet/cap/dms.cap")
    if not cap_file.exists():
        return []

    try:
        with open(cap_file, 'r') as f:
            data = json.load(f)

        org_dids = set()
        for token in data.get("provide", {}).get("tok", []):
            root_issuer = get_root_issuer(token)
            if root_issuer:
                org_dids.add(root_issuer)

        return list(org_dids)
    except Exception as e:
        # Always return a list, even on error
        print(f"Error getting organisations you have joined: {str(e)}")
        return []

def get_joined_organizations_with_names():
    """
    Get joined organizations with resolved names if available
    Returns:
        list: List of dicts like {"did": "...", "name": "Org Name"}
    """
    cap_file = Path("/home/ubuntu/.nunet/cap/dms.cap")
    if not cap_file.exists():
        return []

    try:
        with open(cap_file, 'r') as f:
            data = json.load(f)
        known_orgs = load_known_organizations()
        result = []
        seen_dids = set()

        # Traverse provide tokens
        for token in data.get("provide", {}).get("tok", []):
            did = get_root_issuer(token)
            if did and did not in seen_dids:
                entry = {"did": did}
                normalized_did = did.strip() 
                org_info = known_orgs.get(normalized_did)
                if isinstance(org_info, dict):
                    entry["name"] = org_info.get("name", "Unknown Organization")
                elif isinstance(org_info, str):
                    entry["name"] = org_info
                else:
                    entry["name"] = "Unknown Organization"
                result.append(entry)
                seen_dids.add(did)
        return result

    except Exception as e:
        # Always return a list, even on error
        print(f"Error getting organisations you have joined: {str(e)}")
        return []

def get_joined_organizations_with_details():
    """
    Get joined organizations with capabilities and expiry dates
    Returns:
        list: List of dicts like {"did": "...", "name": "Org Name", "capabilities": [...], "expiry": "..."}
    """
    cap_file = Path("/home/ubuntu/.nunet/cap/dms.cap")
    if not cap_file.exists():
        return []

    try:
        with open(cap_file, 'r') as f:
            data = json.load(f)
        known_orgs = load_known_organizations()
        result = []
        seen_dids = set()

        # Traverse provide tokens
        for token in data.get("provide", {}).get("tok", []):
            did = get_root_issuer(token)
            if did and did not in seen_dids:
                entry = {"did": did}
                normalized_did = did.strip() 
                org_info = known_orgs.get(normalized_did)
                if isinstance(org_info, dict):
                    entry["name"] = org_info.get("name", "Unknown Organization")
                elif isinstance(org_info, str):
                    entry["name"] = org_info
                else:
                    entry["name"] = "Unknown Organization"
                
                # Extract capabilities and expiry from the token
                dms_cap = token.get('dms', {})
                entry["capabilities"] = dms_cap.get("cap", [])
                entry["expiry"] = parse_capability_timestamp(dms_cap.get("exp"))
                
                result.append(entry)
                seen_dids.add(did)
        return result

    except Exception as e:
        # Always return a list, even on error
        print(f"Error getting organisations with details: {str(e)}")
        return []

def parse_capability_timestamp(timestamp):
    """Convert capability timestamp to human-readable format"""
    try:
        from datetime import datetime
        # Convert nanoseconds to seconds
        dt = datetime.utcfromtimestamp(int(timestamp) / 1e9)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return "Unknown"
