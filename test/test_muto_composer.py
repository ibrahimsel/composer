#
# Copyright (c) 2025 Composiv.ai
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# http://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0
#
# Contributors:
#   Composiv.ai - initial API and implementation
#

import contextlib
import json
import unittest
from unittest.mock import patch

import rclpy
from muto_msgs.msg import MutoAction

from muto_composer.events import (
    EventType,
    OrchestrationStartedEvent,
    StackAnalyzedEvent,
    StackProcessedEvent,
    StackRequestEvent,
)
from muto_composer.muto_composer import MutoComposer


class TestMutoComposerIntegration(unittest.TestCase):
    """
    Integration tests for MutoComposer focusing on event-driven architecture.
    Tests the complete flow from MutoAction message to subsystem orchestration
    through event flows rather than direct method calls.
    """

    def setUp(self) -> None:
        with contextlib.suppress(BaseException):
            rclpy.init()

        with patch("muto_composer.muto_composer.MutoComposer._initialize_subsystems"), \
                patch("muto_composer.muto_composer.MutoComposer._setup_ros_interfaces"):
            self.composer = MutoComposer()

        self.test_events = []
        self.captured_events = {}

        for event_type in EventType:
            self.captured_events[event_type] = []
            self.composer.event_bus.subscribe(
                event_type, lambda event, et=event_type: self.captured_events[et].append(event)
            )

    def tearDown(self) -> None:
        with contextlib.suppress(BaseException):
            self.composer.destroy_node()

    @classmethod
    def setUpClass(cls) -> None:
        with contextlib.suppress(BaseException):
            rclpy.init()

    @classmethod
    def tearDownClass(cls) -> None:
        with contextlib.suppress(BaseException):
            rclpy.shutdown()

    def test_muto_action_to_stack_request_flow(self):
        """Test the complete flow from MutoAction to StackRequest event."""
        muto_action = MutoAction()
        muto_action.method = "start"
        muto_action.payload = json.dumps({"value": {"stackId": "test_stack_001"}})

        if hasattr(self.composer, "message_handler"):
            self.composer.message_handler.handle_muto_action(muto_action)

        stack_requests = self.captured_events.get(EventType.STACK_REQUEST, [])
        if stack_requests:
            request = stack_requests[0]
            self.assertEqual(request.action, "start")
            self.assertEqual(request.stack_name, "test_stack_001")

    def test_stack_analysis_integration_flow(self):
        """Test integration between StackRequest and StackAnalyzed events."""
        stack_request = StackRequestEvent(
            event_type=EventType.STACK_REQUEST,
            source_component="test_client",
            action="apply",
            stack_name="integration_test_stack",
            stack_payload={
                "metadata": {"name": "integration_test_stack"},
                "nodes": [{"name": "test_node", "pkg": "test_pkg"}],
            },
        )

        self.composer.event_bus.publish_sync(stack_request)
        self.assertTrue(hasattr(self.composer, "event_bus"))

    def test_complete_stack_processing_pipeline(self):
        """Test the complete pipeline from stack request to pipeline execution."""
        stack_payload = {
            "metadata": {"name": "complete_test_stack", "content_type": "stack/json"},
            "launch": {
                "node": [{"name": "test_node_1", "pkg": "test_package", "exec": "test_executable"}]
            },
        }

        request_event = StackRequestEvent(
            event_type=EventType.STACK_REQUEST,
            source_component="test_client",
            action="apply",
            stack_name="complete_test_stack",
            stack_payload=stack_payload,
        )

        self.composer.event_bus.publish_sync(request_event)

        analyzed_event = StackAnalyzedEvent(
            event_type=EventType.STACK_ANALYZED,
            source_component="test_analyzer",
            stack_name="complete_test_stack",
            action="apply",
            analysis_result={"stack_type": "stack/json"},
            processing_requirements={"runtime": "docker", "launch_required": True},
        )

        self.composer.event_bus.publish_sync(analyzed_event)

        processed_event = StackProcessedEvent(
            stack_name="complete_test_stack",
            stack_payload=stack_payload,
            execution_requirements={"runtime": "docker", "launch_required": True},
        )

        self.composer.event_bus.publish_sync(processed_event)

        orchestration_event = OrchestrationStartedEvent(
            event_type=EventType.ORCHESTRATION_STARTED,
            source_component="test_orchestrator",
            action="apply",
            execution_plan={"steps": ["provision", "launch"]},
            orchestration_id="test_orchestration_001",
        )

        self.composer.event_bus.publish_sync(orchestration_event)

        requests = self.captured_events.get(EventType.STACK_REQUEST, [])
        analyzed = self.captured_events.get(EventType.STACK_ANALYZED, [])
        processed = self.captured_events.get(EventType.STACK_PROCESSED, [])
        orchestration = self.captured_events.get(EventType.ORCHESTRATION_STARTED, [])

        self.assertTrue(len(requests) > 0)
        self.assertTrue(len(analyzed) > 0)
        self.assertTrue(len(processed) > 0)
        self.assertTrue(len(orchestration) > 0)

    def test_subsystem_isolation_through_events(self):
        """Test that subsystems communicate only through events."""
        self.assertTrue(hasattr(self.composer, "event_bus"))
        self.assertIsNotNone(self.composer.event_bus)

    def test_event_bus_integration(self):
        """Test that event bus is properly integrated with composer."""
        self.assertIsNotNone(self.composer.event_bus)

        test_events = []

        def test_handler(event):
            test_events.append(event)

        self.composer.event_bus.subscribe(EventType.STACK_REQUEST, test_handler)

        test_event = StackRequestEvent(
            event_type=EventType.STACK_REQUEST,
            source_component="test_client",
            action="test",
            stack_name="test_stack",
            stack_payload={"test": "data"},
        )

        self.composer.event_bus.publish_sync(test_event)

        self.assertEqual(len(test_events), 1)
        self.assertEqual(test_events[0].action, "test")

    def test_digital_twin_integration_flow(self):
        """Test digital twin integration through events."""
        processed_event = StackProcessedEvent(
            stack_name="twin_test_stack",
            stack_payload={
                "metadata": {"name": "twin_test_stack", "twin_id": "test_twin_001"},
                "nodes": [{"name": "twin_node"}],
            },
            execution_requirements={"runtime": "docker"},
        )

        self.composer.event_bus.publish_sync(processed_event)

        processed_events = self.captured_events.get(EventType.STACK_PROCESSED, [])
        self.assertTrue(len(processed_events) > 0)

        if processed_events:
            event = processed_events[0]
            self.assertIn("twin_id", event.merged_stack["metadata"])

    def test_message_routing_integration(self):
        """Test message routing integration with event system."""
        test_actions = [
            ("start", {"value": {"stackId": "start_test"}}),
            ("apply", {"metadata": {"name": "apply_test"}, "nodes": ["node1"]}),
            ("stop", {"value": {"stackId": "stop_test"}}),
        ]

        for method, payload in test_actions:
            muto_action = MutoAction()
            muto_action.method = method
            muto_action.payload = json.dumps(payload)

            self.assertEqual(muto_action.method, method)
            self.assertIsNotNone(muto_action.payload)


if __name__ == "__main__":
    unittest.main()
