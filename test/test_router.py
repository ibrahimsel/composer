import unittest
from unittest.mock import MagicMock, patch
import rclpy
from composer.workflow.router import Router

class TestRouter(unittest.TestCase):

    def setUp(self):
        self.pipelines = {
            'start': MagicMock(),
            'kill': MagicMock(),
            'apply': MagicMock()
        }
        self.payload = {'stackId': 'org.eclipse.muto.sandbox:test', 'action': 'kill'}
        self.pipeline = self.pipelines.get('kill')

    @classmethod
    def setUpClass(cls) -> None:
        rclpy.init()

    @classmethod
    def tearDownClass(cls) -> None:
        rclpy.shutdown()

    @patch("composer.workflow.router.Pipeline.execute_pipeline")
    def test_route(self, mock_pipeline):
        main_route = Router(self.pipelines)
        main_route.route(self.payload.get('action', ''))
        self.pipeline.execute_pipeline.assert_called_once()
        
if __name__ == "__main__":
    unittest.main()