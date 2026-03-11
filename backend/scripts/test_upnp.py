#!/usr/bin/env python3
"""
Simple test script for UPnP functionality.

This script demonstrates how to use the UPnP manager to:
1. Discover UPnP gateways
2. Check current port mappings
3. Configure appliance port forwarding
4. Get comprehensive status

Usage:
    python test_upnp.py
"""

import sys
import json
from pathlib import Path

# Add backend modules to path
backend_path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_path))

from modules.upnp_manager import UPnPManager


def print_section(title):
    """Print a formatted section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def print_json(data, indent=2):
    """Print data as formatted JSON."""
    print(json.dumps(data, indent=indent))


def test_upnp():
    """Run comprehensive UPnP tests."""
    
    print_section("UPnP Gateway Discovery Test")
    
    # Initialize manager
    upnp = UPnPManager()
    
    # Test 1: Discover gateway
    print("1. Discovering UPnP gateway...")
    gateway = upnp.discover_gateway()
    print_json(gateway)
    
    if gateway.get('status') != 'success':
        print("\n❌ UPnP gateway not found or error occurred.")
        print("   Possible reasons:")
        print("   - UPnP is disabled on your router")
        print("   - No UPnP-capable router on network")
        print("   - miniupnpc library not installed")
        print("\n   To enable UPnP, check your router's admin interface.")
        return
    
    print(f"\n✅ Gateway found!")
    print(f"   External IP: {gateway['gateway_info']['external_ip']}")
    print(f"   Local IP: {gateway['gateway_info']['local_ip']}")
    print(f"   Connection: {gateway['gateway_info']['connection_status']}")
    
    # Test 2: List existing port mappings
    print_section("Current Port Mappings")
    
    print("2. Listing existing port mappings...")
    mappings = upnp.list_port_mappings()
    print_json(mappings)
    
    if mappings.get('total_count', 0) > 0:
        print(f"\n✅ Found {mappings['total_count']} existing port mapping(s):")
        for m in mappings['mappings']:
            print(f"   - Port {m['external_port']}/{m['protocol']} -> "
                  f"{m['internal_ip']}:{m['internal_port']} ({m['description']})")
    else:
        print("\n   No existing port mappings found.")
    
    # Test 3: Check specific ports
    print_section("Check Appliance Ports")
    
    print("3. Checking if appliance ports are already forwarded...")
    
    port_443 = upnp.check_port_mapping(443, "TCP")
    port_8443 = upnp.check_port_mapping(8443, "TCP")
    
    print("\nPort 443 status:")
    if port_443.get('mapping_exists'):
        print(f"   ✅ Port 443 is forwarded to {port_443['mapping']['internal_ip']}:"
              f"{port_443['mapping']['internal_port']}")
    else:
        print("   ❌ Port 443 is not forwarded")
    
    print("\nPort 8443 status:")
    if port_8443.get('mapping_exists'):
        print(f"   ✅ Port 8443 is forwarded to {port_8443['mapping']['internal_ip']}:"
              f"{port_8443['mapping']['internal_port']}")
    else:
        print("   ❌ Port 8443 is not forwarded")
    
    # Test 4: Configure appliance port forwarding
    print_section("Configure Appliance Port Forwarding")
    
    print("4. Configuring appliance port forwarding (443 -> 8443)...")
    
    response = input("\nDo you want to configure port forwarding? (y/n): ").strip().lower()
    
    if response == 'y':
        result = upnp.configure_appliance_port_forwarding(
            external_port=443,
            internal_port=8443
        )
        print_json(result)
        
        if result.get('status') == 'success':
            print(f"\n✅ {result['message']}")
            if result.get('newly_created'):
                print("   Port mapping was created successfully!")
            else:
                print("   Port mapping already existed.")
        else:
            print(f"\n❌ Failed to configure port forwarding: {result.get('message')}")
    else:
        print("   Skipped port forwarding configuration.")
    
    # Test 5: Get comprehensive status
    print_section("Comprehensive Appliance Status")
    
    print("5. Getting comprehensive appliance status...")
    status = upnp.get_appliance_status()
    print_json(status)
    
    if status.get('status') == 'success':
        print("\n✅ Status Summary:")
        print(f"   External IP: {status['gateway_info']['external_ip']}")
        print(f"   Local IP: {status['gateway_info']['local_ip']}")
        
        port_443_status = status['appliance_forwarding']['port_443']
        port_8443_status = status['appliance_forwarding']['port_8443']
        
        if port_443_status.get('mapping_exists'):
            print("   ✅ Port 443 forwarding: ACTIVE")
            print(f"      Access appliance at: https://{status['gateway_info']['external_ip']}")
        else:
            print("   ❌ Port 443 forwarding: NOT CONFIGURED")
        
        if port_8443_status.get('mapping_exists'):
            print("   ✅ Port 8443 forwarding: ACTIVE")
        else:
            print("   ❌ Port 8443 forwarding: NOT CONFIGURED")
    
    print_section("Test Complete")
    print("UPnP testing finished successfully!\n")


def main():
    """Main entry point."""
    print("\n" + "=" * 60)
    print("  NuNet Appliance - UPnP Test Script")
    print("=" * 60)
    print("\nThis script will test the UPnP functionality of your appliance.")
    print("It will:")
    print("  1. Discover UPnP gateways on your network")
    print("  2. List current port mappings")
    print("  3. Check appliance-specific ports")
    print("  4. Optionally configure port forwarding")
    print("  5. Display comprehensive status")
    
    input("\nPress Enter to continue...")
    
    try:
        test_upnp()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


