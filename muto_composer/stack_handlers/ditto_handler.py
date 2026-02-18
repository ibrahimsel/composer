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

from __future__ import annotations

from typing import Any

from muto_composer.model.stack import Stack
from muto_composer.plugins.base_plugin import (
    BasePlugin,
    StackContext,
    StackOperation,
    StackTypeHandler,
)
from muto_composer.workflow.launcher import Ros2LaunchParent


class DittoStackHandler(StackTypeHandler):
    """Handler for Ditto (stack/legacy) format stacks."""

    def __init__(self, logger=None):
        self.logger = logger
        self.managed_launchers = {}

    def can_handle(self, payload: dict[str, Any]) -> bool:
        """
        Check if payload matches legacy format:
        - No proper metadata.content_type (not a properly defined solution)
        - Has launch-related structure (node, composable, or legacy patterns)
        """
        if not isinstance(payload, dict):
            return False

        metadata = payload.get("metadata", {})
        content_type = metadata.get("content_type")

        # If there's a content_type, it's a properly defined solution
        if content_type and content_type not in ("stack/json", "stack/ditto", "stack/legacy"):
            return False

        # Check for legacy launch structures
        has_nodes = bool(payload.get("node") or payload.get("composable"))
        has_launch = bool(payload.get("launch"))
        has_legacy_patterns = bool(
            payload.get("launch_description_source") or (payload.get("on_start") and payload.get("on_kill"))
        )

        return has_nodes or has_launch or has_legacy_patterns

    def apply_to_plugin(self, plugin: BasePlugin, context: StackContext, request, response) -> bool:
        """Double dispatch: delegate to plugin's accept method."""

        try:
            if context.operation == StackOperation.PROVISION:
                return True
            elif context.operation == StackOperation.START:
                return self._start_ditto(context, plugin)
            elif context.operation == StackOperation.KILL:
                return self._kill_ditto(context, plugin)
            elif context.operation == StackOperation.APPLY:
                return self._apply_ditto(context, plugin)
            elif context.operation == StackOperation.COMPOSE:
                return True
            else:
                if self.logger:
                    self.logger.warning(f"Unsupported operation for Ditto stack: {context.operation}")
                return False
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error processing Ditto stack operation: {e}")
            return False

    def _start_ditto(self, context: StackContext, plugin: BasePlugin) -> bool:
        """Start a Ditto stack."""
        try:
            # Check if it's a script-based legacy stack (on_start/on_kill)
            if context.stack_data.get("on_start") and context.stack_data.get("on_kill"):
                if self.logger:
                    self.logger.info("Ditto script-based stack start delegated to plugin")
                return True

            # Kill any previous launch for this stack before starting
            self._kill_ditto(context, plugin)

            launcher = Ros2LaunchParent([])

            # Try node/composable arrays
            if context.stack_data.get("node") or context.stack_data.get("composable"):
                stack = Stack(manifest=context.stack_data)
                stack.launch(launcher)
                self.managed_launchers[context.hash] = launcher
                plugin._managed_launchers[context.hash] = launcher
                return True

            # Try launch structure
            launch_data = context.stack_data.get("launch")
            if launch_data:
                stack = Stack(manifest=launch_data)
                stack.launch(launcher)
                self.managed_launchers[context.hash] = launcher
                plugin._managed_launchers[context.hash] = launcher
                return True

            if self.logger:
                self.logger.warning("No recognizable launch structure in Ditto stack")
            return False

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error starting Ditto stack: {e}")
            return False

    def _kill_ditto(self, context: StackContext, plugin: BasePlugin) -> bool:
        """Kill a Ditto stack."""
        try:
            launcher = self.managed_launchers.get(context.hash)
            if launcher:
                launcher.kill()
                self.managed_launchers.pop(context.hash, None)
                plugin._managed_launchers.pop(context.hash, None)
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error killing Ditto stack: {e}")
            return False

    def _apply_ditto(self, context: StackContext, plugin: BasePlugin) -> bool:
        """Apply a Ditto stack configuration."""
        try:
            # Kill then start
            self._kill_ditto(context, plugin)

            launcher = Ros2LaunchParent([])

            if context.stack_data.get("node") or context.stack_data.get("composable"):
                stack = Stack(manifest=context.stack_data)
                stack.apply(launcher)
                self.managed_launchers[context.hash] = launcher
                plugin._managed_launchers[context.hash] = launcher
                return True

            launch_data = context.stack_data.get("launch")
            if launch_data:
                stack = Stack(manifest=launch_data)
                stack.apply(launcher)
                self.managed_launchers[context.hash] = launcher
                plugin._managed_launchers[context.hash] = launcher
                return True

            if self.logger:
                self.logger.info("Ditto script-based stacks do not support apply (no-op)")
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error applying Ditto stack: {e}")
            return False
