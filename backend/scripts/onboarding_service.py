import sys
import os
from pathlib import Path

# Add the parent directory (menu) to Python path so we can import modules
menu_dir = Path(__file__).parent.parent
sys.path.insert(0, str(menu_dir))

import time
from modules.onboarding_manager import OnboardingManager
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("OnboardingService")

def main():
    mgr = OnboardingManager()
    
    # Create initial state file if it doesn't exist
    if not mgr.STATE_PATH.exists():
        logger.info("Creating initial onboarding state file")
        initial_state = {
            "step": "init",
            "progress": 0,
            "wormhole_code": None,
            "form_data": {},
            "error": None,
            "logs": []
        }
        mgr.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(mgr.STATE_PATH, "w") as f:
            import json
            json.dump(initial_state, f, indent=2)
        logger.info(f"Created state file at {mgr.STATE_PATH}")
    
    last_step = None
    while True:
        try:
            logger.info("Calling run_onboarding_steps()")
            mgr.run_onboarding_steps()
            logger.info("Finished run_onboarding_steps()")
            state = mgr.get_onboarding_status()
            step = state.get("step")
            error = state.get("error")
            # Print step only if it changed
            if step != last_step:
                logger.info(f"Current step: {step}")
                last_step = step
            if error:
                logger.error(f"Error: {error}")
            if state.get("status") in ("complete", "error"):
                logger.info(f"Onboarding reached terminal state: {state.get('status')}")
                break
                
            time.sleep(5)
        except Exception as e:
            logger.exception(f"Exception in onboarding service main loop: {e}")
            time.sleep(5)
    
    logger.info("Onboarding service script exiting")

if __name__ == "__main__":
    main() 