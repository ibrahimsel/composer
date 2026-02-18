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
Message handling subsystem for the Muto Composer.
Manages all ROS 2 communication including topics, services, and publishers.
"""

import copy
import json
from typing import Any

from muto_msgs.msg import MutoAction, MutoActionMeta
from rclpy.node import Node
from std_msgs.msg import String

from muto_composer.events import EventBus, EventType, StackRequestEvent


class ResponseHandler:
    """Sends responses back to the agent after pipeline completion/failure."""

    def __init__(self, node: Node, event_bus: EventBus, logger=None):
        self.node = node
        self.event_bus = event_bus
        self.logger = logger
        self._pending_requests: dict[str, dict[str, Any]] = {}

        # Publisher to send responses back through the agent
        self._response_pub = node.create_publisher(MutoAction, "command_to_agent", 10)

        # Subscribe to pipeline completion/failure events
        self.event_bus.subscribe(EventType.PIPELINE_COMPLETED, self._handle_completed)
        self.event_bus.subscribe(EventType.PIPELINE_FAILED, self._handle_failed)

        if self.logger:
            self.logger.info("ResponseHandler initialized")

    def register_request(
        self,
        correlation_id: str,
        response_topic: str,
        correlation_data: str,
        original_payload: dict[str, Any],
    ) -> None:
        """Register a pending request for response tracking."""
        self._pending_requests[correlation_id] = {
            "response_topic": response_topic,
            "correlation_data": correlation_data,
            "original_payload": original_payload,
        }
        if self.logger:
            self.logger.debug(f"Registered pending request: {correlation_id}")

    def _handle_completed(self, event) -> None:
        """Handle pipeline completion by sending success response."""
        request = self._pending_requests.pop(event.correlation_id, None)
        if not request:
            return
        self._send_response(
            request, status=200, value={"message": "Stack operation completed"}
        )

    def _handle_failed(self, event) -> None:
        """Handle pipeline failure by sending error response."""
        request = self._pending_requests.pop(event.correlation_id, None)
        if not request:
            return
        error_msg = (
            str(event.error_details)
            if hasattr(event, "error_details")
            else "Pipeline execution failed"
        )
        self._send_response(request, status=500, value={"message": error_msg})

    def _send_response(self, request: dict, status: int, value: dict) -> None:
        """Construct and publish a response message back to the agent."""
        try:
            # Build response payload from the original Ditto envelope
            response_payload = copy.deepcopy(request["original_payload"])
            response_payload["path"] = response_payload.get("path", "").replace(
                "/inbox", "/outbox"
            )
            response_payload["status"] = status
            response_payload["value"] = value

            # Build MutoActionMeta with original routing info
            meta = MutoActionMeta()
            meta.response_topic = request["response_topic"]
            meta.correlation_data = request["correlation_data"]

            # Build and publish MutoAction
            msg = MutoAction()
            msg.context = ""
            msg.method = ""
            msg.payload = json.dumps(response_payload)
            msg.meta = meta

            self._response_pub.publish(msg)

            if self.logger:
                self.logger.info(
                    f"Response sent (status={status}) to {request['response_topic']}"
                )

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to send response: {e}")


class MessageRouter:
    """Routes incoming messages to appropriate handlers via events."""

    def __init__(self, event_bus: EventBus, logger=None, response_handler: ResponseHandler | None = None):
        self.event_bus = event_bus
        self.logger = logger
        self.response_handler = response_handler

    def route_muto_action(self, action: MutoAction) -> None:
        """Route MutoAction to orchestration manager via events."""
        try:
            payload = json.loads(action.payload) if action.payload.strip() else {}
            stack_name = self._extract_stack_name(payload, f"unknown:{action.method}")

            # Unwrap Ditto protocol envelope: the actual stack manifest is in "value"
            stack_payload = payload.get("value", payload) if "path" in payload else payload

            # Extract correlation info from meta for response tracking
            correlation_id = action.meta.correlation_data or None

            event = StackRequestEvent(
                event_type=EventType.STACK_REQUEST,
                source_component="message_router",
                stack_name=stack_name,
                action=action.method,
                stack_payload=stack_payload,
                correlation_id=correlation_id,
            )

            # Register request so ResponseHandler can send a reply when pipeline completes
            if self.response_handler and correlation_id:
                self.response_handler.register_request(
                    correlation_id=correlation_id,
                    response_topic=action.meta.response_topic,
                    correlation_data=action.meta.correlation_data,
                    original_payload=payload,
                )

            if self.logger:
                self.logger.info(f"Routing {action.method} action via event system")

            self.event_bus.publish_sync(event)

        except json.JSONDecodeError as e:
            if self.logger:
                self.logger.error(f"Failed to parse MutoAction payload: {e}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error routing MutoAction: {e}")

    def _extract_stack_name(self, payload: dict[str, Any], default_name: str) -> str:
        """Extract stack name from payload."""
        # Try to extract from value key
        if "value" in payload and "stackId" in payload["value"]:
            return payload["value"]["stackId"]

        # Try to extract from metadata
        if "metadata" in payload and "name" in payload["metadata"]:
            return payload["metadata"]["name"]

        # Return default if not found
        return default_name


class PublisherManager:
    """Manages all outbound publishing with consolidated publishers."""

    def __init__(self, node: Node):
        self.node = node
        # Consolidated publisher instead of multiple deprecated ones
        self.stack_state_pub = node.create_publisher(String, "stack_state", 10)
        self.logger = node.get_logger()

    def publish_stack_state(self, stack_data: dict[str, Any], state_type: str = "current") -> None:
        """Publish consolidated stack state information."""
        try:
            # Create consolidated state message
            state_message = {
                "type": state_type,
                "timestamp": str(self.node.get_clock().now().to_msg()),
                "data": stack_data,
            }

            msg = String()
            msg.data = json.dumps(state_message)
            self.stack_state_pub.publish(msg)

            self.logger.debug(f"Published {state_type} stack state")

        except Exception as e:
            self.logger.error(f"Error publishing stack state: {e}")


class MessageHandler:
    """Main message handling subsystem coordinator."""

    def __init__(self, node: Node, event_bus: EventBus):
        self.node = node
        self.event_bus = event_bus
        self.logger = node.get_logger()

        # Initialize response handler (subscribes to pipeline events)
        self.response_handler = ResponseHandler(node, event_bus, self.logger)

        # Initialize components
        self.router = MessageRouter(event_bus, self.logger, self.response_handler)
        self.publisher_manager = PublisherManager(node)

        # Set up subscribers
        self._setup_subscribers()

        self.logger.info("MessageHandler subsystem initialized")

    def _setup_subscribers(self):
        """Set up ROS 2 subscribers."""
        # Get stack topic from parameters
        stack_topic = self.node.get_parameter("stack_topic").get_parameter_value().string_value

        # Subscribe to MutoAction messages
        self.node.create_subscription(MutoAction, stack_topic, self._muto_action_callback, 10)

        self.logger.info(f"Subscribed to {stack_topic} for MutoAction messages")

    def _muto_action_callback(self, msg: MutoAction):
        """Callback for MutoAction messages."""
        try:
            self.router.route_muto_action(msg)
        except Exception as e:
            self.logger.error(f"Error in MutoAction callback: {e}")

    def publish_stack_state(self, stack_data: dict[str, Any], state_type: str = "current"):
        """Publish stack state through publisher manager."""
        self.publisher_manager.publish_stack_state(stack_data, state_type)

    def handle_muto_action(self, muto_action: MutoAction):
        """Handle MutoAction message."""
        self.router.route_muto_action(muto_action)

    def get_router(self) -> MessageRouter:
        """Get message router."""
        return self.router

    def get_publisher_manager(self) -> PublisherManager:
        """Get publisher manager."""
        return self.publisher_manager
