from pathlib import Path

# Repository structure
REPO_ROOT = Path(__file__).resolve().parents[2]

# Home directory context
HOME_DIR = Path.home()
DMS_DEFAULT_CONTEXT = "dms"

# Ensemble templates
ENSEMBLES_DIR = HOME_DIR / "ensembles"
ENSEMBLES_SCAN_ROOT = Path("/home/ubuntu/ensembles")
ENSEMBLE_TEMPLATE_ROOT = ENSEMBLES_DIR
DEFAULT_ENSEMBLE_JSON_TEMPLATE = ENSEMBLE_TEMPLATE_ROOT / "default-ensemble.json"
DEFAULT_CONTRACT_JSON_TEMPLATE = ENSEMBLE_TEMPLATE_ROOT / "default-contract.json"

# Appliance state
APPLIANCE_DIR = HOME_DIR / "nunet" / "appliance"
APPLIANCE_DEPLOYMENTS_DIR = Path("/home/ubuntu/nunet/appliance/deployments")
APPLIANCE_DEPLOYMENT_LOGS_DIR = APPLIANCE_DIR / "deployment_logs"
APPLIANCE_PUBLIC_IP_CACHE = APPLIANCE_DIR / "public_ip_cache.json"
ONBOARDING_STATE_FILE = APPLIANCE_DIR / "onboarding_state.json"
ONBOARDING_LOG_FILE = APPLIANCE_DIR / "onboarding.log"
KNOWN_ORGS_FILE = APPLIANCE_DIR / "known_orgs" / "known_organizations.json"
CONTRACTS_DIR = HOME_DIR / "contracts"
ROLE_METADATA_FILE = APPLIANCE_DIR / "role_metadata.json"

# DMS artefacts
LOCAL_DEPLOYMENTS_DIR = HOME_DIR / "nunet" / "deployments"
DMS_DEPLOYMENTS_LOGS = Path("/home/nunet/nunet/deployments")
DMS_DEPLOYMENTS_DIR = Path("/home/nunet/nunet/deployments")
DMS_LOG_PATH = Path("/home/nunet/logs/nunet-dms.log")
DMS_CAP_FILE = Path("/home/ubuntu/.nunet/cap/dms.cap")

# Credentials
# Use ~/.secrets/ for credentials (works in both dev and prod)
ADMIN_CREDENTIALS_PATH = HOME_DIR / ".secrets" / "admin_credentials.json"

__all__ = [
    "REPO_ROOT",
    "HOME_DIR",
    "ENSEMBLES_DIR",
    "ENSEMBLES_SCAN_ROOT",
    "ENSEMBLE_TEMPLATE_ROOT",
    "DEFAULT_ENSEMBLE_JSON_TEMPLATE",
    "DEFAULT_CONTRACT_JSON_TEMPLATE",
    "APPLIANCE_DIR",
    "DMS_DEPLOYMENTS_LOGS",
    "APPLIANCE_DEPLOYMENTS_DIR",
    "APPLIANCE_DEPLOYMENT_LOGS_DIR",
    "APPLIANCE_PUBLIC_IP_CACHE",
    "ONBOARDING_STATE_FILE",
    "ONBOARDING_LOG_FILE",
    "KNOWN_ORGS_FILE",
    "CONTRACTS_DIR",
    "DMS_DEFAULT_CONTEXT",
    "ROLE_METADATA_FILE",
    "LOCAL_DEPLOYMENTS_DIR",
    "DMS_DEPLOYMENTS_DIR",
    "DMS_LOG_PATH",
    "DMS_CAP_FILE",
    "ADMIN_CREDENTIALS_PATH",
]
