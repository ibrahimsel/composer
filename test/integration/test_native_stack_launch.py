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
Integration test: Verify that a stack/native manifest can launch nodes
and that they appear in the ROS 2 graph.

Uses launch_testing with demo_nodes_cpp talker/listener (headless,
no GUI dependency unlike turtlesim).
"""

import time
import unittest

import launch
import launch_testing
import launch_testing.actions
from launch_ros.actions import Node

import rclpy


def generate_test_description():
    """Launch two demo nodes that a native stack handler would manage."""
    talker = Node(
        package="demo_nodes_cpp",
        executable="talker",
        name="native_talker",
        namespace="/native_test",
        output="screen",
    )

    listener = Node(
        package="demo_nodes_cpp",
        executable="listener",
        name="native_listener",
        namespace="/native_test",
        output="screen",
    )

    return (
        launch.LaunchDescription([
            talker,
            listener,
            launch_testing.actions.ReadyToTest(),
        ]),
        {"talker": talker, "listener": listener},
    )


class TestNativeStackNodes(unittest.TestCase):
    """Test that natively launched nodes appear in the ROS 2 graph."""

    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node("test_native_observer")

    @classmethod
    def tearDownClass(cls):
        cls.node.destroy_node()
        rclpy.shutdown()

    def test_nodes_appear_in_graph(self):
        """Verify both nodes are discoverable in the ROS 2 graph."""
        expected = {"/native_test/native_talker", "/native_test/native_listener"}
        found = set()

        # Poll for up to 10 seconds
        deadline = time.time() + 10.0
        while time.time() < deadline and not expected.issubset(found):
            node_names_and_namespaces = self.node.get_node_names_and_namespaces()
            for name, ns in node_names_and_namespaces:
                fqn = f"{ns.rstrip('/')}/{name}" if ns != "/" else f"/{name}"
                found.add(fqn)
            time.sleep(0.5)

        self.assertTrue(
            expected.issubset(found),
            f"Expected nodes {expected} not all found. Discovered: {found}",
        )

    def test_talker_publishes_to_chatter(self):
        """Verify the talker node publishes to /native_test/chatter topic."""
        topics = self.node.get_topic_names_and_types()
        topic_names = [t[0] for t in topics]

        # Poll briefly for topic discovery
        deadline = time.time() + 5.0
        while time.time() < deadline and "/native_test/chatter" not in topic_names:
            time.sleep(0.5)
            topics = self.node.get_topic_names_and_types()
            topic_names = [t[0] for t in topics]

        self.assertIn(
            "/native_test/chatter",
            topic_names,
            f"Expected /native_test/chatter topic. Found: {topic_names}",
        )


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):
    def test_exit_codes(self, proc_info):
        """Verify clean shutdown."""
        launch_testing.asserts.assertExitCodes(
            proc_info,
            allowable_exit_codes=[0, -2, -15],  # OK, SIGINT, SIGTERM
        )
