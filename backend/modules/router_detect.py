"""
Router Detection Module

Detects the default gateway router and identifies its brand via MAC address lookup.
"""

import subprocess
import re
import logging
from typing import Tuple, Optional, Dict

logger = logging.getLogger(__name__)


# MAC OUI (Organizationally Unique Identifier) to vendor mapping
# First 3 bytes of MAC address identify the manufacturer
MAC_OUI_VENDORS = {
    # MikroTik
    "00:0C:42": "MikroTik",
    "4C:5E:0C": "MikroTik",
    "6C:3B:6B": "MikroTik",
    "74:4D:28": "MikroTik",
    "D4:CA:6D": "MikroTik",
    "E7:16:34": "MikroTik",
    "48:A9:8A": "MikroTik",
    "DC:2C:6E": "MikroTik",
    
    # TP-Link
    "14:CC:20": "TP-Link",
    "50:C7:BF": "TP-Link",
    "A4:2B:8C": "TP-Link",
    "E8:DE:27": "TP-Link",
    "F4:F2:6D": "TP-Link",
    "C0:25:E9": "TP-Link",
    "98:DE:D0": "TP-Link",
    
    # Netgear
    "00:14:6C": "Netgear",
    "20:E5:2A": "Netgear",
    "28:C6:8E": "Netgear",
    "A0:63:91": "Netgear",
    "B0:39:56": "Netgear",
    "E0:46:9A": "Netgear",
    "08:02:8E": "Netgear",
    
    # Asus
    "00:1E:8C": "Asus",
    "04:D4:C4": "Asus",
    "08:60:6E": "Asus",
    "10:BF:48": "Asus",
    "1C:87:2C": "Asus",
    "2C:56:DC": "Asus",
    "38:D5:47": "Asus",
    
    # Linksys / Cisco
    "00:0C:41": "Linksys",
    "00:12:17": "Linksys",
    "00:18:F8": "Linksys",
    "00:1C:10": "Linksys",
    "00:1E:E5": "Linksys",
    "48:F8:B3": "Linksys",
    "C4:41:1E": "Linksys",
    
    # D-Link
    "00:05:5D": "D-Link",
    "00:0D:88": "D-Link",
    "00:11:95": "D-Link",
    "00:13:46": "D-Link",
    "00:15:E9": "D-Link",
    "00:17:9A": "D-Link",
    "00:19:5B": "D-Link",
    
    # Ubiquiti
    "00:15:6D": "Ubiquiti",
    "04:18:D6": "Ubiquiti",
    "24:A4:3C": "Ubiquiti",
    "68:72:51": "Ubiquiti",
    "70:A7:41": "Ubiquiti",
    "74:83:C2": "Ubiquiti",
    "F0:9F:C2": "Ubiquiti",
    
    # Belkin
    "00:11:50": "Belkin",
    "08:86:3B": "Belkin",
    "94:44:52": "Belkin",
    "EC:1A:59": "Belkin",
    
    # Zyxel
    "00:13:49": "Zyxel",
    "40:4A:03": "Zyxel",
    "F8:A0:97": "Zyxel",
    
    # Huawei
    "00:E0:FC": "Huawei",
    "28:6E:D4": "Huawei",
    "00:18:82": "Huawei",
    
    # Apple Airport
    "00:03:93": "Apple",
    "00:0A:95": "Apple",
    "00:0D:93": "Apple",
    "A8:FA:D8": "Apple",
}


def get_default_gateway() -> Optional[str]:
    """
    Get the IP address of the default gateway (router).
    
    Tries multiple methods in order of preference:
    1. Read from /proc/net/route (no subprocess, works with limited permissions)
    2. ip route command (requires subprocess)
    3. route command (requires subprocess)
    
    Returns:
        Gateway IP address as string, or None if not found
    """
    # Method 1: Read from /proc/net/route (no subprocess needed, works in containers/services)
    try:
        with open('/proc/net/route', 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 3 and parts[1] == '00000000':  # Destination 0.0.0.0
                    # Gateway is in hex format, convert to IP
                    gateway_hex = parts[2]
                    if len(gateway_hex) == 8:
                        # Convert hex to IP: "0101A8C0" -> "192.168.1.1"
                        gateway_ip = '.'.join([
                            str(int(gateway_hex[i:i+2], 16)) 
                            for i in range(6, -1, -2)
                        ])
                        # Skip 0.0.0.0 (no gateway)
                        if gateway_ip != '0.0.0.0':
                            logger.debug(f"Found default gateway from /proc/net/route: {gateway_ip}")
                            return gateway_ip
    except (FileNotFoundError, PermissionError, IOError) as e:
        logger.warning(f"Could not read /proc/net/route: {e} - trying alternative methods")
    except Exception as e:
        logger.warning(f"Error parsing /proc/net/route: {e} - trying alternative methods")
    
    # Method 1b: Try reading from /sys/class/net (alternative to /proc)
    try:
        import os
        import glob
        # Look for default route in /sys/class/net/*/route
        for iface_dir in glob.glob('/sys/class/net/*'):
            route_file = os.path.join(iface_dir, 'route')
            if os.path.exists(route_file):
                try:
                    with open(route_file, 'r') as f:
                        for line in f:
                            # Format: destination gateway ... (space-separated)
                            parts = line.strip().split()
                            if len(parts) >= 2 and parts[0] == '00000000':
                                gateway_hex = parts[1]
                                if len(gateway_hex) == 8:
                                    gateway_ip = '.'.join([
                                        str(int(gateway_hex[i:i+2], 16)) 
                                        for i in range(6, -1, -2)
                                    ])
                                    if gateway_ip != '0.0.0.0':
                                        logger.debug(f"Found default gateway from /sys/class/net: {gateway_ip}")
                                        return gateway_ip
                except (PermissionError, IOError):
                    continue
    except Exception as e:
        logger.debug(f"Could not read from /sys/class/net: {e}")
    
    # Method 2: Try ip route command (Linux)
    try:
        result = subprocess.run(
            ['ip', 'route', 'show', 'default'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # Parse: "default via 192.168.1.1 dev eth0"
            match = re.search(r'default via ([\d.]+)', result.stdout)
            if match:
                gateway_ip = match.group(1)
                logger.debug(f"Found default gateway via ip route: {gateway_ip}")
                return gateway_ip
    except (FileNotFoundError, PermissionError) as e:
        logger.debug(f"Could not run ip route command: {e}")
    except Exception as e:
        logger.debug(f"Error running ip route: {e}")
    
    # Method 3: Fallback: try route command
    try:
        result = subprocess.run(
            ['route', '-n'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if line.startswith('0.0.0.0'):
                    parts = line.split()
                    if len(parts) >= 2:
                        gateway_ip = parts[1]
                        logger.debug(f"Found default gateway via route: {gateway_ip}")
                        return gateway_ip
    except (FileNotFoundError, PermissionError) as e:
        logger.debug(f"Could not run route command: {e}")
    except Exception as e:
        logger.debug(f"Error running route: {e}")
    
    logger.warning("Could not determine default gateway using any method")
    return None


def get_mac_address(ip_address: str) -> Optional[str]:
    """
    Get the MAC address for a given IP address via ARP.
    
    Tries multiple methods in order of preference:
    1. Read from /proc/net/arp (no subprocess, works with limited permissions)
    2. ip neigh command (requires subprocess)
    3. arp command (requires subprocess)
    
    Args:
        ip_address: IP address to lookup
        
    Returns:
        MAC address as string (e.g., "00:0C:42:12:34:56"), or None if not found
    """
    # Method 1: Read directly from /proc/net/arp (no subprocess needed)
    try:
        with open('/proc/net/arp', 'r') as f:
            for line in f:
                # Format: "IP address     HW type     Flags     HW address     Mask     Device"
                # Example: "192.168.88.1   0x1        0x2       74:4d:28:91:c0:73     *        bridge"
                parts = line.strip().split()
                if len(parts) >= 4 and parts[0] == ip_address:
                    mac_address = parts[3].upper()
                    # Validate MAC format (should be XX:XX:XX:XX:XX:XX)
                    if re.match(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$', mac_address):
                        logger.debug(f"Found MAC address for {ip_address} from /proc/net/arp: {mac_address}")
                        return mac_address
    except (FileNotFoundError, PermissionError, IOError) as e:
        logger.debug(f"Could not read /proc/net/arp: {e} - trying alternative methods")
    except Exception as e:
        logger.debug(f"Error parsing /proc/net/arp: {e} - trying alternative methods")
    
    # Method 2: Try ip neigh command (requires subprocess)
    try:
        # First, ping the IP to ensure it's in ARP cache
        subprocess.run(
            ['ping', '-c', '1', '-W', '1', ip_address],
            capture_output=True,
            timeout=2
        )
        
        # Get MAC from ARP cache
        result = subprocess.run(
            ['ip', 'neigh', 'show', ip_address],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # Parse: "192.168.88.1 dev bridge lladdr 4c:5e:0c:12:34:56 REACHABLE"
            match = re.search(r'lladdr ([0-9a-fA-F:]{17})', result.stdout)
            if match:
                mac_address = match.group(1).upper()
                logger.debug(f"Found MAC address for {ip_address} via ip neigh: {mac_address}")
                return mac_address
    except (FileNotFoundError, PermissionError) as e:
        logger.debug(f"Could not run ip neigh command: {e}")
    except Exception as e:
        logger.debug(f"Error running ip neigh: {e}")
    
    # Method 3: Fallback: try arp command
    try:
        result = subprocess.run(
            ['arp', '-n', ip_address],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # Parse: "192.168.88.1  ether  4c:5e:0c:12:34:56  C  eth0"
            match = re.search(r'([0-9a-fA-F:]{17})', result.stdout)
            if match:
                mac_address = match.group(1).upper()
                logger.debug(f"Found MAC address via arp command for {ip_address}: {mac_address}")
                return mac_address
    except (FileNotFoundError, PermissionError) as e:
        logger.debug(f"Could not run arp command: {e}")
    except Exception as e:
        logger.debug(f"Error running arp: {e}")
    
    logger.warning(f"Could not find MAC address for {ip_address} using any method")
    return None


def identify_vendor_from_mac(mac_address: str) -> str:
    """
    Identify the vendor/brand from a MAC address OUI.
    
    Args:
        mac_address: MAC address (e.g., "4C:5E:0C:12:34:56")
        
    Returns:
        Vendor name as string, or "Unknown" if not recognized
    """
    if not mac_address or len(mac_address) < 8:
        return "Unknown"
    
    # Extract OUI (first 3 bytes)
    oui = mac_address[:8].upper()  # "4C:5E:0C"
    
    vendor = MAC_OUI_VENDORS.get(oui, "Unknown")
    
    if vendor != "Unknown":
        logger.info(f"Identified router vendor from MAC {mac_address}: {vendor}")
    else:
        logger.debug(f"Unknown vendor for MAC {mac_address} (OUI: {oui})")
    
    return vendor


def detect_router() -> Dict[str, any]:
    """
    Detect the default gateway router and identify its brand.
    
    Returns:
        Dictionary with router information:
        {
            "detected": bool,
            "gateway_ip": str,
            "mac_address": str,
            "brand": str,
            "message": str
        }
    """
    logger.info("Detecting router...")
    
    # Get gateway IP
    try:
        gateway_ip = get_default_gateway()
        if not gateway_ip:
            logger.warning("get_default_gateway() returned None - all detection methods failed")
            # Try to get more info about why it failed
            import os
            proc_accessible = os.access('/proc/net/route', os.R_OK)
            logger.debug(f"/proc/net/route accessible: {proc_accessible}")
            return {
                "detected": False,
                "gateway_ip": None,
                "mac_address": None,
                "brand": "Unknown",
                "message": "Could not detect default gateway (all methods failed)"
            }
    except Exception as e:
        logger.error(f"Exception in get_default_gateway(): {e}", exc_info=True)
        return {
            "detected": False,
            "gateway_ip": None,
            "mac_address": None,
            "brand": "Unknown",
            "message": f"Error detecting gateway: {str(e)}"
        }
    
    # Get MAC address
    mac_address = get_mac_address(gateway_ip)
    if not mac_address:
        return {
            "detected": True,
            "gateway_ip": gateway_ip,
            "mac_address": None,
            "brand": "Unknown",
            "message": f"Found router at {gateway_ip} but could not determine brand"
        }
    
    # Identify brand
    brand = identify_vendor_from_mac(mac_address)
    
    return {
        "detected": True,
        "gateway_ip": gateway_ip,
        "mac_address": mac_address,
        "brand": brand,
        "message": f"Detected {brand} router at {gateway_ip}"
    }


if __name__ == "__main__":
    # Test the router detection
    logging.basicConfig(level=logging.DEBUG)
    
    print("=" * 70)
    print("  ROUTER DETECTION TEST")
    print("=" * 70)
    
    info = detect_router()
    
    print(f"\nDetected: {info['detected']}")
    print(f"Gateway IP: {info['gateway_ip']}")
    print(f"MAC Address: {info['mac_address']}")
    print(f"Brand: {info['brand']}")
    print(f"Message: {info['message']}")
    
    print("\n" + "=" * 70)

