import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APPLIANCE_ROOT = REPO_ROOT

HOME_DIR = Path.home()

# Project structure (repo code)
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
DEFAULT_SCRIPTS_DIR = BACKEND_DIR / "scripts"

# Data layout (writable paths matching packaged install)
NUNET_DATA_DIR = Path("/home/ubuntu/nunet")
APPLIANCE_DIR = NUNET_DATA_DIR / "appliance"
APPLIANCE_DEPLOYMENTS_DIR = APPLIANCE_DIR / "deployments"
APPLIANCE_DEPLOYMENT_LOGS_DIR = APPLIANCE_DIR / "deployment_logs"
APPLIANCE_PUBLIC_IP_CACHE = APPLIANCE_DIR / "public_ip_cache.json"
ONBOARDING_STATE_FILE = APPLIANCE_DIR / "onboarding_state.json"
ONBOARDING_LOG_FILE = APPLIANCE_DIR / "onboarding.log"
KNOWN_ORGS_FILE = APPLIANCE_DIR / "known_orgs" / "known_organizations.json"
ROLE_METADATA_FILE = APPLIANCE_DIR / "role_metadata.json"
LOCAL_DEPLOYMENTS_DIR = APPLIANCE_DIR / "local_deployments"

# Templates and contracts
ENSEMBLES_DIR = Path("/home/ubuntu/ensembles")
ENSEMBLES_SCAN_ROOT = ENSEMBLES_DIR
ENSEMBLE_TEMPLATE_ROOT = ENSEMBLES_DIR
DEFAULT_ENSEMBLE_JSON_TEMPLATE = ENSEMBLE_TEMPLATE_ROOT / "default-ensemble.json"
DEFAULT_CONTRACT_JSON_TEMPLATE = ENSEMBLE_TEMPLATE_ROOT / "default-contract.json"
CONTRACTS_DIR = Path("/home/ubuntu/contracts")

# DMS artefacts / defaults
DMS_DEFAULT_CONTEXT = "dms"
DMS_DEPLOYMENTS_DIR = APPLIANCE_DIR / "dms_deployments"
DMS_DEPLOYMENTS_LOGS = DMS_DEPLOYMENTS_DIR
DMS_LOG_PATH = APPLIANCE_DIR / "logs" / "nunet-dms.log"
DMS_INIT_SCRIPT = DEFAULT_SCRIPTS_DIR / "configure-dms.sh"
DMS_CAP_FILE = HOME_DIR / ".nunet" / "cap" / "dms.cap"
SERVICE_DMS_CAP_FILE = Path("/home/nunet/.nunet/cap/dms.cap")
NUNET_CONFIG_PATH = Path("/home/nunet/config/dms_config.json")

# Credentials
ADMIN_CREDENTIALS_PATH = HOME_DIR / ".secrets" / "admin_credentials.json"

GITLAB_PACKAGES_URL = "https://gitlab.com/api/v4/projects/74166253/packages?sort=desc&order_by=version"
GITLAB_DMS_PACKAGES_URL = "https://gitlab.com/api/v4/projects/nunet%2Fdevice-management-service/packages?sort=desc&order_by=version"

__all__ = [
    "APPLIANCE_ROOT",
    "REPO_ROOT",
    "HOME_DIR",
    "BACKEND_DIR",
    "FRONTEND_DIR",
    "DEFAULT_SCRIPTS_DIR",
    "NUNET_DATA_DIR",
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
    "SERVICE_DMS_CAP_FILE",
    "NUNET_CONFIG_PATH",
    "DMS_INIT_SCRIPT",
    "ADMIN_CREDENTIALS_PATH",
    "GITLAB_PACKAGES_URL",
    "GITLAB_DMS_PACKAGES_URL",
]
