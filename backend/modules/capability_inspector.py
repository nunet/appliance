# modules/capability_inspector.py

import json
from pathlib import Path
from datetime import datetime

def parse_capability_timestamp(timestamp):
    """Convert capability timestamp to human-readable format"""
    try:
        # Convert nanoseconds to seconds
        dt = datetime.utcfromtimestamp(int(timestamp) / 1e9)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return "Unknown"

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

def get_trusted_organizations_from_require():
    """
    Get organizations YOU trust (i.e., where YOU are the subject)
    Returns:
        list of dicts with keys: org_did, caps, exp
    """
    cap_file = Path("/home/ubuntu/.nunet/cap/dms.cap")
    from modules.org_utils import load_known_organizations
    known_orgs = load_known_organizations()
    if not cap_file.exists():
        return []

    try:
        with open(cap_file, 'r') as f:
            data = json.load(f)

        result = []
        seen = set()

        for token in data.get("require", {}).get("tok", []):
            dms = token.get("dms", {})
            org_did = dms.get("sub", {}).get("uri")  # In require, YOU are the issuer, ORG is sub
            caps = ", ".join(dms.get("cap", ["none"]))
            exp = parse_capability_timestamp(dms.get("exp"))
            # Handle both old string format and new object format
            org_info = known_orgs.get(org_did)
            if isinstance(org_info, dict):
                org_name = org_info.get("name", "Unknown Organisation")
            elif isinstance(org_info, str):
                org_name = org_info
            else:
                org_name = "Unknown Organisation"
            
            if org_did and org_did not in seen:
                result.append({
                    "org_did": org_did,
                    "caps": caps,
                    "exp": exp,
                    "org_name": org_name
                })
                seen.add(org_did)

        return result
    except Exception as e:
        print(f"[ERROR] Failed to parse require section: {e}")
        return []

def get_trusted_by_organizations_from_provide():
    """
    Get organizations THAT TRUST YOU (i.e., where YOU are the sub)
    Returns:
        list of dicts with keys: org_did, caps, exp
    """
    cap_file = Path("/home/ubuntu/.nunet/cap/dms.cap")
    from modules.dms_manager import DMSManager
    from modules.org_utils import load_known_organizations
    dms_manager = DMSManager()
    known_orgs = load_known_organizations()

    self_peer_did = dms_manager.get_self_peer_info()['did']
    if not cap_file.exists():
        return []

    try:
        with open(cap_file, 'r') as f:
            data = json.load(f)

        result = []
        seen = set()

        for token in data.get("provide", {}).get("tok", []):
            dms = token.get("dms", {})
            user_did = dms.get("sub", {}).get("uri")
            my_did = self_peer_did  # Or read from config
            if user_did == my_did:
                org_did = get_root_issuer(token)
                caps = ", ".join(dms.get("cap", ["none"]))
                exp = parse_capability_timestamp(dms.get("exp"))
                
                # Handle both old string format and new object format
                org_info = known_orgs.get(org_did)
                if isinstance(org_info, dict):
                    org_name = org_info.get("name", "Unknown Organisation")
                elif isinstance(org_info, str):
                    org_name = org_info
                else:
                    org_name = "Unknown Organisation"
                
                if org_did and org_did not in seen:
                    result.append({
                        "org_did": org_did,
                        "caps": caps,
                        "exp": exp,
                        "org_name": org_name
                    })
                    seen.add(org_did)

        return result
    except Exception as e:
        print(f"[ERROR] Failed to parse provide section: {e}")
        return []

def inspect_capabilities():
    """
    Main function to show bidirectional trust relationships
    """
    require_orgs = get_trusted_organizations_from_require()
    provide_orgs = get_trusted_by_organizations_from_provide()

    print("=" * 80)
    print("ORGANIZATIONS YOU TRUST (REQUIRE)")
    print("-" * 80)
    if not require_orgs:
        print("No organizations found.")
    else:
        print("{:<60} {:<30} {:<30} {:<20}".format("Organisation DID", "Organisation Name", "Capabilities You Granted", "Expiry Date"))
        for org in require_orgs:
            print("{:<60} {:<30} {:<30} {:<20}".format(org["org_did"], org["org_name"], org["caps"], org["exp"]))

    print()
    print("=" * 80)
    print("ORGANIZATIONS THAT TRUST YOU (PROVIDE)")
    print("-" * 80)
    if not provide_orgs:
        print("No organizations found.")
    else:
        print("{:<60} {:<30} {:<30} {:<20}".format("Organisation DID", "Orgnisation Name", "Capabilities They Granted You", "Expiry Date"))
        for org in provide_orgs:
            print("{:<60} {:<30} {:<30} {:<20}".format(org["org_did"], org["org_name"], org["caps"], org["exp"]))