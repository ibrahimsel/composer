import unittest
import rclpy
import json
from unittest.mock import MagicMock, patch
from composer.compose_plugin import MutoDefaultComposePlugin
from std_msgs.msg import String


class TestComposePlugin(unittest.TestCase):
    
    def setUp(self):
        self.node = MutoDefaultComposePlugin()
        self.node.incoming_stack = None
        self.node.composed_stack_publisher = MagicMock()
     
    def tearDown(self):
        self.node.destroy_node()
    
    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()
    
    
    def test_handle_raw_stack(self):
        self.node.incoming_stack = None
        stack_msg = String(data='{"name": "Muto Run Rototui from repo", "context": "eteration_office", "stackId": "org.eclipse.muto.sandbox:muto_repo_test_stack", "container": {"image_name": "ros:humble", "container_name": "muto_launch_desc_container"}, "mode": "native", "url": "https://nexus.eteration.com/repository/muto/composer/raws_no_build/raws_cropped_no_build_install.tar.gz", "native": {"native_mode": "repo", "repo": {"path_to_download_relative_to_home_dir": "muto_rototui_autoware_ws", "launch_file_name": "run_autoware.launch.py"}, "local": {"ws_full_path": "", "launcher_path_relative_to_ws": ""}}, "source": {"ros": "/opt/ros/humble/setup.bash", "workspace": "/home/sel/muto_workspaces/install/setup.bash", "autoware": "/home/sel/autoware/install/setup.bash"}, "args": {"launch_muto": "false", "launch_fms": "false", "launch_record_rosbag": "false", "launch_safety_plc": "false", "launch_logger": "false", "launch_css": "false", "vehicle_model": "rototui_vehicle", "sensor_model": "rototui_sensor_kit", "map_path": "/home/sel/autoware_map/tofas_rd6", "lanelet2_map_file": "64_prod_lanelet_finetuning.osm", "pointcloud_map_file": "pointcloud_map.pcd", "map_projector_info_path": "/home/sel/autoware_map/tofas_rd6/map_projector_info.yaml", "launch_ouster": "false", "launch_imu": "false", "launch_gnss": "false", "launch_camera0": "false", "launch_camera1": "false", "launch_realsense": "false", "camera0_device": "/dev/video0", "camera1_device": "/dev/video1", "ouster_host_ip": "192.168.1.206", "gnss_host_ip": "192.168.1.223", "vehicle_id": "att-999", "rviz_respawn": "false"}}') 
        self.node.handle_raw_stack(stack_msg)
        self.assertEqual(self.node.incoming_stack, json.loads(stack_msg.data))
    
    @patch("composer.compose_plugin.MutoDefaultComposePlugin.publish_composed_stack")
    @patch("composer.compose_plugin.ComposePlugin")
    def test_handle_compose(self, mock_compose_plugin, mock_publish_composed_stack):
        request = mock_compose_plugin.request(start = True)
        response = mock_compose_plugin.response(success = None, err_msg = None)
        
        self.node.handle_compose(request, response)
        
        mock_publish_composed_stack.assert_called_once()
        self.assertTrue(response.success)
        
        
    @patch("composer.compose_plugin.MutoDefaultComposePlugin.publish_composed_stack")
    @patch("composer.compose_plugin.ComposePlugin")
    def test_handle_compose_exception(self, mock_compose_plugin, mock_publish_composed_stack):
        request = mock_compose_plugin.request = None
        response = mock_compose_plugin.response(success = None, err_msg = None)
        
        self.node.handle_compose(request, response)
        
        mock_publish_composed_stack.assert_not_called()
        self.assertFalse(response.success)
        
        
    @patch("composer.compose_plugin.LocalMode")
    @patch("composer.compose_plugin.RepoMode")
    @patch("composer.compose_plugin.NativeMode")
    @patch("composer.compose_plugin.StackManifest")
    def test_publish_composed_stack_no_stack(self, mock_stack_manifest, mock_native_mode, mock_repo_mode, mock_local_mode):
        self.node.incoming_stack = None
        self.node.publish_composed_stack()
        mock_native_mode.assert_not_called()
        mock_repo_mode.assert_not_called()
        mock_stack_manifest.assert_not_called()
        mock_local_mode.assert_not_called()
        
        
    @patch("composer.compose_plugin.LocalMode")
    @patch("composer.compose_plugin.RepoMode")
    @patch("composer.compose_plugin.NativeMode")
    @patch("composer.compose_plugin.StackManifest")
    def test_publish_composed_stack(self, mock_stack_manifest, mock_native_mode, mock_repo_mode, mock_local_mode):
        stack_msg = String(data='{"name": "Muto Run Rototui from repo", "context": "eteration_office", "stackId": "org.eclipse.muto.sandbox:muto_repo_test_stack", "container": {"image_name": "ros:humble", "container_name": "muto_launch_desc_container"}, "mode": "native", "url": "https://nexus.eteration.com/repository/muto/composer/raws_no_build/raws_cropped_no_build_install.tar.gz", "native": {"native_mode": "repo", "repo": {"path_to_download_relative_to_home_dir": "muto_rototui_autoware_ws", "launch_file_name": "run_autoware.launch.py"}, "local": {"ws_full_path": "", "launcher_path_relative_to_ws": ""}}, "source": {"ros": "/opt/ros/humble/setup.bash", "workspace": "/home/sel/muto_workspaces/install/setup.bash", "autoware": "/home/sel/autoware/install/setup.bash"}, "args": {"launch_muto": "false", "launch_fms": "false", "launch_record_rosbag": "false", "launch_safety_plc": "false", "launch_logger": "false", "launch_css": "false", "vehicle_model": "rototui_vehicle", "sensor_model": "rototui_sensor_kit", "map_path": "/home/sel/autoware_map/tofas_rd6", "lanelet2_map_file": "64_prod_lanelet_finetuning.osm", "pointcloud_map_file": "pointcloud_map.pcd", "map_projector_info_path": "/home/sel/autoware_map/tofas_rd6/map_projector_info.yaml", "launch_ouster": "false", "launch_imu": "false", "launch_gnss": "false", "launch_camera0": "false", "launch_camera1": "false", "launch_realsense": "false", "camera0_device": "/dev/video0", "camera1_device": "/dev/video1", "ouster_host_ip": "192.168.1.206", "gnss_host_ip": "192.168.1.223", "vehicle_id": "att-999", "rviz_respawn": "false"}}') 
        self.node.incoming_stack = json.loads(stack_msg.data)
        native = self.node.incoming_stack.get("native", {})
        self.node.publish_composed_stack()
        
        mock_stack_manifest.assert_called_once()
        mock_native_mode.assert_called_once()
        mock_repo_mode.assert_called_once()
        mock_local_mode.assert_called_once()
        self.assertEqual(mock_stack_manifest().name, self.node.incoming_stack.get("name", ""))
        self.assertEqual(mock_stack_manifest().context, self.node.incoming_stack.get("context", ""))
        self.assertEqual(mock_stack_manifest().mode, self.node.incoming_stack.get("mode", ""))
        self.assertEqual(mock_stack_manifest().stack_id, self.node.incoming_stack.get("stackId", ""))
        self.assertEqual(mock_stack_manifest().workspace_url, self.node.incoming_stack.get("url", "https://"))
        self.assertEqual(mock_stack_manifest().native.native_mode, native.get("native_mode", ""))        
        self.assertEqual(mock_stack_manifest().native.repo.path_to_download_relative_to_home_dir, native.get("repo", {}).get("path_to_download_relative_to_home_dir", ""))
        self.assertEqual(mock_stack_manifest().native.repo.launch_file_name, native.get("repo", {}).get("launch_file_name", ""))
        self.assertEqual(mock_stack_manifest().native.local.ws_full_path, native.get("local", {}).get("ws_full_path", ""))
        self.assertEqual(mock_stack_manifest().native.local.launcher_path_relative_to_ws, native.get("local", {}).get("launcher_path_relative_to_ws", ""))
    
    
    def test_publish_composed_stack_except(self):
        self.node.incoming_stack = 5
        with self.assertRaises(Exception):
            self.node.publish_composed_stack()

        
    
    if __name__ == "__main__":
        unittest.main()

    