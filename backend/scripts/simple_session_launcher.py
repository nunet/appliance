#!/usr/bin/env python3
"""
Simplified Session Launcher with Splash Screens
Uses 3 simple text files to manage boot stages with beautiful splash screens.
"""

import sys
import os
import time
import subprocess
from pathlib import Path

# Add the menu directory to the Python path
menu_dir = Path(__file__).parent.parent
sys.path.insert(0, str(menu_dir))

# Only import boot_splash when needed (lazy loading)
boot_splash = None

def get_boot_splash():
    """Lazy load boot_splash only when needed."""
    global boot_splash
    if boot_splash is None:
        from modules.boot_splash import boot_splash as bs
        boot_splash = bs
    return boot_splash

def update_organizations_and_ensembles():
    """Update known organizations and example ensembles for onboarding"""
    try:
        print("🔄 Updating known organizations and ensembles...")
        
        # Update known organizations
        from modules.appliance_manager import ApplianceManager
        org_manager = ApplianceManager()
        org_result = org_manager.update_known_organizations()
        
        if org_result.get('status') == 'success':
            print(f"✅ Organizations updated: {org_result.get('message', 'Success')}")
        else:
            print(f"⚠️  Organizations update: {org_result.get('message', 'Unknown error')}")
        
        # Download example ensembles
        from modules.ensemble_manager import EnsembleManager
        ensemble_manager = EnsembleManager()
        ensemble_result = ensemble_manager.download_example_ensembles()
        
        if ensemble_result.get('status') == 'success':
            print(f"✅ Ensembles downloaded: {ensemble_result.get('message', 'Success')}")
        else:
            print(f"⚠️  Ensembles download: {ensemble_result.get('message', 'Unknown error')}")
        
        print("✅ Organizations and ensembles update complete!")
        time.sleep(2)  # Give user time to see the results
        
    except Exception as e:
        print(f"⚠️  Error updating organizations and ensembles: {e}")
        # Don't fail the onboarding process for this

def show_qr_code():
    """Show QR code for onboarding using the splash screen."""
    try:
        # Clear any existing onboarding state to start fresh
        onboarding_state_file = Path.home() / "nunet" / "appliance" / "onboarding_state.json"
        if onboarding_state_file.exists():
            try:
                import json
                with open(onboarding_state_file, 'r') as f:
                    existing_state = json.load(f)
                
                # Only clear if it's a leftover 'complete' state
                if existing_state.get('step') == 'complete' or existing_state.get('status') == 'complete':
                    onboarding_state_file.unlink()
                    print("Cleared existing onboarding state to start fresh")
            except Exception as e:
                print(f"Warning: Could not clear existing state: {e}")
        
        # Start the onboarding service
        try:
            subprocess.run(['sudo', 'systemctl', 'start', 'nunet-onboarding.service'], 
                          capture_output=True, text=True, check=True)
            print("Started onboarding service")
        except subprocess.CalledProcessError as e:
            print(f"Warning: Could not start onboarding service: {e}")
        
        # Check if web manager service is running
        result = subprocess.run(['systemctl', 'is-active', 'nunet-web-manager.service'], 
                              capture_output=True, text=True)
        
        if result.stdout.strip() != 'active':
            get_boot_splash().show_error_splash("Web manager service is not running. Please start it manually.")
            return False
        
        # Get local IP address using the existing utility function
        from modules.utils import get_local_ip
        local_ip = get_local_ip()
        url = f"https://{local_ip}:8080"
        
        # Try to get password from web manager config
        config_file = Path.home() / ".config" / "nunet" / "web_manager_config.json"
        password = "setup-password"
        
        if config_file.exists():
            try:
                import json
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    password = config.get('password', 'setup-password')
            except Exception:
                pass
        
        # Generate QR code using qrcode library
        try:
            import qrcode
            qr_data = f"{url}?password={password}"
            qr = qrcode.QRCode(border=2)
            qr.add_data(qr_data)
            qr.make()
            
            # Convert QR code to text representation
            matrix = qr.get_matrix()
            qr_lines = [''.join('██' if cell else '  ' for cell in row) for row in matrix]
            
            # Create instruction text
            text_lines = [
                "Scan this QR code to open the onboarding wizard:",
                "",
                f"🌐 Or visit this URL in your web browser:",
                f"{url}",
                "",
                f"🔑 Setup Password:",
                f"{password}",
                "",
                f"📋 Instructions:",
                "- The password will expire after 30 minutes",
                "- You have 10 login attempts",
                "- The web interface will close after successful onboarding",
                "",
                f"🔄 Web manager service is running",
                f"📊 Onboarding progress will be shown below:",
                "",
                "=" * 60
            ]
            
            # Display QR code and instructions side by side
            max_qr_height = len(qr_lines)
            max_text_height = len(text_lines)
            total_lines = max(max_qr_height, max_text_height)
            
            # Pad arrays to same length
            qr_lines += [' ' * len(qr_lines[0])] * (total_lines - max_qr_height)
            text_lines += [''] * (total_lines - max_text_height)
            
            # Display header
            print("🚀 NuNet Appliance - Onboarding")
            print("=" * 60)
            print()
            
            for qr_line, text_line in zip(qr_lines, text_lines):
                print(f"{qr_line}   {text_line}")
            
            # Start monitoring immediately without user input
            monitor_onboarding_progress()
            return True
            
        except ImportError:
            get_boot_splash().show_error_splash("QR code library not available. Please install python3-qrcode.")
            return False
        
    except Exception as e:
        get_boot_splash().show_error_splash(f"Error showing QR code: {e}")
        return False

def monitor_onboarding_progress():
    """Monitor onboarding progress and show updates using splash screens."""
    onboarding_state_file = Path.home() / "nunet" / "appliance" / "onboarding_state.json"
    last_step = None
    onboarding_started = False
    
    # Don't show initial splash - keep QR code visible
    print("\n⏳ Monitoring onboarding progress...")
    
    # Create OnboardingManager instance once
    from modules.onboarding_manager import OnboardingManager
    onboarding_mgr = OnboardingManager()
    
    while True:
        try:
            
            if onboarding_mgr.is_onboarding_complete():
                print("✅ Onboarding completed successfully!")
                time.sleep(3)
                
                # Mark onboarding as complete using sudo since it requires root permissions
                try:
                    subprocess.run(['sudo', 'touch', '/var/lib/cloud/instance/onboarding_complete'], 
                                  capture_output=True, text=True, check=True)
                    print("✅ Onboarding completion marker created")
                except subprocess.CalledProcessError as e:
                    print(f"⚠️  Warning: Could not create completion marker: {e}")
                    # Continue anyway since onboarding is actually complete
                
                # Update .bashrc for direct menu access
                update_bashrc_for_direct_menu()
                
                # Launch the menu
                launch_menu()
                break
            
            # Also monitor the state file for progress updates
            if onboarding_state_file.exists():
                import json
                with open(onboarding_state_file, 'r') as f:
                    state = json.load(f)
                
                current_step = state.get('step', 'Unknown')
                error = state.get('error')
                
                # Check if onboarding has actually started (not just a leftover state)
                if not onboarding_started and current_step not in ['init', 'Unknown']:
                    onboarding_started = True
                    print(f"✅ Onboarding started - Current step: {current_step}")
                
                if current_step != last_step:
                    # Show progress update without clearing the QR code
                    if current_step in ['init', 'select_org', 'collect_join_data']:
                        print(f"🔄 Step: {current_step} - Organization selection")
                    elif current_step in ['submit_data', 'join_data_sent', 'pending_authorization']:
                        print(f"🔄 Step: {current_step} - Waiting for organization approval")
                    elif current_step in ['join_data_received', 'capabilities_applied', 'telemetry_configured', 'mtls_certs_saved']:
                        print(f"🔄 Step: {current_step} - Applying configuration")
                    elif current_step == 'complete':
                        print(f"🔄 Step: {current_step} - Finalizing onboarding")
                    
                    last_step = current_step
                
                if error:
                    print(f"❌ Error: {error}")
                    
            time.sleep(2)
            
        except Exception as e:
            print(f"❌ Error monitoring onboarding progress: {e}")
            time.sleep(5)

def update_bashrc_for_direct_menu():
    """Update .bashrc to launch menu.py directly instead of session launcher."""
    try:
        bashrc_file = Path.home() / ".bashrc"
        menu_script = Path(__file__).parent.parent / "menu.py"
        session_launcher = Path(__file__)  # Current script path
        
        if not menu_script.exists():
            print("⚠️  Menu script not found, skipping .bashrc update")
            return False
        
        # Read current .bashrc
        with open(bashrc_file, 'r') as f:
            lines = f.readlines()
        
        # Check if we already have the direct menu launch
        menu_launch_pattern = f"python3 {menu_script}"
        if any(menu_launch_pattern in line for line in lines):
            print("✅ .bashrc already updated for direct menu access")
            return True
        
        # Find and replace the session launcher line
        session_launcher_pattern = str(session_launcher)
        updated_lines = []
        replaced = False
        
        for line in lines:
            if session_launcher_pattern in line:
                # Replace session launcher with direct menu call
                updated_lines.append(f"# Launch NuNet menu directly (post-onboarding)\n")
                updated_lines.append(f"python3 {menu_script}\n")
                replaced = True
                print(f"🔄 Replaced session launcher with direct menu access")
            else:
                updated_lines.append(line)
        
        # If we didn't find the session launcher line, add the menu call at the end
        if not replaced:
            updated_lines.append(f"\n# Launch NuNet menu directly (post-onboarding)\n")
            updated_lines.append(f"python3 {menu_script}\n")
            print(f"➕ Added direct menu access to .bashrc")
        
        # Write the updated content back to .bashrc
        with open(bashrc_file, 'w') as f:
            f.writelines(updated_lines)
        
        print("✅ Updated .bashrc for direct menu access")
        return True
        
    except Exception as e:
        print(f"⚠️  Error updating .bashrc: {e}")
        return False

def launch_menu():
    """Launch the main menu."""
    try:
        menu_script = Path(__file__).parent.parent / "menu.py"
        if menu_script.exists():
            subprocess.run([sys.executable, str(menu_script)], check=True)
        else:
            print("❌ Menu script not found")
    except Exception as e:
        print(f"❌ Error launching menu: {e}")

def main():
    """Main entry point - simplified logic using 3 text files with splash screens."""
    
    # Define the 3 key files that control boot behavior
    first_boot_complete = Path("/var/lib/cloud/instance/first_boot_complete")
    onboarding_complete = Path("/var/lib/cloud/instance/onboarding_complete")
    auto_onboarding_enabled = Path("/var/lib/cloud/instance/auto_onboarding_enabled")
    
    # Check if .bashrc has been updated for direct menu access
    bashrc_file = Path.home() / ".bashrc"
    menu_script = Path(__file__).parent.parent / "menu.py"
    
    if bashrc_file.exists() and menu_script.exists():
        try:
            with open(bashrc_file, 'r') as f:
                content = f.read()
            
            # If .bashrc already has direct menu access and onboarding is complete, skip session launcher
            if f"python3 {menu_script}" in content and onboarding_complete.exists():
                print("Debug: Direct menu access enabled, launching menu directly")
                launch_menu()
                return
        except Exception:
            pass  # Continue with normal flow if there's any error
    
    # Debug logging
    print(f"Debug: first_boot_complete exists: {first_boot_complete.exists()}")
    print(f"Debug: onboarding_complete exists: {onboarding_complete.exists()}")
    print(f"Debug: auto_onboarding_enabled exists: {auto_onboarding_enabled.exists()}")
    
    # Check if first boot is still in progress
    if not first_boot_complete.exists():
        print("Debug: First boot in progress - showing Phase 0 splash")
        # Show Phase 0 splash screen first (only on first boot)
        get_boot_splash().show_phase0_splash()
        
        # After Phase 0 completes, always show Phase 1 splash
        print(f"Debug: Phase 0 completed, showing Phase 1 splash")
        
        # Show Phase 1 splash screen and monitor progress
        progress_file = Path("/tmp/boot_progress.txt")
        
        # If first boot is already complete, show completion immediately
        if first_boot_complete.exists():
            print("Debug: First boot already complete, showing completion message")
            get_boot_splash().show_phase1_splash(step="complete", progress=100)
            time.sleep(3)
            
            # Trigger reboot after showing completion message
            print("Debug: First boot complete, triggering reboot...")
            try:
                subprocess.run(['sudo', 'reboot'], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Debug: Could not trigger reboot: {e}")
                print("Debug: Please reboot manually to continue")
        else:
            print("Debug: First boot still in progress - monitoring progress")
            # Monitor progress until first boot completes
            while not first_boot_complete.exists():
                # Read progress from file if it exists
                if progress_file.exists():
                    try:
                        with open(progress_file, 'r') as f:
                            lines = f.read().strip().split('\n')
                            if len(lines) >= 2:
                                progress = int(lines[0])
                                step = lines[1]
                                get_boot_splash().show_phase1_splash(step=step.lower().replace(' ', '_'), progress=progress)
                    except Exception:
                        # Fallback to generic progress
                        get_boot_splash().show_phase1_splash(step="initializing", progress=0)
                else:
                    get_boot_splash().show_phase1_splash(step="initializing", progress=0)
                
                time.sleep(2)
            
            # Show completion message
            get_boot_splash().show_phase1_splash(step="complete", progress=100)
            time.sleep(3)
            
            # Trigger reboot after showing completion message
            print("Debug: First boot complete, triggering reboot...")
            try:
                subprocess.run(['sudo', 'reboot'], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Debug: Could not trigger reboot: {e}")
                print("Debug: Please reboot manually to continue")
        
        # Don't return here - continue to check other phases
    
    # Check if onboarding is complete
    if onboarding_complete.exists():
        print("Debug: Onboarding complete - showing welcome splash and launching menu")
        # Show welcome splash for normal operation
        get_boot_splash().show_phase2_splash(step="complete")
        launch_menu()
        return
    
    # Check if auto-onboarding is enabled (only on second boot)
    if auto_onboarding_enabled.exists():
        print("Debug: Auto-onboarding enabled - starting onboarding process")
        # Show Phase 2 welcome splash
        get_boot_splash().show_phase2_splash(step="welcome")
        time.sleep(2)  # Brief pause to show welcome message
        
        # Update organizations and ensembles
        update_organizations_and_ensembles()

        # Show QR code for onboarding
        if show_qr_code():
            # Remove the auto-onboarding flag after showing QR code
            auto_onboarding_enabled.unlink(missing_ok=True)
        else:
            # If QR code fails, show error and launch menu
            get_boot_splash().show_error_splash("Failed to show QR code. Launching menu instead.")
            launch_menu()
    else:
        print("Debug: No auto-onboarding flag - showing welcome splash and launching menu")
        # Normal operation - show welcome and launch menu
        get_boot_splash().show_phase2_splash(step="complete")
        launch_menu()

if __name__ == "__main__":
    main() 