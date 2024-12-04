import unittest
import rclpy
from composer.plugins.launch_plugin import MutoDefaultLaunchPlugin
from unittest.mock import MagicMock, patch
import asyncio
from muto_msgs.srv import LaunchPlugin
import json

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
        
    def test_run_async_loop(self):
        self.node.run_async_loop()
        self.node.async_loop.stop.assert_called_once()
        self.node.async_loop.run_forever.assert_called_once()
    
    @patch("subprocess.PIPE")
    @patch("subprocess.Popen")
    def test_source_workspace(self, mock_popen, mock_pipe):
        self.node.current_stack.source = '{"test":"mock"}'
        self.node.source_workspaces()    
        mock_popen.assert_called_once_with('bash -c "source mock && env"', stdout=mock_pipe, shell=True, executable='/bin/bash')
        
    @patch("composer.plugins.launch_plugin.MutoDefaultLaunchPlugin.source_workspaces")    
    @patch("os.chdir")
    @patch("composer.plugins.launch_plugin.LaunchPlugin")
    def test_handle_start_local(self, mock_launch_plugin, mock_os, mock_ws):
        mock_launch_plugin.request(start=True)
        mock_launch_plugin.response(success=False, err_msg='')
        self.node.current_stack.native.native_mode = "local"
        self.node.launch_arguments = ['test:=mock']
        self.node.ws_full_path = MagicMock()
        self.node.launcher_full_path = MagicMock()
        self.node.handle_start(mock_launch_plugin.request, mock_launch_plugin.response)
        mock_os.assert_called_once()
        mock_ws.assert_called_once_with()
        self.node.get_logger().info.assert_called_once_with("Argument: test:=mock")
    
    @patch("composer.plugins.launch_plugin.MutoDefaultLaunchPlugin.source_workspaces")    
    @patch("os.chdir")
    @patch("composer.plugins.launch_plugin.LaunchPlugin")
    def test_handle_start_repo(self, mock_launch_plugin, mock_os, mock_source_ws, mock_build_ws):
        mock_launch_plugin.request(start=True)
        mock_launch_plugin.response(success=False, err_msg='')
        self.node.current_stack.native.native_mode = "repo"
        self.node.launch_arguments = ['test:=mock']
        self.node.ws_full_path = MagicMock()
        self.node.launcher_full_path = MagicMock()
        self.node.handle_start(mock_launch_plugin.request, mock_launch_plugin.response)
        mock_os.assert_called_once()
        mock_source_ws.assert_called_once_with()
        mock_build_ws.assert_called_once_with()
        self.node.get_logger().info.assert_called_with("launcher path: None")
        
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
    
    @patch("composer.plugins.launch_plugin.CoreTwin")
    @patch("composer.plugins.launch_plugin.LaunchPlugin")    
    def test_handle_kill(self, mock_launch_plugin, mock_core_twin):
        mock_launch_plugin.request(start=True)
        mock_launch_plugin.response(success=False, err_msg='')
        self.node.current_stack = MagicMock()
        self.node.set_stack_cli = MagicMock()
        self.node.launcher = MagicMock()
        mock_core_twin.Request = MagicMock()
        returned_value = self.node.handle_kill(mock_launch_plugin.request, mock_launch_plugin.response)
        mock_core_twin.Request.assert_called_once()
        self.node.set_stack_cli.call_async.assert_called_once_with(mock_core_twin.Request())
        self.node.launcher.kill.assert_called_once()
        self.assertEqual(returned_value, mock_launch_plugin.response)
    
    @patch("composer.plugins.launch_plugin.CoreTwin")
    @patch("composer.plugins.launch_plugin.LaunchPlugin")    
    def test_handle_kill_exception(self, mock_launch_plugin, mock_core_twin):
        mock_launch_plugin.request = None
        mock_launch_plugin.response(success=None, err_msg='')
        self.node.current_stack = MagicMock()
        self.node.set_stack_cli = MagicMock()
        self.node.launcher = MagicMock()
        mock_core_twin.Request = MagicMock()
        returned_value = self.node.handle_kill(mock_launch_plugin.request, mock_launch_plugin.response)
        
        mock_core_twin.Request.assert_not_called()
        self.node.set_stack_cli.call_async.assert_not_called()
        self.node.launcher.kill.assert_not_called()
        self.assertEqual(returned_value, None)
        self.assertFalse(mock_launch_plugin.response.success)
        self.assertEqual(mock_launch_plugin.response.err_msg,"'NoneType' object has no attribute 'start'")

    def test_handle_apply(self):
        request = LaunchPlugin.Request()
        request.start = True
        response = LaunchPlugin.Response()

        response = self.node.handle_apply(request, response)
        self.node.get_logger().info.assert_called_once_with("Handling apply")
        self.assertTrue(response.success)
        self.assertEqual(response.err_msg, "")
    
    def test_set_stack_done_callback_true(self):
        future = MagicMock()
        future.result.return_value = True
        self.node.set_stack_done_callback(future)
        self.node.get_logger().info.assert_called_once_with("Edge device stack setting is done successfully")
    
    def test_set_stack_done_callback_false(self):
        future = MagicMock()
        future.result.return_value = False
        self.node.set_stack_done_callback(future)    
        self.node.get_logger().warn.assert_called_once_with("Edge Device stack setting failed. Try your request again.")    
    

if __name__ == "__main__":
    unittest.main()
