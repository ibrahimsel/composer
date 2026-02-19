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
Stack management subsystem for the Muto Composer.
Handles stack states, analysis, and transformations.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ament_index_python.packages import get_package_share_directory

from muto_composer.events import (
    EventBus,
    EventType,
    OrchestrationFailedEvent,
    OrchestrationStartedEvent,
    StackAnalyzedEvent,
    StackMergedEvent,
    StackProcessedEvent,
    StackRequestEvent,
    StackTransformedEvent,
)
from muto_composer.model.stack import Stack
from muto_composer.state.persistence import StatePersistence
from muto_composer.utils.stack_parser import create_stack_parser


class StackType(Enum):
    """Enumeration of stack types."""

    DECLARATIVE = "stack/declarative"
    WORKSPACE = "stack/workspace"
    NATIVE = "stack/native"
    LEGACY = "stack/legacy"
    # Backward-compatible aliases
    ARCHIVE = "stack/archive"
    JSON = "stack/json"
    DITTO = "stack/ditto"
    RAW = "stack/raw"
    UNKNOWN = "stack/unknown"


@dataclass
class ExecutionRequirements:
    """Stack execution requirements."""

    requires_provision: bool = False
    requires_launch: bool = False
    has_nodes: bool = False
    has_composables: bool = False
    has_launch_description: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "requires_provision": self.requires_provision,
            "requires_launch": self.requires_launch,
            "has_nodes": self.has_nodes,
            "has_composables": self.has_composables,
            "has_launch_description": self.has_launch_description,
        }


@dataclass
class StackTransition:
    """Represents a transition between stack states."""

    current: dict[str, Any] | None = None
    next: dict[str, Any] | None = None
    transition_type: str = "deploy"


class StackStateManager:
    """Manages current and next stack states with persistent storage."""

    def __init__(self, event_bus: EventBus, logger=None):
        self.event_bus = event_bus
        self.logger = logger
        self.current_stack: dict | None = None
        self.next_stack: dict | None = None
        self._current_stack_name: str | None = None
        self._deploying_stack_name: str | None = None

        # Initialize state persistence
        self.persistence = StatePersistence(logger=logger)

        # Subscribe to events
        self.event_bus.subscribe(EventType.ORCHESTRATION_STARTED, self.handle_orchestration_started)
        self.event_bus.subscribe(EventType.STACK_MERGED, self.handle_stack_merged)
        self.event_bus.subscribe(EventType.ORCHESTRATION_COMPLETED, self.handle_orchestration_completed)
        self.event_bus.subscribe(EventType.ORCHESTRATION_FAILED, self.handle_orchestration_failed)

        if self.logger:
            self.logger.info("StackStateManager initialized with persistence")

    def _get_stack_name(self, stack: dict | None) -> str:
        """Extract stack name from stack definition."""
        if not stack:
            return "default"
        metadata = stack.get("metadata", {})
        return metadata.get("name", stack.get("name", "default"))

    def set_current_stack(self, stack: dict) -> None:
        """Update current stack state."""
        self.current_stack = stack
        self._current_stack_name = self._get_stack_name(stack)
        if self.logger:
            self.logger.debug("Current stack updated")

    def set_next_stack(self, stack: dict) -> None:
        """Set stack for next deployment."""
        self.next_stack = stack
        if self.logger:
            self.logger.debug("Next stack set")

    def get_current_stack(self) -> dict | None:
        """Get current stack."""
        return self.current_stack

    def get_next_stack(self) -> dict | None:
        """Get next stack."""
        return self.next_stack

    def get_stack_transition(self) -> StackTransition:
        """Calculate transition from current to next."""
        return StackTransition(
            current=self.current_stack,
            next=self.next_stack,
            transition_type=self._determine_transition_type(),
        )

    def _determine_transition_type(self) -> str:
        """Determine the type of transition."""
        if not self.current_stack:
            return "initial_deploy"
        elif not self.next_stack:
            return "shutdown"
        else:
            return "update"

    def get_previous_stack(self) -> dict | None:
        """Get the previous stack for rollback."""
        if self._current_stack_name:
            return self.persistence.get_previous_stack(self._current_stack_name)
        return None

    def can_rollback(self) -> bool:
        """Check if rollback is possible."""
        if self._current_stack_name:
            return self.persistence.can_rollback(self._current_stack_name)
        return False

    def mark_deployment_started(self, stack: dict) -> None:
        """Mark deployment as started and persist state."""
        stack_name = self._get_stack_name(stack)
        self.persistence.mark_deployment_started(stack_name, stack)
        self.set_next_stack(stack)
        if self.logger:
            self.logger.info(f"Deployment started for {stack_name}")

    def handle_orchestration_started(self, event: OrchestrationStartedEvent):
        """Mark per-stack deployment as started when orchestration begins."""
        stack_payload = getattr(event, "stack_payload", None)
        if stack_payload:
            # Skip kill actions — they don't deploy a new stack
            ctx_vars = getattr(event, "context_variables", {})
            if ctx_vars.get("is_kill_action", False):
                return
            self._deploying_stack_name = self._get_stack_name(stack_payload)
            self.mark_deployment_started(stack_payload)

    def handle_stack_merged(self, event: StackMergedEvent):
        """Handle stack merged event."""
        self.set_current_stack(event.merged_stack)
        if self.logger:
            self.logger.info("Updated current stack from merge event")

    def handle_orchestration_completed(self, event):
        """Handle orchestration completion and persist state."""
        self._deploying_stack_name = None

        # Kill actions don't deploy a new stack — skip state mutation
        if getattr(event, "is_kill_action", False):
            if self.logger:
                self.logger.info("Kill orchestration completed, skipping state persistence")
            return

        if hasattr(event, "final_stack_state") and event.final_stack_state:
            self.set_current_stack(event.final_stack_state)
            stack_name = self._get_stack_name(event.final_stack_state)
            self.persistence.mark_deployment_completed(stack_name)
            if self.logger:
                self.logger.info(f"Orchestration completed for {stack_name}, state persisted")

    def handle_orchestration_failed(self, event: OrchestrationFailedEvent):
        """Handle orchestration failure and persist state."""
        stack_name = self._deploying_stack_name or self._current_stack_name or "unknown"
        self._deploying_stack_name = None
        error_msg = getattr(event, "error_details", str(event)) if hasattr(event, "error_details") else "Unknown error"
        self.persistence.mark_deployment_failed(stack_name, error_msg)
        if self.logger:
            self.logger.error(f"Orchestration failed for {stack_name}: {error_msg}")

    def complete_rollback(self) -> bool:
        """Mark rollback as completed after successful restore."""
        if self._current_stack_name:
            success = self.persistence.mark_rollback_completed(self._current_stack_name)
            if success:
                # Update in-memory state to match persisted state
                state = self.persistence.load_state(self._current_stack_name)
                if state and state.current_stack:
                    self.current_stack = state.current_stack
            return success
        return False


class StackAnalyzer:
    """Analyzes stack characteristics and determines execution requirements."""

    def __init__(self, event_bus: EventBus, logger=None):
        self.event_bus = event_bus
        self.logger = logger
        self.stack_parser = create_stack_parser(logger)

        # Subscribe to stack request events
        self.event_bus.subscribe(EventType.STACK_REQUEST, self.handle_stack_request)

        if self.logger:
            self.logger.info("StackAnalyzer initialized")

    # Map content_type strings to canonical StackType (includes aliases)
    _CONTENT_TYPE_MAP = {
        "stack/declarative": StackType.DECLARATIVE,
        "stack/json": StackType.DECLARATIVE,       # alias
        "stack/workspace": StackType.WORKSPACE,
        "stack/archive": StackType.WORKSPACE,       # alias
        "stack/native": StackType.NATIVE,
        "stack/legacy": StackType.LEGACY,
        "stack/ditto": StackType.LEGACY,            # alias
        "stack/raw": StackType.RAW,
        # Unprefixed forms for backward compatibility
        "declarative": StackType.DECLARATIVE,
        "json": StackType.DECLARATIVE,
        "workspace": StackType.WORKSPACE,
        "archive": StackType.WORKSPACE,
        "native": StackType.NATIVE,
        "legacy": StackType.LEGACY,
        "ditto": StackType.LEGACY,
        "raw": StackType.RAW,
    }

    def analyze_stack_type(self, stack: dict) -> StackType:
        """Determine the canonical stack type from metadata or structure."""
        metadata = stack.get("metadata", {})
        content_type = metadata.get("content_type", "")

        # Look up in the content type map (handles all aliases)
        if content_type in self._CONTENT_TYPE_MAP:
            return self._CONTENT_TYPE_MAP[content_type]

        # Fallback: infer from stack structure
        if stack.get("launch", {}).get("file"):
            return StackType.NATIVE
        elif stack.get("source", {}).get("archive") or stack.get("source", {}).get("url"):
            return StackType.WORKSPACE
        elif stack.get("launch", {}).get("node") or stack.get("node") or stack.get("composable"):
            return StackType.DECLARATIVE
        elif stack.get("launch_description_source") or (stack.get("on_start") and stack.get("on_kill")):
            return StackType.LEGACY
        else:
            return StackType.UNKNOWN

    def determine_execution_requirements(self, stack: dict) -> ExecutionRequirements:
        """Calculate provisioning and launch requirements."""
        stack_type = self.analyze_stack_type(stack)

        return ExecutionRequirements(
            requires_provision=stack_type in (StackType.WORKSPACE, StackType.ARCHIVE),
            requires_launch=stack_type in (
                StackType.DECLARATIVE, StackType.WORKSPACE, StackType.NATIVE,
                StackType.ARCHIVE, StackType.JSON, StackType.RAW,
            ),
            has_nodes=bool(stack.get("node")),
            has_composables=bool(stack.get("composable")),
            has_launch_description=bool(stack.get("launch_description_source")),
        )

    def handle_stack_request(self, event: StackRequestEvent):
        """Handle stack request by analyzing and validating the payload."""
        try:
            stack_payload = event.stack_payload or {}

            # For kill actions, we only need a stackId reference, not a full manifest
            # Skip full validation for these reference-only payloads
            if event.action == "kill":
                # stackId can be at top level or inside 'value' key
                stack_id = stack_payload.get("stackId") or stack_payload.get("value", {}).get("stackId")
                if not stack_id:
                    if self.logger:
                        self.logger.error(f"Kill action requires stackId for {event.stack_name}")
                    return

                # For kill actions, emit a special analyzed event that skips provisioning/launching
                analyzed_event = StackAnalyzedEvent(
                    event_type=EventType.STACK_ANALYZED,
                    source_component="stack_analyzer",
                    stack_name=event.stack_name,
                    action=event.action,
                    analysis_result={
                        "stack_type": "kill",
                        "is_kill_action": True,
                        "stack_id": stack_id,
                        "requires_provision": False,
                        "requires_launch": False,
                    },
                    processing_requirements={
                        "requires_provision": False,
                        "requires_launch": False,
                        "is_kill_action": True,
                    },
                    stack_payload=stack_payload,
                    correlation_id=event.correlation_id,
                    metadata={"action": event.action, "stack_id": stack_id},
                )

                if self.logger:
                    self.logger.info(f"Kill action for stack_id={stack_id}")

                self.event_bus.publish_sync(analyzed_event)
                return

            # Validate full stack manifest for start/apply actions
            if not self.stack_parser.validate_stack(stack_payload):
                if self.logger:
                    self.logger.error(f"Stack validation failed for {event.stack_name} - malformed manifest")
                return

            stack_type = self.analyze_stack_type(stack_payload)
            requirements = self.determine_execution_requirements(stack_payload)

            # Build processing requirements with merge/expression flags
            proc_reqs = requirements.to_dict()
            if stack_type in (StackType.DECLARATIVE, StackType.JSON, StackType.LEGACY, StackType.DITTO):
                proc_reqs["merge_manifests"] = True
                proc_reqs["resolve_expressions"] = True

            analyzed_event = StackAnalyzedEvent(
                event_type=EventType.STACK_ANALYZED,
                source_component="stack_analyzer",
                stack_name=event.stack_name,
                action=event.action,
                analysis_result={
                    "stack_type": stack_type.value,
                    "content_type": stack_payload.get("metadata", {}).get("content_type"),
                    "requires_provision": requirements.requires_provision,
                    "requires_launch": requirements.requires_launch,
                    "has_nodes": requirements.has_nodes,
                    "has_composables": requirements.has_composables,
                    "has_launch_description": requirements.has_launch_description,
                },
                processing_requirements=proc_reqs,
                stack_payload=stack_payload,  # Use direct field instead of nested structure
                correlation_id=event.correlation_id,
                metadata={"action": event.action},
            )

            if self.logger:
                self.logger.info(
                    f"Analyzed stack as {stack_type.value}, requires_provision={requirements.requires_provision}"
                )

            self.event_bus.publish_sync(analyzed_event)

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error analyzing stack: {e}")


class StackProcessor:
    """Handles stack transformations and merging."""

    def __init__(self, event_bus: EventBus, logger=None, state_manager=None):
        self.event_bus = event_bus
        self.logger = logger
        self.stack_parser = create_stack_parser(logger)
        self._state_manager = state_manager

        # Subscribe to events that require processing
        self.event_bus.subscribe(EventType.STACK_ANALYZED, self.handle_stack_analyzed)

        if self.logger:
            self.logger.info("StackProcessor initialized")

    def handle_stack_analyzed(self, event: StackAnalyzedEvent):
        """Handle stack analyzed event and perform required processing."""
        try:
            processing_requirements = event.processing_requirements
            stack_payload = event.manifest_data.get("stack_payload", {})
            processed_payload = stack_payload
            processing_applied = False

            # Check if merging is required
            if processing_requirements.get("merge_manifests", False):
                current_stack = {}
                if self._state_manager:
                    current_stack = self._state_manager.get_current_stack() or {}
                processed_payload = self.merge_stacks(current_stack, processed_payload)
                processing_applied = True

                if self.logger:
                    self.logger.info("Stack merging completed as required by analysis")

            # Check if expression resolution is required
            if processing_requirements.get("resolve_expressions", False):
                resolved_json = self.resolve_expressions(json.dumps(processed_payload))
                processed_payload = json.loads(resolved_json)
                processing_applied = True

                if self.logger:
                    self.logger.info("Expression resolution completed as required by analysis")

            # If processing was applied, update the event's payload in-place so the
            # orchestrator handler (which runs next on the same STACK_ANALYZED event
            # via publish_sync's sequential execution) sees the processed payload.
            if processing_applied:
                event.stack_payload = processed_payload
                event.manifest_data["stack_payload"] = processed_payload

                processed_event = StackProcessedEvent(
                    event_type=EventType.STACK_PROCESSED,
                    source_component="stack_processor",
                    correlation_id=event.correlation_id,
                    stack_name=event.stack_name,
                    action=event.action,
                    stack_payload=processed_payload,
                    original_payload=stack_payload,
                    processing_applied=list(processing_requirements.keys()),
                )
                self.event_bus.publish_sync(processed_event)

                if self.logger:
                    self.logger.info(
                        f"Published processed stack event with applied processing: {processing_requirements}"
                    )

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error processing analyzed stack: {e}")

    def merge_stacks(self, current: dict, next: dict) -> dict:
        """Merge current and next stacks intelligently."""
        try:
            if not current:
                current = {}

            stack_1 = Stack(manifest=current)
            stack_2 = Stack(manifest=next)
            merged = stack_1.merge(stack_2)

            # Publish merge event
            merge_event = StackMergedEvent(
                event_type=EventType.STACK_MERGED,
                source_component="stack_processor",
                current_stack=current,
                next_stack=next,
                stack_payload=merged.manifest,
                merge_strategy="intelligent_merge",
            )
            self.event_bus.publish_sync(merge_event)

            if self.logger:
                self.logger.info("Successfully merged stacks")

            return merged.manifest

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error merging stacks: {e}")
            return next  # Fallback to next stack

    def resolve_expressions(self, stack_json: str, current_stack: dict | None = None) -> str:
        """Resolve dynamic expressions in stack definitions."""
        try:
            expressions = re.findall(r"\$\(([\s0-9a-zA-Z_-]+)\)", stack_json)
            result = stack_json
            resolved_expressions = {}

            for expression in expressions:
                parts = expression.split()
                if len(parts) != 2:
                    if self.logger:
                        self.logger.warning(f"Invalid expression format: {expression}")
                    continue

                expr, var = parts
                resolved_value = ""

                try:
                    if expr == "find":
                        resolved_value = get_package_share_directory(var)
                    elif expr == "env":
                        resolved_value = os.getenv(var, "")
                    elif expr == "arg":
                        if current_stack:
                            resolved_value = current_stack.get("args", {}).get(var, "")
                        if self.logger:
                            self.logger.info(f"Resolved arg {var}: {resolved_value}")

                    resolved_expressions[expression] = resolved_value
                    result = re.sub(
                        r"\$\(" + re.escape(expression) + r"\)",
                        resolved_value,
                        result,
                        count=1,
                    )
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Failed to resolve expression {expression}: {e}")
                    continue

            # Publish transformation event if any expressions were resolved
            if resolved_expressions:
                transform_event = StackTransformedEvent(
                    event_type=EventType.STACK_TRANSFORMED,
                    source_component="stack_processor",
                    original_stack=json.loads(stack_json),
                    stack_payload=json.loads(result),
                    expressions_resolved=resolved_expressions,
                    transformation_type="expression_resolution",
                )
                self.event_bus.publish_sync(transform_event)

                if self.logger:
                    self.logger.info(f"Resolved {len(resolved_expressions)} expressions")

            return result

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error resolving expressions: {e}")
            return stack_json  # Return original on error

    def parse_payload(self, payload: dict) -> dict:
        """Parse and normalize different payload formats."""
        try:
            parsed = self.stack_parser.parse_payload(payload)
            if parsed and parsed != payload:
                if self.logger:
                    self.logger.info("Parsed stack payload using stack parser utility")
                return parsed
            return payload
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error parsing payload: {e}")
            return payload


class StackManager:
    """Main stack management subsystem coordinator."""

    def __init__(self, event_bus: EventBus, logger=None):
        self.event_bus = event_bus
        self.logger = logger

        # Initialize components
        self.state_manager = StackStateManager(event_bus, logger)
        self.analyzer = StackAnalyzer(event_bus, logger)
        self.processor = StackProcessor(event_bus, logger, state_manager=self.state_manager)

        if self.logger:
            self.logger.info("StackManager subsystem initialized")

    def get_state_manager(self) -> StackStateManager:
        """Get state manager."""
        return self.state_manager

    def get_analyzer(self) -> StackAnalyzer:
        """Get analyzer."""
        return self.analyzer

    def get_processor(self) -> StackProcessor:
        """Get processor."""
        return self.processor
