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

"""
Muto Composer using modular, event-driven architecture.
Coordinates subsystems to handle stack deployment orchestration.
"""

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from muto_composer.events import EventBus, EventType, ProcessCrashedEvent
from muto_composer.subsystems.digital_twin_integration import DigitalTwinIntegration
from muto_composer.subsystems.graph_reconciliation import GraphReconciliationManager
from muto_composer.subsystems.message_handler import MessageHandler
from muto_composer.subsystems.orchestration_manager import OrchestrationManager
from muto_composer.subsystems.pipeline_engine import PipelineEngine
from muto_composer.subsystems.stack_manager import StackManager


class MutoComposer(Node):
    """
    Muto Composer using modular, event-driven architecture.
    Coordinates subsystems to handle stack deployment orchestration.
    """

    def __init__(self):
        super().__init__("muto_composer")

        # Initialize configuration parameters
        self.declare_parameter("stack_topic", "stack")
        self.declare_parameter("twin_url", "sandbox.composiv.ai")
        self.declare_parameter("namespace", "org.eclipse.muto.sandbox")
        self.declare_parameter("name", "example-01")

        # Extract parameter values
        self.twin_url = self.get_parameter("twin_url").get_parameter_value().string_value
        self.twin_namespace = self.get_parameter("namespace").get_parameter_value().string_value
        self.name = self.get_parameter("name").get_parameter_value().string_value
        self.next_stack_topic = self.get_parameter("stack_topic").get_parameter_value().string_value

        # Initialize event bus for subsystem communication
        self.event_bus = EventBus()
        self.event_bus.set_logger(self.get_logger())

        # Initialize all subsystems with dependency injection
        self._initialize_subsystems()

        # Set up ROS 2 interfaces after subsystems are ready
        self._setup_ros_interfaces()

        # Subscribe to relevant events for coordination
        self._subscribe_to_events()

        self.get_logger().info("MutoComposer initialized successfully")

    def _initialize_subsystems(self):
        """Initialize all subsystems in correct dependency order.

        Order matters: EventBus delivers events to subscribers in subscription
        order.  GraphReconciliationManager must subscribe to ORCHESTRATION_STARTED
        *before* PipelineEngine so that drift detection is paused before the
        pipeline runs (and potentially completes) synchronously.
        """
        try:
            # Initialize core subsystems
            self.message_handler = MessageHandler(node=self, event_bus=self.event_bus)

            self.digital_twin = DigitalTwinIntegration(node=self, event_bus=self.event_bus, logger=self.get_logger())

            self.stack_manager = StackManager(event_bus=self.event_bus, logger=self.get_logger())

            self.orchestration_manager = OrchestrationManager(event_bus=self.event_bus, logger=self.get_logger())

            # GraphReconciliation subscribes to ORCHESTRATION_STARTED here —
            # must come before PipelineEngine so the "paused" state is set
            # before the pipeline executes and fires ORCHESTRATION_COMPLETED.
            self.graph_reconciliation = GraphReconciliationManager(
                node=self, event_bus=self.event_bus, logger=self.get_logger()
            )

            self.pipeline_engine = PipelineEngine(event_bus=self.event_bus, logger=self.get_logger())

            self.get_logger().info("All subsystems initialized successfully")

        except Exception as e:
            self.get_logger().error(f"Failed to initialize subsystems: {e}")
            raise

    def _setup_ros_interfaces(self):
        """Set up ROS 2 publishers and subscribers."""
        try:
            # Subscribe to process crash notifications from launch_plugin
            self._crash_subscription = self.create_subscription(
                String, "launch_plugin/process_crashed", self._handle_process_crash_notification, 10
            )

            self.get_logger().info("ROS 2 interfaces set up successfully")

        except Exception as e:
            self.get_logger().error(f"Failed to set up ROS interfaces: {e}")
            raise

    def _subscribe_to_events(self):
        """Subscribe to coordination events from subsystems."""
        try:
            self.event_bus.subscribe(EventType.PIPELINE_COMPLETED, self._handle_pipeline_completed)
            self.event_bus.subscribe(EventType.PIPELINE_FAILED, self._handle_pipeline_failed)

            self.get_logger().debug("Event subscriptions set up successfully")

        except Exception as e:
            self.get_logger().error(f"Failed to set up event subscriptions: {e}")
            raise

    def _handle_pipeline_completed(self, event):
        """Handle pipeline completion for high-level coordination."""
        try:
            self.get_logger().info(f"Pipeline completed: {event.pipeline_name}")

            if hasattr(event, "final_result") and event.final_result:
                self.get_logger().info(f"Pipeline result keys: {list(event.final_result.keys())}")

        except Exception as e:
            self.get_logger().error(f"Error handling pipeline completion: {e}")

    def _handle_pipeline_failed(self, event):
        """Handle pipeline failure for error recovery."""
        try:
            self.get_logger().error(f"Pipeline failed: {event.pipeline_name} - {event.error_details}")

        except Exception as e:
            self.get_logger().error(f"Error handling pipeline failure: {e}")

    def _handle_process_crash_notification(self, msg: String):
        """Handle process crash notification from launch_plugin."""
        try:
            crash_data = json.loads(msg.data)

            self.get_logger().error(
                f"Process crashed: {crash_data.get('process_name', 'unknown')} "
                f"(stack: {crash_data.get('stack_name', 'unknown')}, "
                f"exit code: {crash_data.get('exit_code', -1)})"
            )

            crash_event = ProcessCrashedEvent(
                event_type=EventType.PROCESS_CRASHED,
                source_component="muto_composer",
                process_name=crash_data.get("process_name", ""),
                exit_code=crash_data.get("exit_code", -1),
                stack_name=crash_data.get("stack_name", ""),
                error_message=crash_data.get("error_message", ""),
                process_output=crash_data.get("process_output", ""),
            )

            self.event_bus.publish_sync(crash_event)

            self.get_logger().info("ProcessCrashedEvent published, rollback may be triggered")

        except json.JSONDecodeError as e:
            self.get_logger().error(f"Invalid JSON in crash notification: {e}")
        except Exception as e:
            self.get_logger().error(f"Error handling process crash notification: {e}")


def main(args=None):
    """Main entry point for the Muto Composer node."""
    composer = None
    try:
        rclpy.init(args=args)
        composer = MutoComposer()
        rclpy.spin(composer)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        rclpy.logging.get_logger("muto_composer").error(f"Error in main: {e}")
    finally:
        if composer is not None:
            composer.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()
