import importlib
import json
import rclpy
from rclpy.node import Node
import rclpy.logging


class Pipeline:
    def __init__(self, name, steps, compensation):
        """
        Initializes the Pipeline with a name, steps, and compensation steps.

        Args:
            name (str): The name of the pipeline.
            steps (list): A list of steps to execute in the pipeline.
            compensation (list): A list of compensation steps to execute on failure.
        """
        self.name = name
        self.steps = steps
        self.compensation = compensation
        self.plugins = self.load_plugins()
        self.logger = rclpy.logging.get_logger(f"{self.name}_pipeline")

    def load_plugins(self) -> dict:
        """
        Load the plugins defined in the pipeline configuration.

        Returns:
            dict: A dictionary mapping plugin names to their corresponding classes.

        Raises:
            Exception: If a plugin class cannot be found in the module.
        """
        plugin_dict = {}
        try:
            module_name = "muto_msgs.srv"
            module = importlib.import_module(module_name)
        except ImportError as e:
            self.logger.error(f"Failed to import module '{module_name}': {e}")
            raise

        for item in self.steps:
            sequence = item.get("sequence", [])
            for step in sequence:
                plugin_name = step.get("plugin")
                if plugin_name and plugin_name not in plugin_dict:
                    try:
                        plugin_class = getattr(module, plugin_name)
                        plugin_dict[plugin_name] = plugin_class
                    except AttributeError:
                        self.logger.error(
                            f"Plugin '{plugin_name}' not found in '{module_name}'"
                        )
                        raise Exception(
                            f"Plugin '{plugin_name}' not found in module '{module_name}'. "
                            "Ensure the plugin has a corresponding service definition."
                        )
        return plugin_dict

    def execute_pipeline(self):
        """
        Execute each pipeline step sequentially.
        If a step fails, execute compensation steps and abort the pipeline.
        """
        executor = rclpy.create_node(f"{self.name}_pipeline_executor")
        failed = False

        for item in self.steps:
            if failed:
                break
            sequence = item.get("sequence", [])
            for step in sequence:
                try:
                    response = self.execute_step(step, executor)
                    if not response:
                        raise Exception(
                            "No response from the service call. The service might not be up yet."
                        )

                    if not response.success:
                        raise Exception(f"Step execution error: {response.err_msg}")
                    executor.get_logger().info(f"Step passed: {step.get('plugin', '')}")

                except Exception as e:
                    executor.get_logger().warn(
                        f"Step failed: {step.get('plugin', '')}, Exception: {e}"
                    )
                    self.execute_compensation(executor)
                    failed = True
                    executor.get_logger().error("Aborting the rest of the pipeline")
                    break

        executor.destroy_node()

    def execute_step(self, step, executor: Node):
        """
        Executes a single step using the appropriate ROS 2 service.

        Args:
            step (dict): The step configuration containing 'plugin' and 'service'.
            executor (Node): The ROS node used for service communication.

        Returns:
            The response from the service call.

        Raises:
            Exception: If the service call fails or required fields are missing.
        """
        plugin_name = step.get("plugin")
        service_name = step.get("service")

        if not plugin_name or not service_name:
            raise ValueError("Step must contain 'plugin' and 'service' fields.")

        plugin = self.plugins.get(plugin_name)
        if not plugin:
            raise Exception(f"Plugin '{plugin_name}' not loaded.")

        cli = executor.create_client(plugin, service_name)
        executor.get_logger().info(f"Executing step: {plugin_name}")

        if not cli.wait_for_service(timeout_sec=5.0):
            executor.get_logger().error(
                f"Service '{cli.srv_name}' is not available. Cannot execute step."
            )
            return None

        req = plugin.Request()
        req.start = True
        future = cli.call_async(req)
        rclpy.spin_until_future_complete(executor, future)

        if future.result():
            return future.result()
        else:
            raise Exception(f"Service call failed: {future.exception()}")

    def execute_compensation(self, executor: Node):
        """
        Executes compensation steps if the primary step execution fails.

        Args:
            executor (Node): The ROS node used for service communication.
        """
        executor.get_logger().info("Executing compensation steps.")
        if self.compensation:
            for step in self.compensation:
                try:
                    self.execute_step(step, executor)
                except Exception as e:
                    executor.get_logger().warn(
                        f"Compensation step failed: {step.get('plugin', '')}, Exception: {e}"
                    )
        else:
            executor.get_logger().warn("No compensation steps to execute.")
