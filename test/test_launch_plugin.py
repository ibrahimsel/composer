import unittest
import rclpy
from composer.plugins.launch_plugin import MutoDefaultLaunchPlugin
from unittest.mock import MagicMock, patch
import asyncio
from muto_msgs.srv import LaunchPlugin
import json
import os

class TestLaunchPlugin(unittest.TestCase):
    
    def setUp(self) -> None:
        self.node = MutoDefaultLaunchPlugin()
        self.node.async_loop = MagicMock()
        self.node.get_logger = MagicMock()
        self.node.current_stack = MagicMock()
    
    def tearDown(self) -> None:
        self.node.destroy_node()
    
    @classmethod
    def setUpClass(cls) -> None:
        rclpy.init()
                
    @classmethod
    def tearDownClass(cls) -> None:
        rclpy.shutdown()
        
    @patch("composer.plugins.launch_plugin.MutoDefaultLaunchPlugin.source_workspaces")    
    @patch("os.chdir")
    @patch("composer.plugins.launch_plugin.LaunchPlugin")
    def test_handle_start_exception(self, mock_launch_plugin, mock_os, mock_ws):
        mock_launch_plugin.request = None
        mock_launch_plugin.response(success=None, err_msg='')
        self.node.current_stack.native.native_mode = "local"
        self.node.launch_arguments = ['test:=mock']
        self.node.ws_full_path = MagicMock()
        self.node.launcher_full_path = MagicMock()
        self.node.handle_start(mock_launch_plugin.request, mock_launch_plugin.response)
        mock_os.assert_not_called()
        mock_ws.assert_not_called()
        self.assertFalse(mock_launch_plugin.response.success)
        self.assertEqual(mock_launch_plugin.response.err_msg,"'NoneType' object has no attribute 'start'")
    
    def test_run_async_loop(self):
        self.node.run_async_loop()
        self.node.async_loop.stop.assert_called_once()
        self.node.async_loop.run_forever.assert_called_once()
    
    def test_get_stack(self):
        pass
    
    def test_find_file(self):
        pass
    
    def test_source_workspaces(self):
        pass
    
    def test_handle_start(self):
        pass
    
    @patch("subprocess.run")
    @patch("os.path")
    @patch("os.access")
    @patch("os.chmod")
    def test_run_script(self, mock_chmod, mock_access, mock_path, mock_run):
        script_path = "/mock/script/path"
        self.node.run_script(script_path)
        mock_chmod.assert_not_called()
        mock_access.assert_called_once_with(script_path, os.X_OK)
        mock_path.isfile.assert_called_once_with(script_path)
        mock_run.assert_called_once_with(['/mock/script/path'], check=True, capture_output=True, text=True)
        
    
    @patch("subprocess.run")
    @patch("os.path")
    @patch("os.access")
    @patch("os.chmod")
    def test_run_script_is_not_file(self, mock_chmod, mock_access, mock_path, mock_run):
        mock_path.isfile.return_value = False
        script_path = "/mock/script/path"
        with self.assertRaises(FileNotFoundError):
            self.node.run_script(script_path)
        mock_chmod.assert_not_called()
        mock_access.assert_not_called()
        mock_path.isfile.assert_called_once_with(script_path)
    
    
    @patch("subprocess.run")
    @patch("os.path")
    @patch("os.access")
    @patch("os.chmod")
    def test_run_script_not_access(self, mock_chmod, mock_access, mock_path, mock_run):
        mock_access.return_value = False
        script_path = "/mock/script/path"
        self.node.run_script(script_path)
        mock_chmod.assert_called_once_with(script_path, 0o755)
        
        mock_chmod.assert_called_once_with(script_path, 0o755)
        mock_access.assert_called_once_with(script_path, os.X_OK)
        mock_path.isfile.assert_called_once_with(script_path)
    
    
    
    #TEST
    @patch("composer.plugins.launch_plugin.CoreTwin")
    @patch("composer.plugins.launch_plugin.LaunchPlugin")
    def test_handle_kill(self, mock_launch_plugin, mock_core_twin):
        request = mock_launch_plugin.request
        request.start = True
        response = mock_launch_plugin.response
        response.success = None
        response.err_msg = None
        self.node.current_stack = "MockStack"

    
        
    @patch("composer.plugins.launch_plugin.LaunchPlugin")
    def test_handle_apply(self, mock_launch_plugin):
        request = mock_launch_plugin.request
        request.start = True
        response = mock_launch_plugin.response
        response.success = None
        response.err_msg = None
        
        self.node.handle_apply(request, response)        
        self.assertTrue(response.success)
        self.assertEqual(response.err_msg, "")
        self.node.get_logger().info.assert_called_once_with("Handling apply operation.")
        
    @patch("composer.plugins.launch_plugin.LaunchPlugin")
    def test_handle_apply_start_none(self, mock_launch_plugin):
        request = mock_launch_plugin.request
        request.start = None
        response = mock_launch_plugin.response
        response.success = None
        response.err_msg = None
        
        self.node.handle_apply(request, response)        
        self.assertFalse(response.success)
        self.assertEqual(response.err_msg, "Start flag not set in request.")
        self.node.get_logger().warning.assert_called_once_with("Start flag not set in apply request.")

    
    def test_set_stack_done_callback_true(self):
        future = MagicMock()
        future.result.return_value = True
        self.node.set_stack_done_callback(future)
        self.node.get_logger().info.assert_called_once_with("Edge device stack setting completed successfully.")
    
    def test_set_stack_done_callback_false(self):
        future = MagicMock()
        future.result.return_value = False
        self.node.set_stack_done_callback(future)    
        self.node.get_logger().warning.assert_called_once_with("Edge device stack setting failed. Please try your request again.")    
    
    
    
    
    
if __name__ == "__main__":
    unittest.main()