"""
Organizations management module for NuNet
"""

import datetime
import subprocess
import requests
import os
from pathlib import Path
from typing import Dict, Literal
from .dms_utils import run_dms_command_with_passphrase
from modules.utils import (
    Colors, ConfigManager, clear_screen, pause)
from .org_utils import load_known_organizations, get_joined_organizations_with_names

OrganizationType = Literal["nunet", "auki", "jam_galaxy", "ocean"]

class OrganizationManager:
    def __init__(self):
        self.home_dir = Path.home()
        self.scripts_dir = self.home_dir / "menu" / "scripts"

    def join_organization(self, org_type: str = None, step: str = 'generate', code: str = None, email: str = None, location: str = None, discord: str = None, dms_did: str = None, peer_id: str =None) -> Dict[str, str]:
        """
        Two-step join process for web onboarding.
        step='generate': generate and return wormhole code.
        step='join': join using the provided wormhole code.
        """
        try:
            script_path = self.scripts_dir / "join-org-web.sh"
            if not script_path.exists():
                return {
                    "status": "error",
                    "message": "Organization join script for web not found"
                }
            if step == 'generate':
                result = subprocess.run(['bash', str(script_path), 'generate'], capture_output=True, text=True)
                output = result.stdout + result.stderr
                # Log output
                with open("/home/ubuntu/nunet/appliance/onboarding.log", "a") as logf:
                    logf.write("[SCRIPT OUTPUT] join-org-web.sh generate:\n")
                    logf.write(output + "\n")
                if result.returncode == 0:
                    return {
                        "status": "success",
                        "wormhole_code": result.stdout.strip(),
                        "output": output
                    }
                else:
                    return {
                        "status": "error",
                        "message": result.stderr.strip() or result.stdout.strip(),
                        "output": output
                    }
            elif step == 'join' and code:
                payload = {
                    'email': email,
                    'location': location,
                    'discord': discord,
                    'wormhole': code,
                    'dms_did': dms_did,
                    'peer_id': peer_id
                }
                print("==========")
                print(payload)
                print("==========")

                result = subprocess.run(['bash', str(script_path), 'join', code], capture_output=True, text=True)
                output = result.stdout + result.stderr
                # Log output
                with open("/home/ubuntu/nunet/appliance/onboarding.log", "a") as logf:
                    logf.write("[SCRIPT OUTPUT] join-org-web.sh join:\n")
                    logf.write(output + "\n")
                if result.returncode == 0:
                    return {
                        "status": "success",
                        "message": f"✅ Organization join process completed.",
                        "output": output
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"Failed to join organization. Process exited with code {result.returncode}",
                        "output": output
                    }
            else:
                return {
                    "status": "error",
                    "message": "Invalid step or missing wormhole code."
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error joining organization: {str(e)}"
            }

    def join_nunet_network(self) -> Dict[str, str]:
        """Join the NuNet Compute Testnet"""
        return self.join_organization("nunet")

    def join_auki_network(self) -> Dict[str, str]:
        """Join the AUKI Compute Testnet"""
        return self.join_organization("auki")

    def join_jam_galaxy_network(self) -> Dict[str, str]:
        """Join the Jam Galaxy Testnet"""
        return self.join_organization("jam_galaxy")

    def join_ocean_network(self) -> Dict[str, str]:
        """Join the Ocean Protocol Testnet"""
        return self.join_organization("ocean") 

    def view_capability_relationships(self):
        """Display trusted organizations and who trusts the user"""
        from modules.capability_inspector import inspect_capabilities

        clear_screen()
        print(f"{Colors.CYAN}{'='*50}\nKnown Organizations Considered Safe by NuNet\n{'='*50}{Colors.NC}")
        known = load_known_organizations()
        if known:
            for idx, (did, name) in enumerate(known.items(), start=1):
                print(f"{idx}. {name} ({did})")
        else:
            print(f"{Colors.MAGENTA}No known organizations found.{Colors.NC}")

        print(f"{Colors.CYAN}{'='*50}\nOrganisations You have joined \n{'='*50}{Colors.NC}")
        org_list = get_joined_organizations_with_names()
        if not org_list:
            print(f"{Colors.MAGENTA}You are not part of any organization yet.{Colors.NC}")
        else:
            for idx, org in enumerate(org_list, start=1):
                did = org["did"]
                name = org.get("name")
                if name:
                    print(f"{idx}. {Colors.YELLOW}{name}{Colors.NC} ({Colors.BLUE}{did}{Colors.NC})")
                else:
                    print(f"{idx}. {Colors.BLUE}{did}{Colors.NC} (Unknown Organization)")
        print(f"{Colors.CYAN}{'='*50}\nTrust Table (Your relationship with organisations) \n{'='*50}{Colors.NC}")
        inspect_capabilities()
        pause()

    def get_organization_status(self):
        """Return joined and known organizations using org_utils functions."""
        return {
            "joined": get_joined_organizations_with_names(),
            "known": load_known_organizations()
        }