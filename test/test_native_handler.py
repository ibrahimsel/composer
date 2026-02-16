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
Unit tests for NativeStackHandler (MEP-0001 Phase 1c).

Tests can_handle(), provision validation, start/kill lifecycle,
and setup file sourcing.
"""

import unittest
from unittest.mock import MagicMock, patch

from muto_composer.plugins.base_plugin import StackContext, StackOperation
from muto_composer.stack_handlers.native_handler import NativeStackHandler


class TestNativeHandlerCanHandle(unittest.TestCase):
    """Test NativeStackHandler.can_handle()."""

    def setUp(self):
        self.handler = NativeStackHandler(logger=MagicMock())

    def test_accepts_stack_native(self):
        payload = {
            "metadata": {"content_type": "stack/native"},
            "launch": {"file": "/opt/ros/humble/share/turtlesim/launch/turtlesim.launch.py"},
        }
        self.assertTrue(self.handler.can_handle(payload))

    def test_rejects_stack_json(self):
        payload = {"metadata": {"content_type": "stack/json"}, "launch": {"node": []}}
        self.assertFalse(self.handler.can_handle(payload))

    def test_rejects_stack_archive(self):
        payload = {"metadata": {"content_type": "stack/archive"}}
        self.assertFalse(self.handler.can_handle(payload))

    def test_rejects_stack_declarative(self):
        payload = {"metadata": {"content_type": "stack/declarative"}}
        self.assertFalse(self.handler.can_handle(payload))

    def test_rejects_no_metadata(self):
        payload = {"launch": {"file": "/some/path"}}
        self.assertFalse(self.handler.can_handle(payload))

    def test_rejects_non_dict(self):
        self.assertFalse(self.handler.can_handle("not a dict"))
        self.assertFalse(self.handler.can_handle(None))


class TestNativeHandlerProvision(unittest.TestCase):
    """Test NativeStackHandler provision (validates launch file exists)."""

    def setUp(self):
        self.handler = NativeStackHandler(logger=MagicMock())
        self.plugin = MagicMock()

    def _make_context(self, stack_data):
        return StackContext(
            stack_data=stack_data,
            metadata=stack_data.get("metadata", {}),
            operation=StackOperation.PROVISION,
        )

    @patch("muto_composer.stack_handlers.native_handler.os.path.isfile")
    def test_provision_validates_launch_file_exists(self, mock_isfile):
        mock_isfile.return_value = True
        stack_data = {
            "metadata": {"content_type": "stack/native"},
            "launch": {"file": "/opt/ros/humble/share/turtlesim/launch/turtlesim.launch.py"},
            "source": {"setup_files": []},
        }
        ctx = self._make_context(stack_data)
        result = self.handler._provision_native(ctx, self.plugin)
        self.assertTrue(result)
        mock_isfile.assert_called_with("/opt/ros/humble/share/turtlesim/launch/turtlesim.launch.py")

    @patch("muto_composer.stack_handlers.native_handler.os.path.isfile")
    def test_provision_fails_missing_file(self, mock_isfile):
        mock_isfile.return_value = False
        stack_data = {
            "metadata": {"content_type": "stack/native"},
            "launch": {"file": "/nonexistent/path.launch.py"},
        }
        ctx = self._make_context(stack_data)
        result = self.handler._provision_native(ctx, self.plugin)
        self.assertFalse(result)

    def test_provision_fails_no_launch_file(self):
        stack_data = {
            "metadata": {"content_type": "stack/native"},
            "launch": {},
        }
        ctx = self._make_context(stack_data)
        result = self.handler._provision_native(ctx, self.plugin)
        self.assertFalse(result)

    @patch("muto_composer.stack_handlers.native_handler.os.path.isfile")
    def test_provision_sources_setup_files(self, mock_isfile):
        mock_isfile.return_value = True
        stack_data = {
            "metadata": {"content_type": "stack/native"},
            "launch": {"file": "/opt/test.launch.py"},
            "source": {"setup_files": ["/opt/ros/humble/setup.bash"]},
        }
        ctx = self._make_context(stack_data)
        with patch.object(self.handler, "_source_file") as mock_source:
            result = self.handler._provision_native(ctx, self.plugin)
            self.assertTrue(result)
            mock_source.assert_called_once_with("/opt/ros/humble/setup.bash")


class TestNativeHandlerStartKill(unittest.TestCase):
    """Test NativeStackHandler start and kill operations."""

    def setUp(self):
        self.handler = NativeStackHandler(logger=MagicMock())
        self.plugin = MagicMock()

    def _make_context(self, stack_data, operation):
        return StackContext(
            stack_data=stack_data,
            metadata=stack_data.get("metadata", {}),
            operation=operation,
        )

    @patch("muto_composer.stack_handlers.native_handler.subprocess.Popen")
    @patch("muto_composer.stack_handlers.native_handler.os.path.isfile", return_value=True)
    def test_start_launches_process(self, mock_isfile, mock_popen):
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        stack_data = {
            "metadata": {"content_type": "stack/native"},
            "launch": {"file": "/opt/test.launch.py", "args": {"bg_r": "100"}},
            "source": {"setup_files": []},
        }
        ctx = self._make_context(stack_data, StackOperation.START)
        result = self.handler._start_native(ctx, self.plugin)

        self.assertTrue(result)
        mock_popen.assert_called_once()
        # Verify the command includes the launch file and args
        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        self.assertIn("/opt/test.launch.py", cmd)
        self.assertIn("bg_r:=100", cmd)

    @patch("muto_composer.stack_handlers.native_handler.subprocess.Popen")
    @patch("muto_composer.stack_handlers.native_handler.os.path.isfile", return_value=True)
    def test_start_with_setup_files(self, mock_isfile, mock_popen):
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        stack_data = {
            "metadata": {"content_type": "stack/native"},
            "launch": {"file": "/opt/test.launch.py", "args": {}},
            "source": {"setup_files": ["/opt/ros/humble/setup.bash"]},
        }
        ctx = self._make_context(stack_data, StackOperation.START)
        result = self.handler._start_native(ctx, self.plugin)

        self.assertTrue(result)
        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        self.assertIn("source /opt/ros/humble/setup.bash", cmd)

    def test_kill_no_process(self):
        """Kill when no process is managed should succeed (no-op)."""
        stack_data = {
            "metadata": {"content_type": "stack/native"},
            "launch": {"file": "/opt/test.launch.py"},
        }
        ctx = self._make_context(stack_data, StackOperation.KILL)
        result = self.handler._kill_native(ctx, self.plugin)
        self.assertTrue(result)

    @patch("muto_composer.stack_handlers.native_handler.os.killpg")
    @patch("muto_composer.stack_handlers.native_handler.os.getpgid", return_value=100)
    def test_kill_terminates_process(self, mock_getpgid, mock_killpg):
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.wait.return_value = 0

        launch_file = "/opt/test.launch.py"
        self.handler._managed_launchers[launch_file] = mock_process

        stack_data = {
            "metadata": {"content_type": "stack/native"},
            "launch": {"file": launch_file},
        }
        ctx = self._make_context(stack_data, StackOperation.KILL)
        result = self.handler._kill_native(ctx, self.plugin)

        self.assertTrue(result)
        mock_killpg.assert_called_once()
        self.assertNotIn(launch_file, self.handler._managed_launchers)


class TestNativeHandlerApply(unittest.TestCase):
    """Test NativeStackHandler apply (kill + start)."""

    def setUp(self):
        self.handler = NativeStackHandler(logger=MagicMock())
        self.plugin = MagicMock()

    @patch.object(NativeStackHandler, "_start_native", return_value=True)
    @patch.object(NativeStackHandler, "_kill_native", return_value=True)
    def test_apply_calls_kill_then_start(self, mock_kill, mock_start):
        stack_data = {
            "metadata": {"content_type": "stack/native"},
            "launch": {"file": "/opt/test.launch.py"},
        }
        ctx = StackContext(
            stack_data=stack_data,
            metadata=stack_data["metadata"],
            operation=StackOperation.APPLY,
        )
        result = self.handler._apply_native(ctx, self.plugin)
        self.assertTrue(result)
        mock_kill.assert_called_once()
        mock_start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
