import unittest
import rclpy
import json
from composer.muto_composer import MutoComposer
from unittest.mock import MagicMock, patch
from std_msgs.msg import String
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node

class TestMutoComposer(unittest.TestCase):
    
    @patch("composer.muto_composer.Pipeline")
    def setUp(self, mock_pipeline) -> None:
        self.node = MutoComposer()
        self.incoming_stack_topic = MagicMock()
        self.get_stack_cli = MagicMock()
        self.incoming_stack = None
        self.method = None
        self.raw_stack_publisher = MagicMock()
        self.pipeline_file_path = "/composer/config/config.yaml"
        self.router = MagicMock()
        self.logger = MagicMock()
        self.get_logger = MagicMock()
                

    def tearDown(self) -> None:
        self.node.destroy_node()
    
    @classmethod
    def setUpClass(cls) -> None:
        rclpy.init()

                
    @classmethod
    def tearDownClass(cls) -> None:
        rclpy.shutdown()
        
    @patch("json.loads")
    def test_on_stack_callback(self, mock_json):
        stack_msg = MagicMock()
        self.node.get_logger = MagicMock()
        self.node.get_stack_cli = MagicMock()
        self.node.get_stack_cli.call_async = MagicMock()
        
        stack_msg.method = "start"
        stack_msg.payload = json.dumps({"value": {"stackId": "8"}})
        mock_json.return_value = {"value": {"stackId": "8"}}
        
        self.node.on_stack_callback(stack_msg)
        self.assertEqual(self.node.method, "start")
        
        self.node.get_stack_cli.call_async.assert_called_once()
        async_value = self.node.get_stack_cli.call_async.return_value
        async_value.add_done_callback.assert_called_once_with(self.node.get_stack_done_callback)

            
        
    @patch("composer.muto_composer.MutoComposer.resolve_expression")
    @patch("composer.muto_composer.MutoComposer.publish_raw_stack")
    @patch("composer.muto_composer.Router.route")
    def test_get_stack_done_callback(self, mock_route, mock_raw_stack, mock_resolve_expression):
        future = MagicMock()
        future.result = MagicMock()
        self.node.get_stack_done_callback(future)
        mock_route.assert_not_called()
        mock_raw_stack.assert_called_once()
        mock_resolve_expression.assert_called_once()
        
    
    @patch("composer.muto_composer.MutoComposer.resolve_expression")
    @patch("composer.muto_composer.MutoComposer.publish_raw_stack")
    @patch("composer.muto_composer.Router.route")
    def test_get_stack_done_callback_if(self, mock_route, mock_raw_stack, mock_resolve_expression):
        future = MagicMock()
        future.result = MagicMock()
        self.node.method = "apply"
        self.node.get_stack_done_callback(future)
        mock_raw_stack.assert_called_once()
        mock_resolve_expression.assert_called_once()
        mock_route.assert_called_once()

    @patch.object(MutoComposer, 'get_logger')    
    @patch("composer.muto_composer.MutoComposer.resolve_expression")
    @patch("composer.muto_composer.MutoComposer.publish_raw_stack")
    @patch("composer.muto_composer.Router.route")
    def test_get_stack_done_callback_else(self, mock_route, mock_raw_stack, mock_resolve_expression, mock_get_logger):
        future = MagicMock()
        future.result = MagicMock()
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        future.result.return_value = None
        self.node.get_stack_done_callback(future)
        mock_raw_stack.assert_not_called()
        mock_resolve_expression.assert_not_called()
        mock_route.assert_not_called()        
        mock_logger.warn.assert_called_with("Stack getting failed. Try your request again.")

    @patch('composer.muto_composer.get_package_share_directory')
    def test_resolve_expression_find(self, mock_get_package):
        mock_get_package.return_value = "/mock_path/test_pkg"
        input = "$(find test_pkg)"
        self.node.resolve_expression(input)
        mock_get_package.assert_called()
        
    @patch('composer.muto_composer.os.getenv')
    def test_resolve_expression_env(self, mock_get_env):
        mock_get_env.return_value = "test_env"
        input = "$(env test_env)"
        self.node.resolve_expression(input)
        mock_get_env.assert_called()
        
    @patch.object(MutoComposer, 'get_logger')    
    def test_resolve_expression_no_expression(self, mock_get_logger):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        input = "$(test_exp test_pkg)"
        self.node.resolve_expression(input)
        mock_logger.info.assert_called_with("No muto expression found in the given string")
        
    @patch.object(MutoComposer, 'get_logger')
    def test_resolve_expression_key_error(self, mock_get_logger):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        input_value = "$(find demo_pkg)"

        with patch('composer.muto_composer.get_package_share_directory', side_effect=KeyError):
            result = self.node.resolve_expression(input_value)

        mock_logger.warn.assert_called_with("demo_pkg does not exist.")
        self.assertEqual(result, input_value)
        
    @patch.object(MutoComposer, 'get_logger')
    def test_resolve_expression_exception(self, mock_get_logger):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        input_value = "$(find demo_pkg)"

        with patch('composer.muto_composer.get_package_share_directory', side_effect=Exception):
            result = self.node.resolve_expression(input_value)

        mock_logger.info.assert_called_with("Exception occurred: ")
        self.assertEqual(result, input_value)
        
    def test_publish_raw_stack(self):
        stack = "test_stack"
        expected_value = String(data=stack)
        MutoComposer.publish_raw_stack(self, stack)
        self.raw_stack_publisher.publish.assert_called_once_with(expected_value)
        # self.node.publish_raw_stack(stack)
        # self.node.raw_stack_publisher = MagicMock()
        # self.node.raw_stack_publisher.publish.assert_called_once_with(expected_value)
                        
if __name__ == "__main__":
    unittest.main()
