"""Tests for role-aware DMS onboarding during organization join."""

from unittest.mock import MagicMock, patch

import pytest

from backend.modules.org_utils import normalize_role_id, role_requires_compute_onboarding


class TestRoleHelpers:
    def test_normalize_role_id(self):
        assert normalize_role_id("Orchestrator") == "orchestrator"
        assert normalize_role_id(" compute_provider ") == "compute_provider"
        assert normalize_role_id("") is None
        assert normalize_role_id(None) is None

    def test_role_requires_compute_onboarding(self):
        assert role_requires_compute_onboarding("compute_provider") is True
        assert role_requires_compute_onboarding("Compute Provider") is True
        assert role_requires_compute_onboarding("orchestrator") is False
        assert role_requires_compute_onboarding("Orchestrator") is False
        assert role_requires_compute_onboarding("contract_host") is False
        assert role_requires_compute_onboarding(None) is False


class TestCollectResourceSnapshot:
    @pytest.fixture
    def onboarding_manager(self):
        from backend.modules.onboarding_manager import OnboardingManager

        with patch.object(OnboardingManager, "_load_state") as mock_load:
            mock_load.return_value = OnboardingManager._baseline_state()
            mgr = OnboardingManager(use_mock_api=True)
            yield mgr

    def test_compute_provider_runs_pre_onboarding(self, onboarding_manager):
        onboarded_snapshot = {"onboarding_status": "ONBOARDED", "onboarded_resources": "cpu"}
        with patch.object(onboarding_manager, "_ensure_pre_onboarding", return_value=onboarded_snapshot) as mock_pre:
            with patch("backend.modules.onboarding_manager.get_dms_resource_info") as mock_info:
                result = onboarding_manager.collect_resource_snapshot(role_id="compute_provider")
        assert result == onboarded_snapshot
        mock_pre.assert_called_once()
        mock_info.assert_not_called()

    def test_orchestrator_skips_pre_onboarding(self, onboarding_manager):
        raw_snapshot = {"onboarding_status": "NOT ONBOARDED", "onboarded_resources": "None"}
        with patch.object(onboarding_manager, "_ensure_pre_onboarding") as mock_pre:
            with patch("backend.modules.onboarding_manager.get_dms_resource_info", return_value=raw_snapshot) as mock_info:
                result = onboarding_manager.collect_resource_snapshot(role_id="orchestrator")
        assert result == raw_snapshot
        mock_pre.assert_not_called()
        mock_info.assert_called_once()


class TestProcessPostApprovalPayload:
    @pytest.fixture
    def onboarding_manager(self):
        from backend.modules.onboarding_manager import OnboardingManager

        with patch.object(OnboardingManager, "_load_state") as mock_load:
            mock_load.return_value = OnboardingManager._baseline_state()
            mgr = OnboardingManager(use_mock_api=True)
            mgr.state["org_data"] = {"did": "did:key:test-org", "name": "Test Org"}
            mgr.state["form_data"] = {"roles": ["compute_provider"]}
            mgr.dms_manager.onboard_compute = MagicMock(
                return_value={"status": "success", "message": "should not be called"}
            )
            yield mgr

    def test_does_not_re_onboard_dms(self, onboarding_manager):
        with patch.object(onboarding_manager, "generate_and_apply_require_token", return_value=True):
            with patch.object(onboarding_manager, "_apply_provide_token"):
                with patch.object(onboarding_manager, "_configure_observability"):
                    with patch.object(onboarding_manager, "_write_certificates"):
                        with patch.object(onboarding_manager, "copy_capability_tokens_to_dms_user", return_value=True):
                            ok = onboarding_manager.process_post_approval_payload(
                                {
                                    "organization_did": "did:key:test-org",
                                    "capability_token": {"token": "demo"},
                                }
                            )
        assert ok is True
        onboarding_manager.dms_manager.onboard_compute.assert_not_called()
