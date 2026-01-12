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
Simplified Muto Composer for fleet deployment orchestration.

This composer validates release metadata and forwards deployment requests
to Symphony for distribution to device agents. It treats user software as
opaque artifacts - no ROS-specific processing is performed.
"""

from __future__ import annotations

import contextlib
import json
import re
from typing import Any

import rclpy  # type: ignore[import-not-found]
from muto_msgs.msg import MutoAction  # type: ignore[import-not-found]
from muto_msgs.srv import CoreTwin  # type: ignore[import-not-found]
from rclpy.node import Node  # type: ignore[import-not-found]
from std_msgs.msg import String  # type: ignore[import-not-found]

from composer.release_forwarder import ForwardStatus, ReleaseForwarder
from composer.release_model import validate_release_payload


class MutoComposer(Node):
    """
    Simplified Muto Composer for release validation and forwarding.

    This composer:
    1. Receives deployment requests via ROS2 topics
    2. Validates release metadata (name, version, artifact_uri, checksum, start_command)
    3. Forwards valid releases to Symphony for deployment to agents

    No ROS-specific processing of user software is performed.
    """

    def __init__(self) -> None:
        super().__init__("muto_composer")

        # Configuration parameters
        self.declare_parameter("namespace", "org.eclipse.muto.sandbox")
        self.declare_parameter("name", "example-01")
        self.declare_parameter("stack_topic", "stack")
        self.declare_parameter("result_topic", "deployment_result")

        self._namespace = (
            self.get_parameter("namespace").get_parameter_value().string_value
        )
        self._name = self.get_parameter("name").get_parameter_value().string_value
        stack_topic = (
            self.get_parameter("stack_topic").get_parameter_value().string_value
        )
        result_topic = (
            self.get_parameter("result_topic").get_parameter_value().string_value
        )

        # Initialize release forwarder
        self._forwarder = ReleaseForwarder(logger=self.get_logger())

        # Set up subscriptions and publishers
        self._subscription = self.create_subscription(
            MutoAction, stack_topic, self._on_deployment_request, 10
        )
        self._result_publisher = self.create_publisher(String, result_topic, 10)
        self._stack_definition_client = self.create_client(
            CoreTwin, "/muto/core_twin/get_stack_definition"
        )

    def _on_deployment_request(self, msg: MutoAction) -> None:
        """Handle incoming deployment request.

        Args:
            msg: MutoAction message containing deployment payload.
        """
        try:
            self.get_logger().info(f"Received deployment request: {msg.method}")

            # Parse payload
            try:
                payload = json.loads(msg.payload)
            except json.JSONDecodeError as exc:
                self._publish_error(f"Invalid JSON payload: {exc}")
                return

            if self._should_fetch_manifest(payload):
                stack_id = self._extract_stack_id(payload)
                if not stack_id:
                    self._publish_error("Missing stackId in deployment payload")
                    return
                self._request_stack_manifest(stack_id, msg)
                return

            self._process_deployment(msg, payload)

        except Exception as exc:
            self.get_logger().error(f"Error handling deployment request: {exc}")
            self._publish_error(str(exc))

    def _process_deployment(self, msg: MutoAction, payload: dict[str, Any]) -> None:
        """Process a deployment request with a fully resolved payload."""
        # Extract release payload from various formats
        release_payload = self._extract_release_payload(payload)
        if not release_payload:
            self._publish_error("Could not extract release metadata from payload")
            return

        # Handle different methods
        if msg.method in ("start", "apply", "deploy"):
            self._handle_deploy(release_payload)
        elif msg.method in ("stop", "kill", "remove"):
            self._handle_stop(release_payload)
        else:
            self._publish_error(f"Unknown method: {msg.method}")

    def _should_fetch_manifest(self, payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False

        manifest_markers = {
            "metadata",
            "node",
            "composable",
            "launch",
            "launch_description_source",
            "artifact",
            "archive_properties",
            "stack",
            "runtime",
            "features",
        }

        if manifest_markers.intersection(payload.keys()):
            return False

        if "stackId" in payload and len(payload.keys()) <= 2:
            return True

        if "value" in payload and isinstance(payload["value"], dict):
            value = payload["value"]
            if "stackId" in value and not manifest_markers.intersection(value.keys()):
                return True

        return False

    def _extract_stack_id(self, payload: dict[str, Any]) -> str | None:
        if "stackId" in payload:
            return str(payload["stackId"])
        if "value" in payload and isinstance(payload["value"], dict):
            stack_id = payload["value"].get("stackId")
            if stack_id:
                return str(stack_id)
        return None

    def _request_stack_manifest(self, stack_id: str, msg: MutoAction) -> None:
        if not self._stack_definition_client.wait_for_service(timeout_sec=0.5):
            self._publish_error("CoreTwin get_stack_definition service is not available")
            return

        request = CoreTwin.Request()
        request.input = stack_id
        future = self._stack_definition_client.call_async(request)
        future.add_done_callback(
            lambda fut: self._handle_stack_definition_response(fut, msg, stack_id)
        )

    def _handle_stack_definition_response(
        self,
        future: rclpy.Future,
        msg: MutoAction,
        stack_id: str,
    ) -> None:
        try:
            result = future.result()
            if not result or not getattr(result, "output", None):
                self._publish_error(f"CoreTwin returned an empty manifest for {stack_id}")
                return

            try:
                manifest = json.loads(result.output)
            except json.JSONDecodeError as exc:
                self._publish_error(f"Failed to decode manifest for {stack_id}: {exc}")
                return

            self.get_logger().info(f"Fetched stack manifest for {stack_id}")
            self._process_deployment(msg, manifest)
        except Exception as exc:
            self._publish_error(f"Error fetching stack manifest for {stack_id}: {exc}")

    def _extract_release_payload(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Extract release metadata from various payload formats.

        Supports:
        - Direct release format: {name, version, artifact_uri, ...}
        - Nested format: {value: {name, version, ...}}
        - Stack format: {features: {stack: {properties: {...}}}}

        Args:
            payload: Raw payload dictionary.

        Returns:
            Extracted release payload or None if not found.
        """
        # Direct format
        if "artifact_uri" in payload and "start_command" in payload:
            return payload

        # Nested value format
        if "value" in payload and isinstance(payload["value"], dict):
            value = payload["value"]
            if "artifact_uri" in value or "artifact" in value:
                return self._normalize_release(value)

        # Stack/features format (Symphony style)
        if "features" in payload and isinstance(payload["features"], dict):
            features = payload["features"]
            if "stack" in features and isinstance(features["stack"], dict):
                stack = features["stack"]
                if "properties" in stack:
                    return self._normalize_release(stack["properties"])

        # Try to normalize the payload directly
        normalized = self._normalize_release(payload)
        if normalized:
            return normalized

        return None

    def _normalize_release(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize release data to standard format.

        Args:
            data: Raw release data.

        Returns:
            Normalized release payload or None.
        """
        result: dict[str, Any] = {}

        metadata = data.get("metadata", {}) if isinstance(data.get("metadata", {}), dict) else {}
        stack_id = data.get("stackId", "")
        definition = data.get("definition", "")

        # Extract name
        result["name"] = data.get("name") or metadata.get("name") or stack_id
        if not result["name"] and isinstance(stack_id, str) and ":" in stack_id:
            result["name"] = stack_id.split(":")[-1]

        # Extract version
        result["version"] = data.get("version") or metadata.get("version")
        if not result["version"] and isinstance(definition, str) and ":" in definition:
            result["version"] = definition.split(":")[-1]

        # Extract artifact info
        artifact = data.get("artifact", {})
        result["artifact_uri"] = data.get("artifact_uri", artifact.get("uri", ""))
        result["checksum"] = data.get("checksum", artifact.get("checksum", ""))

        # Extract runtime info
        runtime = data.get("runtime", {})
        result["start_command"] = data.get(
            "start_command", runtime.get("start_command", "")
        )
        result["stop_command"] = data.get(
            "stop_command", runtime.get("stop_command")
        )
        result["working_directory"] = data.get(
            "working_directory", runtime.get("working_directory")
        )
        result["environment"] = data.get(
            "environment", runtime.get("environment", {})
        )

        if not result["name"] or not result["version"]:
            inferred_name, inferred_version = self._infer_name_version(
                result.get("artifact_uri", "")
            )
            if not result["name"] and inferred_name:
                result["name"] = inferred_name
            if not result["version"] and inferred_version:
                result["version"] = inferred_version

        # Validate we have minimum required fields
        if not result["name"] or not result["start_command"]:
            return None

        return result

    def _infer_name_version(self, artifact_uri: str) -> tuple[str | None, str | None]:
        if not artifact_uri:
            return None, None

        filename = artifact_uri.split("?", 1)[0].rsplit("/", 1)[-1]
        base = filename
        for suffix in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".zip", ".tar"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break

        match = re.match(
            r"^(?P<name>.+)-(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z\.-]+)?)$",
            base,
        )
        if match:
            return match.group("name"), match.group("version")

        if "-" in base:
            name_part, version_part = base.rsplit("-", 1)
            if any(ch.isdigit() for ch in version_part):
                return name_part, version_part

        return None, None

    def _handle_deploy(self, release_payload: dict[str, Any]) -> None:
        """Handle deploy/start request.

        Args:
            release_payload: Validated release payload.
        """
        result = self._forwarder.validate_and_forward(release_payload)

        if result.status == ForwardStatus.SUCCESS:
            self.get_logger().info(
                f"Release validated and forwarded: {result.solution_name}"
            )
            self._publish_result({
                "status": "success",
                "message": result.message,
                "solution": result.solution_name,
            })
        else:
            self.get_logger().error(f"Deployment failed: {result.message}")
            self._publish_error(result.message)

    def _handle_stop(self, release_payload: dict[str, Any]) -> None:
        """Handle stop/kill request.

        Args:
            release_payload: Release payload identifying what to stop.
        """
        try:
            release = validate_release_payload(release_payload)
            self.get_logger().info(
                f"Stop request for release: {release.name}:{release.version}"
            )
            self._publish_result({
                "status": "success",
                "message": f"Stop request forwarded for {release.name}:{release.version}",
            })
        except ValueError as exc:
            self._publish_error(f"Invalid release for stop: {exc}")

    def _publish_result(self, result: dict[str, Any]) -> None:
        """Publish deployment result.

        Args:
            result: Result dictionary.
        """
        msg = String()
        msg.data = json.dumps(result)
        self._result_publisher.publish(msg)

    def _publish_error(self, error: str) -> None:
        """Publish error result.

        Args:
            error: Error message.
        """
        self.get_logger().error(f"Deployment error: {error}")
        self._publish_result({"status": "error", "message": error})


def main(args: list[str] | None = None) -> None:
    """Main entry point for the Muto Composer node."""
    try:
        rclpy.init(args=args)
        composer = MutoComposer()
        rclpy.spin(composer)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"Error in main: {exc}")
    finally:
        with contextlib.suppress(NameError, UnboundLocalError):
            composer.destroy_node()  # type: ignore[possibly-undefined]

        if rclpy.ok():
            rclpy.shutdown()
