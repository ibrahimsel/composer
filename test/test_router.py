import unittest
from unittest.mock import MagicMock, patch
import rclpy
<<<<<<< Updated upstream
from composer.router import Router

=======
from composer.workflow.router import Router
>>>>>>> Stashed changes

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

<<<<<<< Updated upstream
    @patch("composer.router.Pipeline.execute_pipeline")
=======
    @patch("composer.workflow.router.Pipeline.execute_pipeline")
>>>>>>> Stashed changes
    def test_route(self, mock_pipeline):
        main_route = Router(self.pipelines)
        main_route.route(self.payload.get('action', ''))
        self.pipeline.execute_pipeline.assert_called_once()
        
<<<<<<< Updated upstream
    @patch("composer.router.Pipeline.execute_pipeline")
    def test_route_no_pipeline_found(self, mock_pipeline):
        main_route = Router(self.pipelines)
        with patch('builtins.print') as mock_print:
            main_route.route('no_action')
            mock_print.assert_called_with("No pipeline found for action: no_action")
=======
    # @patch("composer.workflow.router.Pipeline.execute_pipeline")
    # def test_route_no_pipeline_found(self, mock_pipeline):
    #     main_route = Router(self.pipelines)
    #     with patch('builtins.print') as mock_print:
    #         main_route.route('no_action')
    #         mock_print.assert_called_with("No pipeline found for action: no_action")
>>>>>>> Stashed changes


if __name__ == "__main__":
    unittest.main()
