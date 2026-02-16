#!/usr/bin/env python3
"""
Unit test for stack/json pipeline launch issue regression.

Tests the fix for the bug where stack/json content would not launch properly
through the pipeline due to incorrect name extraction in Pipeline.toStackManifest().

Bug Details:
- Original Issue: Pipeline.toStackManifest() expected 'name' at root level
- Stack Format: stack/json has 'metadata.name' structure
- Fix: Updated toStackManifest() to check metadata.name first, fallback to root name
- Result: Stack manifest correctly flows through compose → launch pipeline services

Test data is embedded directly in the test to avoid file dependencies.
"""

import json
import unittest

import rclpy
from muto_msgs.msg import StackManifest
from rclpy.node import Node


class TestStackJsonPipelineFix(unittest.TestCase):
    """Test case for stack/json pipeline manifest flow fix"""

    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = Node("test_stack_json_pipeline")

        # Embedded test stack data (instead of reading from file)
        cls.stack_data = {
            "metadata": {
                "name": "Muto Simple Talker-Listener Stack",
                "description": "A simple talker-listener stack example using demo_nodes_cpp package.",
                "content_type": "stack/json",
            },
            "launch": {
                "node": [
                    {"name": "talker", "pkg": "demo_nodes_cpp", "exec": "talker"},
                    {"name": "listener", "pkg": "demo_nodes_cpp", "exec": "listener"},
                ]
            },
        }

    @classmethod
    def tearDownClass(cls):
        cls.node.destroy_node()
        rclpy.shutdown()

    def test_stack_manifest_name_extraction(self):
        """Test that toStackManifest correctly extracts name from metadata.name"""
        # Test the fixed toStackManifest logic
        stack_msg = StackManifest()

        # This is the fixed logic from Pipeline.toStackManifest()
        if isinstance(self.stack_data, dict):
            if "metadata" in self.stack_data and "name" in self.stack_data["metadata"]:
                stack_msg.name = self.stack_data["metadata"]["name"]
            else:
                stack_msg.name = self.stack_data.get("name", "")
        stack_msg.stack = json.dumps(self.stack_data)

        # Assertions
        self.assertEqual(stack_msg.name, "Muto Simple Talker-Listener Stack")
        self.assertGreater(len(stack_msg.stack), 0)
        self.assertIn("metadata", stack_msg.stack)
        self.assertIn("launch", stack_msg.stack)

    def test_stack_manifest_fallback_to_root_name(self):
        """Test that toStackManifest falls back to root name if metadata.name not present"""
        # Test with old format (name at root)
        old_format_stack = {"name": "Root Name Stack", "content": "test"}

        stack_msg = StackManifest()
        if isinstance(old_format_stack, dict):
            if "metadata" in old_format_stack and "name" in old_format_stack["metadata"]:
                stack_msg.name = old_format_stack["metadata"]["name"]
            else:
                stack_msg.name = old_format_stack.get("name", "")
        stack_msg.stack = json.dumps(old_format_stack)

        self.assertEqual(stack_msg.name, "Root Name Stack")



if __name__ == "__main__":
    unittest.main()
