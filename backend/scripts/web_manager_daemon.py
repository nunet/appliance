#!/usr/bin/env python3
"""
Web Manager Daemon Script
Runs the web manager in service mode for systemd.
"""

import sys
import os
import signal
import logging
from pathlib import Path

# Add the menu directory to the Python path
menu_dir = Path(__file__).parent.parent
sys.path.insert(0, str(menu_dir))

from modules.web_manager import WebManager
from modules.onboarding_manager import OnboardingManager

# Configure logging for systemd
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("WebManagerDaemon")

class WebManagerDaemon:
    """Daemon class for running the web manager as a service."""
    
    def __init__(self):
        self.web_manager = None
        self.onboarding_manager = None
        self.running = False
        self.server_thread = None
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()
    
    def start(self):
        """Start the web manager daemon."""
        try:
            logger.info("Starting Web Manager Daemon...")
            
            # Initialize onboarding manager
            self.onboarding_manager = OnboardingManager()
            logger.info("Onboarding manager initialized")
            
            # Initialize web manager in service mode
            self.web_manager = WebManager(self.onboarding_manager, service_mode=True)
            logger.info("Web manager initialized in service mode")
            
            # Generate password if needed
            if not self.web_manager.setup_password:
                password = self.web_manager.generate_setup_password()
                logger.info(f"Generated new password: {password}")
            
            # Start the server in silent mode for service
            self.running = True
            logger.info("Starting web server...")
            
            # Start server in a separate thread for better shutdown handling
            import threading
            self.server_thread = threading.Thread(
                target=self.web_manager.start_server,
                kwargs={'silent': True},
                daemon=True
            )
            self.server_thread.start()
            
            # Wait for server to start
            import time
            time.sleep(2)
            logger.info("Web server started successfully")
            
        except Exception as e:
            logger.error(f"Error starting web manager daemon: {e}")
            self.stop()
            sys.exit(1)
    
    def stop(self):
        """Stop the web manager daemon."""
        if self.running:
            logger.info("Stopping Web Manager Daemon...")
            self.running = False
            
            if self.web_manager:
                try:
                    self.web_manager.stop_server()
                    logger.info("Web server stopped")
                except Exception as e:
                    logger.error(f"Error stopping web server: {e}")
            
            # Wait for server thread to finish (with timeout)
            if self.server_thread and self.server_thread.is_alive():
                logger.info("Waiting for server thread to finish...")
                self.server_thread.join(timeout=5)
                if self.server_thread.is_alive():
                    logger.warning("Server thread did not finish within timeout")
            
            logger.info("Web Manager Daemon stopped")
    
    def run(self):
        """Run the daemon."""
        try:
            self.start()
            
            # Keep the daemon running
            while self.running:
                import time
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            self.stop()


def main():
    """Main entry point."""
    daemon = WebManagerDaemon()
    daemon.run()


if __name__ == "__main__":
    main() 