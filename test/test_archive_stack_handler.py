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

import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, mock_open, patch

from composer.stack_handlers.archive_handler import ArchiveStackHandler


class TestArchiveStackHandler(TestCase):
    def setUp(self):
        self.logger = MagicMock()
        self.handler = ArchiveStackHandler(logger=self.logger)

    @patch("composer.stack_handlers.archive_handler.subprocess.run")
    def test_source_workspaces_runs_scripts(self, mock_run):
        current = SimpleNamespace(source=json.dumps({"ws": "/tmp/setup.sh"}))
        context = SimpleNamespace(workspace_path="/tmp/ws")
        mock_run.return_value.stdout = ""

        self.handler._source_workspaces(current, context)

        mock_run.assert_called_once()

    def test_start_archive_invokes_helpers(self):
        context = SimpleNamespace(
            stack_data={"launch": {"properties": {"launch_file": "demo.launch.py"}}},
            workspace_path="/tmp/ws",
        )
        plugin = MagicMock()
        current = MagicMock()
        self.handler._source_workspaces = MagicMock()
        self.handler._launch_via_ros2 = MagicMock(return_value=True)

        success = self.handler._start_archive(context, current, plugin)

        self.assertTrue(success)
        self.handler._source_workspaces.assert_called_once_with(current, context)
        self.handler._launch_via_ros2.assert_called_once()

    @patch("composer.stack_handlers.archive_handler.subprocess.Popen")
    @patch("composer.stack_handlers.archive_handler.os.chmod")
    @patch("composer.stack_handlers.archive_handler.open", new_callable=mock_open)
    def test_launch_via_ros2_invokes_ros_launch(self, mock_file, mock_chmod, mock_popen):
        plugin = MagicMock()
        plugin.find_file.return_value = "/tmp/ws/src/launch/demo.launch.py"
        context = SimpleNamespace(workspace_path="/tmp/ws")

        process = MagicMock()
        process.stdout = None
        process.stderr = None
        mock_popen.return_value = process
        self.handler._monitor_process = MagicMock()

        success = self.handler._launch_via_ros2(plugin, context, "demo.launch.py")

        self.assertTrue(success)
        plugin.find_file.assert_called_once()
        mock_popen.assert_called_once()
        self.handler._monitor_process.assert_called_once()

    @patch("composer.stack_handlers.archive_handler.os.killpg")
    def test_terminate_launch_process_cleans_up(self, mock_killpg):
        process = MagicMock()
        process.poll.return_value = None
        process.wait.return_value = 0
        process.pid = 1234
        self.handler._managed_processes["demo.launch.py"] = process

        self.handler._terminate_launch_process("demo.launch.py")

        mock_killpg.assert_called_once()
        self.assertEqual(self.handler._managed_processes, {})
