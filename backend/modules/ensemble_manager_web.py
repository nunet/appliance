import os
import json
from modules.dms_utils import run_dms_command_with_passphrase

DEPLOYMENTS_BASE = "/home/nunet/nunet/deployments"

def get_manifest_web(deployment_id):
    """
    Fetch the manifest for a deployment as JSON using the DMS CLI.
    Returns a dict with status and manifest or error message.
    """
    try:
        result = run_dms_command_with_passphrase([
            "nunet", "-c", "dms", "actor", "cmd", "/dms/node/deployment/manifest", "--id", deployment_id
        ], capture_output=True, text=True, check=True)
        manifest_json = json.loads(result.stdout)
        return {"status": "success", "manifest": manifest_json}
    except Exception as e:
        return {"status": "error", "message": f"Failed to get manifest: {e}"}

def request_logs_web(deployment_id, allocation_id):
    """
    Request logs from the compute provider for a given deployment/allocation.
    Returns a dict with status and logs_info or error message.
    """
    try:
        result = run_dms_command_with_passphrase([
            "nunet", "-c", "dms", "actor", "cmd", "/dms/node/deployment/logs",
            "--id", deployment_id, "--allocation", allocation_id
        ], capture_output=True, text=True, check=True)
        logs_json = json.loads(result.stdout)
        return {"status": "success", "logs_info": logs_json}
    except Exception as e:
        return {"status": "error", "message": f"Failed to request logs: {e}"}

def get_logs_web(deployment_id, allocation_id):
    """
    Read stdout.logs and stderr.logs from the deployment's logs directory.
    Returns a dict with status and logs (stdout, stderr), or error messages.
    """
    base_path = os.path.join(DEPLOYMENTS_BASE, deployment_id, allocation_id)
    stdout_path = os.path.join(base_path, "stdout.logs")
    stderr_path = os.path.join(base_path, "stderr.logs")
    logs = {}
    try:
        with open(stdout_path, "r") as f:
            logs["stdout"] = f.read()
    except Exception as e:
        logs["stdout"] = f"Error reading stdout: {e}"
    try:
        with open(stderr_path, "r") as f:
            logs["stderr"] = f.read()
    except Exception as e:
        logs["stderr"] = f"Error reading stderr: {e}"
    return {"status": "success", "logs": logs} 