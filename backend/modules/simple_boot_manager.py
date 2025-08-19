#!/usr/bin/env python3
"""
Simplified Boot Manager
Manages boot stages using 3 simple text files instead of complex JSON state.
"""

import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SimpleBootManager:
    """Simplified boot manager using 3 text files."""
    
    def __init__(self):
        # The 3 key files that control boot behavior
        self.first_boot_complete = Path("/var/lib/cloud/instance/first_boot_complete")
        self.onboarding_complete = Path("/var/lib/cloud/instance/onboarding_complete")
        self.auto_onboarding_enabled = Path("/var/lib/cloud/instance/auto_onboarding_enabled")
    
    def is_first_boot(self) -> bool:
        """Check if this is the first boot (before first_boot_complete exists)."""
        return not self.first_boot_complete.exists()
    
    def is_onboarding_complete(self) -> bool:
        """Check if onboarding is complete."""
        return self.onboarding_complete.exists()
    
    def is_auto_onboarding_enabled(self) -> bool:
        """Check if auto-onboarding should be shown (second boot only)."""
        return self.auto_onboarding_enabled.exists()
    
    def get_boot_phase(self) -> str:
        """Get the current boot phase."""
        if self.is_first_boot():
            return "first_boot"
        elif not self.is_onboarding_complete():
            return "onboarding_needed"
        else:
            return "normal_operation"
    
    def mark_first_boot_complete(self) -> bool:
        """Mark first boot as complete."""
        try:
            self.first_boot_complete.touch()
            logger.info("First boot marked as complete")
            return True
        except Exception as e:
            logger.error(f"Error marking first boot complete: {e}")
            return False
    
    def mark_onboarding_complete(self) -> bool:
        """Mark onboarding as complete."""
        try:
            self.onboarding_complete.touch()
            logger.info("Onboarding marked as complete")
            return True
        except Exception as e:
            logger.error(f"Error marking onboarding complete: {e}")
            return False
    
    def enable_auto_onboarding(self) -> bool:
        """Enable auto-onboarding for next boot."""
        try:
            self.auto_onboarding_enabled.touch()
            logger.info("Auto-onboarding enabled")
            return True
        except Exception as e:
            logger.error(f"Error enabling auto-onboarding: {e}")
            return False
    
    def disable_auto_onboarding(self) -> bool:
        """Disable auto-onboarding."""
        try:
            if self.auto_onboarding_enabled.exists():
                self.auto_onboarding_enabled.unlink()
                logger.info("Auto-onboarding disabled")
            return True
        except Exception as e:
            logger.error(f"Error disabling auto-onboarding: {e}")
            return False
    
    def get_boot_info(self) -> Dict[str, Any]:
        """Get information about the current boot state."""
        return {
            'phase': self.get_boot_phase(),
            'is_first_boot': self.is_first_boot(),
            'is_onboarding_complete': self.is_onboarding_complete(),
            'is_auto_onboarding_enabled': self.is_auto_onboarding_enabled(),
            'first_boot_complete_exists': self.first_boot_complete.exists(),
            'onboarding_complete_exists': self.onboarding_complete.exists(),
            'auto_onboarding_enabled_exists': self.auto_onboarding_enabled.exists()
        }
    
    def get_phase_description(self) -> str:
        """Get a human-readable description of the current phase."""
        phase = self.get_boot_phase()
        descriptions = {
            "first_boot": "First Boot - System Configuration",
            "onboarding_needed": "Onboarding Required - Complete Setup",
            "normal_operation": "Normal Operation - Main Menu"
        }
        return descriptions.get(phase, "Unknown Phase")
    
    def reset_boot_state(self) -> bool:
        """Reset boot state (for testing or recovery)."""
        try:
            # Remove all boot state files
            for file_path in [self.first_boot_complete, self.onboarding_complete, self.auto_onboarding_enabled]:
                if file_path.exists():
                    file_path.unlink()
            
            logger.info("Boot state reset successfully")
            return True
        except Exception as e:
            logger.error(f"Error resetting boot state: {e}")
            return False
    
    def show_boot_status(self) -> None:
        """Display current boot status information."""
        from .utils import clear_screen
        
        clear_screen()
        print("📊 Boot Status Information")
        print("=" * 50)
        
        info = self.get_boot_info()
        
        print(f"Current Phase: {info['phase']}")
        print(f"Description: {self.get_phase_description()}")
        print()
        
        print("File Status:")
        print(f"  First Boot Complete: {'✅' if info['first_boot_complete_exists'] else '❌'}")
        print(f"  Onboarding Complete: {'✅' if info['onboarding_complete_exists'] else '❌'}")
        print(f"  Auto-Onboarding Enabled: {'✅' if info['auto_onboarding_enabled_exists'] else '❌'}")
        print()
        
        print("Phase Status:")
        print(f"  First Boot: {'✅' if info['is_first_boot'] else '❌'}")
        print(f"  Onboarding Complete: {'✅' if info['is_onboarding_complete'] else '❌'}")
        print(f"  Auto-Onboarding Enabled: {'✅' if info['is_auto_onboarding_enabled'] else '❌'}")
        print()
        
        print("Next Action:")
        if info['is_first_boot']:
            print("  System will wait for first boot to complete")
        elif info['is_auto_onboarding_enabled']:
            print("  System will show QR code for onboarding")
        elif info['is_onboarding_complete']:
            print("  System will launch main menu")
        else:
            print("  System will launch main menu (manual onboarding available)")
        print()
        
        input("Press Enter to continue...")


# Global instance for easy access
simple_boot_manager = SimpleBootManager() 