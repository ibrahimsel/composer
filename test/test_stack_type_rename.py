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
Unit tests for stack content type renames (MEP-0001 Phase 1b).

Verifies that handlers accept both old and new content type names,
and that the registry resolves all types to the correct handler.
"""

import unittest
from unittest.mock import MagicMock

from muto_composer.stack_handlers.archive_handler import ArchiveStackHandler
from muto_composer.stack_handlers.ditto_handler import DittoStackHandler
from muto_composer.stack_handlers.json_handler import JsonStackHandler
from muto_composer.stack_handlers.native_handler import NativeStackHandler
from muto_composer.stack_handlers.registry import StackTypeRegistry


class TestJsonHandlerContentTypes(unittest.TestCase):
    """Test that JsonStackHandler accepts both stack/json and stack/declarative."""

    def setUp(self):
        self.handler = JsonStackHandler(logger=MagicMock())

    def test_accepts_stack_json(self):
        payload = {"metadata": {"content_type": "stack/json"}, "launch": {"node": []}}
        self.assertTrue(self.handler.can_handle(payload))

    def test_accepts_stack_declarative(self):
        payload = {"metadata": {"content_type": "stack/declarative"}, "launch": {"node": []}}
        self.assertTrue(self.handler.can_handle(payload))

    def test_rejects_stack_archive(self):
        payload = {"metadata": {"content_type": "stack/archive"}}
        self.assertFalse(self.handler.can_handle(payload))

    def test_rejects_stack_native(self):
        payload = {"metadata": {"content_type": "stack/native"}}
        self.assertFalse(self.handler.can_handle(payload))

    def test_rejects_no_content_type(self):
        payload = {"metadata": {}}
        self.assertFalse(self.handler.can_handle(payload))

    def test_rejects_non_dict(self):
        self.assertFalse(self.handler.can_handle("not a dict"))


class TestArchiveHandlerContentTypes(unittest.TestCase):
    """Test that ArchiveStackHandler accepts both stack/archive and stack/workspace."""

    def setUp(self):
        self.handler = ArchiveStackHandler(logger=MagicMock())

    def test_accepts_stack_archive(self):
        payload = {"metadata": {"content_type": "stack/archive"}}
        self.assertTrue(self.handler.can_handle(payload))

    def test_accepts_stack_workspace(self):
        payload = {"metadata": {"content_type": "stack/workspace"}}
        self.assertTrue(self.handler.can_handle(payload))

    def test_rejects_stack_json(self):
        payload = {"metadata": {"content_type": "stack/json"}}
        self.assertFalse(self.handler.can_handle(payload))

    def test_rejects_stack_native(self):
        payload = {"metadata": {"content_type": "stack/native"}}
        self.assertFalse(self.handler.can_handle(payload))


class TestDittoHandlerContentTypes(unittest.TestCase):
    """Test that DittoStackHandler accepts stack/ditto and stack/legacy."""

    def setUp(self):
        self.handler = DittoStackHandler(logger=MagicMock())

    def test_accepts_legacy_format_no_content_type(self):
        payload = {"node": [{"name": "test", "pkg": "test_pkg", "exec": "test_exec"}]}
        self.assertTrue(self.handler.can_handle(payload))

    def test_accepts_stack_ditto(self):
        payload = {"metadata": {"content_type": "stack/ditto"}, "node": [{"name": "test"}]}
        self.assertTrue(self.handler.can_handle(payload))

    def test_accepts_stack_legacy(self):
        payload = {"metadata": {"content_type": "stack/legacy"}, "node": [{"name": "test"}]}
        self.assertTrue(self.handler.can_handle(payload))

    def test_accepts_script_based(self):
        payload = {"on_start": "ros2 run demo_nodes_cpp talker", "on_kill": "pkill -f talker"}
        self.assertTrue(self.handler.can_handle(payload))

    def test_rejects_stack_native(self):
        payload = {"metadata": {"content_type": "stack/native"}, "launch": {"file": "/test"}}
        self.assertFalse(self.handler.can_handle(payload))

    def test_rejects_stack_workspace(self):
        payload = {"metadata": {"content_type": "stack/workspace"}}
        self.assertFalse(self.handler.can_handle(payload))


class TestRegistryResolvesAllTypes(unittest.TestCase):
    """Test that the registry resolves all content types to correct handlers."""

    def setUp(self):
        mock_node = MagicMock()
        self.registry = StackTypeRegistry(mock_node, MagicMock())
        self.registry.discover_and_register_handlers()

    def test_resolves_stack_json(self):
        payload = {"metadata": {"content_type": "stack/json"}, "launch": {"node": []}}
        handler = self.registry.get_handler(payload)
        self.assertIsNotNone(handler)
        self.assertEqual(handler.__class__.__name__, "JsonStackHandler")

    def test_resolves_stack_declarative(self):
        payload = {"metadata": {"content_type": "stack/declarative"}, "launch": {"node": []}}
        handler = self.registry.get_handler(payload)
        self.assertIsNotNone(handler)
        self.assertEqual(handler.__class__.__name__, "JsonStackHandler")

    def test_resolves_stack_archive(self):
        payload = {"metadata": {"content_type": "stack/archive"}}
        handler = self.registry.get_handler(payload)
        self.assertIsNotNone(handler)
        self.assertEqual(handler.__class__.__name__, "ArchiveStackHandler")

    def test_resolves_stack_workspace(self):
        payload = {"metadata": {"content_type": "stack/workspace"}}
        handler = self.registry.get_handler(payload)
        self.assertIsNotNone(handler)
        self.assertEqual(handler.__class__.__name__, "ArchiveStackHandler")

    def test_resolves_stack_native(self):
        payload = {"metadata": {"content_type": "stack/native"}, "launch": {"file": "/test"}}
        handler = self.registry.get_handler(payload)
        self.assertIsNotNone(handler)
        self.assertEqual(handler.__class__.__name__, "NativeStackHandler")

    def test_resolves_stack_legacy(self):
        payload = {"metadata": {"content_type": "stack/legacy"}, "node": [{"name": "test"}]}
        handler = self.registry.get_handler(payload)
        self.assertIsNotNone(handler)
        self.assertEqual(handler.__class__.__name__, "DittoStackHandler")

    def test_resolves_legacy_no_content_type(self):
        payload = {"node": [{"name": "test"}]}
        handler = self.registry.get_handler(payload)
        self.assertIsNotNone(handler)
        self.assertEqual(handler.__class__.__name__, "DittoStackHandler")

    def test_no_handler_for_unknown_type(self):
        payload = {"metadata": {"content_type": "stack/unknown"}}
        handler = self.registry.get_handler(payload)
        self.assertIsNone(handler)


if __name__ == "__main__":
    unittest.main()
