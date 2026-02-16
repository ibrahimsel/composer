#
# Copyright (c) 2025 Composiv.ai
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# http://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

"""
Unit tests for GraphReconciliationManager.

Tests cover:
- Pause on orchestration started
- Declarative desired state extraction and publishing
- Multi-sample stabilization (intersection logic)
- Reconciliation policies (safety, mission, standard)
- Escalation when package/executable unknown
- Retry exhaustion -> full redeploy
- Rollback on orchestration failure
- Criticality map glob matching
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from muto_composer.events import (
    BaseComposeEvent,
    EventBus,
    EventType,
    OrchestrationCompletedEvent,
    OrchestrationFailedEvent,
    OrchestrationStartedEvent,
)


def _make_manager(event_bus=None):
    """Create a GraphReconciliationManager with mocked ROS interfaces."""
    if event_bus is None:
        event_bus = EventBus(max_workers=1)

    logger = MagicMock()

    with patch(
        "muto_composer.subsystems.graph_reconciliation.GraphReconciliationManager"
        "._setup_ros_interfaces"
    ):
        from muto_composer.subsystems.graph_reconciliation import (
            GraphReconciliationManager,
        )

        mgr = GraphReconciliationManager.__new__(GraphReconciliationManager)
        # Manually initialize without ROS
        mgr._node = MagicMock()
        mgr._event_bus = event_bus
        mgr._logger = logger
        mgr._stabilization_samples = 3
        mgr._stabilization_sec = 0.01  # fast for tests
        mgr._cooldown_sec = 30.0
        mgr._max_retries = 3
        mgr._ignored_prefixes = ["/_", "/rosout", "/muto"]
        mgr._archived_baseline = None
        mgr._current_desired_state = None
        mgr._active_stack_payload = None
        mgr._criticality_map = {}
        mgr._retry_counts = {}
        mgr._last_restart_time = {}
        mgr._stabilization_active = False
        mgr._paused = False
        mgr._managed_reconciliation_launchers = {}
        mgr._ros_available = False
        import threading
        mgr._lock = threading.Lock()

        # Subscribe to events
        mgr._subscribe_to_events()

    return mgr


# ── Declarative manifests for testing ─────────────────────────────

DECLARATIVE_MANIFEST = {
    "metadata": {
        "name": "declarative-demo",
        "content_type": "stack/declarative",
        "version": "1.0.0",
    },
    "launch": {
        "node": [
            {
                "name": "talker",
                "pkg": "demo_nodes_cpp",
                "exec": "talker",
                "namespace": "/demo",
                "criticality": "mission",
            },
            {
                "name": "listener",
                "pkg": "demo_nodes_cpp",
                "exec": "listener",
                "namespace": "/demo",
                "criticality": "standard",
            },
        ]
    },
}

LEGACY_MANIFEST = {
    "name": "legacy-demo",
    "stackId": "org.eclipse.muto.demo:legacy",
    "composable": [
        {
            "name": "demo_container",
            "namespace": "",
            "package": "rclcpp_components",
            "executable": "component_container",
            "node": [
                {"pkg": "composition", "plugin": "composition::Server", "name": "server"},
                {"pkg": "composition", "plugin": "composition::Client", "name": "client"},
            ],
        }
    ],
    "node": [],
}

NATIVE_MANIFEST = {
    "metadata": {
        "name": "native-turtlesim",
        "content_type": "stack/native",
        "version": "1.0.0",
    },
    "launch": {"file": "native_turtlesim.launch.py"},
    "criticality_map": {
        "/turtlesim": "mission",
        "/teleop_turtle": "standard",
    },
}


class TestPauseOnOrchestrationStarted(unittest.TestCase):
    """Test that drift detection pauses when orchestration begins."""

    def test_pause_on_orchestration_started(self):
        event_bus = EventBus(max_workers=1)
        mgr = _make_manager(event_bus)

        # Set an existing baseline
        mgr._current_desired_state = {"stack_name": "old", "nodes": []}

        event = OrchestrationStartedEvent(
            event_type=EventType.ORCHESTRATION_STARTED,
            source_component="test",
            action="start",
            orchestration_id="orch-1",
            stack_payload=DECLARATIVE_MANIFEST,
        )
        event_bus.publish_sync(event)

        self.assertTrue(mgr.is_paused)
        self.assertIsNotNone(mgr._archived_baseline)
        self.assertEqual(mgr._archived_baseline["stack_name"], "old")


class TestDeclarativeDesiredState(unittest.TestCase):
    """Test desired state extraction from declarative manifests."""

    def test_declarative_desired_state_published(self):
        event_bus = EventBus(max_workers=1)
        mgr = _make_manager(event_bus)

        # Track GRAPH_STATE_UPDATED events
        updated_events = []
        event_bus.subscribe(
            EventType.GRAPH_STATE_UPDATED,
            lambda e: updated_events.append(e),
        )

        event = OrchestrationCompletedEvent(
            event_type=EventType.ORCHESTRATION_COMPLETED,
            source_component="test",
            orchestration_id="orch-1",
            stack_payload=DECLARATIVE_MANIFEST,
        )
        event_bus.publish_sync(event)

        self.assertFalse(mgr.is_paused)
        desired = mgr.current_desired_state
        self.assertIsNotNone(desired)
        self.assertEqual(desired["stack_name"], "declarative-demo")
        self.assertEqual(desired["stack_version"], "1.0.0")
        self.assertEqual(len(desired["nodes"]), 2)

        # Verify node details
        fqns = [n["fully_qualified_name"] for n in desired["nodes"]]
        self.assertIn("/demo/talker", fqns)
        self.assertIn("/demo/listener", fqns)

        # Verify package/executable populated
        talker = next(n for n in desired["nodes"] if n["name"] == "talker")
        self.assertEqual(talker["package_name"], "demo_nodes_cpp")
        self.assertEqual(talker["executable"], "talker")

        # Verify event fired
        self.assertEqual(len(updated_events), 1)

    def test_legacy_manifest_extraction(self):
        event_bus = EventBus(max_workers=1)
        mgr = _make_manager(event_bus)

        # Simulate orchestration completed with legacy payload
        # For legacy, content_type is empty so it goes through try_extract path
        mgr._active_stack_payload = LEGACY_MANIFEST
        event = OrchestrationCompletedEvent(
            event_type=EventType.ORCHESTRATION_COMPLETED,
            source_component="test",
            orchestration_id="orch-2",
            stack_payload=LEGACY_MANIFEST,
        )
        event_bus.publish_sync(event)

        desired = mgr.current_desired_state
        self.assertIsNotNone(desired)
        # Should have container + 2 component nodes
        self.assertEqual(len(desired["nodes"]), 3)
        fqns = [n["fully_qualified_name"] for n in desired["nodes"]]
        self.assertIn("/demo_container", fqns)
        self.assertIn("/server", fqns)
        self.assertIn("/client", fqns)


class TestMultiSampleStabilization(unittest.TestCase):
    """Test baseline learning via multi-sample stabilization."""

    def test_stabilization_intersection(self):
        """3 samples: {A,B,C}, {A,B}, {A,B,D} -> baseline = {A,B}."""
        event_bus = EventBus(max_workers=1)
        mgr = _make_manager(event_bus)

        # Mock the probe to return different samples each call
        samples = [
            {"/app/A", "/app/B", "/app/C"},
            {"/app/A", "/app/B"},
            {"/app/A", "/app/B", "/app/D"},
        ]
        call_count = [0]

        def mock_probe():
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(samples):
                return samples[idx]
            return set()

        mgr._probe_actual_nodes = mock_probe

        # Run stabilization synchronously
        mgr._stabilization_worker(NATIVE_MANIFEST)

        desired = mgr.current_desired_state
        self.assertIsNotNone(desired)
        fqns = {n["fully_qualified_name"] for n in desired["nodes"]}
        self.assertEqual(fqns, {"/app/A", "/app/B"})
        self.assertFalse(mgr.is_stabilization_active)

    def test_stabilization_transient_logged(self):
        """Transient nodes (C, D) should be logged."""
        event_bus = EventBus(max_workers=1)
        mgr = _make_manager(event_bus)

        samples = [
            {"/app/A", "/app/B", "/app/C"},
            {"/app/A", "/app/B"},
            {"/app/A", "/app/B", "/app/D"},
        ]
        call_count = [0]

        def mock_probe():
            idx = call_count[0]
            call_count[0] += 1
            return samples[idx] if idx < len(samples) else set()

        mgr._probe_actual_nodes = mock_probe
        mgr._stabilization_worker(NATIVE_MANIFEST)

        # Check that logger was called with transient info
        log_calls = [str(c) for c in mgr._logger.info.call_args_list]
        transient_logged = any("Transient" in c or "transient" in c.lower() for c in log_calls)
        self.assertTrue(transient_logged, f"Expected transient log, got: {log_calls}")

    def test_stabilization_filters_ignored_prefixes(self):
        """System nodes matching ignored prefixes should be excluded."""
        event_bus = EventBus(max_workers=1)
        mgr = _make_manager(event_bus)

        # All samples include system nodes
        samples = [
            {"/app/A", "/_hidden", "/rosout", "/muto/agent"},
            {"/app/A", "/_hidden", "/rosout", "/muto/agent"},
            {"/app/A", "/_hidden", "/rosout", "/muto/agent"},
        ]
        call_count = [0]

        def mock_probe():
            idx = call_count[0]
            call_count[0] += 1
            return samples[idx] if idx < len(samples) else set()

        mgr._probe_actual_nodes = mock_probe
        mgr._stabilization_worker(NATIVE_MANIFEST)

        desired = mgr.current_desired_state
        fqns = {n["fully_qualified_name"] for n in desired["nodes"]}
        self.assertEqual(fqns, {"/app/A"})


class TestReconciliationPolicies(unittest.TestCase):
    """Test reconciliation actions based on criticality."""

    def _setup_manager_with_desired_state(self):
        event_bus = EventBus(max_workers=1)
        mgr = _make_manager(event_bus)
        mgr._current_desired_state = {
            "stack_name": "test-stack",
            "nodes": [
                {
                    "name": "safety_cam",
                    "node_namespace": "/perception",
                    "fully_qualified_name": "/perception/safety_cam",
                    "package_name": "perception_pkg",
                    "executable": "safety_cam",
                },
                {
                    "name": "lidar",
                    "node_namespace": "/perception",
                    "fully_qualified_name": "/perception/lidar",
                    "package_name": "lidar_pkg",
                    "executable": "lidar_node",
                },
                {
                    "name": "logger",
                    "node_namespace": "/utils",
                    "fully_qualified_name": "/utils/logger",
                    "package_name": "",
                    "executable": "",
                },
            ],
            "ignored_prefixes": ["/_", "/rosout"],
        }
        mgr._criticality_map = {
            "/perception/safety_cam": "safety",
            "/perception/*": "mission",
            "/utils/*": "standard",
        }
        mgr._active_stack_payload = DECLARATIVE_MANIFEST
        return mgr, event_bus

    def test_safety_no_restart(self):
        """Safety node missing -> alert only, no restart attempt."""
        mgr, event_bus = self._setup_manager_with_desired_state()

        actions = []
        event_bus.subscribe(
            EventType.RECONCILIATION_ACTION_TAKEN,
            lambda e: actions.append(e),
        )

        mgr._reconcile_missing_node("/perception/safety_cam")

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_type, "alert")
        self.assertEqual(actions[0].criticality, "safety")

    def test_mission_with_cooldown(self):
        """Mission node -> restart, then cooldown blocks second attempt."""
        mgr, event_bus = self._setup_manager_with_desired_state()

        actions = []
        event_bus.subscribe(
            EventType.RECONCILIATION_ACTION_TAKEN,
            lambda e: actions.append(e),
        )

        with patch(
            "muto_composer.subsystems.graph_reconciliation.GraphReconciliationManager"
            "._restart_node_direct",
            return_value=True,
        ):
            mgr._reconcile_missing_node("/perception/lidar")

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].criticality, "mission")
        self.assertEqual(actions[0].action_type, "restart")

        # Second attempt within cooldown should be skipped
        actions.clear()
        mgr._reconcile_missing_node("/perception/lidar")
        self.assertEqual(len(actions), 0)  # Blocked by cooldown

    def test_standard_restart(self):
        """Standard node missing -> immediate restart via ros2 run."""
        mgr, event_bus = self._setup_manager_with_desired_state()

        actions = []
        event_bus.subscribe(
            EventType.RECONCILIATION_ACTION_TAKEN,
            lambda e: actions.append(e),
        )

        # Standard node with unknown pkg/exe -> full relaunch
        stack_requests = []
        event_bus.subscribe(
            EventType.STACK_REQUEST,
            lambda e: stack_requests.append(e),
        )

        mgr._reconcile_missing_node("/utils/logger")

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_type, "relaunch")
        self.assertEqual(actions[0].criticality, "standard")

    def test_unknown_pkg_escalates(self):
        """Node with empty package/executable -> full relaunch via event bus."""
        mgr, event_bus = self._setup_manager_with_desired_state()

        stack_requests = []
        event_bus.subscribe(
            EventType.STACK_REQUEST,
            lambda e: stack_requests.append(e),
        )

        mgr._reconcile_missing_node("/utils/logger")

        self.assertEqual(len(stack_requests), 1)
        self.assertEqual(stack_requests[0].action, "start")

    def test_retries_exhausted_redeploy(self):
        """3 failed restarts -> full redeploy via StackRequestEvent(action=apply)."""
        mgr, event_bus = self._setup_manager_with_desired_state()
        mgr._max_retries = 3
        mgr._retry_counts["/perception/lidar"] = 3  # Already exhausted

        stack_requests = []
        event_bus.subscribe(
            EventType.STACK_REQUEST,
            lambda e: stack_requests.append(e),
        )

        mgr._reconcile_missing_node("/perception/lidar")

        self.assertEqual(len(stack_requests), 1)
        self.assertEqual(stack_requests[0].action, "apply")


class TestRollbackRestoresBaseline(unittest.TestCase):
    """Test that orchestration failure restores the archived baseline."""

    def test_rollback_restores_baseline(self):
        event_bus = EventBus(max_workers=1)
        mgr = _make_manager(event_bus)

        # Set initial baseline
        original = {"stack_name": "original", "nodes": [{"fully_qualified_name": "/a"}]}
        mgr._current_desired_state = original

        # Orchestration starts -> archives baseline
        start_event = OrchestrationStartedEvent(
            event_type=EventType.ORCHESTRATION_STARTED,
            source_component="test",
            action="start",
            orchestration_id="orch-1",
        )
        event_bus.publish_sync(start_event)
        self.assertTrue(mgr.is_paused)
        self.assertEqual(mgr._archived_baseline["stack_name"], "original")

        # Orchestration fails -> restore
        fail_event = OrchestrationFailedEvent(
            event_type=EventType.ORCHESTRATION_FAILED,
            source_component="test",
            orchestration_id="orch-1",
            error_details="build failed",
        )
        event_bus.publish_sync(fail_event)

        self.assertFalse(mgr.is_paused)
        self.assertEqual(mgr.current_desired_state["stack_name"], "original")
        self.assertIsNone(mgr._archived_baseline)


class TestCriticalityMapGlobMatching(unittest.TestCase):
    """Test glob/fnmatch pattern matching for criticality lookups."""

    def test_exact_match_takes_priority(self):
        mgr = _make_manager()
        mgr._criticality_map = {
            "/perception/lidar": "safety",
            "/perception/*": "mission",
        }
        self.assertEqual(mgr._get_node_criticality("/perception/lidar"), "safety")

    def test_glob_match(self):
        mgr = _make_manager()
        mgr._criticality_map = {"/perception/*": "mission"}
        self.assertEqual(mgr._get_node_criticality("/perception/camera"), "mission")

    def test_default_standard(self):
        mgr = _make_manager()
        mgr._criticality_map = {"/perception/*": "mission"}
        self.assertEqual(mgr._get_node_criticality("/utils/logger"), "standard")


class TestFqnUtilities(unittest.TestCase):
    """Test FQN build/split utilities."""

    def test_build_fqn_with_namespace(self):
        mgr = _make_manager()
        self.assertEqual(mgr._build_fqn("talker", "/demo"), "/demo/talker")

    def test_build_fqn_root_namespace(self):
        mgr = _make_manager()
        self.assertEqual(mgr._build_fqn("talker", "/"), "/talker")

    def test_build_fqn_empty_namespace(self):
        mgr = _make_manager()
        self.assertEqual(mgr._build_fqn("talker", ""), "/talker")

    def test_build_fqn_no_leading_slash(self):
        mgr = _make_manager()
        self.assertEqual(mgr._build_fqn("talker", "demo"), "/demo/talker")

    def test_split_fqn(self):
        mgr = _make_manager()
        name, ns = mgr._split_fqn("/demo/talker")
        self.assertEqual(name, "talker")
        self.assertEqual(ns, "/demo")

    def test_split_fqn_root(self):
        mgr = _make_manager()
        name, ns = mgr._split_fqn("/talker")
        self.assertEqual(name, "talker")
        self.assertEqual(ns, "/")


class TestContentTypeDetection(unittest.TestCase):
    """Test content type extraction from payloads."""

    def test_declarative(self):
        mgr = _make_manager()
        self.assertEqual(mgr._get_content_type(DECLARATIVE_MANIFEST), "stack/declarative")

    def test_native(self):
        mgr = _make_manager()
        self.assertEqual(mgr._get_content_type(NATIVE_MANIFEST), "stack/native")

    def test_legacy_no_content_type(self):
        mgr = _make_manager()
        self.assertEqual(mgr._get_content_type(LEGACY_MANIFEST), "")

    def test_none_payload(self):
        mgr = _make_manager()
        self.assertEqual(mgr._get_content_type(None), "")


if __name__ == "__main__":
    unittest.main()
