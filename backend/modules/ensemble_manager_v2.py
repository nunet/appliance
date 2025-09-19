"""
Enhanced Ensemble management module for NuNet (V2)
Includes improved deployment tracking and log management
"""

import os
import subprocess
import shutil
import json
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from .dms_utils import run_dms_command_with_passphrase
from .utils import get_current_branch, Colors, print_header, print_menu_option, pause

class EnsembleManagerV2:
    def __init__(self):
        """Initialize the EnsembleManagerV2"""
        self.home_dir = Path.home()
        self.base_dir = self.home_dir / "ensembles"
        self.log_dir = self.home_dir / "nunet" / "appliance" / "deployment_logs"
        self.deployments_dir = self.home_dir / "nunet" / "deployments"
        # Default settings for example ensembles
        self.repo = "nunet/solutions/nunet-appliance"
        self.source_dir = "ensembles/examples"
        self.show_help_message = False  # Default: help is off

    def _ensure_directories(self):
        """Ensure required directories exist"""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _normalize_deployment_status_label(self, raw_status: Optional[str]) -> str:
        """Map arbitrary status strings from DMS into UI-friendly buckets."""
        if raw_status is None:
            return "unknown"
        text_value = str(raw_status).strip()
        if not text_value:
            return "unknown"
        normalized = text_value.lower().replace('_', ' ')
        if "not running" in normalized or any(token in normalized for token in ("stopped", "shutdown", "terminated", "complete", "completed", "finished", "done", "inactive", "teardown", "removed")):
            return "completed"
        if any(token in normalized for token in ("fail", "error", "cancel", "cancelled", "canceled", "abort", "aborted", "crash", "panic")):
            return "failed"
        if any(token in normalized for token in ("pending", "queue", "queued", "init", "starting", "initializing", "shutt", "wait", "boot")):
            return "pending"
        if "running" in normalized or "active" in normalized or "executing" in normalized or "deploying" in normalized:
            return "running"
        return "unknown"

    def _parse_timestamp_value(self, value: Any) -> Optional[datetime]:
        """Convert various timestamp representations into datetime objects."""
        if isinstance(value, datetime):
            return value
        if value is None:
            return None
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value)
            except (OverflowError, ValueError):
                return None
        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                return None
            if candidate.isdigit():
                try:
                    return datetime.fromtimestamp(int(candidate))
                except (OverflowError, ValueError):
                    pass
            iso_candidate = candidate
            if iso_candidate.endswith('Z'):
                iso_candidate = iso_candidate[:-1] + '+00:00'
            try:
                return datetime.fromisoformat(iso_candidate)
            except ValueError:
                pass
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f'):
                try:
                    return datetime.strptime(candidate, fmt)
                except ValueError:
                    continue
        return None

    def _normalize_deployment_entry(self, dep_id: str, meta: Any) -> Dict[str, Any]:
        """Normalize deployment metadata returned by DMS."""
        details = meta if isinstance(meta, dict) else {}
        status_sources: List[Dict[str, Any]] = []
        if isinstance(details, dict):
            status_sources.append(details)
            nested = details.get('Deployment') or details.get('deployment') or details.get('summary') or details.get('info')
            if isinstance(nested, dict):
                status_sources.append(nested)
        status_raw = ''
        for source in status_sources:
            for key in ('Status', 'status', 'State', 'state', 'Phase', 'phase'):
                val = source.get(key)
                if val:
                    status_raw = str(val)
                    break
            if status_raw:
                break
        if not status_raw and not isinstance(meta, dict):
            status_raw = str(meta)
        timestamp_val = None
        for source in status_sources:
            for key in ('SubmittedAt', 'submittedAt', 'SubmissionTime', 'submission_time', 'CreatedAt', 'createdAt', 'created_at', 'Timestamp', 'timestamp', 'UpdatedAt', 'updatedAt', 'updated_at'):
                val = source.get(key)
                if val:
                    timestamp_val = val
                    break
            if timestamp_val:
                break
        ensemble_file = None
        for source in status_sources:
            for key in ('ManifestPath', 'manifest_path', 'ManifestFile', 'manifestFile', 'manifest_file', 'EnsembleFile', 'ensemble_file', 'File', 'file'):
                val = source.get(key)
                if val:
                    ensemble_file = val
                    break
            if ensemble_file:
                break
        if ensemble_file is None and isinstance(details, dict):
            manifest = details.get('Manifest') or details.get('manifest')
            if isinstance(manifest, dict):
                for key in ('path', 'file', 'source'):
                    val = manifest.get(key)
                    if val:
                        ensemble_file = val
                        break
        deployment_type = None
        for source in status_sources:
            for key in ('Type', 'type', 'DeploymentType', 'deployment_type'):
                val = source.get(key)
                if val:
                    deployment_type = val
                    break
            if deployment_type:
                break
        normalized_status = self._normalize_deployment_status_label(status_raw)
        timestamp_dt = self._parse_timestamp_value(timestamp_val)
        if isinstance(ensemble_file, Path):
            ensemble_file = str(ensemble_file)
        entry: Dict[str, Any] = {
            'id': dep_id,
            'status': normalized_status,
            'status_raw': status_raw or None,
            'timestamp': timestamp_dt,
            'ensemble_file': ensemble_file,
            'type': deployment_type,
            'details': details if isinstance(meta, dict) else {'value': meta},
        }
        return entry

    def _parse_deployment_list_json(self, payload: Any) -> Dict[str, Dict[str, Any]]:
        """Parse deployment list JSON payloads from DMS."""
        deployments: Dict[str, Dict[str, Any]] = {}
        items: Any = None
        if isinstance(payload, dict):
            for key in ('Deployments', 'deployments', 'items', 'data', 'ActiveDeployments', 'activeDeployments'):
                if key in payload:
                    items = payload[key]
                    break
            if items is None and {'DeploymentID', 'Status'} <= set(payload.keys()):
                items = [payload]
        else:
            items = payload
        if isinstance(items, dict):
            for dep_id, meta in items.items():
                if dep_id:
                    dep_key = str(dep_id)
                    deployments[dep_key] = self._normalize_deployment_entry(dep_key, meta)
        elif isinstance(items, list):
            for meta in items:
                dep_id = None
                if isinstance(meta, dict):
                    for key in ('id', 'ID', 'deployment_id', 'DeploymentID', 'EnsembleID'):
                        if meta.get(key):
                            dep_id = str(meta[key])
                            break
                elif isinstance(meta, str):
                    dep_id = meta
                if dep_id:
                    deployments[dep_id] = self._normalize_deployment_entry(dep_id, meta)
        return deployments

    def _parse_deployment_list_text(self, stdout: str) -> Dict[str, Dict[str, Any]]:
        """Best-effort parse for text formatted deployment lists."""
        deployments: Dict[str, Dict[str, Any]] = {}
        current_id: Optional[str] = None
        current_data: Dict[str, Any] = {}
        for raw_line in (stdout or '').splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lowered = line.lower()
            if lowered.startswith('deployment id') or lowered.startswith('deployment:') or lowered.startswith('ensemble id'):
                if current_id:
                    deployments[current_id] = self._normalize_deployment_entry(current_id, current_data)
                current_data = {}
                _, _, tail = line.partition(':')
                current_id = tail.strip() or line.split()[-1]
                continue
            if ':' in line and current_id:
                key, _, value = line.partition(':')
                current_data[key.strip()] = value.strip()
            elif current_id and line.startswith('/'):
                current_data.setdefault('ManifestPath', line)
            elif current_id and not current_data and line:
                current_id = line
        if current_id:
            deployments[current_id] = self._normalize_deployment_entry(current_id, current_data)
        return deployments

    def get_active_deployments(self) -> Dict[str, Dict[str, Any]]:
        """Get list of deployments known to DMS."""
        try:
            result = run_dms_command_with_passphrase(
                ['nunet', '-c', 'dms', 'actor', 'cmd', '/dms/node/deployment/list'],
                capture_output=True,
                text=True,
                check=True
            )
            stdout = (result.stdout or '').strip()
            if not stdout:
                return {}
            try:
                payload = json.loads(stdout)
                deployments = self._parse_deployment_list_json(payload)
                if deployments:
                    return deployments
            except json.JSONDecodeError:
                pass
            return self._parse_deployment_list_text(stdout)
        except Exception as e:
            print(f"Error getting active deployments: {e}")
            return {}

    def get_deployment_history(self) -> Dict[str, Dict]:
        """Get deployment history from deployment_logs directory"""
        history = {}
        try:
            for log_file in self.log_dir.glob('*.log'):
                try:
                    timestamp = datetime.fromtimestamp(float(log_file.stem))
                except ValueError:
                    timestamp = datetime.fromtimestamp(log_file.stat().st_mtime)
                
                with open(log_file, 'r') as f:
                    content = f.read().strip()
                
                history[log_file.name] = {
                    "timestamp": timestamp,
                    "content": content,
                    "type": "deployment_log"
                }
        except Exception as e:
            print(f"Error reading deployment logs: {e}")
        return history

    def get_historical_deployments(self) -> Dict[str, Dict]:
        """Get historical deployments from deployments directory"""
        historical = {}
        try:
            if self.deployments_dir.exists():
                for deployment_id in os.listdir(self.deployments_dir):
                    deployment_path = self.deployments_dir / deployment_id
                    if deployment_path.is_dir():
                        timestamp = datetime.fromtimestamp(deployment_path.stat().st_ctime)
                        historical[deployment_id] = {
                            "status": "Historical",
                            "timestamp": timestamp,
                            "type": "historical_deployment"
                        }
        except Exception as e:
            print(f"Error reading historical deployments: {e}")
        return historical

    def parse_deployment_log(self) -> Dict[str, Dict]:
        """Parse the deployment log to get historical deployments"""
        deployments = {}
        try:
            log_file = self.log_dir / "deployments.log"
            if not log_file.exists():
                return deployments

            with open(log_file, 'r') as f:
                lines = f.readlines()
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    if "Submitting deployment on" in line:
                        # Get timestamp and file info
                        timestamp_str = line.split("Submitting deployment on ")[1].split(" for:")[0]
                        file_path = line.split(" for: ")[1].strip()  # Get the full path
                        
                        # Look ahead for success/failure and deployment ID
                        success = False
                        deployment_id = None
                        for j in range(1, 6):  # Look at next 5 lines
                            if i + j >= len(lines):
                                break
                            next_line = lines[i + j].strip()
                            if "Ensemble was submitted successfully" in next_line:
                                success = True
                            elif '"EnsembleID":' in next_line:
                                deployment_id = next_line.split('"EnsembleID":')[1].strip().strip('"').strip(',').strip('"')
                            elif "Ensemble deployment unsuccessful" in next_line:
                                success = False
                                break

                        if deployment_id:
                            deployments[deployment_id] = {
                                'timestamp': datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S"),
                                'file_name': file_path,  # Store the full path
                                'file_basename': os.path.basename(file_path),  # Store basename separately if needed
                                'status': 'Submitted' if success else 'Failed',
                                'active': False
                            }
                    i += 1

        except Exception as e:
            print(f"Error parsing deployment log: {e}")
        return deployments

    def format_deployment_table(self, items):
        """Format deployments as a table with colors"""
        headers = ['No.', 'Deployment ID', 'Status', 'Type', 'Ensemble File', 'Date Started']
        num_cols = len(headers)

        total_width = self._get_terminal_width() - 20

        fixed_widths = {
            'No.': 5,
            'Deployment ID': 64,
            'Status': 12,
            'Type': 12,
            'Date Started': 16,
        }

        used_width = sum(fixed_widths.values())
        border_and_padding = num_cols + 1
        remaining_width = total_width - used_width - border_and_padding
        ensemble_file_width = max(10, remaining_width)

        widths = [
            fixed_widths['No.'],
            fixed_widths['Deployment ID'],
            fixed_widths['Status'],
            fixed_widths['Type'],
            ensemble_file_width,
            fixed_widths['Date Started'],
        ]

        rows = []
        for idx, (item_id, info) in enumerate(items, 1):
            raw_status = str(info.get('status', 'unknown'))
            status_lower = raw_status.lower()
            if status_lower == 'running':
                status = f"{Colors.GREEN}Running{Colors.NC}"
            elif status_lower == 'completed':
                status = f"{Colors.BLUE}Completed{Colors.NC}"
            elif status_lower == 'failed':
                status = f"{Colors.RED}Failed{Colors.NC}"
            elif status_lower == 'pending':
                status = f"{Colors.YELLOW}Pending{Colors.NC}"
            elif status_lower == 'unknown':
                status = f"{Colors.YELLOW}Unknown{Colors.NC}"
            elif 'deployment log' in status_lower:
                continue
            else:
                status = raw_status.title()

            item_type = 'Active' if info.get('active') else 'Historical'

            ts_value = info.get('timestamp')
            if isinstance(ts_value, datetime):
                timestamp = ts_value.strftime('%Y-%m-%d %H:%M')
            else:
                timestamp = str(ts_value or '')

            file_name = info.get('file_name', 'N/A')
            if isinstance(file_name, Path):
                file_name = file_name.name
            elif isinstance(file_name, str):
                file_name = os.path.basename(file_name) or file_name
            else:
                file_name = str(file_name)

            if file_name.endswith('.yaml'):
                file_name = file_name[:-5]
            if len(file_name) > ensemble_file_width - 2:
                file_name = file_name[:ensemble_file_width - 5] + '...'

            row = [
                str(idx),
                item_id,
                status,
                item_type,
                file_name,
                timestamp,
            ]
            rows.append(row)

        table = []
        border = '+' + '+'.join('-' * (w + 2) for w in widths) + '+'
        table.append(border)

        header_row = '| ' + ' | '.join(f"{Colors.CYAN}{h:<{w}}{Colors.NC}" for h, w in zip(headers, widths)) + ' |'
        table.append(header_row)
        table.append(border)

        for row in rows:
            data_row = '| '
            for i, (cell, width) in enumerate(zip(row, widths)):
                if i > 0:
                    data_row += ' | '
                if i == 2 and any(color in cell for color in (Colors.GREEN, Colors.BLUE, Colors.RED, Colors.YELLOW)):
                    clean_cell = cell
                    for color in (Colors.GREEN, Colors.BLUE, Colors.RED, Colors.YELLOW, Colors.NC):
                        clean_cell = clean_cell.replace(color, '')
                    data_row += cell.ljust(width + len(cell) - len(clean_cell))
                else:
                    data_row += cell.ljust(width)
            data_row += ' |'
            table.append(data_row)

        table.append(border)
        return "\n".join(table), len(rows)

    def view_running_ensembles(self) -> Dict[str, str]:
        """Enhanced view of currently running ensembles with historical data"""
        active = self.get_active_deployments()
        deployment_log = self.parse_deployment_log()

        all_items: Dict[str, Dict[str, Any]] = {}
        now = datetime.now()

        for dep_id, meta in active.items():
            status_norm = str(meta.get('status', 'unknown')).lower()
            log_info = deployment_log.get(dep_id)
            timestamp = meta.get('timestamp') or (log_info.get('timestamp') if log_info else None) or now
            file_name = meta.get('ensemble_file') or (log_info.get('file_name') if log_info else None) or 'N/A'
            if isinstance(file_name, Path):
                file_name = file_name.name
            elif isinstance(file_name, str):
                file_name = os.path.basename(file_name) or file_name
            else:
                file_name = str(file_name)

            all_items[dep_id] = {
                'status': status_norm,
                'active': status_norm in ('running', 'pending'),
                'timestamp': timestamp,
                'type': 'active_deployment' if status_norm in ('running', 'pending') else 'deployment_record',
                'file_name': file_name,
            }

            if log_info:
                log_ts = log_info.get('timestamp')
                if isinstance(log_ts, datetime):
                    all_items[dep_id]['timestamp'] = log_ts
                log_name = log_info.get('file_name')
                if log_name:
                    all_items[dep_id]['file_name'] = os.path.basename(log_name)

        for dep_id, info in deployment_log.items():
            if dep_id in all_items:
                continue
            status_norm = 'completed' if info.get('status') == 'Submitted' else str(info.get('status', 'failed')).lower()
            all_items[dep_id] = {
                'status': status_norm,
                'active': False,
                'timestamp': info['timestamp'],
                'type': 'historical_deployment',
                'file_name': os.path.basename(info.get('file_name', 'N/A')),
            }

        if not all_items:
            return {
                'status': 'success',
                'message': 'No deployments found.',
                'items': [],
                'count': 0,
            }

        sorted_items = sorted(
            all_items.items(),
            key=lambda item: item[1].get('timestamp') or datetime.min,
            reverse=True,
        )[:20]

        table_str, num_items = self.format_deployment_table(sorted_items)

        return {
            'status': 'success',
            'message': table_str,
            'items': sorted_items,
            'count': num_items,
        }

    def _get_node_ping(self, host: str) -> str:
        """Get ping response time for a node"""
        try:
            result = run_dms_command_with_passphrase(
                ['nunet', '-c', 'dms', 'actor', 'cmd', '/dms/node/peers/ping',
                 '--host', host],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse the JSON response
            response = json.loads(result.stdout)
            if response.get("Error"):
                return "Error"
            return f"{response.get('RTT', 'N/A')}ms"
        except Exception:
            return "Timeout"

    def _truncate_id(self, id_str: str, max_length: int = 40) -> str:
        """Truncate a long ID by removing characters from the middle"""
        if len(id_str) <= max_length:
            return id_str
        
        # Keep first and last parts, replace middle with ...
        part_length = (max_length - 3) // 2
        return f"{id_str[:part_length]}...{id_str[-part_length:]}"

    def _get_terminal_width(self) -> int:
        """Get the current terminal width, fallback to 150 if cannot be determined"""
        try:
            # Get terminal size
            columns, _ = shutil.get_terminal_size()
            # Ensure minimum width of 80 characters
            return max(80, columns)
        except Exception:
            # Fallback to 150 if we can't determine the width
            return 150

    def format_manifest_tables(self, manifest_data: str) -> str:
        """Format manifest data into readable tables"""
        try:
            # Parse the JSON manifest
            data = json.loads(manifest_data)
            manifest = data.get("manifest", {})
            
            # Get terminal width and adjust
            TOTAL_WIDTH = self._get_terminal_width() - 20
            
            # Fixed widths
            FIELD_COL_WIDTH = 25
            ALLOC_ID_WIDTH = 40
            DNS_NAME_WIDTH = 30
            
            # Get deployment ID and look up ensemble file path
            deployment_id = manifest.get("id", "N/A")
            deployment_log = self.parse_deployment_log()
            ensemble_file_path = None
            
            # Get the full path from deployment log
            if deployment_id in deployment_log:
                log_entry = deployment_log[deployment_id]
                if 'file_name' in log_entry:
                    # The file_name in the log is actually the full path
                    ensemble_file_path = Path(log_entry['file_name'])
            
            # Parse ensemble file if found
            ensemble_info = None
            if ensemble_file_path and ensemble_file_path.exists():
                try:
                    with open(ensemble_file_path, 'r') as f:
                        ensemble_info = yaml.safe_load(f)
                except Exception as e:
                    print(f"\nDebug: Error reading ensemble file: {e}")
            
            # Format the main deployment details
            deployment_details = [
                ["Deployment ID", deployment_id],
                ["Ensemble File", str(ensemble_file_path) if ensemble_file_path else "N/A"],
                ["Orchestrator", manifest.get("orchestrator", {}).get("addr", {}).get("host", "N/A")],
                ["Status", self._get_overall_status(manifest.get("allocations", {}))]
            ]
            
            deployment_table = self.format_simple_table(
                headers=["Field", "Value"],
                rows=deployment_details,
                widths=[FIELD_COL_WIDTH, TOTAL_WIDTH - FIELD_COL_WIDTH - 7]
            )
            
            # Add orchestrator details table
            orchestrator = manifest.get("orchestrator", {})
            orchestrator_details = [
                ["Host", orchestrator.get("addr", {}).get("host", "N/A")],
                ["Inbox", orchestrator.get("addr", {}).get("inbox", "N/A")],
                ["DID", orchestrator.get("did", {}).get("uri", "N/A")],
                ["Public Key", orchestrator.get("id", {}).get("pub", "N/A")]
            ]
            
            orchestrator_table = self.format_simple_table(
                headers=["Field", "Value"],
                rows=orchestrator_details,
                widths=[FIELD_COL_WIDTH, TOTAL_WIDTH - FIELD_COL_WIDTH - 7]
            )
            
            # Format allocations table with ports and private addresses
            allocation_rows = []
            allocations = manifest.get("allocations", {})
            for alloc_name, alloc in allocations.items():
                port_mappings = []
                for internal, external in alloc.get("ports", {}).items():
                    port_mappings.append(f"{internal}→{external}")
                ports_str = ", ".join(port_mappings)
                
                # Only truncate the allocation ID
                alloc_id = self._truncate_id(alloc.get("id", "N/A"), 40)
                
                allocation_rows.append([
                    alloc_id,
                    alloc.get("type", "N/A"),
                    alloc.get("node_id", "N/A"),
                    alloc.get("dns_name", "N/A"),
                    alloc.get("priv_addr", "N/A"),
                    ports_str,
                    self._colorize_status(alloc.get("status", "N/A"))
                ])
                
            # Calculate remaining width for DNS Name in Allocations table
            # Total of fixed widths: 40 + 12 + 8 + 15 + 15 + 14 = 104
            # Plus borders and padding for 7 columns: (7 * 3) + 1 = 22
            # So DNS Name gets: TOTAL_WIDTH - (104 + 22)
            dns_name_width = TOTAL_WIDTH - 126  # Updated from 128 to 126 due to Node column reduction
            
            # Allocations table with 8-char Node column
            allocations_table = self.format_simple_table(
                headers=["Allocation ID", "Type", "Node", "DNS Name", "Private IP", "Ports", "Status"],
                rows=allocation_rows,
                widths=[ALLOC_ID_WIDTH, 12, 8, dns_name_width, 15, 15, 14]
            )
            
            # Format nodes detail table with ping times
            node_rows = []
            nodes = manifest.get("nodes", {})
            for node_name, node in nodes.items():
                location = node.get("location", {})
                location_str = f"{location.get('country', 'N/A')} ({location.get('continent', 'N/A')})"
                node_allocations = ", ".join(node.get("allocations", []))
                
                # Get ping response time
                peer_id = node.get("peer", "N/A")
                ping_time = self._get_node_ping(peer_id)
                
                node_rows.append([
                    node.get("id", "N/A"),  # Not truncated
                    peer_id,                 # Not truncated
                    location_str,
                    ping_time,
                    node_allocations
                ])
                    
            nodes_table = self.format_simple_table(
                headers=["Node ID", "Peer ID", "Location", "Ping", "Allocations"],
                rows=node_rows,
                widths=[
                    20,  # Node ID
                    TOTAL_WIDTH - (20 + 7 + 7 + 7 + 7 + 7 + 7 + 7),  # Peer ID gets remaining space
                    7,  # Location
                    7,  # Ping
                    7  # Allocations
                ]
            )

            # Add ensemble configuration if available
            ensemble_section = ""
            if ensemble_info:
                # Format allocations section
                ensemble_alloc_rows = []
                for alloc_name, alloc in ensemble_info.get("allocations", {}).items():
                    resources = alloc.get("resources", {})
                    
                    # Get CPU cores
                    cpu = resources.get("cpu", {})
                    cpu_cores = cpu.get("cores", "N/A")
                    
                    # Get RAM
                    ram = resources.get("ram", {})
                    ram_size = ram.get("size", "N/A")
                    
                    # Get Disk
                    disk = resources.get("disk", {})
                    disk_size = disk.get("size", "N/A")
                    
                    # Get GPU info
                    gpus = resources.get("gpus", [])
                    gpu_info = "Yes" if gpus else "No"
                    
                    # Get execution info
                    execution = alloc.get("execution", {})
                    image = execution.get("image", "N/A")
                    
                    # Add row
                    ensemble_alloc_rows.append([
                        alloc_name,
                        str(cpu_cores),
                        ram_size,
                        disk_size,
                        gpu_info,
                        image
                    ])
                
                if ensemble_alloc_rows:
                    alloc_table = self.format_simple_table(
                        headers=["Allocation", "CPU Cores", "RAM", "Disk", "GPU", "Image"],
                        rows=ensemble_alloc_rows,
                        widths=[20, 15, 15, 15, 8, TOTAL_WIDTH - 92]  # 92 = sum of other widths + borders
                    )
                    
                # Format nodes section from ensemble
                ensemble_node_rows = []
                for node_name, node in ensemble_info.get("nodes", {}).items():
                    # Get port mappings
                    ports = node.get("ports", [])
                    port_mappings = []
                    for port in ports:
                        port_mappings.append(f"{port.get('public', 'N/A')}→{port.get('private', 'N/A')}")
                    
                    # Get allocations
                    node_allocs = ", ".join(node.get("allocations", []))
                    
                    # Add row
                    ensemble_node_rows.append([
                        node_name,
                        node.get("peer", "N/A"),
                        ", ".join(port_mappings),
                        node_allocs
                    ])
                
                if ensemble_node_rows:
                    node_table = self.format_simple_table(
                        headers=["Node", "Peer ID", "Port Mappings", "Allocations"],
                        rows=ensemble_node_rows,
                        widths=[15, TOTAL_WIDTH - 89, 35, 26]  # 89 = sum of other widths + borders
                    )
                    
                ensemble_section = f"""
Ensemble Configuration:

Allocations:
{alloc_table}

Node Configuration:
{node_table}
"""

            # Combine all sections
            return f"""
=== Manifest for Deployment {deployment_id} ===

Deployment Details:
{deployment_table}

{ensemble_section}
Orchestrator:
{orchestrator_table}

Allocations:
{allocations_table}

Nodes Detail:
{nodes_table}
"""
        except json.JSONDecodeError:
            return manifest_data
        except Exception as e:
            return f"Error formatting manifest: {e}\n\nOriginal manifest:\n{manifest_data}"

    def _get_overall_status(self, allocations: dict) -> str:
        """Determine overall deployment status from allocations"""
        if not allocations:
            return "Unknown"
        
        statuses = [alloc.get("status", "").lower() for alloc in allocations.values()]
        if all(status == "completed" for status in statuses):
            return self._colorize_status("Completed")
        elif any(status == "failed" for status in statuses):
            return self._colorize_status("Failed")
        else:
            return self._colorize_status("Running")

    def _colorize_status(self, status: str) -> str:
        """Add color to status text"""
        status = status.lower()
        if status == "completed":
            return f"{Colors.GREEN}{status.title()}{Colors.NC}"
        elif status == "running":
            return f"{Colors.BLUE}{status.title()}{Colors.NC}"
        elif "failed" in status:
            return f"{Colors.RED}{status.title()}{Colors.NC}"
        return status.title()

    def format_simple_table(self, headers: List[str], rows: List[List[str]], widths: List[int]) -> str:
        """Helper function to format a simple table with given headers and rows"""
        # Create the border line
        border = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
        
        # Format the table
        table = [border]
        
        # Add headers
        header_row = "| " + " | ".join(f"{Colors.CYAN}{h:<{w}}{Colors.NC}" for h, w in zip(headers, widths)) + " |"
        table.append(header_row)
        table.append(border)
        
        # Add data rows
        for row in rows:
            data_row = "| "
            for i, (cell, width) in enumerate(zip(row, widths)):
                if i > 0:
                    data_row += " | "
                # Add extra padding for colored status values
                if "Running" in str(cell) and (Colors.BLUE in str(cell) or Colors.GREEN in str(cell) or Colors.RED in str(cell)):
                    data_row += f"{cell}{''.ljust(7)}"
                else:
                    data_row += str(cell).ljust(width)
            data_row += " |"
            table.append(data_row)
        
        # Add bottom border
        table.append(border)
        
        return "\n".join(table)

    def view_manifest(self, item_id: str) -> Dict[str, str]:
        """View manifest for a deployment or log contents for a deployment log"""
        try:
            if item_id.endswith('.log'):
                # This is a deployment log
                log_path = self.log_dir / item_id
                with open(log_path, 'r') as f:
                    content = f.read()
                return {"status": "success", "message": f"\nDeployment Log Contents:\n{content}"}
            else:
                # This is a deployment ID
                result = run_dms_command_with_passphrase(
                    ['nunet', '-c', 'dms', 'actor', 'cmd', '/dms/node/deployment/manifest',
                     '-i', item_id],
                    capture_output=True,
                    text=True,
                    check=True
                )
                # Debug: Print raw manifest data
                print("\nRaw manifest data:")
                print(result.stdout)
                
                try:
                    # Try to parse JSON and print structure
                    manifest_data = json.loads(result.stdout)
                    print("\nParsed JSON structure:")
                    print(json.dumps(manifest_data, indent=2))
                    
                    # Format the manifest into tables
                    formatted_manifest = self.format_manifest_tables(result.stdout)
                    return {"status": "success", "message": formatted_manifest}
                except json.JSONDecodeError as je:
                    return {"status": "error", "message": f"Invalid JSON format: {je}\n\nRaw data:\n{result.stdout}"}
        except Exception as e:
            return {"status": "error", "message": f"Error viewing manifest: {e}"}

    def view_logs(self, deployment_id: str) -> Dict[str, str]:
        """View logs for a deployment"""
        try:
            # First try to get allocations (for running/successful deployments)
            allocations = self.get_deployment_allocations(deployment_id)
            dms_log_path = "/home/nunet/logs/nunet-dms.log"
            
            log_content = "\nLog Contents:\n"
            
            # If we have allocations, show the regular deployment logs
            if allocations:
                # If multiple allocations, let user choose
                if len(allocations) > 1:
                    print("\nAvailable allocations:")
                    for idx, alloc in enumerate(allocations, 1):
                        print(f"{idx}. {alloc}")
                    choice = input("\nSelect allocation number: ")
                    try:
                        alloc_idx = int(choice) - 1
                        if 0 <= alloc_idx < len(allocations):
                            selected_alloc = allocations[alloc_idx]
                        else:
                            return {"status": "error", "message": "Invalid allocation number"}
                    except ValueError:
                        return {"status": "error", "message": "Invalid input"}
                else:
                    selected_alloc = allocations[0]
                
                # Construct the deployment directory path
                deployment_dir = f"/home/nunet/nunet/deployments/{deployment_id}/{selected_alloc}"
                stdout_path = f"{deployment_dir}/stdout.logs"
                stderr_path = f"{deployment_dir}/stderr.logs"
                
                log_content += f"\nDeployment directory: {deployment_dir}\n"
                
                log_content += "\n=== STDOUT ===\n"
                log_content += f"Path: {stdout_path}\n"
                try:
                    stdout_result = subprocess.run(
                        ['sudo', 'cat', stdout_path],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    log_content += stdout_result.stdout
                except subprocess.CalledProcessError as e:
                    log_content += f"Error reading stdout: {e}\n"
                    
                log_content += "\n=== STDERR ===\n"
                log_content += f"Path: {stderr_path}\n"
                try:
                    stderr_result = subprocess.run(
                        ['sudo', 'cat', stderr_path],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    log_content += stderr_result.stdout
                except subprocess.CalledProcessError as e:
                    log_content += f"Error reading stderr: {e}\n"
            
            # Always check DMS logs for any mentions of this deployment
            log_content += f"\n=== DMS LOG ENTRIES ===\n"
            log_content += f"Searching in: {dms_log_path}\n\n"
            try:
                # Use grep to find lines containing the deployment ID
                grep_result = subprocess.run(
                    ['sudo', 'grep', '-A', '5', '-B', '5', deployment_id, dms_log_path],
                    capture_output=True,
                    text=True
                )
                if grep_result.stdout:
                    log_content += grep_result.stdout
                else:
                    log_content += "No entries found in DMS log\n"
            except subprocess.CalledProcessError as e:
                log_content += f"Error searching DMS log: {e}\n"
            
            return {"status": "success", "message": log_content}
            
        except Exception as e:
            return {"status": "error", "message": f"Error viewing logs: {e}"}

    # Include all other methods from original EnsembleManager
    # but inherit their implementation for now
    def get_ensemble_files(self) -> List[Tuple[int, Path]]:
        """Get all ensemble files with their indices"""
        self._ensure_directories()
        files = sorted(self.base_dir.rglob("*"))
        files = [f for f in files if f.is_file()]
        return [(i+1, f) for i, f in enumerate(files)]

    def deploy_ensemble(self, file_path: Path, timeout: int = 60) -> Dict[str, str]:
        """Deploy an ensemble with the specified timeout"""
        try:
            self._ensure_directories()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_message = f"Submitting deployment on {timestamp} for: {file_path}\n"
            
            with open(self.log_dir / "deployments.log", "a") as log:
                log.write(log_message)
                
                result = run_dms_command_with_passphrase(
                    ['nunet', '-c', 'dms', 'actor', 'cmd', '/dms/node/deployment/new',
                     '-t', f"{timeout}s", '-f', str(file_path)],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                success_msg = "Ensemble was submitted successfully.\n"
                log.write(success_msg + result.stdout + "\n")
                
                # Extract deployment ID from output
                deployment_id = None
                for line in result.stdout.split('\n'):
                    if '"EnsembleID":' in line:
                        deployment_id = line.split('"EnsembleID":')[1].strip().strip('"').strip(',').strip('"')
                        break
                
                return {
                    "status": "success",
                    "message": success_msg + result.stdout,
                    "deployment_id": deployment_id
                }
                
        except subprocess.CalledProcessError as e:
            error_msg = f"Ensemble deployment unsuccessful.\nError: {str(e)}\n"
            with open(self.log_dir / "deployments.log", "a") as log:
                log.write(error_msg)
            return {"status": "error", "message": error_msg}

    def get_deployment_status(self, deployment_id: str) -> Dict[str, str]:
        """Get the current status of a deployment"""
        try:
            active_deployments = self.get_active_deployments()
            deployment = active_deployments.get(deployment_id)
            if deployment:
                status_norm = str(deployment.get('status', 'unknown')).lower()
                message_map = {
                    'running': 'Deployment is currently running',
                    'pending': 'Deployment is pending or shutting down',
                    'completed': 'Deployment completed or was shut down',
                    'failed': 'Deployment failed',
                    'unknown': 'Deployment status is unknown',
                }
                response = {
                    'status': 'success',
                    'deployment_status': status_norm,
                    'message': message_map.get(status_norm, message_map['unknown']),
                }
                status_detail = deployment.get('status_raw')
                if status_detail:
                    response['status_detail'] = status_detail
                return response

            historical = self.parse_deployment_log()
            if deployment_id in historical:
                deployment_info = historical[deployment_id]
                status_norm = 'completed' if deployment_info.get('status') == 'Submitted' else 'failed'
                return {
                    'status': 'success',
                    'deployment_status': status_norm,
                    'message': 'Deployment completed successfully' if status_norm == 'completed' else 'Deployment failed',
                }

            return {
                'status': 'error',
                'message': f'Deployment {deployment_id} not found',
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Error getting deployment status: {str(e)}',
            }

    def get_deployment_manifest_text(self, deployment_id: str) -> Dict[str, str]:
        """Get the raw manifest as formatted text for web display"""
        try:
            result = self.view_manifest(deployment_id)
            if result["status"] == "success":
                return {
                    "status": "success",
                    "manifest_text": result["message"]
                }
            else:
                return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error getting deployment manifest: {str(e)}"
            }

    def get_deployment_logs_text(self, deployment_id: str) -> Dict[str, str]:
        """Get combined logs as formatted text for web display"""
        try:
            result = self.view_logs(deployment_id)
            if result["status"] == "success":
                return {
                    "status": "success",
                    "logs_text": result["message"]
                }
            else:
                return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error getting deployment logs: {str(e)}"
            }

    def get_deployments_for_web(self) -> Dict[str, Any]:
        """Get all deployments in a format suitable for web API consumption"""
        try:
            active_deployments = self.get_active_deployments()
            historical = self.parse_deployment_log()

            deployments: List[Dict[str, Any]] = []
            seen: set[str] = set()
            now = datetime.now()

            for deployment_id, meta in active_deployments.items():
                seen.add(deployment_id)
                status_norm = str(meta.get('status', 'unknown')).lower()
                log_info = historical.get(deployment_id)
                timestamp = meta.get('timestamp') or (log_info.get('timestamp') if log_info else None) or now
                ensemble_file = meta.get('ensemble_file') or (log_info.get('file_name') if log_info else None) or 'Active deployment'
                if isinstance(ensemble_file, Path):
                    ensemble_file = str(ensemble_file)
                if isinstance(ensemble_file, str):
                    ensemble_label = os.path.basename(ensemble_file) or ensemble_file
                else:
                    ensemble_label = str(ensemble_file)

                deployments.append({
                    'id': deployment_id,
                    'status': status_norm,
                    'type': 'active' if status_norm in ('running', 'pending') else 'historical',
                    'timestamp': timestamp,
                    'ensemble_file': ensemble_label,
                })

            for deployment_id, info in historical.items():
                if deployment_id in seen:
                    continue
                status_norm = 'completed' if info.get('status') == 'Submitted' else str(info.get('status', 'failed')).lower()
                deployments.append({
                    'id': deployment_id,
                    'status': status_norm,
                    'type': 'historical',
                    'timestamp': info['timestamp'],
                    'ensemble_file': os.path.basename(info.get('file_name', 'Unknown')),
                })

            deployments.sort(key=lambda item: item.get('timestamp') or datetime.min, reverse=True)

            formatted: List[Dict[str, Any]] = []
            for item in deployments:
                ts = item.get('timestamp')
                if isinstance(ts, datetime):
                    ts_value = ts.isoformat()
                elif ts:
                    ts_value = str(ts)
                else:
                    ts_value = datetime.now().isoformat()
                formatted.append({
                    'id': item['id'],
                    'status': item['status'],
                    'type': item['type'],
                    'timestamp': ts_value,
                    'ensemble_file': item['ensemble_file'],
                })

            return {
                'status': 'success',
                'deployments': formatted,
                'count': len(formatted),
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f"Error getting deployments: {str(e)}",
                'deployments': [],
                'count': 0,
            }

    def manage_deployment_actions(self, deployment_id: str, deployment_type: str):
        """Handle actions for a selected deployment"""
        while True:
            print("\nDeployment Actions:")
            print_menu_option(1, "View Manifest", "📄")
            print_menu_option(2, "View Logs", "📋")
            if deployment_type != "deployment_log":
                print_menu_option(3, "Shutdown Ensemble", "🛑")
            print_menu_option(0, "Back to deployment list", "🔙")
            
            choice = input("\nChoose an action: ")
            
            if choice == "1":
                result = self.view_manifest(deployment_id)
                print(result["message"])
                input("\nPress Enter to continue...")
            elif choice == "2":
                result = self.view_logs(deployment_id)
                print(result["message"])
                input("\nPress Enter to continue...")
            elif choice == "3" and deployment_type != "deployment_log":
                result = self.shutdown_deployment(deployment_id)
                print(result["message"])
                break  # Return to deployment list after shutdown
            elif choice == "0":
                break
            else:
                print(f"{Colors.RED}Invalid action{Colors.NC}")

    def show_deployments_menu(self):
        """Show deployments and handle ensemble actions"""
        # Get and display current deployments
        result = self.view_running_ensembles()
        print("\nCurrent Deployments:")
        print(result["message"])
        
        print("\nOptions:")
        if result["count"] > 0:
            print_menu_option(1, "Select an ensemble", "🎯")
        print_menu_option(2, "Deploy new ensemble", "🚀")
        print_menu_option(3, "Refresh list", "🔄")
        print_menu_option(0, "Return to main menu", "🔙")
        
        choice = input("\nSelect an option: ")
        return {"status": "success", "message": "", "choice": choice, "deployments": result}

    def handle_ensemble_selection(self, deployments):
        """Handle ensemble selection and actions"""
        dep_num = input(f"\nEnter ensemble number (1-{deployments['count']}) or 0 to cancel: ")
        try:
            if dep_num == "0":
                return {"status": "cancelled", "message": ""}
                
            idx = int(dep_num) - 1
            if 0 <= idx < deployments['count']:
                selected_id, info = deployments["items"][idx]
                print(f"\nSelected ensemble: {selected_id}")
                print("\nEnsemble Actions:")
                print_menu_option(1, "View manifest", "📄")
                print_menu_option(2, "View logs", "📋")
                if info["type"] != "deployment_log":
                    print_menu_option(3, "Shutdown ensemble", "🛑")
                print_menu_option(0, "Back", "🔙")
                
                action = input("\nSelect action: ")
                if action == "1":
                    return self.view_manifest(selected_id)
                elif action == "2":
                    return self.view_logs(selected_id)
                elif action == "3" and info["type"] != "deployment_log":
                    return self.shutdown_deployment(selected_id)
                elif action == "0":
                    return {"status": "cancelled", "message": ""}
                else:
                    return {"status": "error", "message": "Invalid action"}
            else:
                return {"status": "error", "message": "Invalid ensemble number"}
        except ValueError:
            return {"status": "error", "message": "Invalid input"}

    def deploy_ensemble_menu(self) -> None:
        """Enhanced menu for deploying ensembles"""
        while True:
            print_header("Deploy Ensemble")
            
            # Get list of ensembles
            ensembles = self.get_ensemble_files()
            
            if not ensembles:
                print("\nNo ensemble templates found.")
                print("\nOptions:")
                print_menu_option(1, "Download example ensembles")
                print_menu_option(2, "Back to main menu")
                
                choice = input("\nEnter your choice (1-2): ")
                
                if choice == "1":
                    result = self.download_example_ensembles()
                    print(f"\n{result['message']}")
                    pause()
                elif choice == "2":
                    break
                continue
            
            # Display ensembles
            print("\nAvailable ensemble templates:")
            for idx, path in ensembles:
                print(f"{idx}. {path.name}")
            
            print("\nOptions:")
            print_menu_option(1, "Deploy ensemble")
            print_menu_option(2, "Back to main menu")
            
            choice = input("\nEnter your choice (1-2): ")
            
            if choice == "2":
                break
            
            if choice == "1":
                file_idx = input("\nEnter ensemble number: ")
                try:
                    file_idx = int(file_idx)
                    if 1 <= file_idx <= len(ensembles):
                        _, file_path = ensembles[file_idx - 1]
                        
                        timeout = input("\nEnter deployment timeout in seconds (default: 60): ")
                        try:
                            timeout = int(timeout) if timeout else 60
                        except ValueError:
                            timeout = 60
                            print("\nInvalid timeout value, using default (60 seconds)")
                        
                        result = self.deploy_ensemble(file_path, timeout)
                        print(f"\n{result['message']}")
                        pause()
                    else:
                        print("\nInvalid ensemble number")
                        pause()
                except ValueError:
                    print("\nInvalid input")
                    pause()

    def shutdown_deployment(self, deployment_id: str) -> Dict[str, str]:
        """Shutdown a running deployment"""
        try:
            command = ['nunet', '-c', 'dms', 'actor', 'cmd', '/dms/node/deployment/shutdown',
                      '-i', deployment_id]
            print(f"\nExecuting command: {' '.join(command)}")
            
            result = run_dms_command_with_passphrase(
                command,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                return {"status": "success", "message": f"Successfully shutdown deployment {deployment_id}"}
            else:
                error_msg = f"Error shutting down deployment:\n"
                if result.stdout:
                    error_msg += f"Output: {result.stdout}\n"
                if result.stderr:
                    error_msg += f"Error: {result.stderr}"
                return {"status": "error", "message": error_msg}
            
        except Exception as e:
            return {"status": "error", "message": f"Unexpected error shutting down deployment: {e}"}

    def get_deployment_allocations(self, deployment_id: str) -> Dict[str, str]:
        """Get allocations for a deployment from its manifest"""
        try:
            result = run_dms_command_with_passphrase(
                ['nunet', '-c', 'dms', 'actor', 'cmd', '/dms/node/deployment/manifest',
                 '-i', deployment_id],
                capture_output=True,
                text=True,
                check=True
            )
            manifest = json.loads(result.stdout)
            return list(manifest.get('manifest', {}).get('allocations', {}).keys())
        except Exception as e:
            print(f"Error getting allocations: {e}")
            return []

    def edit_ensemble(self, file_path: Path) -> Dict[str, str]:
        """Open ensemble file in the default editor and return new contents."""
        try:
            editor = os.environ.get('EDITOR', 'nano')
            subprocess.run([editor, str(file_path)], check=True)
            with open(file_path, 'r') as f:
                content = f.read()
            return {
                "status": "success",
                "message": f"File updated. New contents:\n{content}"
            }
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": f"Error editing file: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": f"Error: {str(e)}"}

    def copy_ensemble(self, source: Path, dest: Path) -> Dict[str, str]:
        """Copy an ensemble file to a new location."""
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            return {
                "status": "success",
                "message": f"File copied from {source.name} to {dest}"
            }
        except Exception as e:
            return {"status": "error", "message": f"Error copying file: {str(e)}"}

    def download_example_ensembles(
        self,
        repo: str = "nunet/solutions/nunet-appliance",
        branch: str = None,
        source_dir: str = "ensembles/examples",
        target_dir: Optional[Path] = None
    ) -> Dict[str, str]:
        """Download example ensembles from a Git repository."""
        self._ensure_directories()
        target_dir = target_dir or self.base_dir

        try:
            if branch is None:
                branch = get_current_branch()

            temp_dir = Path("/tmp/nunet-examples")
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

            clone_result = subprocess.run(
                ['git', 'clone', '-b', branch, f'https://gitlab.com/{repo}.git', str(temp_dir)],
                capture_output=True,
                text=True
            )

            if clone_result.returncode != 0:
                return {"status": "error", "message": f"Git clone failed: {clone_result.stderr}"}

            source_path = temp_dir / source_dir
            if not source_path.exists():
                return {
                    "status": "error",
                    "message": f"Source directory {source_dir} not found in repository"
                }

            files_copied = 0
            for item in source_path.glob("*"):
                if item.is_file():
                    shutil.copy2(item, target_dir)
                    files_copied += 1
                else:
                    shutil.copytree(item, target_dir / item.name, dirs_exist_ok=True)
                    files_copied += 1

            shutil.rmtree(temp_dir)

            if files_copied == 0:
                return {
                    "status": "warning",
                    "message": f"No files found to copy in {source_dir}"
                }

            return {
                "status": "success",
                "message": f"Successfully copied {files_copied} items to {target_dir}"
            }

        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": f"Git operation failed: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": f"Error downloading examples: {str(e)}"}

    def edit_ensemble_menu(self):
        ensembles = self.get_ensemble_files()
        if not ensembles:
            print(f"{Colors.RED}No ensemble templates available.{Colors.NC}")
            return
        for idx, file_path in ensembles:
            print(f"{idx:3d}) {file_path.relative_to(self.base_dir)}")
        try:
            file_number = int(input("Enter the number of the ensemble to edit: "))
            if file_number < 1 or file_number > len(ensembles):
                print(f"{Colors.RED}Invalid selection.{Colors.NC}")
                return
            selected_file = ensembles[file_number - 1][1]
            result = self.edit_ensemble(selected_file)
            print(result['message'])
        except ValueError:
            print(f"{Colors.RED}Invalid input.{Colors.NC}")

    def copy_ensemble_menu(self):
        ensembles = self.get_ensemble_files()
        if not ensembles:
            print(f"{Colors.RED}No ensemble templates available.{Colors.NC}")
            return
        for idx, file_path in ensembles:
            print(f"{idx:3d}) {file_path.relative_to(self.base_dir)}")
        try:
            file_number = int(input("Enter the number of the ensemble to copy: "))
            if file_number < 1 or file_number > len(ensembles):
                print(f"{Colors.RED}Invalid selection.{Colors.NC}")
                return
            selected_file = ensembles[file_number - 1][1]
            dest_path = input("Enter the destination path (relative to ~/ensembles): ")
            dest_file = self.base_dir / dest_path
            result = self.copy_ensemble(selected_file, dest_file)
            print(result['message'])
        except ValueError:
            print(f"{Colors.RED}Invalid input.{Colors.NC}")

    def download_examples_menu(self):
        print(f"{Colors.CYAN}Downloading example ensembles from the NuNet repository...{Colors.NC}")
        result = self.download_example_ensembles()
        print(f"{Colors.GREEN if result['status'] == 'success' else Colors.RED}[{result['status'].upper()}]{Colors.NC} {result['message']}")

        # List what was downloaded if successful
        if result['status'] == 'success':
            target_dir = self.base_dir
            print(f"\n{Colors.YELLOW}Downloaded files and directories:{Colors.NC}")
            for item in sorted(target_dir.iterdir()):
                if item.is_file():
                    print(f"  [File] {item.name}")
                elif item.is_dir():
                    print(f"  [Dir]  {item.name}")
        input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.NC}")

    def delete_ensemble_menu(self):
        ensembles = self.get_ensemble_files()
        if not ensembles:
            print(f"{Colors.RED}No ensemble templates available.{Colors.NC}")
            return
        for idx, file_path in ensembles:
            print(f"{idx:3d}) {file_path.relative_to(self.base_dir)}")
        try:
            file_number = int(input("Enter the number of the ensemble to delete: "))
            if file_number < 1 or file_number > len(ensembles):
                print(f"{Colors.RED}Invalid selection.{Colors.NC}")
                return
            selected_file = ensembles[file_number - 1][1]
            confirm = input(f"Are you sure you want to delete '{selected_file.name}'? [y/N]: ").lower()
            if confirm == 'y':
                try:
                    selected_file.unlink()
                    print(f"File {selected_file.name} deleted successfully")
                except Exception as e:
                    print(f"Error deleting file: {str(e)}")
            else:
                print("Deletion cancelled.")
        except ValueError:
            print(f"{Colors.RED}Invalid input.{Colors.NC}")

    def show_help(self):
        print(f"""{Colors.CYAN}
Enhanced Ensemble Manager Help
-----------------------------
- This enhanced ensemble manager allows you to check the status of your deployments and to view the manifest / logs of your deployments.  Note: this is a beta version and some features may not work as expected. 

- The table above shows a list of deployments the appliance knows about ordered by the most recent deployment.

- The Type Column will show a Type of active for any deployments that DMS knows about and type of historical if the appliance 
  has a record of a deployment (the deployment was requested via this menu). 

- The Status Column will show the status of the deployment as failed if DMS does not have a record of the deployment. 
  The reason we do this is because if a deployment fails, DMS will not store it (bug) so we currently show all deployments
  that DMS does not know about as failed.  This is so you can easily see failed deployments.  Just be aware that this will also show deployments that were
  successfully deployed but that DMS doesnt have info for anymore as failed.  This is a bug and will be fixed in a future version.

- The list of the deployments does not auto refresh so use option 3 to refresh the list to get the latest status of your deployments.

- Option 1 has a submenu to select an ensemble to view the details of any active deployments and to request the logs of any active deployments.
  Note: the logs are stored for later review but they are not stored by default by DMS you have to manually request them in the submenu.

- You can deploy, edit, copy, and manage your ensemble templates.
- Use 'Download example ensembles' to get started with sample templates.
- We suggest you copy templates before you edit to customize your deployments as if you edit the defaults they will be overwritten by the next update.
- Use 'Deploy' to launch an ensemble on the network. (you will need to be granted access by an organization to do so) You can launch an ensemble on your own node
  without being granted access by an organization but you need to configure your capabilites and we suggest you target yourself (using your peerid) 
  in the ensemble file.  There are some examples you can use, and there is a menu option comming soon to automate this, stay tuned.
{Colors.NC}""")

    def toggle_help(self):
        self.show_help_message = not self.show_help_message
        state = "ON" if self.show_help_message else "OFF"
        print(f"{Colors.CYAN}Help message is now {state}.{Colors.NC}")
