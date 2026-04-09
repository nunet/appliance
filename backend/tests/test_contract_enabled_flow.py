"""
Tests for the Contract-Enabled Onboarding Flow

These tests validate the two-phase capability granting process:
- Phase 1: Contract capabilities
- Phase 2: Contract creation
- Phase 3: Contract signing
- Phase 4: Deployment capabilities
- Phase 5: Deployment test

Run with: pytest backend/tests/test_contract_enabled_flow.py -v
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_onboarding_manager():
    """Create a mock OnboardingManager for testing."""
    from backend.modules.onboarding_manager import OnboardingManager
    
    with patch.object(OnboardingManager, '_load_state') as mock_load:
        mock_load.return_value = OnboardingManager._baseline_state()
        mgr = OnboardingManager(use_mock_api=True)
        yield mgr


@pytest.fixture
def mock_state_with_org():
    """Create a state dict with organization data."""
    state = {
        "step": "pending_authorization",
        "progress": 55,
        "org_data": {
            "did": "did:key:z6MknaPMu6ju2PNYWQ3wnshnLA8erLb5sauVgTtY7Ni18VyR",
            "name": "NuTestNet",
        },
        "form_data": {
            "email": "test@example.com",
            "name": "Test User",
            "roles": ["compute_provider"],
        },
        "request_id": "test-request-123",
        "status_token": "test-token-456",
        "api_status": None,
        "contract_caps_applied": False,
        "deployment_caps_applied": False,
        "contract_signed": False,
        "seen_contract_dids": [],
    }
    return state


# =============================================================================
# Tests - State Baseline
# =============================================================================

class TestBaselineState:
    """Test that baseline state includes contract-enabled fields."""

    def test_baseline_state_has_contract_caps_applied(self):
        """Baseline state should have contract_caps_applied field."""
        from backend.modules.onboarding_manager import OnboardingManager
        state = OnboardingManager._baseline_state()
        assert "contract_caps_applied" in state
        assert state["contract_caps_applied"] is False

    def test_baseline_state_has_deployment_caps_applied(self):
        """Baseline state should have deployment_caps_applied field."""
        from backend.modules.onboarding_manager import OnboardingManager
        state = OnboardingManager._baseline_state()
        assert "deployment_caps_applied" in state
        assert state["deployment_caps_applied"] is False

    def test_baseline_state_has_contract_signed(self):
        """Baseline state should have contract_signed field."""
        from backend.modules.onboarding_manager import OnboardingManager
        state = OnboardingManager._baseline_state()
        assert "contract_signed" in state
        assert state["contract_signed"] is False

    def test_baseline_state_has_seen_contract_dids(self):
        """Baseline state should have seen_contract_dids field."""
        from backend.modules.onboarding_manager import OnboardingManager
        state = OnboardingManager._baseline_state()
        assert "seen_contract_dids" in state
        assert state["seen_contract_dids"] == []


# =============================================================================
# Tests - API Methods
# =============================================================================

class TestAPIConfirmCaps:
    """Test api_confirm_caps method."""

    def test_api_confirm_caps_mock_mode(self, mock_onboarding_manager):
        """api_confirm_caps should work in mock mode."""
        result = mock_onboarding_manager.api_confirm_caps(
            "test-id", "test-token", "contract"
        )
        assert result["status"] == "success"

    def test_api_confirm_caps_accepts_contract_type(self, mock_onboarding_manager):
        """api_confirm_caps should accept 'contract' cap_type."""
        result = mock_onboarding_manager.api_confirm_caps(
            "test-id", "test-token", "contract"
        )
        assert result is not None

    def test_api_confirm_caps_accepts_deployment_type(self, mock_onboarding_manager):
        """api_confirm_caps should accept 'deployment' cap_type."""
        result = mock_onboarding_manager.api_confirm_caps(
            "test-id", "test-token", "deployment"
        )
        assert result is not None


class TestAPIContractReceived:
    """Test api_contract_received method."""

    def test_api_contract_received_mock_mode(self, mock_onboarding_manager):
        """api_contract_received should work in mock mode."""
        result = mock_onboarding_manager.api_contract_received(
            "test-id", "test-token"
        )
        assert result["status"] == "success"


class TestAPIContractSigned:
    """Test api_contract_signed method."""

    def test_api_contract_signed_mock_mode(self, mock_onboarding_manager):
        """api_contract_signed should work in mock mode."""
        result = mock_onboarding_manager.api_contract_signed(
            "test-id", "test-token"
        )
        assert result["status"] == "success"


# =============================================================================
# Tests - Capability Application
# =============================================================================

class TestApplyContractCapabilities:
    """Test apply_contract_capabilities method."""

    def test_apply_contract_capabilities_requires_org_did(self, mock_onboarding_manager):
        """apply_contract_capabilities should fail without org_did."""
        mock_onboarding_manager.state = {"org_data": None}
        result = mock_onboarding_manager.apply_contract_capabilities("test-token")
        assert result is False

    @patch('backend.modules.onboarding_manager.run_dms_command_with_passphrase')
    def test_apply_contract_capabilities_calls_anchor(
        self, mock_run_cmd, mock_onboarding_manager
    ):
        """apply_contract_capabilities should anchor the provide token."""
        mock_onboarding_manager.state = {
            "org_data": {"did": "did:key:test"},
            "form_data": {"roles": ["compute_provider"]},
        }
        mock_run_cmd.return_value = Mock(
            returncode=0, stdout="success", stderr=""
        )
        
        # Mock restart_dms_service
        with patch.object(mock_onboarding_manager, 'restart_dms_service', return_value=True):
            with patch.object(mock_onboarding_manager, 'generate_and_apply_require_token', return_value=True):
                with patch.object(mock_onboarding_manager, 'copy_capability_tokens_to_dms_user', return_value=True):
                    result = mock_onboarding_manager.apply_contract_capabilities("test-token")
        



        
        # Should have called anchor command
        assert mock_run_cmd.called


class TestApplyDeploymentCapabilities:
    """Test apply_deployment_capabilities method."""

    def test_apply_deployment_capabilities_requires_org_did(self, mock_onboarding_manager):
        """apply_deployment_capabilities should fail without org_did."""
        mock_onboarding_manager.state = {"org_data": None}
        result = mock_onboarding_manager.apply_deployment_capabilities("test-token")
        assert result is False

    @patch('backend.modules.onboarding_manager.run_dms_command_with_passphrase')
    def test_apply_deployment_capabilities_writes_certificates(
        self, mock_run_cmd, mock_onboarding_manager
    ):
        """apply_deployment_capabilities should write certificates."""
        mock_onboarding_manager.state = {
            "org_data": {"did": "did:key:test"},
            "form_data": {"roles": ["compute_provider"]},
        }
        mock_run_cmd.return_value = Mock(
            returncode=0, stdout="success", stderr=""
        )
        
        certificates = {
            "client_crt": "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
            "client_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
            "infra_bundle_crt": "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        }
        
        with patch.object(mock_onboarding_manager, 'restart_dms_service', return_value=True):
            with patch.object(mock_onboarding_manager, 'generate_and_apply_require_token', return_value=True):
                with patch.object(mock_onboarding_manager, '_write_certificates') as mock_write:
                    with patch.object(mock_onboarding_manager, '_configure_observability'):
                        with patch.object(mock_onboarding_manager, 'copy_capability_tokens_to_dms_user', return_value=True):
                            mock_onboarding_manager.apply_deployment_capabilities(
                                "test-token", certificates, "api-key"
                            )
        
        mock_write.assert_called_once_with(certificates)


# =============================================================================
# Tests - Contract Signing
# =============================================================================

class TestSignContract:
    """Test sign_contract method."""

    @patch('backend.modules.onboarding_manager.run_dms_command_with_passphrase')
    def test_sign_contract_success(self, mock_run_cmd, mock_onboarding_manager):
        """sign_contract should return True on success."""
        mock_run_cmd.return_value = Mock(
            returncode=0, stdout="signed", stderr=""
        )
        
        result = mock_onboarding_manager.sign_contract("did:contract:test")
        assert result is True

    @patch('backend.modules.onboarding_manager.run_dms_command_with_passphrase')
    def test_sign_contract_failure(self, mock_run_cmd, mock_onboarding_manager):
        """sign_contract should return False on failure."""
        mock_run_cmd.return_value = Mock(
            returncode=1, stdout="", stderr="error"
        )
        
        result = mock_onboarding_manager.sign_contract("did:contract:test")
        assert result is False


# =============================================================================
# Tests - Contract Polling
# =============================================================================

class TestPollForContracts:
    """Test poll_for_contracts method."""

    @patch("backend.modules.dms_utils.run_dms_command_with_passphrase")
    def test_poll_for_contracts_returns_none_on_empty(
        self, mock_run_cmd, mock_onboarding_manager
    ):
        """poll_for_contracts should return None when no contracts."""
        mock_run_cmd.return_value = Mock(
            returncode=0, stdout="[]", stderr=""
        )
        mock_onboarding_manager.state = {"seen_contract_dids": []}
        
        result = mock_onboarding_manager.poll_for_contracts("test-id")
        assert result is None

    @patch("backend.modules.dms_utils.run_dms_command_with_passphrase")
    def test_poll_for_contracts_returns_new_contract(
        self, mock_run_cmd, mock_onboarding_manager
    ):
        """poll_for_contracts should return new contracts."""
        contract_data = [{"did": "did:contract:new", "data": {"test": True}}]
        mock_run_cmd.return_value = Mock(
            returncode=0, stdout=json.dumps(contract_data), stderr=""
        )
        mock_onboarding_manager.state = {"seen_contract_dids": []}
        
        result = mock_onboarding_manager.poll_for_contracts("test-id")
        assert result is not None
        assert result["did"] == "did:contract:new"

    @patch("backend.modules.dms_utils.run_dms_command_with_passphrase")
    def test_poll_for_contracts_skips_seen_contracts(
        self, mock_run_cmd, mock_onboarding_manager
    ):
        """poll_for_contracts should skip already seen contracts."""
        contract_data = [{"did": "did:contract:seen", "data": {"test": True}}]
        mock_run_cmd.return_value = Mock(
            returncode=0, stdout=json.dumps(contract_data), stderr=""
        )
        mock_onboarding_manager.state = {"seen_contract_dids": ["did:contract:seen"]}
        
        result = mock_onboarding_manager.poll_for_contracts("test-id")
        assert result is None


# =============================================================================
# Tests - Router Step Definitions
# =============================================================================

class TestRouterStepDefinitions:
    """Test that router has correct step definitions."""

    def test_step_defs_include_contract_steps(self):
        """STEP_DEFS should include contract-enabled flow steps."""
        from backend.nunet_api.routers.organizations import STEP_DEFS
        
        step_ids = [s["id"] for s in STEP_DEFS]
        
        assert "contract_caps_ready" in step_ids
        assert "contract_caps_applied" in step_ids
        assert "contract_created" in step_ids
        assert "contract_received" in step_ids
        assert "contract_signed" in step_ids
        assert "deployment_caps_ready" in step_ids
        assert "deployment_caps_applied" in step_ids

    def test_progress_map_includes_contract_steps(self):
        """PROGRESS_MAP should include contract-enabled flow steps."""
        from backend.nunet_api.routers.organizations import PROGRESS_MAP
        
        assert "contract_caps_ready" in PROGRESS_MAP
        assert "contract_caps_applied" in PROGRESS_MAP
        assert "contract_created" in PROGRESS_MAP
        assert "contract_received" in PROGRESS_MAP
        assert "contract_signed" in PROGRESS_MAP
        assert "deployment_caps_ready" in PROGRESS_MAP
        assert "deployment_caps_applied" in PROGRESS_MAP

    def test_progress_map_has_correct_order(self):
        """PROGRESS_MAP should have increasing progress values."""
        from backend.nunet_api.routers.organizations import PROGRESS_MAP
        
        # Contract flow should progress in order
        assert PROGRESS_MAP["contract_caps_ready"] < PROGRESS_MAP["contract_caps_applied"]
        assert PROGRESS_MAP["contract_caps_applied"] < PROGRESS_MAP["contract_created"]
        assert PROGRESS_MAP["contract_created"] < PROGRESS_MAP["contract_received"]
        assert PROGRESS_MAP["contract_received"] < PROGRESS_MAP["contract_signed"]
        assert PROGRESS_MAP["contract_signed"] < PROGRESS_MAP["deployment_caps_ready"]
        assert PROGRESS_MAP["deployment_caps_ready"] < PROGRESS_MAP["deployment_caps_applied"]


# =============================================================================
# Tests - Status Handling
# =============================================================================

class TestStatusHandling:
    """Test status handling in poll_join endpoint."""

    def test_contract_caps_ready_status_recognized(self):
        """contract_caps_ready should be a recognized status."""
        from backend.nunet_api.routers.organizations import PROGRESS_MAP
        assert "contract_caps_ready" in PROGRESS_MAP

    def test_deployment_caps_ready_status_recognized(self):
        """deployment_caps_ready should be a recognized status."""
        from backend.nunet_api.routers.organizations import PROGRESS_MAP
        assert "deployment_caps_ready" in PROGRESS_MAP

    def test_deployment_test_complete_status_recognized(self):
        """deployment_test_complete should be a recognized status."""
        from backend.nunet_api.routers.organizations import PROGRESS_MAP
        assert "deployment_test_complete" in PROGRESS_MAP


# =============================================================================
# Integration Tests - Full Flow Simulation
# =============================================================================

class TestFullFlowSimulation:
    """Simulate the full contract-enabled flow."""

    def test_status_transition_contract_caps_ready_to_applied(
        self, mock_onboarding_manager, mock_state_with_org
    ):
        """Test transition from contract_caps_ready to contract_caps_applied."""
        mock_onboarding_manager.state = mock_state_with_org
        mock_onboarding_manager.state["api_status"] = "contract_caps_ready"
        
        # Simulate applying contract caps
        with patch.object(mock_onboarding_manager, 'apply_contract_capabilities', return_value=True):
            with patch.object(mock_onboarding_manager, 'api_confirm_caps', return_value={"status": "success"}):
                mock_onboarding_manager.apply_contract_capabilities("test-token")
                mock_onboarding_manager.update_state(
                    step="contract_caps_applied",
                    contract_caps_applied=True
                )
        
        assert mock_onboarding_manager.state["contract_caps_applied"] is True
        assert mock_onboarding_manager.state["step"] == "contract_caps_applied"

    def test_status_transition_deployment_caps_ready_to_applied(
        self, mock_onboarding_manager, mock_state_with_org
    ):
        """Test transition from deployment_caps_ready to deployment_caps_applied."""
        mock_onboarding_manager.state = mock_state_with_org
        mock_onboarding_manager.state["api_status"] = "deployment_caps_ready"
        mock_onboarding_manager.state["contract_signed"] = True
        
        # Simulate applying deployment caps
        with patch.object(mock_onboarding_manager, 'apply_deployment_capabilities', return_value=True):
            with patch.object(mock_onboarding_manager, 'api_confirm_caps', return_value={"status": "success"}):
                mock_onboarding_manager.apply_deployment_capabilities("test-token", {}, "api-key")
                mock_onboarding_manager.update_state(
                    step="deployment_caps_applied",
                    deployment_caps_applied=True
                )
        
        assert mock_onboarding_manager.state["deployment_caps_applied"] is True
        assert mock_onboarding_manager.state["step"] == "deployment_caps_applied"


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
