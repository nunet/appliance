"""
Ensemble utilities module for NuNet Appliance
Handles ensemble directory scanning, metadata loading, and YAML processing
"""

import os
import json
import yaml
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import logging
import jinja2

logger = logging.getLogger(__name__)

def is_resource_field(field_name: str) -> bool:
    """
    Check if a field name represents a resource field based on hierarchical naming
    
    Args:
        field_name: The field name to check
        
    Returns:
        True if the field is a resource field, False otherwise
    """
    return field_name.startswith('allocations_') and '_resources_' in field_name

def get_field_category(field_name: str, field_config: Dict[str, Any]) -> str:
    """
    Get the category for a field, either from explicit category or inferred from name
    
    Args:
        field_name: The field name
        field_config: The field configuration dictionary
        
    Returns:
        Category string for the field
    """
    # Check for explicit category in field config
    if 'category' in field_config:
        return field_config['category']
    
    # Infer category from field name
    if is_resource_field(field_name):
        return 'resources'
    
    return 'general'

def parse_hierarchical_field_name(field_name: str) -> Dict[str, str]:
    """
    Parse hierarchical field names to extract allocation and resource information
    
    Args:
        field_name: The hierarchical field name (e.g., 'allocations_alloc1_resources_cpu_cores')
        
    Returns:
        Dictionary with parsed components
    """
    parts = field_name.split('_')
    result = {
        'allocation_id': None,
        'resource_type': None,
        'resource_property': None,
        'is_resource': False
    }
    
    if len(parts) >= 4 and parts[0] == 'allocations':
        result['allocation_id'] = parts[1]
        if parts[2] == 'resources' and len(parts) >= 4:
            result['is_resource'] = True
            result['resource_type'] = parts[3]
            if len(parts) > 4:
                result['resource_property'] = '_'.join(parts[4:])
    
    return result

def generate_categorized_fields(metadata: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Generate categorized fields for UI rendering with hierarchical information
    
    Args:
        metadata: Ensemble metadata with field definitions
        
    Returns:
        Dictionary with categories as keys and lists of field configs as values
    """
    if 'fields' not in metadata:
        return {}
    
    categories = {}
    
    for field_name, field_config in metadata['fields'].items():
        category = get_field_category(field_name, field_config)
        
        if category not in categories:
            categories[category] = []
        
        # Add hierarchical parsing information
        field_info = {
            'name': field_name,
            'config': field_config,
            'hierarchical': parse_hierarchical_field_name(field_name)
        }
        
        categories[category].append(field_info)
    
    return categories

def generate_form_html(metadata: Dict[str, Any]) -> str:
    """
    Generate HTML form with collapsible resource sections
    
    Args:
        metadata: Ensemble metadata with field definitions
        
    Returns:
        HTML string for the form
    """
    categories = generate_categorized_fields(metadata)
    
    html_parts = []
    
    # General fields first
    if 'general' in categories:
        html_parts.append('<div class="form-section">')
        html_parts.append('<h5>General Configuration</h5>')
        for field_info in categories['general']:
            html_parts.append(generate_field_html(field_info))
        html_parts.append('</div>')
    
    # Resource fields in collapsible section
    if 'resources' in categories:
        html_parts.append('<div class="form-section">')
        html_parts.append('<div class="resource-section">')
        html_parts.append('<h5 class="resource-header" onclick="toggleResourceSection()">')
        html_parts.append('<i class="bi bi-chevron-down" id="resourceChevron"></i>')
        html_parts.append('Resource Configuration')
        html_parts.append('</h5>')
        html_parts.append('<div class="resource-fields" id="resourceFields">')
        for field_info in categories['resources']:
            html_parts.append(generate_field_html(field_info))
        html_parts.append('</div>')
        html_parts.append('</div>')
        html_parts.append('</div>')
    
    return '\n'.join(html_parts)

def generate_field_html(field_info: Dict[str, Any]) -> str:
    """
    Generate HTML for a single form field
    
    Args:
        field_info: Field information dictionary
        
    Returns:
        HTML string for the field
    """
    field_name = field_info['name']
    config = field_info['config']
    field_type = config.get('type', 'text')
    
    html_parts = []
    html_parts.append(f'<div class="form-field">')
    html_parts.append(f'<label for="{field_name}" class="form-label">{config.get("label", field_name)}</label>')
    
    if field_type == 'text':
        html_parts.append(f'<input type="text" class="form-control" id="{field_name}" name="{field_name}"')
        if 'placeholder' in config:
            html_parts.append(f' placeholder="{config["placeholder"]}"')
        if 'default' in config:
            html_parts.append(f' value="{config["default"]}"')
        html_parts.append('>')
    
    elif field_type == 'number':
        html_parts.append(f'<input type="number" class="form-control" id="{field_name}" name="{field_name}"')
        if 'min' in config:
            html_parts.append(f' min="{config["min"]}"')
        if 'max' in config:
            html_parts.append(f' max="{config["max"]}"')
        if 'step' in config:
            html_parts.append(f' step="{config["step"]}"')
        if 'default' in config:
            html_parts.append(f' value="{config["default"]}"')
        html_parts.append('>')
    
    elif field_type == 'select':
        html_parts.append(f'<select class="form-control" id="{field_name}" name="{field_name}">')
        for option in config.get('options', []):
            selected = 'selected' if option.get('value') == config.get('default') else ''
            html_parts.append(f'<option value="{option["value"]}" {selected}>{option["label"]}</option>')
        html_parts.append('</select>')
    
    elif field_type == 'textarea':
        html_parts.append(f'<textarea class="form-control" id="{field_name}" name="{field_name}" rows="3">')
        if 'default' in config:
            html_parts.append(config['default'])
        html_parts.append('</textarea>')
    
    if 'description' in config:
        html_parts.append(f'<div class="form-text">{config["description"]}</div>')
    
    html_parts.append('</div>')
    
    return '\n'.join(html_parts)

def scan_ensembles_directory(base_path: str = "/home/ubuntu/ensembles") -> Dict[str, List[Dict[str, str]]]:
    """
    Recursively scan the ensembles directory and return a structured dictionary of categories and ensembles
    
    Args:
        base_path: Path to the ensembles directory
        
    Returns:
        Dictionary with categories as keys and lists of ensemble info as values
    """
    try:
        base_path = Path(base_path)
        if not base_path.exists():
            logger.warning(f"Ensembles directory does not exist: {base_path}")
            return {}
        
        categories = {}
        
        # Scan for category directories
        for category_dir in base_path.iterdir():
            if category_dir.is_dir():
                category_name = category_dir.name
                ensembles = []
                
                # Scan for YAML files in the category directory
                for yaml_file in category_dir.glob("*.yaml"):
                    ensemble_info = {
                        "name": yaml_file.stem,  # filename without extension
                        "path": str(yaml_file),
                        "category": category_name,
                        "filename": yaml_file.name
                    }
                    
                    # Try to load metadata if it exists
                    metadata_path = yaml_file.with_suffix('.json')
                    if metadata_path.exists():
                        try:
                            with open(metadata_path, 'r') as f:
                                metadata = json.load(f)
                                ensemble_info["metadata"] = metadata
                                
                                # Categorize fields for UI grouping
                                if 'fields' in metadata:
                                    field_categories = {}
                                    for field_name, field_config in metadata['fields'].items():
                                        category = get_field_category(field_name, field_config)
                                        if category not in field_categories:
                                            field_categories[category] = []
                                        field_categories[category].append(field_name)
                                    ensemble_info["field_categories"] = field_categories
                        except Exception as e:
                            logger.warning(f"Failed to load metadata for {yaml_file}: {e}")
                    
                    ensembles.append(ensemble_info)
                
                if ensembles:
                    categories[category_name] = ensembles
        
        return categories
        
    except Exception as e:
        logger.error(f"Error scanning ensembles directory: {e}")
        return {}

def load_ensemble_metadata(ensemble_path: str) -> Optional[Dict[str, Any]]:
    """
    Load and validate JSON metadata files for ensembles
    
    Args:
        ensemble_path: Path to the ensemble YAML file
        
    Returns:
        Metadata dictionary or None if not found/invalid
    """
    try:
        metadata_path = Path(ensemble_path).with_suffix('.json')
        if not metadata_path.exists():
            logger.info(f"No metadata file found for {ensemble_path}")
            return None
        
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        # Validate required fields
        required_fields = ['name', 'description', 'fields']
        for field in required_fields:
            if field not in metadata:
                logger.warning(f"Missing required field '{field}' in metadata for {ensemble_path}")
                return None
        
        return metadata
        
    except Exception as e:
        logger.error(f"Error loading metadata for {ensemble_path}: {e}")
        return None

def process_yaml_template(yaml_path: str, form_values: Dict[str, Any], deployment_type: str = "local") -> Optional[str]:
    """
    Replace placeholders in YAML templates with user-provided values using Jinja2
    
    Args:
        yaml_path: Path to the YAML template file
        form_values: Dictionary of form field values
        deployment_type: Type of deployment ("local", "targeted", "non_targeted")
        
    Returns:
        Processed YAML content as string or None if error
    """
    try:
        with open(yaml_path, 'r') as f:
            yaml_content = f.read()
        
        # Remove peer_id for non-targeted deployments
        if deployment_type == "non_targeted":
            form_values = {k: v for k, v in form_values.items() if k != 'peer_id'}
        
        # Render with Jinja2 - handles hierarchical variable names automatically
        template = jinja2.Template(yaml_content)
        processed_content = template.render(**form_values)
        
        # For non-targeted deployments, remove the entire peer line
        if deployment_type == "non_targeted":
            import re
            processed_content = re.sub(r'^\s*peer:\s*.*$', '', processed_content, flags=re.MULTILINE)
            processed_content = re.sub(r'\n\s*\n', '\n\n', processed_content)
        
        return processed_content
        
    except Exception as e:
        logger.error(f"Error processing YAML template {yaml_path}: {e}")
        return None

def generate_timestamped_filename(original_name: str) -> str:
    """
    Create timestamped filenames for deployed ensembles
    
    Args:
        original_name: Original ensemble name
        
    Returns:
        Timestamped filename
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{original_name}_{timestamp}.yaml"

def validate_form_data(metadata: Dict[str, Any], form_values: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate user input against the metadata field definitions
    
    Args:
        metadata: Ensemble metadata with field definitions
        form_values: User-provided form values
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    if 'fields' not in metadata:
        return False, ["No field definitions found in metadata"]
    
    fields = metadata['fields']
    
    # Check required fields
    for field_name, field_config in fields.items():
        if field_config.get('required', False):
            if field_name not in form_values or not form_values[field_name]:
                errors.append(f"Field '{field_name}' is required")
    
    # Validate field types and constraints
    for field_name, field_value in form_values.items():
        if field_name not in fields:
            continue  # Skip unknown fields
            
        field_config = fields[field_name]
        field_type = field_config.get('type', 'text')
        
        if not field_value:  # Skip empty values for non-required fields
            continue
            
        # Type validation
        if field_type == 'number':
            try:
                float(field_value)
            except ValueError:
                errors.append(f"Field '{field_name}' must be a number")
        
        elif field_type == 'integer':
            try:
                int(field_value)
            except ValueError:
                errors.append(f"Field '{field_name}' must be an integer")
        
        # Pattern validation
        if 'pattern' in field_config:
            pattern = field_config['pattern']
            if not re.match(pattern, str(field_value)):
                errors.append(f"Field '{field_name}' does not match required pattern")
        
        # Min/max validation for numbers
        if field_type in ['number', 'integer']:
            try:
                num_value = float(field_value) if field_type == 'number' else int(field_value)
                
                if 'min' in field_config and num_value < field_config['min']:
                    errors.append(f"Field '{field_name}' must be at least {field_config['min']}")
                
                if 'max' in field_config and num_value > field_config['max']:
                    errors.append(f"Field '{field_name}' must be at most {field_config['max']}")
                    
            except ValueError:
                pass  # Already caught by type validation
    
    return len(errors) == 0, errors

def save_deployment_instance(template_path: str, processed_content: str, timestamp: str) -> Optional[str]:
    """
    Save the processed YAML with timestamp suffix
    
    Args:
        template_path: Path to the original template
        processed_content: Processed YAML content
        timestamp: Timestamp string for the filename
        
    Returns:
        Path to the saved file or None if error
    """
    try:
        template_path = Path(template_path)
        original_name = template_path.stem
        timestamped_name = f"{original_name}_{timestamp}.yaml"
        
        # Save to the correct appliance deployments directory
        deployments_dir = Path("/home/ubuntu/nunet/appliance/deployments")
        deployments_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = deployments_dir / timestamped_name
        
        with open(output_path, 'w') as f:
            f.write(processed_content)
        
        logger.info(f"Saved deployment instance to {output_path}")
        return str(output_path)
        
    except Exception as e:
        logger.error(f"Error saving deployment instance: {e}")
        return None

def get_ensemble_categories() -> List[str]:
    """
    Get list of available ensemble categories
    
    Returns:
        List of category names
    """
    categories = scan_ensembles_directory()
    return list(categories.keys())

def get_ensembles_by_category(category: str) -> List[Dict[str, str]]:
    """
    Get all ensembles in a specific category
    
    Args:
        category: Category name
        
    Returns:
        List of ensemble info dictionaries
    """
    categories = scan_ensembles_directory()
    return categories.get(category, [])

def get_local_peer_id(dms_manager=None) -> Optional[str]:
    """
    Get the local peer ID from DMS using existing DMS manager
    
    Args:
        dms_manager: Optional DMS manager instance
        
    Returns:
        Local peer ID or None if not available
    """
    try:
        if dms_manager is None:
            # Try to get DMS manager from web manager if available
            from modules.onboarding_manager import OnboardingManager
            onboarding_manager = OnboardingManager()
            dms_manager = onboarding_manager.dms_manager
        
        peer_info = dms_manager.get_self_peer_info()
        return peer_info.get('peer_id')
        
    except Exception as e:
        logger.error(f"Error getting local peer ID: {e}")
        return None

def get_known_peers(dms_manager=None) -> List[Dict[str, str]]:
    """
    Get list of known peers from DMS using existing DMS manager
    
    Args:
        dms_manager: Optional DMS manager instance
        
    Returns:
        List of peer dictionaries with id and name
    """
    try:
        if dms_manager is None:
            # Try to get DMS manager from web manager if available
            from modules.onboarding_manager import OnboardingManager
            onboarding_manager = OnboardingManager()
            dms_manager = onboarding_manager.dms_manager
        
        peers_json = dms_manager.view_peer_details()
        peers_list = []
        
        if peers_json["status"] == "success":
            import re, json
            ANSI_RE = re.compile(r'\x1B\[[0-9;]*m')
            clean_str = ANSI_RE.sub('', peers_json["message"])  # remove colour codes
            try:
                peers_data = json.loads(clean_str)
                peers = peers_data.get("Peers", [])
                
                # Convert to list of dictionaries
                for peer in peers:
                    if isinstance(peer, dict):
                        peers_list.append({
                            'id': peer.get('ID', ''),
                            'name': peer.get('Name', peer.get('ID', 'Unknown'))
                        })
                    elif isinstance(peer, str):
                        peers_list.append({
                            'id': peer,
                            'name': peer
                        })
            except Exception as e:
                logger.error(f"Peer-JSON parse error: {e}")
        
        return peers_list
        
    except Exception as e:
        logger.error(f"Error getting known peers: {e}")
        return []

def get_deployment_options(dms_manager=None) -> Dict[str, Any]:
    """
    Get deployment options including local peer ID and known peers
    
    Args:
        dms_manager: Optional DMS manager instance
        
    Returns:
        Dictionary with deployment options
    """
    return {
        'local_peer_id': get_local_peer_id(dms_manager),
        'known_peers': get_known_peers(dms_manager),
        'deployment_types': [
            {'value': 'local', 'label': 'Deploy Locally', 'description': 'Deploy to this appliance'},
            {'value': 'targeted', 'label': 'Targeted Deployment', 'description': 'Deploy to a specific peer'},
            {'value': 'non_targeted', 'label': 'Non-Targeted Deployment', 'description': 'Let the network decide'}
        ]
    } 