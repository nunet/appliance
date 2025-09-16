"""
Web Manager module for NuNet Appliance
Handles the web-based setup interface and authentication
"""

import os
import secrets
import time
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pathlib import Path
import subprocess
import importlib.util
import sys
import random
from flask import Flask, render_template, request, redirect, url_for, session
from modules.onboarding_manager import OnboardingManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests
from functools import wraps
from modules.org_utils import load_known_organizations
from modules.dms_utils import get_dms_status_info, get_dms_resource_info
from modules.system_status import get_system_status
from modules.ensemble_manager_v2 import EnsembleManagerV2
from modules.ensemble_utils import (
    scan_ensembles_directory, load_ensemble_metadata, process_yaml_template,
    generate_timestamped_filename, validate_form_data, save_deployment_instance,
    get_deployment_options
)
from modules.ensemble_manager_web import get_manifest_web, request_logs_web, get_logs_web
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("WebManager")

def check_dependencies() -> bool:
    """Check if all required packages are installed"""
    required_packages = {
        'flask': 'python3-flask',
        'flask_limiter': 'python3-flask-limiter',
        'OpenSSL': 'python3-openssl',
        'cryptography': 'python3-cryptography'
    }
    
    missing_packages = []
    for module, package in required_packages.items():
        if importlib.util.find_spec(module) is None:
            missing_packages.append(package)
    
    if missing_packages:
        print("\nMissing required packages. Please run the following command:")
        print(f"sudo apt-get install {' '.join(missing_packages)}")
        return False
    return True

# Only import Flask and related modules if dependencies are available
if check_dependencies():
    from flask import Flask, request, jsonify, session, render_template_string
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    import threading
else:
    raise ImportError("Required packages are not installed. Please run the installation script first.")

# HTML Templates
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>NuNet Appliance Setup</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .error { color: red; margin: 10px 0; }
        .success { color: green; margin: 10px 0; }
        input[type="password"] { width: 100%; padding: 8px; margin: 10px 0; }
        button { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        button:disabled { background: #ccc; }
        .attempts { color: #666; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="header">
        <img src="https://docs.nunet.io/~gitbook/image?url=https%3A%2F%2F2832281263-files.gitbook.io%2F%7E%2Ffiles%2Fv0%2Fb%2Fgitbook-x-prod.appspot.com%2Fo%2Forganizations%252FHmQiiAfFnBUd24KadDsO%252Fsites%252Fsite_29YoC%252Flogo%252FoWIZXAaXL2h5S8VZIUfb%252Fnunet_logo_update_white%2520%281%29.png%3Falt%3Dmedia%26token%3D21d0f202-a01b-4c7e-9bdb-fda673c338d8&width=260&dpr=4&quality=100&sign=25f98d74&sv=2" alt="NuNet Logo" class="logo">
    </div>
    <div class="container">
        <h1>NuNet Appliance Setup</h1>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        {% if success %}
        <div class="success">{{ success }}</div>
        {% endif %}
        <form method="POST" action="/login">
            <div>
                <label for="password">Enter Setup Password:</label>
                <input type="password" id="password" name="password" required>
            </div>
            <div class="attempts">Remaining attempts: {{ attempts }}</div>
            <button type="submit" {% if attempts <= 0 %}disabled{% endif %}>Login</button>
        </form>
    </div>
</body>
</html>
"""

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>NuNet Appliance Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .status-box { margin: 10px 0; padding: 15px; border-radius: 4px; background: #f8f9fa; }
        .status-box form {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }
        .form-group {
            display: flex;
            flex-direction: column;
        }

        .form-group label {
            font-weight: bold;
            margin-bottom: 5px;
        }

        .form-group input {
            padding: 10px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 1em;
            width: 100%;
            box-sizing: border-box;
        }
        .status-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }
        .status-label { font-weight: bold; min-width: 180px;}
        .status-value { 
            flex-grow: 1;
            text-align: right; 
        }
        .header {
            text-align: center;
            margin-bottom: 20px;
        }
        .success { color: green; }
        .error { color: red; }
        .warning { color: orange; }
        .wormhole-code { 
            background: #f8f9fa; 
            padding: 15px; 
            border-radius: 4px; 
            margin: 10px 0; 
            font-family: monospace;
            font-size: 1.2em;
        }
        .progress { margin: 20px 0; }
        .progress-bar { 
            height: 24px;
            background: #e9ecef;
            border-radius: 12px;
            overflow: hidden;
            margin: 10px 0;
        }
        .progress-bar-fill { 
            height: 100%; 
            background: linear-gradient(to right, #007bff, #00c6ff);
            transition: width 0.4s ease-in-out;
        }
        .progress-step {
            font-size: 0.9em;
            color: #666;
        }
        .org-select-form { margin: 20px 0; }
        select { padding: 8px; font-size: 1em; }
        button {
            background: #007bff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1em;
        }
        button:hover {
            background: #0056b3;
        }
        button#submit-btn {
            background-color: #007bff;
            color: white;
            border: none;
            padding: 12px;
            font-size: 1em;
            border-radius: 4px;
            cursor: pointer;
            transition: background-color 0.3s ease;
        }
        button#submit-btn:hover:not(:disabled) {
            background-color: #0056b3;
        }

        button#submit-btn:disabled {
            background-color: #ccc;
            cursor: not-allowed;
        }
        .confirmation-detail {
            margin: 10px 0;
            padding: 10px;
            background: #f1f1f1;
            border-left: 4px solid #007bff;
            font-size: 0.95em;
        }
    </style>
</head>
<body>
    <div class="header">
        <img src="https://docs.nunet.io/~gitbook/image?url=https%3A%2F%2F2832281263-files.gitbook.io%2F%7E%2Ffiles%2Fv0%2Fb%2Fgitbook-x-prod.appspot.com%2Fo%2Forganizations%252FHmQiiAfFnBUd24KadDsO%252Fsites%252Fsite_29YoC%252Flogo%252FoWIZXAaXL2h5S8VZIUfb%252Fnunet_logo_update_white%2520%281%29.png%3Falt%3Dmedia%26token%3D21d0f202-a01b-4c7e-9bdb-fda673c338d8&width=260&dpr=4&quality=100&sign=25f98d74&sv=2" alt="NuNet Logo" class="logo">
    </div>
    <div class="container">
        <h1>NuNet Appliance Dashboard</h1>
        
        <div class="status-box">
            <h2>System Status</h2>
            <div class="status-row">
                <span class="status-label">DMS Version:</span> 
                <span class="status-value">{{ dms_version }}</span>
            </div>
            <div class="status-row">
                <span class="status-label">DMS Status:</span> 
                <span class="status-value {{ dms_status_class }}">{{ dms_status }}</span>
            </div>
            <div class="status-row">
                <span class="status-label">Proxy Status:</span> 
                <span class="status-value {{ proxy_status_class }}">{{ proxy_status }}</span>
            </div>
            <div class="status-row"><span class="status-label">Organization Status:</span> <span class="status-value {{ org_status_class }}">{{ org_status_str }}</span></div>
            <div class="status-row"><span class="status-label">DMS DID:</span> <span class="status-value">{{ dms_did }}</span></div>
            <div class="status-row"><span class="status-label">Peer ID:</span> <span class="status-value">{{ peer_id }}</span></div>
            <div class="status-row"><span class="status-label">Local Address:</span> <span class="status-value">{{ local_address }}</span></div>
            <div class="status-row"><span class="status-label">Public Address:</span> <span class="status-value">{{ public_address }}</span></div>
        </div>

        {% if current_step == 'init' %}
        <div class="status-box">
            <h2>Join an Organization</h2>
            <form class="org-select-form" method="POST" action="/join_org">
                <label for="org">Select Organization:</label>
                <select name="org" id="org">
                    {% for did, org in known_orgs.items() %}
                    <option value="{{ did }}">{{ org.name if org.name else org }} ({{ did }})</option>
                    {% endfor %}
                </select>
                <button type="submit">Join</button>
            </form>
        </div>
        {% elif current_step == 'collect_join_data' %}
        <div class="status-box">
            <h2>Selected Organization</h2>
            <div><strong>{{ selected_org_name }}</strong></div>
            <form id="onboarding-form" method="POST" action="/continue_join">
                <input type="hidden" name="wormhole_code" value="{{ wormhole_code }}">
                {% for field in join_fields %}
                <div class="form-group">
                    <label for="{{ field.name }}">{{ field.label }}{% if field.required %}*{% endif %}</label>
                    <input type="{{ field.type }}" id="{{ field.name }}" name="{{ field.name }}" {% if field.required %}required{% endif %}>
                </div>
                {% endfor %}
                <button type="submit" id="submit-btn">Continue</button>
            </form>
        </div>
        {% elif current_step == 'join_data_received' %}
        <div class="status-box">
            <h2>Join Data Received</h2>
            <p>Your information has been received and would be submitted to the API as follows:</p>
            <pre>{{ form_data | tojson(indent=2) }}</pre>
            <p>Please wait while we process your request.</p>
        </div>
        {% elif current_step == 'api_data_sent' %}
        <div class="status-box">
            <h2>API Data Sent</h2>
            <p>Your join data has been sent to the API. Proceeding to organization authorization...</p>
        </div>
        {% elif current_step == 'pending_authorization' %}
        <div class="status-box">
            <h2>Pending Authorization</h2>
            <p>Your request has been sent. Waiting for organization approval...</p>
        </div>
        {% endif %}

        {% if join_status %}
        <div class="status-box">
            <h2>Join Status</h2>
            <pre>{{ join_status }}</pre>
        </div>
        {% endif %}

        {% if wormhole_code and not show_wormhole_code %}
        <div class="status-box">
            <h2>Organization Setup</h2>
            <p>Please provide this wormhole code to your organization administrator:</p>
            <div class="wormhole-code">{{ wormhole_code }}</div>
        </div>
        {% endif %}

        {% if not onboarding_complete %}
        <div class="progress">
            <h2>Onboarding Progress</h2>
            <div class="progress-bar">
                <div class="progress-bar-fill" style="width: {{ progress }}%"></div>
            </div>
            <div class="progress-step">Current Step: <strong>{{ current_step }}</strong></div>
        </div>
        {% endif %}

        {% if script_output %}
        <div class="status-box">
            <h2>Script Output</h2>
            <pre>{{ script_output }}</pre>
        </div>
        {% endif %}
    </div>
    <script>
        // Auto-refresh status every 5 seconds
        setInterval(() => {
            fetch('/api/system/status')
                .then(response => response.json())
                .then(data => {
                    // Optionally update status fields
                });
        }, 5000);
    </script>
</body>
<script>
    document.getElementById('onboarding-form').addEventListener('submit', function(e) {
    const btn = document.getElementById('submit-btn');
    btn.disabled = true;
    btn.textContent = 'Submitting...';
});
</script>
</html>
"""

def load_known_orgs():
    # Replace with your actual org loading logic
    return {
        "nunet": {"name": "NuNet Testnet"},
        "auki": {"name": "Auki Testnet"}
    }

class WebManager:
    def __init__(self, onboarding_manager, service_mode=False):
        self.app = Flask(__name__, template_folder='../web-assets', static_folder='../web-assets')
        self.app.secret_key = secrets.token_hex(32)
        self.onboarding_manager = onboarding_manager
        self.setup_password = None
        self.password_expiry = None
        self.failed_attempts = 0
        self.max_attempts = 10
        self.port = 8080
        self.service_mode = service_mode
        self.config_file = Path.home() / ".config" / "nunet" / "web_manager_config.json"
        self.limiter = Limiter(
            get_remote_address,
            app=self.app,
            default_limits=[]
        )
        self.ensemble_manager = EnsembleManagerV2()
        self.setup_routes()
        
        # Load persistent password if in service mode
        if self.service_mode:
            self._load_persistent_password()

    def setup_routes(self):
        def login_required(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                if 'authenticated' not in session:
                    return redirect(url_for('index'))
                return f(*args, **kwargs)
            return decorated_function

        @self.app.route('/')
        def index():
            if 'authenticated' in session:
                onboarding_status = self.onboarding_manager.get_onboarding_status()
                step = onboarding_status.get('step')
                if step == 'complete':
                    return redirect(url_for('status'))
                elif step in ('init', 'select_org'):
                    return redirect(url_for('wizard'))
                else:
                    return redirect(url_for('onboarding_status'))
            password_param = request.args.get('password')
            if password_param and self.setup_password and password_param == self.setup_password and datetime.now() < self.password_expiry:
                session['authenticated'] = True
                return redirect(url_for('wizard'))
            return render_template('login.html', error=None, attempts=self.max_attempts - self.failed_attempts)

        @self.app.route('/wizard', methods=['GET', 'POST'])
        @login_required
        def wizard():
            if request.method == 'POST':
                choice = request.form.get('setup_choice')
                self.onboarding_manager.update_state(setup_choice=choice)
                if choice == 'local':
                    self.onboarding_manager.update_state(step='complete')
                    return redirect(url_for('deploy'))
                else:
                    self.onboarding_manager.update_state(step='select_org')
                    return redirect(url_for('join_org'))
            status = self.onboarding_manager.get_onboarding_status()
            return render_template('wizard.html', status=status)

        @self.app.route('/join_org', methods=['GET', 'POST'])
        @login_required
        def join_org():
            status = self.onboarding_manager.get_onboarding_status()
            known_orgs = load_known_organizations()
            if request.method == 'POST':
                org_did = request.form.get('org')
                org_entry = known_orgs.get(org_did, {})
                org_name = org_entry['name'] if isinstance(org_entry, dict) and 'name' in org_entry else org_entry
                
                # Start the onboarding service and let it handle the process
                try:
                    self.onboarding_manager.enable_systemd_service()
                    logger.info("Onboarding service started successfully")
                except Exception as e:
                    logger.error(f"Failed to start onboarding service: {e}")
                    return render_template('error.html', error=f"Failed to start onboarding service: {e}")
                
                # Just update the state to indicate organization selection
                # The service will handle the rest
                self.onboarding_manager.update_state(org_data={"did": org_did, "name": org_name})
                return redirect(url_for('join_form'))
            return render_template('join_org.html', known_orgs=known_orgs, status=status)

        @self.app.route('/join_form', methods=['GET', 'POST'])
        @login_required
        def join_form():
            status = self.onboarding_manager.get_onboarding_status()
            if request.method == 'POST':
                form_data = {
                    "name": request.form.get('name'),
                    "email": request.form.get('email'),
                    "why_join": request.form.get('why_join')
                }
                # Fetch DMS info and add to form_data
                dms_info = get_dms_status_info()
                form_data['dms_did'] = dms_info.get('dms_did')
                form_data['dms_peer_id'] = dms_info.get('dms_peer_id')
                
                # Collect onboarded resource information
                try:
                    resource_info = get_dms_resource_info()
                    onboarding_status = resource_info.get('onboarding_status', 'Unknown')
                    onboarded_resources = resource_info.get('onboarded_resources', 'Unknown')
                    
                    # Extract boolean status and clean resource string
                    is_onboarded = 'ONBOARDED' in onboarding_status
                    clean_resources = onboarded_resources.replace('\033[92m', '').replace('\033[0m', '').replace('\033[91m', '')
                    
                    # Add resources data to form_data
                    form_data['resources'] = {
                        'onboarding_status': is_onboarded,
                        'onboarded_resources': clean_resources
                    }
                    
                    logger.info(f"Resource data collected during form submission - Onboarding Status: {is_onboarded}, Onboarded Resources: {clean_resources}")
                    
                except Exception as e:
                    logger.warning(f"Failed to collect resource information during form submission: {e}")
                    # Continue with onboarding even if resource collection fails
                    form_data['resources'] = {
                        'onboarding_status': False,
                        'onboarded_resources': 'Unknown (collection failed)'
                    }
                
                self.onboarding_manager.update_state(form_data=form_data)
                # The service will handle the onboarding steps automatically
                return redirect(url_for('onboarding_status'))
            
            # For GET request, fetch current DMS info to display
            try:
                dms_info = get_dms_status_info()
                resource_info = get_dms_resource_info()
                onboarding_status = resource_info.get('onboarding_status', 'Unknown')
                onboarded_resources = resource_info.get('onboarded_resources', 'Unknown')
                
                # Extract boolean status and clean resource string
                is_onboarded = 'ONBOARDED' in onboarding_status
                clean_resources = onboarded_resources.replace('\033[92m', '').replace('\033[0m', '').replace('\033[91m', '')
                
                current_dms_info = {
                    'dms_did': dms_info.get('dms_did', 'Unknown'),
                    'dms_peer_id': dms_info.get('dms_peer_id', 'Unknown'),
                    'onboarding_status': is_onboarded,
                    'onboarded_resources': clean_resources
                }
            except Exception as e:
                logger.warning(f"Failed to collect current DMS info for form display: {e}")
                current_dms_info = {
                    'dms_did': 'Unknown',
                    'dms_peer_id': 'Unknown',
                    'onboarding_status': False,
                    'onboarded_resources': 'Unknown'
                }
            
            return render_template('join_form.html', status=status, dms_info=current_dms_info)

        @self.app.route('/onboarding_status')
        @login_required
        def onboarding_status():
            status = self.onboarding_manager.get_onboarding_status()
            steps = [
                ('submit_data', 'Submit Data'),
                ('join_data_sent', 'Data Sent'),
                ('email_verified', 'Email Verified'),
                ('pending_authorization', 'Pending Authorization'),
                ('join_data_received', 'Join Data Received'),
                ('capabilities_applied', 'Capabilities Applied'),
                ('telemetry_configured', 'Telemetry Configured'),
                ('mtls_certs_saved', 'mTLS Certs Saved'),
                ('complete', 'Complete')
            ]
            logs = status.get('logs', [])
            current_step = logs[-1]['step'] if logs else 'submit_data'
            api_status = status.get('api_status')
            # Determine current_index for step_states
            if api_status == 'email_verified':
                current_step = 'email_verified'
            step_keys = [s[0] for s in steps]
            current_index = step_keys.index(current_step) if current_step in step_keys else 0
            step_states = []
            for i, (key, label) in enumerate(steps):
                if i < current_index:
                    state = 'done'
                elif i == current_index:
                    state = 'active'
                else:
                    state = 'todo'
                step_states.append({'label': label, 'state': state})
            onboarding_service_active = self.is_onboarding_service_active()
            api_available = self.is_api_available()
            ui_state, ui_message = self.get_onboarding_ui_state(status)
            return render_template(
                'onboarding_status.html',
                status=status,
                step_states=step_states,
                current_index=current_index,
                current_step=current_step,
                steps=steps,
                onboarding_service_active=onboarding_service_active,
                api_available=api_available,
                ui_state=ui_state,
                ui_message=ui_message
            )

        @self.app.route('/deploy')
        @login_required
        def deploy():
            return render_template('deploy.html')

        @self.app.route('/login', methods=['POST'])
        def login():
            password = request.form.get('password')
            if self.failed_attempts >= self.max_attempts:
                return render_template('login.html', error="Too many failed attempts. Please restart the setup process.", attempts=0)
            if not password or not self.setup_password:
                self.failed_attempts += 1
                return render_template('login.html', error="Invalid password", attempts=self.max_attempts - self.failed_attempts)
            if password == self.setup_password and datetime.now() < self.password_expiry:
                session['authenticated'] = True
                return redirect(url_for('index'))
            else:
                self.failed_attempts += 1
                return render_template('login.html', error="Invalid password", attempts=self.max_attempts - self.failed_attempts)

        @self.app.route('/api/system/status')
        @login_required
        def api_system_status():
            from modules.system_status import get_system_status
            return jsonify(get_system_status())
        
        @self.app.route('/status')
        @login_required
        def status():
            """
            Renders the main status page.

            - `status`        → original onboarding-status dict (template already expects it)
            - `sys_status`    → new comprehensive system-status dict
            - `dms_status`    → current DMS runtime info
            - `dms_resources` → CPU / RAM / GPU resource snapshot
            """
            onboarding_status = self.onboarding_manager.get_onboarding_status()
            sys_status        = get_system_status()
            dms_status        = get_dms_status_info()
            dms_resources     = get_dms_resource_info()
            peers_json  = self.onboarding_manager.dms_manager.view_peer_details()
            peers_list  = []
            if peers_json["status"] == "success":
                import re, json
                ANSI_RE   = re.compile(r'\x1B\[[0-9;]*m')
                clean_str = ANSI_RE.sub('', peers_json["message"])   # remove colour codes
                try:
                    peers_list = json.loads(clean_str).get("Peers", [])
                except Exception as e:
                    print("Peer-JSON parse error:", e)
            return render_template(
                'status.html',
                status        = onboarding_status,
                sys_status    = sys_status,
                dms_status    = dms_status,
                dms_resources = dms_resources,
                dms_peers     = peers_list

            )

        @self.app.route('/logout')
        def logout():
            session.clear()
            return redirect(url_for('index'))

        @self.app.route('/organizations')
        @login_required
        def organizations():
            status = self.onboarding_manager.get_onboarding_status()
            return render_template('organizations.html', status=status)

        # Ensemble API endpoints
        @self.app.route('/api/ensembles')
        @login_required
        def api_ensembles():
            """Returns a JSON list of available ensembles organized by category"""
            try:
                categories = scan_ensembles_directory()
                return jsonify(categories)
            except Exception as e:
                logger.error(f"Error scanning ensembles: {e}")
                return jsonify({"error": "Failed to scan ensembles directory"}), 500

        @self.app.route('/api/deployment-options')
        @login_required
        def api_deployment_options():
            """Returns deployment options including local peer ID and known peers"""
            try:
                options = get_deployment_options(self.onboarding_manager.dms_manager)
                return jsonify(options)
            except Exception as e:
                logger.error(f"Error getting deployment options: {e}")
                return jsonify({"error": "Failed to get deployment options"}), 500

        @self.app.route('/api/ensemble/<name>/meta')
        @login_required
        def api_ensemble_metadata(name):
            """Returns the JSON metadata for a specific ensemble to generate the form fields"""
            try:
                # Find the ensemble file by name across all categories
                categories = scan_ensembles_directory()
                ensemble_path = None
                
                for category, ensembles in categories.items():
                    for ensemble in ensembles:
                        if ensemble['name'] == name:
                            ensemble_path = ensemble['path']
                            break
                    if ensemble_path:
                        break
                
                if not ensemble_path:
                    return jsonify({"error": "Ensemble not found"}), 404
                
                metadata = load_ensemble_metadata(ensemble_path)
                if not metadata:
                    return jsonify({"error": "No metadata found for ensemble"}), 404
                
                return jsonify(metadata)
                
            except Exception as e:
                logger.error(f"Error loading ensemble metadata: {e}")
                return jsonify({"error": "Failed to load ensemble metadata"}), 500

        @self.app.route('/api/ensemble/deploy', methods=['POST'])
        @login_required
        def api_ensemble_deploy():
            """Handles deployment requests by processing form data, creating timestamped YAML files, and calling the ensemble manager's deploy function"""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({"error": "No data provided"}), 400
                
                ensemble_name = data.get('ensemble_name')
                form_values = data.get('form_values', {})
                deployment_type = data.get('deployment_type', 'local')
                
                if not ensemble_name:
                    return jsonify({"error": "Ensemble name is required"}), 400
                
                # Find the ensemble file
                categories = scan_ensembles_directory()
                ensemble_path = None
                
                for category, ensembles in categories.items():
                    for ensemble in ensembles:
                        if ensemble['name'] == ensemble_name:
                            ensemble_path = ensemble['path']
                            break
                    if ensemble_path:
                        break
                
                if not ensemble_path:
                    return jsonify({"error": "Ensemble not found"}), 404
                
                # Load metadata for validation
                metadata = load_ensemble_metadata(ensemble_path)
                if metadata:
                    # Validate form data
                    is_valid, errors = validate_form_data(metadata, form_values)
                    if not is_valid:
                        return jsonify({"error": "Validation failed", "errors": errors}), 400
                
                # Process the YAML template
                processed_content = process_yaml_template(ensemble_path, form_values, deployment_type)
                if not processed_content:
                    return jsonify({"error": "Failed to process YAML template"}), 500
                
                # Generate timestamp and save deployment instance
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                saved_path = save_deployment_instance(ensemble_path, processed_content, timestamp)
                if not saved_path:
                    return jsonify({"error": "Failed to save deployment instance"}), 500
                
                # Deploy using EnsembleManagerV2
                deployment_result = self.ensemble_manager.deploy_ensemble(Path(saved_path))
                
                if deployment_result.get('status') == 'success':
                    return jsonify({
                        "status": "success",
                        "message": "Ensemble deployed successfully",
                        "deployment_id": deployment_result.get('deployment_id'),
                        "saved_path": saved_path
                    })
                else:
                    return jsonify({
                        "status": "error",
                        "message": deployment_result.get('message', 'Deployment failed'),
                        "saved_path": saved_path
                    }), 500
                
            except Exception as e:
                logger.error(f"Error deploying ensemble: {e}")
                return jsonify({"error": f"Deployment failed: {str(e)}"}), 500

        @self.app.route('/api/deployment/<deployment_id>/status')
        @login_required
        def api_deployment_status(deployment_id):
            """Get the current status of a deployment"""
            try:
                result = self.ensemble_manager.get_deployment_status(deployment_id)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Error getting deployment status: {e}")
                return jsonify({"error": f"Failed to get deployment status: {str(e)}"}), 500

        @self.app.route('/api/deployment/<deployment_id>/manifest')
        @login_required
        def api_deployment_manifest(deployment_id):
            result = get_manifest_web(deployment_id)
            return jsonify(result)

        @self.app.route('/api/deployment/<deployment_id>/logs/<allocation_id>')
        @login_required
        def api_deployment_logs(deployment_id, allocation_id):
            result = get_logs_web(deployment_id, allocation_id)
            return jsonify(result)

        @self.app.route('/api/deployments')
        @login_required
        def api_deployments():
            """Get all deployments"""
            try:
                result = self.ensemble_manager.get_deployments_for_web()
                return jsonify(result)
            except Exception as e:
                logger.error(f"Error getting deployments: {e}")
                return jsonify({"error": f"Failed to get deployments: {str(e)}"}), 500

        @self.app.route('/deployments')
        @login_required
        def deployments():
            """Render the deployments page"""
            try:
                with open('/home/ubuntu/menu/web-assets/deployments.html', 'r') as f:
                    template_content = f.read()
                return render_template_string(template_content)
            except Exception as e:
                logger.error(f"Error loading deployments template: {e}")
                return "Error loading deployments page", 500

    def start_server(self, silent=False):
        if silent:
            # Redirect Flask output to /dev/null when silent mode is enabled
            import sys
            import os
            with open(os.devnull, 'w') as devnull:
                old_stdout = sys.stdout
                old_stderr = sys.stderr
                sys.stdout = devnull
                sys.stderr = devnull
                try:
                    self.app.run(host='0.0.0.0', port=8080, debug=False, ssl_context='adhoc', use_reloader=False)
                finally:
                    sys.stdout = old_stdout
                    sys.stderr = old_stderr
        else:
            self.app.run(host='0.0.0.0', port=8080, debug=False, ssl_context='adhoc', use_reloader=False)

    def generate_setup_password(self) -> str:
        """Generate a user-friendly setup password using the EFF wordlist"""
        wordlist_path = os.path.expanduser("~/menu/scripts/eff_large_wordlist.txt")
        words = []
        try:
            with open(wordlist_path, "r") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) == 2:
                        words.append(parts[1])
        except Exception as e:
            # Fallback: use a simple password if wordlist is missing
            logger.warning(f"Could not load wordlist: {e}. Using fallback password.")
            self.setup_password = f"{random.randint(1,999)}-setup-password"
            self.password_expiry = datetime.now() + timedelta(minutes=30)
            self.failed_attempts = 0
            return self.setup_password
        if len(words) < 2:
            self.setup_password = f"{random.randint(1,999)}-setup-password"
        else:
            number = random.randint(1, 999)
            word1 = random.choice(words)
            word2 = random.choice(words)
            self.setup_password = f"{number}-{word1}-{word2}"
        self.password_expiry = datetime.now() + timedelta(minutes=30)
        self.failed_attempts = 0
        return self.setup_password

    def get_dashboard(self, error=None, success=None, show_wormhole_code=False, wormhole_code=None, join_status=None, show_confirmation=False, show_join_form=False, selected_org_name=None, join_fields=None, script_output=None):
        status = self.onboarding_manager.get_onboarding_status()
        peer_info = self.onboarding_manager.dms_manager.get_self_peer_info()
        org_status = status.get('organization_status', {})
        joined_orgs = org_status.get('joined', [])
        known_orgs = org_status.get('known', {})
        wormhole_code = status.get('wormhole_code')
        progress = status.get('progress', 0)
        current_step = status.get('step', '')
        onboarding_complete = status.get('status') == 'complete'
        error = status.get('error') or error
        form_data = status.get('form_data', {})
        # Determine selected org name if available
        if not selected_org_name and form_data.get('org_type') and form_data['org_type'] in known_orgs:
            selected_org_name = known_orgs[form_data['org_type']]['name']
        return render_template_string(
            DASHBOARD_TEMPLATE,
            dms_version=status.get('dms_version', 'Unknown'),
            dms_status=status.get('dms_status', 'Unknown'),
            dms_status_class='success' if status.get('dms_status') == 'Running' else 'error',
            proxy_status=status.get('proxy_status', 'Unknown'),
            proxy_status_class='success' if 'Running' in status.get('proxy_status', '') else 'warning',
            org_status_str="Connected" if joined_orgs else "Not Joined",
            org_status_class="success" if joined_orgs else "warning",
            joined_orgs=joined_orgs,
            known_orgs=known_orgs,
            wormhole_code=wormhole_code,
            show_wormhole_code=bool(wormhole_code),
            show_confirmation=show_confirmation,
            join_status=join_status,
            onboarding_complete=onboarding_complete,
            progress=progress,
            current_step=current_step,
            error=error,
            success=success,
            dms_did=peer_info.get('did', 'No DMS DID Yet'),
            peer_id=peer_info.get('peer_id', 'No Peer ID Yet'),
            dms_context=peer_info.get('context', 'Unknown'),
            public_address=peer_info.get('public_addrs', 'Unknown'),
            local_address=peer_info.get('local_addrs', 'Unknown'),
            show_join_form=show_join_form,
            selected_org_name=selected_org_name,
            join_fields=join_fields or [],
            form_data=form_data,
            script_output=script_output
        )

    def stop_server(self):
        """Stop the web server and clean up"""
        try:
            # Shutdown Flask app gracefully
            if hasattr(self, 'app') and self.app:
                # Use Werkzeug's shutdown function if available
                try:
                    from werkzeug.serving import make_server
                    if hasattr(self.app, 'shutdown'):
                        self.app.shutdown()
                    logger.info("Flask app shutdown initiated")
                except Exception as e:
                    logger.warning(f"Could not shutdown Flask app gracefully: {e}")
            
            # Remove firewall rule
            subprocess.run(['sudo', 'ufw', 'delete', 'allow', str(self.port)], check=True)
            logger.info("Firewall rules cleaned up")
        except Exception as e:
            logger.error(f"Failed to clean up firewall rules: {e}")

    def get_server_info(self) -> Dict[str, str]:
        """Get server information for display"""
        return {
            "url": f"https://{self.get_local_ip()}:{self.port}",
            "password": self.setup_password,
            "attempts_remaining": self.max_attempts - self.failed_attempts
        }

    @staticmethod
    def get_local_ip() -> str:
        """Get the local IP address"""
        try:
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, check=True)
            return result.stdout.strip().split()[0]
        except Exception:
            return "localhost"

    def is_onboarding_service_active(self):
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "nunet-onboarding.service"],
                capture_output=True, text=True, check=True
            )
            return result.stdout.strip() == "active"
        except Exception:
            return False

    def is_api_available(self):
        try:
            # Replace with your real API endpoint
            resp = requests.get("https://api.example.com/health", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    def get_onboarding_ui_state(self, onboarding_status):
        step = onboarding_status.get('step')
        api_status = onboarding_status.get('api_status')
        rejection_reason = onboarding_status.get('rejection_reason', '')
        error = onboarding_status.get('error')
        org_name = onboarding_status.get('org_data', {}).get('name', 'the organization')

        # 1. Data Ready
        if step == 'collect_join_data' and onboarding_status.get('form_data'):
            return ('data_ready', "Your join data is ready. Preparing to submit to the organization's onboarding service...")
        # 2. Waiting for API to be Available
        if step == 'submit_data' and not api_status:
            return ('waiting_api', "Waiting for the organization's onboarding service to become available...")
        # 3. Data Submitted to API
        if step == 'join_data_sent' and api_status in [None, '', 'pending', 'processing', 'email_sent']:
            return ('data_submitted', 'Your join data has been submitted to the organization. Awaiting further instructions...')
        # 4. Waiting for Email Verification
        if step == 'join_data_sent' and api_status == 'email_sent':
            return ('waiting_email', 'A verification email has been sent. Please check your inbox and verify your email address to continue.')
        # 5. Email Verified (show as completed, move to pending authorization)
        if api_status == 'email_verified':
            return ('email_verified', 'Your email has been verified! Waiting for organization approval...')
        # 6. Waiting for Approval
        if step == 'join_data_sent' and api_status in ['pending', 'processing']:
            return ('waiting_approval', 'Your request is being reviewed by the organization. Please wait for approval.')
        # 7. Approved / Join Data Received
        if step in ['pending_authorization', 'join_data_received'] or (step == 'join_data_sent' and api_status in ['approved', 'ready']):
            return ('approved', 'Your request has been approved! Finalizing onboarding...')
        # 8. Capabilities Applied
        if step == 'capabilities_applied':
            return ('capabilities_applied', 'Applying organization capabilities...')
        # 9. Telemetry Configured
        if step == 'telemetry_configured':
            return ('telemetry_configured', 'Configuring telemetry...')
        # 10. mTLS Certs Saved
        if step == 'mtls_certs_saved':
            return ('mtls_certs_saved', 'Saving mTLS certificates...')
        # 11. Complete
        if step == 'complete':
            return ('complete', f'Onboarding complete! You are now a member of {org_name}.')
        # 12. Rejected
        if step == 'rejected' and rejection_reason:
            return ('rejected', f'Your onboarding request was rejected. Reason: {rejection_reason}')
        # 13. Error
        if error:
            return ('error', f'An error occurred: {error}')
        # Default fallback
        return (step, f'Current step: {step}')

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading config: {e}")
        return {}
    
    def _save_config(self, config: Dict[str, Any]) -> bool:
        """Save configuration to file."""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            # Set secure permissions
            self.config_file.chmod(0o600)
            return True
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False
    
    def _load_persistent_password(self) -> Optional[str]:
        """Load persistent password from config."""
        config = self._load_config()
        password = config.get('password')
        expiry_str = config.get('password_expiry')
        
        if password and expiry_str:
            try:
                expiry = datetime.fromisoformat(expiry_str)
                if datetime.now() < expiry:
                    self.setup_password = password
                    self.password_expiry = expiry
                    logger.info("Loaded persistent password from config")
                    return password
                else:
                    logger.info("Persistent password has expired")
            except Exception as e:
                logger.error(f"Error parsing password expiry: {e}")
        
        return None
    
    def _save_persistent_password(self, password: str, expiry_hours: int = 24) -> bool:
        """Save password to config with expiry."""
        config = self._load_config()
        config['password'] = password
        config['password_expiry'] = (datetime.now() + timedelta(hours=expiry_hours)).isoformat()
        return self._save_config(config)
    
    def generate_setup_password(self) -> str:
        """Generate a user-friendly setup password using the EFF wordlist"""
        # Check for existing password first if in service mode
        if self.service_mode:
            existing_password = self._load_persistent_password()
            if existing_password:
                logger.info("Using existing persistent password")
                return existing_password
        
        wordlist_path = os.path.expanduser("~/menu/scripts/eff_large_wordlist.txt")
        words = []
        try:
            with open(wordlist_path, "r") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) == 2:
                        words.append(parts[1])
        except Exception as e:
            # Fallback: use a simple password if wordlist is missing
            logger.warning(f"Could not load wordlist: {e}. Using fallback password.")
            self.setup_password = f"{random.randint(1,999)}-setup-password"
            self.password_expiry = datetime.now() + timedelta(minutes=30)
            self.failed_attempts = 0
            return self.setup_password
        if len(words) < 2:
            self.setup_password = f"{random.randint(1,999)}-setup-password"
        else:
            number = random.randint(1, 999)
            word1 = random.choice(words)
            word2 = random.choice(words)
            self.setup_password = f"{number}-{word1}-{word2}"
        
        # Set expiry based on service mode
        if self.service_mode:
            self.password_expiry = datetime.now() + timedelta(hours=24)
            # Save persistent password
            self._save_persistent_password(self.setup_password, 24)
        else:
            self.password_expiry = datetime.now() + timedelta(minutes=30)
        
        self.failed_attempts = 0
        return self.setup_password
    
    def regenerate_password(self) -> str:
        """Regenerate the setup password."""
        # Generate new password
        new_password = self.generate_setup_password()
        
        # If in service mode, restart the service to pick up new password
        if self.service_mode:
            logger.info("Password regenerated, service should be restarted to pick up changes")
        
        return new_password
    
    def get_password_info(self) -> Dict[str, Any]:
        """Get password information including expiry."""
        config = self._load_config()
        password = config.get('password')
        expiry_str = config.get('password_expiry')
        
        info = {
            'has_password': bool(password),
            'expires_at': expiry_str,
            'is_expired': False,
            'service_mode': self.service_mode
        }
        
        if password and expiry_str:
            try:
                expiry = datetime.fromisoformat(expiry_str)
                info['is_expired'] = datetime.now() >= expiry
                info['expires_in'] = str(expiry - datetime.now())
            except Exception as e:
                logger.error(f"Error parsing expiry: {e}")
        
        return info

WebManager.is_onboarding_service_active = WebManager.is_onboarding_service_active
WebManager.is_api_available = WebManager.is_api_available

if __name__ == "__main__":
    if check_dependencies():
        onboarding_manager = OnboardingManager()
        web_manager = WebManager(onboarding_manager)
        web_manager.start_server() 