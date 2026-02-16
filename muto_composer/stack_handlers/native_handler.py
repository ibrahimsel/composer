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

import os
import subprocess
from typing import Any

from muto_composer.plugins.base_plugin import (
    BasePlugin,
    StackContext,
    StackOperation,
    StackTypeHandler,
)


class NativeStackHandler(StackTypeHandler):
    """Handler for stack/native type stacks.

    Launches locally-installed software via an existing launch file on the
    device. No archive download, no workspace build — the software is already
    installed (e.g. via apt, colcon build on the device, or a container mount).
    """

    def __init__(self, logger=None):
        self.logger = logger
        self._managed_launchers = {}

    def can_handle(self, payload: dict[str, Any]) -> bool:
        """Check for stack/native content_type."""
        if not isinstance(payload, dict):
            return False
        metadata = payload.get("metadata", {})
        content_type = metadata.get("content_type", "")
        return content_type == "stack/native"

    def apply_to_plugin(self, plugin: BasePlugin, context: StackContext, request, response) -> bool:
        """Double dispatch: delegate to plugin's accept method."""
        if context.operation == StackOperation.PROVISION:
            return self._provision_native(context, plugin)
        elif context.operation == StackOperation.START:
            return self._start_native(context, plugin)
        elif context.operation == StackOperation.KILL:
            return self._kill_native(context, plugin)
        elif context.operation == StackOperation.APPLY:
            return self._apply_native(context, plugin)
        else:
            if self.logger:
                self.logger.warning(f"Unsupported operation for native stack: {context.operation}")
            return False

    def _provision_native(self, context: StackContext, plugin: BasePlugin) -> bool:
        """Validate the launch file exists and source setup files."""
        try:
            launch_config = context.stack_data.get("launch", {})
            launch_file = launch_config.get("file", "")

            if not launch_file:
                if self.logger:
                    self.logger.error("No launch file specified in stack/native manifest")
                return False

            if not os.path.isfile(launch_file):
                if self.logger:
                    self.logger.error(f"Launch file does not exist: {launch_file}")
                return False

            # Source setup files if specified
            source_config = context.stack_data.get("source", {})
            setup_files = source_config.get("setup_files", [])
            for setup_file in setup_files:
                if not os.path.isfile(setup_file):
                    if self.logger:
                        self.logger.warning(f"Setup file not found: {setup_file}")
                    continue
                self._source_file(setup_file)

            if self.logger:
                self.logger.info(f"Native stack provisioned: {launch_file}")
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error provisioning native stack: {e}")
            return False

    def _start_native(self, context: StackContext, plugin: BasePlugin) -> bool:
        """Launch the native stack via ros2 launch."""
        try:
            self._kill_native(context, plugin)

            launch_config = context.stack_data.get("launch", {})
            launch_file = launch_config.get("file", "")
            launch_args = launch_config.get("args", {})

            if not launch_file or not os.path.isfile(launch_file):
                if self.logger:
                    self.logger.error(f"Launch file not found: {launch_file}")
                return False

            # Build the ros2 launch command
            cmd_parts = ["ros2", "launch", launch_file]
            for key, value in launch_args.items():
                cmd_parts.append(f"{key}:={value}")

            # Source setup files first
            source_config = context.stack_data.get("source", {})
            setup_files = source_config.get("setup_files", [])
            source_cmds = []
            for sf in setup_files:
                if os.path.isfile(sf):
                    source_cmds.append(f"source {sf}")

            if source_cmds:
                full_cmd = " && ".join(source_cmds) + " && " + " ".join(cmd_parts)
            else:
                full_cmd = " ".join(cmd_parts)

            process = subprocess.Popen(
                full_cmd,
                shell=True,
                executable="/bin/bash",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
            )

            self._managed_launchers[launch_file] = process

            if self.logger:
                self.logger.info(f"Native stack launched (PID {process.pid}): {launch_file}")
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error starting native stack: {e}")
            return False

    def _kill_native(self, context: StackContext, plugin: BasePlugin) -> bool:
        """Terminate the native stack launch process."""
        try:
            launch_config = context.stack_data.get("launch", {})
            launch_file = launch_config.get("file", "")

            process = self._managed_launchers.pop(launch_file, None)
            if process is not None:
                import signal

                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    process.wait(timeout=10)
                except ProcessLookupError:
                    pass
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    process.wait(timeout=5)
                if self.logger:
                    self.logger.info(f"Native stack terminated: {launch_file}")
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error killing native stack: {e}")
            return False

    def _apply_native(self, context: StackContext, plugin: BasePlugin) -> bool:
        """Apply = kill then start."""
        self._kill_native(context, plugin)
        return self._start_native(context, plugin)

    def _source_file(self, path: str) -> None:
        """Source a setup file and update the current environment."""
        try:
            result = subprocess.run(
                f"bash -c 'source {path} && env'",
                stdout=subprocess.PIPE,
                shell=True,
                executable="/bin/bash",
                check=True,
                text=True,
            )
            env_vars = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
            os.environ.update(env_vars)
            if self.logger:
                self.logger.info(f"Sourced: {path}")
        except subprocess.CalledProcessError as e:
            if self.logger:
                self.logger.error(f"Failed to source {path}: {e}")
