#!/usr/bin/env python3
"""
Boot splash screen module.
Displays ASCII art, progress indicators, and status messages during boot phases.
"""

import time
import os
import requests
from typing import Optional, Callable
from pathlib import Path

from .utils import clear_screen, Colors


class BootSplash:
    """Boot splash screen manager for different phases."""
    
    def __init__(self):
        self.progress_file = Path("/tmp/boot_progress.txt")
        self.current_progress = 0
        self.max_progress = 100
        self.repo_url = "https://gitlab.com/nunet/solutions/nunet-appliance/-/raw/auki-node-pre-reqs-new-appliance/src/menu/modules/boot_splash.py"
        self.cache_file = Path("/tmp/boot_splash_latest.py")
    
    def check_for_updates(self):
        """Check for newer boot splash from repo and update if available."""
        try:
            # Try to fetch latest version from repo
            response = requests.get(self.repo_url, timeout=10)
            if response.status_code == 200:
                # Save to cache
                with open(self.cache_file, "w") as f:
                    f.write(response.text)
                return True
        except Exception:
            pass
        return False
    
    def load_latest_splash(self):
        """Load the latest splash version if available, otherwise use embedded."""
        if self.cache_file.exists():
            try:
                # Import the cached version
                import importlib.util
                spec = importlib.util.spec_from_file_location("boot_splash_latest", self.cache_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module.BootSplash()
            except Exception:
                pass
        
        # Fallback to current instance
        return self
    
    def _get_nunet_ascii_art(self) -> str:
        """Get NuNet ASCII art logo."""
        return r"""::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::
:+#-+#*:::::::::::#+:::%+::::::::::::::@-::+@@@@@%=:::::::-%@@-:::=%@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@=
:+*:::-%=:::::::::#+:::%+::::::::::::::@-::+@@*=%@@%::::::-%@@-::#@@@=:::::::::::::::::::*@@+:::::::
:+*:::::+#::::::::#+:::%+::::::::::::::@-::+@@*::+@@@+::::-%@@-:-@@%:::::::::::::::::::::*@@+:::::::
:+*::::::-%=::::::#+:::%+::::::::::::::@-::+@@*:::-%@@#:::-%@@-:=@@@@@@@@@@@@@@@@@+::::::*@@+:::::::
:+*::::::::+*:::::#+:::#*:::::::::::::-@:::+@@*:::::*@@@=:-%@@-:-@@@:::::::::::::::::::::*@@+:::::::
:+*:::::::::-%=:::#+::::%-::::::::::::#=:::+@@*::::::-%@@%#@@@-::+@@@#+============::::::*@@+:::::::
:+*:::::::::::=#*+%+:::::*%*+=====+*#*-::::+@@*::::::::-#@@@@@-:::-#@@@@@@@@@@@@@@#::::::*@@+:::::::
::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::"""
    
    def _get_phase1_ascii_art(self) -> str:
        """Get Phase 1 (first boot) ASCII art."""
        return """
    🚀 SYSTEM CONFIGURATION
    Initializing NuNet Appliance v1.5.0
        """
    
    def _get_phase2_ascii_art(self) -> str:
        """Get Phase 2 (onboarding) ASCII art."""
        return """
    📱 ONBOARDING SETUP
    Welcome to NuNet Appliance v1.5.0!
        """
    
    def _create_progress_bar(self, current: int, total: int, width: int = 50) -> str:
        """Create a text-based progress bar."""
        if total == 0:
            return "[" + " " * width + "] 0%"
        
        percentage = min(100, int((current / total) * 100))
        filled_width = int((current / total) * width)
        
        bar = "█" * filled_width + "░" * (width - filled_width)
        return f"[{bar}] {percentage}%"
    
    def _update_progress_file(self, progress: int, message: str = ""):
        """Update the progress file for external monitoring."""
        try:
            with open(self.progress_file, 'w') as f:
                f.write(f"{progress}\n{message}")
        except Exception:
            pass  # Ignore errors writing to progress file
    
    def show_phase1_splash(self, step: str = "initializing", progress: int = 0):
        """Show Phase 1 splash screen (non-interactive first boot)."""
        # Use a more aggressive screen clear to handle systemd messages
        os.system("clear && printf '\033[3J'")  # Clear screen and scrollback buffer
        
        # Display ASCII art with colors
        print(f"{Colors.CYAN}{self._get_nunet_ascii_art()}{Colors.NC}")
        print()
        print(f"{Colors.MAGENTA}{self._get_phase1_ascii_art()}{Colors.NC}")
        print()
        
        # Show current step
        step_messages = {
            "initializing": "🔄 Initializing system components...",
            "updates": "📦 Installing system updates and packages...",
            "password": "🔐 Securing user account with new password...",
            "dms": "⚙️  Configuring Device Management Service...",
            "services": "🚀 Enabling and starting system services...",
            "complete": "✅ System configuration completed successfully!"
        }
        
        step_msg = step_messages.get(step, f"🔄 {step.title()}...")
        print(f"   {Colors.MAGENTA}{step_msg}{Colors.NC}")
        print()
        
        # Show progress bar
        progress_bar = self._create_progress_bar(progress, 100)
        print(f"   {Colors.CYAN}Progress: {progress_bar}{Colors.NC}")
        print()
        
        # Show status message
        if step == "complete":
            print(f"   {Colors.MAGENTA}🎉 System configuration completed successfully!{Colors.NC}")
            print(f"   {Colors.MAGENTA}🔄 System will reboot automatically in 5 seconds...{Colors.NC}")
            print(f"   {Colors.CYAN}📱 After reboot, you'll be guided through onboarding setup.{Colors.NC}")
        else:
            print(f"   {Colors.MAGENTA}⏳ Please wait while the system configures itself...{Colors.NC}")
            print(f"   {Colors.CYAN}📋 This process is automatic and non-interactive.{Colors.NC}")
            print(f"   {Colors.MAGENTA}🔒 Do not power off or interrupt the system.{Colors.NC}")
        
        print()
        print(f"   {Colors.CYAN}{'=' * 60}{Colors.NC}")
        
        # Update progress file
        self._update_progress_file(progress, step_msg)
    
    def _typewriter_effect(self, text: str, delay: float = 0.03, color: str = Colors.NC):
        """Display text with typewriter effect."""
        for char in text:
            print(f"{color}{char}{Colors.NC}", end="", flush=True)
            time.sleep(delay)
            # Check for skip key during typewriter effect
            if 'skip_requested' in globals() and globals()['skip_requested']:
                return
        print()  # New line after text
    
    def _create_phase0_flag(self, status: str = "phase0_complete"):
        """Create flag file to indicate Phase 0 completion status."""
        try:
            import subprocess
            subprocess.run(['sudo', 'touch', '/tmp/phase0_skip'], 
                          capture_output=True, text=True, check=True)
            subprocess.run(['sudo', 'sh', '-c', f'echo "{status}" > /tmp/phase0_skip'], 
                          capture_output=True, text=True, check=True)
        except Exception:
            pass

    def show_phase0_splash(self):
        """Show Phase 0 splash screen with dramatic typewriter effect."""
        clear_screen()
        
        # Flash the screen to grab attention
        for i in range(3):  # Flash 3 times
            print(f"\033[7m{' ' * 1000}\033[0m", end="", flush=True)  # Reverse video (white on black)
            time.sleep(0.1)
            clear_screen()
            time.sleep(0.1)
        
        # Check for skip key during the entire Phase 0
        import select
        import sys
        import threading
        
        skip_requested = False
        
        def check_for_skip():
            nonlocal skip_requested
            try:
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    key = sys.stdin.read(1).lower()
                    if key == 's':
                        skip_requested = True
            except:
                pass
        
        def typewriter_with_skip(text: str, delay: float = 0.03, color: str = Colors.NC):
            """Display text with typewriter effect and skip detection."""
            for char in text:
                print(f"{color}{char}{Colors.NC}", end="", flush=True)
                time.sleep(delay)
                if skip_requested:
                    return
            print()  # New line after text
        
        # Main boot message
        typewriter_with_skip("Booting into the edge of the network...", 0.05, Colors.NC)
        if skip_requested: 
            self._create_phase0_flag("phase0_skipped")
            return
        time.sleep(1.0)  # 1 second pause between paragraphs
        
        # Description paragraphs
        typewriter_with_skip("You're about to bring a NuNet Appliance online — a self-sovereign node in a decentralized compute mesh.", 0.02, Colors.NC)
        if skip_requested: 
            self._create_phase0_flag("phase0_skipped")
            return
        time.sleep(1.0)  # 1 second pause between paragraphs
        
        typewriter_with_skip("This isn't just another server; it's a gateway to distributed intelligence.", 0.02, Colors.NC)
        if skip_requested: 
            self._create_phase0_flag("phase0_skipped")
            return
        time.sleep(1.0)  # 1 second pause between paragraphs
        
        typewriter_with_skip("Once deployed, your appliance joins a global grid of orchestrated compute, unlocking latent power across the network.", 0.02, Colors.NC)
        if skip_requested: 
            self._create_phase0_flag("phase0_skipped")
            return
        time.sleep(1.0)  # 1 second pause before dramatic words
        
        # Dramatic pauses with single words
        print()
        typewriter_with_skip("Permissionless...", 0.08, Colors.NC)
        if skip_requested: 
            self._create_phase0_flag("phase0_skipped")
            return
        time.sleep(2.0)  # 2 second pause between words
        
        typewriter_with_skip("Resilient...", 0.08, Colors.NC)
        if skip_requested: 
            self._create_phase0_flag("phase0_skipped")
            return
        time.sleep(2.0)  # 2 second pause between words
        
        typewriter_with_skip("Autonomous...", 0.08, Colors.NC)
        if skip_requested: 
            self._create_phase0_flag("phase0_skipped")
            return
        time.sleep(2.0)  # 2 second pause after last word
        print()
        
        # Final welcome messages
        typewriter_with_skip("Welcome to the future of decentralized computation.", 0.03, Colors.NC)
        if skip_requested: 
            self._create_phase0_flag("phase0_skipped")
            return
        time.sleep(1.0)  # 1 second pause between paragraphs
        
        typewriter_with_skip("Welcome to NuNet", 0.05, Colors.NC)
        if skip_requested: 
            self._create_phase0_flag("phase0_skipped")
            return
        time.sleep(2.0)  # 2 second pause after "Welcome to NuNet"
        
        # Clear screen and show the dramatic ASCII art
        clear_screen()
        
        # Display the dramatic NuNet ASCII art
        dramatic_art = """                                                                                                                        
                                                                                                                        
                                                                                                                        
                                                                                                                        
                                                        @@@@@@@@@                                                       
                                                      @@@#.@@@@.@@@#                                                    
                                                     %@@..../@....@@.                                                   
                                                     @@@.........%@@                                                    
                                                      @@@@.....,@@@.                                                    
                           @@@,                          @@@@@@@&                                                       
                         @@@@@@@                         @@@@@     ,@@@@@@@@@%                                          
                       @@@@@@@@@@,       (@@@@@@@@@@     @@@@   .@@@@%,,,,/@@@@@@                                       
                     @@@@%....@@@@#     @@@.@@@@...@@@  #@@@   .@@@......@@@@@@@@@                                      
                   @@@@@@@@....@@@@@    @@.........@@@  @@@@   *@@........@@@@@@@@                                      
                 @@@@@..........@@@@@   @@@.......&@@*  @@@    *@@.............@@@           &@@                        
                @@@@@............@@@@@&   @@@@@@@@@@    @@,    .@@@............@@@      @@@@@@@@@@@,                    
                @@@@@@@@@@@@@@@@@@@@@@@@@      @@@@*   .@@    (@@@@@@&,,,,,/@@@@@      @@@@....*@@@@@                   
                      /&@@@@@@@@@@@@@@@@@@@*    *@@@   @@    @@@@@@@@@@@@@@@@&       .@@@@.....@@@@@@                   
                                    @@@@@@@@@@    @@/  @/  %@@@@@@            %@@@@@@@@@@@@......&@@@                   
                               .@@@@      @@@@@@          @@@         *@@@@@@@@@@@@@@@% @@@@@@@@@@@@                    
                            *@@@...@@@                        ,@@@@@@@@#.                  &@@@                         
                           @@@@@&....@@@@@@@@@*    @@@@@@                                        @@@                    
                            @@@.....*@@@@@@&,      %@@@@(       #@@@@@@@@@@@@&#,          @@@@@@@@@@@                   
                              @@@@@@@        &@             @@@           &@@@@@@@@@@@@@@@@.......@@@                   
                                      @@@@@@     %.       @@    @@@@/               @@@@@@....&@@@@@#                   
                              ,@@@@@@@@@       @@@    @@   @@@      @@@@@@              .@@@@....@@@                    
             #@@@@@@@@@@@@@@@@@@@@@@         @@@&    @@@    @@@@.       @@@@@@@            *@@@@@@@%                    
             &@@(.........@@@@@@          (@@@@     .@@@@     @@@@@         @@@@@@@@*         (@@@#                     
              ,@@@@@@....@@@            @@@@@@      @@@@@      @@@@@@           @@@@@@@@@&                              
                @@@....@@@,           @@@@@@,      @@@.&@@.      @@@@@@             @@@@@@@@@@@   @@@@@@@#              
                 @@@,@@@@    @@@@@@@@@@@@@@      (@@%....@@@      @@@@@@@%              @@@@@@@@@@@@@@@@@@@@,           
                  @@@@@   @@@@@@@@@&@@@@@@      @@@...@@..@@@      .@@@@@@@@                @@@@@@........@@@(          
                         @@@@..........@@@      @@@@@@@@@@@@@*       @@@@@@@@@                @@@*.....@@@@@@@          
                         (@@@..........@@@                            (@@@@@@@@@@@@@@@@@@*    @@@@*....(@@@@@           
                          @@@@@@@@.....@@@                              @@@@@@@@@@@@@@@@@@@&    @@@@@@@@@@@@            
                          @@@@@@@@..(@@@@@                              @@@@@@..........@@@@@#     ,@@@%                
                            @@@@@@@@@@@@                               @@@@@..............@@@@@                         
                                                                      %@@@@................@@@@@                        
                                                                      @@@@@.........@@@@/..@@@@@                        
                                                                      %@@@@@.......@@@@@@@@@@@@                         
                                                                        @@@@@@......@@@@@@@@@@                          
                                                                          @@@@@@@@@@@@@@@@@@@                           
                                                                            @@@@@@@@@@@@@@                                                                                                                                                      """
        
        print(f"{Colors.CYAN}{dramatic_art}{Colors.NC}")
        print()
        
        # Check for skip during ASCII art display
        for i in range(50):  # Check 50 times over 5 seconds
            if skip_requested: 
                self._create_phase0_flag("phase0_skipped")
                return
            time.sleep(0.1)
        
        # Clear screen for seamless transition to Phase 1
        clear_screen()
        
        # Create flag file to indicate Phase 0 is complete
        self._create_phase0_flag("phase0_complete")
    
    def show_phase2_splash(self, step: str = "welcome"):
        """Show Phase 2 splash screen (interactive onboarding)."""
        clear_screen()
        
        # Display ASCII art with colors
        print(f"{Colors.CYAN}{self._get_nunet_ascii_art()}{Colors.NC}")
        print()
        print(f"{Colors.MAGENTA}{self._get_phase2_ascii_art()}{Colors.NC}")
        print()
        
        # Show current step
        step_messages = {
            "welcome": "👋 Welcome to NuNet Appliance v1.5.0!",
            "qr_setup": "📱 Setting up QR code access...",
            "organization": "🏢 Configuring organization connection...",
            "network": "🌐 Setting up network access...",
            "complete": "✅ Onboarding completed successfully!"
        }
        
        step_msg = step_messages.get(step, f"🔄 {step.title()}...")
        print(f"   {Colors.MAGENTA}{step_msg}{Colors.NC}")
        print()
        
        if step == "welcome":
            print(f"   {Colors.MAGENTA}🎯 This is your first time setup for NuNet Appliance.{Colors.NC}")
            print(f"   {Colors.CYAN}📋 We'll guide you through the organization connection process.{Colors.NC}")
            print(f"   {Colors.MAGENTA}🔗 You'll need a mobile device to scan QR codes for web access.{Colors.NC}")
            print(f"   {Colors.MAGENTA}🏢 You'll be joining a NuNet organization to start computing.{Colors.NC}")
            print()
            print(f"   {Colors.MAGENTA}Press Enter to begin onboarding setup...{Colors.NC}")
        elif step == "complete":
            print(f"   {Colors.MAGENTA}🎉 Onboarding completed successfully!{Colors.NC}")
            print(f"   {Colors.MAGENTA}🚀 Your NuNet Appliance is now ready for decentralized computing.{Colors.NC}")
            print(f"   {Colors.CYAN}📊 You can access the main menu to monitor and manage your appliance.{Colors.NC}")
            print()
            print(f"   {Colors.MAGENTA}Press Enter to continue to the main menu...{Colors.NC}")
        else:
            print(f"   {Colors.MAGENTA}⏳ Please follow the prompts to complete the setup process...{Colors.NC}")
            print(f"   {Colors.MAGENTA}📱 Use your mobile device to scan the QR code when prompted.{Colors.NC}")
            print()
        
        print(f"   {Colors.CYAN}{'=' * 60}{Colors.NC}")
    
    def show_qr_splash(self, qr_code: str, url: str, password: str):
        """Show QR code splash screen for web access."""
        clear_screen()
        
        print(f"{Colors.CYAN}{self._get_nunet_ascii_art()}{Colors.NC}")
        print()
        print(f"{Colors.YELLOW}📱 WEB ACCESS SETUP{Colors.NC}")
        print()
        print(f"{Colors.BLUE}📱 Scan this QR code with your mobile device:{Colors.NC}")
        print()
        print(qr_code)
        print()
        print(f"{Colors.GREEN}🌐 Or visit manually: {url}{Colors.NC}")
        print(f"{Colors.MAGENTA}🔑 Setup Password: {password}{Colors.NC}")
        print()
        print(f"{Colors.CYAN}💡 Instructions:{Colors.NC}")
        print(f"   {Colors.NC}• Use your phone's camera or QR code scanner app{Colors.NC}")
        print(f"   {Colors.NC}• Enter the setup password when prompted{Colors.NC}")
        print(f"   {Colors.NC}• Follow the web interface to complete onboarding{Colors.NC}")
        print(f"   {Colors.NC}• The password expires after 30 minutes{Colors.NC}")
        print()
        print(f"{Colors.CYAN}{'=' * 60}{Colors.NC}")
        print()
        input(f"{Colors.BLUE}Press Enter when you're ready to continue...{Colors.NC}")
    
    def show_error_splash(self, error_message: str, can_continue: bool = True):
        """Show error splash screen."""
        clear_screen()
        
        print(f"{Colors.CYAN}{self._get_nunet_ascii_art()}{Colors.NC}")
        print()
        print(f"{Colors.RED}❌ ERROR{Colors.NC}")
        print()
        print(f"{Colors.RED}❌ An error occurred during setup:{Colors.NC}")
        print()
        print(f"   {Colors.YELLOW}{error_message}{Colors.NC}")
        print()
        
        if can_continue:
            print(f"{Colors.YELLOW}🔄 You can try again or continue with manual setup.{Colors.NC}")
            print()
            input(f"{Colors.BLUE}Press Enter to continue...{Colors.NC}")
        else:
            print(f"{Colors.RED}🛑 Setup cannot continue. Please check the error and try again.{Colors.NC}")
            print()
            input(f"{Colors.BLUE}Press Enter to exit...{Colors.NC}")
    
    def show_waiting_splash(self, message: str = "Please wait...", spinner: bool = True):
        """Show waiting splash screen with optional spinner."""
        clear_screen()
        
        print(f"{Colors.CYAN}{self._get_nunet_ascii_art()}{Colors.NC}")
        print()
        print(f"{Colors.YELLOW}⏳ WAITING{Colors.NC}")
        print()
        print(f"   {Colors.BLUE}{message}{Colors.NC}")
        print()
        
        if spinner:
            spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            i = 0
            while True:
                print(f"\r   {Colors.GREEN}{spinner_chars[i]} Processing...{Colors.NC}", end="", flush=True)
                time.sleep(0.1)
                i = (i + 1) % len(spinner_chars)
        
        print(f"   {Colors.CYAN}{'=' * 60}{Colors.NC}")
    
    def animate_progress(self, start_progress: int, end_progress: int, 
                        duration: float = 2.0, step_callback: Optional[Callable] = None):
        """Animate progress bar from start to end over duration."""
        steps = int(duration * 10)  # 10 updates per second
        step_size = (end_progress - start_progress) / steps
        
        for i in range(steps + 1):
            current_progress = start_progress + (step_size * i)
            self.current_progress = int(current_progress)
            
            if step_callback:
                step_callback(self.current_progress)
            
            time.sleep(duration / steps)
    
    def cleanup(self):
        """Clean up progress file."""
        try:
            if self.progress_file.exists():
                self.progress_file.unlink()
        except Exception:
            pass


def get_boot_splash():
    """Get boot splash instance with automatic updates."""
    splash = BootSplash()
    
    # Check for updates first
    try:
        splash.check_for_updates()
    except Exception:
        pass  # Continue with current version if update check fails
    
    # Try to load the latest cached version if available
    try:
        updated_splash = splash.load_latest_splash()
        if updated_splash != splash:
            return updated_splash
    except Exception:
        pass
    
    return splash

# Global instance for easy access
boot_splash = get_boot_splash() 