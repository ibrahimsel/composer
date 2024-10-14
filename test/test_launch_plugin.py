import unittest
import rclpy
from composer.launch_plugin import MutoDefaultLaunchPlugin
from unittest.mock import MagicMock, patch
import asyncio
from muto_msgs.srv import LaunchPlugin



class TestLaunchPlugin(unittest.TestCase):
    
    def setUp(self) -> None:
        self.node = MutoDefaultLaunchPlugin()
        self.node.async_loop = MagicMock()
        self.node.get_logger = MagicMock()
    
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

    def test_handle_composed_stack(self):
        pass
    
    @patch("composer.launch_plugin.LocalMode")
    def test_handle_local_launch(self, mock_local_mode):
        self.node.ws_full_path = None
        self.node.launcher_path = None
        self.node.launcher_full_path = None
        mock_local_mode.ws_full_path = "/src/dummy_ws/mock_path"
        mock_local_mode.launcher_path_relative_to_ws = "/mock_path"
        
        

    
    def test_source_workspace(self):
        pass
    
    @patch("composer.launch_plugin.RepoMode")
    def test_handle_repo_launch(self, mock_repo_mode):
        first_value = "/mock/pacth"
        mock_repo_mode.launch_file_name = first_value
        self.node.launcher_path = None
        self.node.handle_repo_launch(mock_repo_mode)
        self.assertEqual(self.node.launcher_path, first_value)
        
    
    def test_handle_start(self):
        pass
    
    
    def test_on_launch_done(self):
        self.node.launch_description = MagicMock()
        self.node.launch_service = MagicMock()
        future = MagicMock()
        future.result.return_value = [None, None]
        self.node.on_launch_done(future)
        self.assertIsNone(self.node.launch_description)
        self.assertIsNone(self.node.launch_service)

    
    def test_on_launch_done_exception(self):
        self.node.launch_description = MagicMock()
        self.node.launch_service = MagicMock()
        future = MagicMock()
        future.result.return_value = []
        self.node.on_launch_done(future)
        self.node.get_logger().warn.assert_called_once_with("Launch failed: not enough values to unpack (expected 2, got 0)")
        
                
    
    @patch("composer.launch_plugin.subprocess")
    def test_build_workspace(self, mock_subprocess):
        self.node.build_workspace()
        mock_subprocess.run.assert_called_once_with(['colcon', 'build', '--symlink-install', '--cmake-args', '-DCMAKE_BUILD_TYPE=Release'], check=True)
    
    def test_handle_kill(self):
        pass
    
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
