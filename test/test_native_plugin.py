import unittest
import rclpy
from unittest.mock import MagicMock, patch
<<<<<<< Updated upstream
from composer.native_plugin import MutoDefaultNativePlugin
=======
from composer.plugins.native_plugin import MutoDefaultNativePlugin
>>>>>>> Stashed changes

class TestNativePlugin(unittest.TestCase):
    
    def setUp(self):
        self.node = MutoDefaultNativePlugin()
        self.get_logger = MagicMock()
    
    def tearDown(self):
        self.node.destroy_node()
        
    @classmethod
    def setUpClass(cls) -> None:
        rclpy.init()
        
    @classmethod
    def tearDownClass(cls) -> None:
        rclpy.shutdown()
    
<<<<<<< Updated upstream
    @patch("composer.native_plugin.MutoDefaultNativePlugin.prep_native")
    @patch("composer.native_plugin.NativePlugin")
=======
    @patch("composer.plugins.native_plugin.MutoDefaultNativePlugin.prep_native")
    @patch("composer.plugins.native_plugin.NativePlugin")
>>>>>>> Stashed changes
    def test_handle_native(self, mock_native_plugin, mock_prep_native):
        mock_native_plugin.request(start=True)
        mock_native_plugin.response(success=False, err_msg='')
        
        self.node.current_stack = MagicMock()
        self.node.current_stack.mode = "native"
        
        self.node.handle_native(mock_native_plugin.request, mock_native_plugin.response)
        mock_prep_native.assert_called_once()

    @patch.object(MutoDefaultNativePlugin, "get_logger")
<<<<<<< Updated upstream
    @patch("composer.native_plugin.MutoDefaultNativePlugin.prep_native")
    @patch("composer.native_plugin.NativePlugin")
=======
    @patch("composer.plugins.native_plugin.MutoDefaultNativePlugin.prep_native")
    @patch("composer.plugins.native_plugin.NativePlugin")
>>>>>>> Stashed changes
    def test_handle_native_container(self, mock_native_plugin, mock_prep_native, mock_get_logger):
        mock_native_plugin.request(start=True)
        mock_native_plugin.response(success=False, err_msg='')
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        self.node.current_stack = MagicMock()
        self.node.current_stack.mode = "container"
        
        self.node.handle_native(mock_native_plugin.request, mock_native_plugin.response)
        mock_prep_native.assert_not_called()
        mock_logger.warn.assert_called_once_with("Skipping NativePlugin as the stack is in container mode")

    @patch.object(MutoDefaultNativePlugin, "get_logger")
<<<<<<< Updated upstream
    @patch("composer.native_plugin.MutoDefaultNativePlugin.prep_native")
    @patch("composer.native_plugin.NativePlugin")
=======
    @patch("composer.plugins.native_plugin.MutoDefaultNativePlugin.prep_native")
    @patch("composer.plugins.native_plugin.NativePlugin")
>>>>>>> Stashed changes
    def test_handle_native_other(self, mock_native_plugin, mock_prep_native, mock_get_logger):
        mock_native_plugin.request(start=True)
        mock_native_plugin.response(success=False, err_msg='')
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        self.node.current_stack = MagicMock()
        self.node.current_stack.mode = "other_mode"
        
        self.node.handle_native(mock_native_plugin.request, mock_native_plugin.response)
        mock_prep_native.assert_not_called()
        mock_logger.warn.assert_called_once_with("No mode provided. Skipping")
        self.assertTrue(mock_native_plugin.response.success)


    @patch.object(MutoDefaultNativePlugin, "get_logger")
<<<<<<< Updated upstream
    @patch("composer.native_plugin.MutoDefaultNativePlugin.prep_native")
    @patch("composer.native_plugin.NativePlugin")
=======
    @patch("composer.plugins.native_plugin.MutoDefaultNativePlugin.prep_native")
    @patch("composer.plugins.native_plugin.NativePlugin")
>>>>>>> Stashed changes
    def test_handle_native_request_false(self, mock_native_plugin, mock_prep_native, mock_get_logger):
        mock_native_plugin.request = None
        mock_native_plugin.response(success=None, err_msg='')
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        self.node.current_stack = MagicMock()
        self.node.current_stack.mode = "other_mode"
        
        self.node.handle_native(mock_native_plugin.request, mock_native_plugin.response)    
            
        mock_prep_native.assert_not_called()
        mock_logger.warn.assert_called_once_with("Exception: 'NoneType' object has no attribute 'start'")
        self.assertFalse(mock_native_plugin.response.success)
        self.assertEqual(mock_native_plugin.response.err_msg, "'NoneType' object has no attribute 'start'")

<<<<<<< Updated upstream
    @patch("composer.native_plugin.MutoDefaultNativePlugin.handle_local_native")
    @patch("composer.native_plugin.MutoDefaultNativePlugin.handle_repo_native")
=======
    @patch("composer.plugins.native_plugin.MutoDefaultNativePlugin.handle_local_native")
    @patch("composer.plugins.native_plugin.MutoDefaultNativePlugin.handle_repo_native")
>>>>>>> Stashed changes
    def test_prep_native_repo(self, mock_repo_native, mock_local_native):
        self.node.prep_native("repo")
        mock_repo_native.assert_called_once()
        mock_local_native.assert_not_called()
        
<<<<<<< Updated upstream
    @patch("composer.native_plugin.MutoDefaultNativePlugin.handle_local_native")
    @patch("composer.native_plugin.MutoDefaultNativePlugin.handle_repo_native")
=======
    @patch("composer.plugins.native_plugin.MutoDefaultNativePlugin.handle_local_native")
    @patch("composer.plugins.native_plugin.MutoDefaultNativePlugin.handle_repo_native")
>>>>>>> Stashed changes
    def test_prep_native_local(self, mock_repo_native, mock_local_native):
        self.node.prep_native("local")
        mock_repo_native.assert_not_called()
        mock_local_native.assert_called_once()

<<<<<<< Updated upstream
    @patch("composer.native_plugin.MutoDefaultNativePlugin.handle_local_native")
    @patch("composer.native_plugin.MutoDefaultNativePlugin.handle_repo_native")
=======
    @patch("composer.plugins.native_plugin.MutoDefaultNativePlugin.handle_local_native")
    @patch("composer.plugins.native_plugin.MutoDefaultNativePlugin.handle_repo_native")
>>>>>>> Stashed changes
    def test_prep_native_nomode(self, mock_repo_native, mock_local_native):
        self.node.prep_native("nomode")
        mock_local_native.assert_not_called()
        mock_repo_native.assert_not_called()


    @patch("os.path.join")
    @patch("os.path.expanduser")
<<<<<<< Updated upstream
    @patch("composer.native_plugin.MutoDefaultNativePlugin.find_launcher")
    @patch("composer.native_plugin.RepoMode")
    @patch("composer.native_plugin.MutoArchive")
=======
    @patch("composer.plugins.native_plugin.MutoDefaultNativePlugin.find_launcher")
    @patch("composer.plugins.native_plugin.RepoMode")
    @patch("composer.plugins.native_plugin.MutoArchive")
>>>>>>> Stashed changes
    def test_handle_repo_native(self, mock_muto_archive, mock_repo_mode, mock_find_launcher, mock_os_expanduser, mock_os_join):
        self.node.current_stack = MagicMock()
        self.node.repo_pub = MagicMock()
        self.node.archive = MagicMock()
        launch_file_name = "launch_file"
        self.node.current_stack.native.repo.launch_file_name = launch_file_name
        self.node.handle_repo_native()
        self.node.archive.decompress_into_local.assert_called_once()
        mock_find_launcher.assert_called_once_with(f"{mock_os_join()}", launch_file_name)
    
    
    @patch("os.walk")
    @patch("os.path.join")
    def test_find_launcher(self, mock_join, mock_walk):
        ws_path = "/mock_ws"
        launcher_name = "mock_launcher"
        mock_walk.return_value = [("root_1"),("dirs_1"),("files_1")], [("root_2"),("dirs_2"),("mock_launcher")], [("root_3"),("dirs_3"),("files_3")]
        returned_value = self.node.find_launcher(ws_path, launcher_name)
        mock_walk.assert_called_once_with("/mock_ws")
        mock_join.assert_called_once_with("root_2", "mock_launcher")
        self.assertEqual(returned_value, mock_join())        
 
 
    @patch("os.walk")
    @patch("os.path.join")
    def test_find_launcher_none(self, mock_join, mock_walk):
        ws_path = "/mock_ws"
        launcher_name = "mock_launcher"
        returned_value = self.node.find_launcher(ws_path, launcher_name)
        mock_walk.assert_called_once_with("/mock_ws")
        mock_join.assert_not_called()
        self.assertEqual(returned_value, None)  
 
    
    @patch("os.chdir")
<<<<<<< Updated upstream
    @patch("composer.native_plugin.LocalMode")
=======
    @patch("composer.plugins.native_plugin.LocalMode")
>>>>>>> Stashed changes
    def test_handle_local_native(self, mock_local_mode, mock_chdir):
        self.node.local_pub = MagicMock()
        self.node.current_stack = MagicMock()
        ws_full_path = "/mock/ws/full/path"
        ws_relative_path = "/mock/ws/relative/path"
        
        self.node.current_stack.native.local.launcher_path_relative_to_ws = ws_relative_path
        self.node.current_stack.native.local.ws_full_path = ws_full_path
        
        
        self.node.handle_local_native()
        mock_chdir.assert_called_once_with(ws_full_path)
        mock_local_mode.assert_called_once()
        self.node.local_pub.publish.assert_called_once_with(mock_local_mode())
        