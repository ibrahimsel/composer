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

from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Dict, Iterable, List, Optional, Tuple

import rclpy
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.descriptions import ComposableNode

from composer.introspection.introspector import Introspector
from composer.model.composable import Container, ComposableNode as ModelComposableNode
from composer.model.node import Node as ModelNode
from composer.model.param import Param


class Stack:
    def __init__(self, manifest: Optional[Dict[str, Any]] = None) -> None:
        self.manifest = manifest or {}
        self.name = str(self.manifest.get("name", ""))
        self.context = str(self.manifest.get("context", ""))
        self.stackId = str(self.manifest.get("stackId", ""))
        self.param = [Param(self, p) for p in self.manifest.get("param", [])]
        self.arg = self.resolve_args(self.manifest.get("arg", []))
        self.node = [ModelNode(self, n) for n in self.manifest.get("node", [])]
        self.composable = [Container(self, c) for c in self.manifest.get("composable", [])]

    def compare_nodes(self, other: "Stack") -> Tuple[set, set, set]:
        self_nodes = set(self.node)
        other_nodes = set(other.node)
        common = {n for n in self_nodes if n in other_nodes}
        added = {n for n in other_nodes if n not in self_nodes}
        difference = {n for n in self_nodes if n not in other_nodes}
        return common, difference, added

    def compare_composable(self, other: "Stack") -> Tuple[List[Container], List[Container], List[Container]]:
        common = [c for c in self.composable if c in other.composable]
        added = [c for c in other.composable if c not in self.composable]
        removed = [c for c in self.composable if c not in other.composable]
        return common, added, removed

    def flatten_nodes(self, nodes: Iterable[ModelNode]) -> List[ModelNode]:
        flat_nodes = list(nodes)
        flat_nodes.extend(self.node)
        return flat_nodes

    def flatten_composable(self, composables: Iterable[Container]) -> List[Container]:
        flat = list(composables)
        flat.extend(self.composable)
        return flat

    @staticmethod
    def compare_ros_params(params1: List[Dict[str, Any]], params2: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        def flatten(params: List[Dict[str, Any]]) -> Dict[str, Any]:
            merged: Dict[str, Any] = {}
            for param in params:
                merged.update(param)
            return merged

        first = flatten(params1)
        second = flatten(params2)
        differences = []
        for key in sorted(set(first.keys()) | set(second.keys())):
            if first.get(key) != second.get(key):
                differences.append(
                    {
                        "key": key,
                        "in_node1": first.get(key),
                        "in_node2": second.get(key),
                    }
                )
        return differences

    def merge(self, other: "Stack") -> "Stack":
        merged = Stack(manifest={})
        self._merge_attributes(merged, other)
        self._merge_nodes(merged, other)
        self._merge_composables(merged, other)
        self._merge_params(merged, other)
        return merged

    def _merge_attributes(self, merged: "Stack", other: "Stack") -> None:
        if other.name:
            merged.name = other.name
        if other.context:
            merged.context = other.context
        if other.stackId:
            merged.stackId = other.stackId

    def _merge_nodes(self, merged: "Stack", other: "Stack") -> None:
        merged.node = []
        for node in self.node:
            node.action = "none"
            merged.node.append(node)
        for node in other.node:
            if node not in self.node:
                node.action = "start"
                merged.node.append(node)

    def _merge_composables(self, merged: "Stack", other: "Stack") -> None:
        merged.composable = []
        for container in self.composable:
            container.action = "none"
            merged.composable.append(container)
        for container in other.composable:
            if container not in self.composable:
                container.action = "start"
                merged.composable.append(container)

    def _merge_params(self, merged: "Stack", other: "Stack") -> None:
        merged.param = list(self.param)
        merged.param.extend(other.param)

    def get_active_nodes(self) -> List[Tuple[str, str]]:
        node = rclpy.create_node("get_active_nodes", enable_rosout=False)
        active_nodes = node.get_node_names_and_namespaces()
        node.destroy_node()
        return active_nodes

    def kill_all(self, launcher: Any) -> None:
        introspector = Introspector()
        for node_map in getattr(launcher, "_active_nodes", []):
            for name, pid in node_map.items():
                introspector.kill(name, pid)

    def kill_diff(self, launcher: Any, stack: "Stack") -> None:
        introspector = Introspector()
        active_nodes = getattr(launcher, "_active_nodes", [])
        for node in stack.node:
            if node.action != "stop":
                continue
            for node_map in active_nodes:
                for name, pid in node_map.items():
                    if name == node.exec:
                        introspector.kill(name, pid)

    def change_params_at_runtime(self, param_differences: Dict[Tuple[str, str], List[Dict[str, Any]]]) -> None:
        for (node1, _node2), diffs in param_differences.items():
            for diff in diffs:
                key = diff.get("key")
                value = diff.get("in_node1")
                subprocess.run(["ros2", "param", "set", node1, str(key), str(value)])

    def toShallowManifest(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "context": self.context,
            "stackId": self.stackId,
            "param": [],
            "arg": [],
            "stack": [],
            "composable": [],
            "node": [],
        }

    def toManifest(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "context": self.context,
            "stackId": self.stackId,
            "param": [{"name": p.name, "value": p.value} for p in self.param],
            "arg": list(self.arg.values()),
            "stack": [],
            "composable": [c.toManifest() for c in self.composable],
            "node": [n.toManifest() for n in self.node],
        }

    def process_remaps(self, remaps_config: List[Dict[str, str]]) -> List[Tuple[str, str]]:
        remaps = []
        for remap in remaps_config:
            remaps.append((remap.get("from", ""), remap.get("to", "")))
        return remaps

    def launch(self, launcher: Any) -> None:
        launch_description = LaunchDescription()
        for node in self.node:
            remaps = self.process_remaps(node.remap)
            action = Node(
                package=node.pkg,
                executable=node.exec,
                name=node.name,
                namespace=node.resolve_namespace(),
                output=node.output,
                parameters=node.param,
                remappings=remaps,
                arguments=node.args,
            )
            launch_description.add_action(action)

        for container in self.composable:
            composable_nodes = []
            for comp_node in container.nodes:
                if not isinstance(comp_node, ModelComposableNode):
                    continue
                composable_nodes.append(
                    ComposableNode(
                        package=comp_node.package,
                        plugin=comp_node.plugin,
                        name=comp_node.name,
                        namespace=comp_node.resolve_namespace(),
                        parameters=comp_node.param,
                        remappings=self.process_remaps(comp_node.remap),
                    )
                )
            action = ComposableNodeContainer(
                name=container.name,
                namespace=container.resolve_namespace(),
                package=container.package,
                executable=container.executable,
                composable_node_descriptions=composable_nodes,
                output=container.output,
            )
            launch_description.add_action(action)

        launcher.start(launch_description)

    def apply(self, launcher: Any) -> None:
        self.kill_diff(launcher, self)
        self.launch(launcher)

    def resolve_expression(self, value: str) -> str:
        find_match = re.match(r"^\$\((find)\s+(.+)\)$", value)
        if find_match:
            return get_package_share_directory(find_match.group(2))

        env_match = re.match(r"^\$\((env)\s+(.+)\)$", value)
        if env_match:
            return os.environ.get(env_match.group(2), value)

        arg_match = re.match(r"^\$\((arg)\s+(.+)\)$", value)
        if arg_match:
            arg_name = arg_match.group(2)
            return str(self.arg.get(arg_name, {}).get("value", value))

        return value

    def resolve_args(self, args: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        resolved = {}
        for arg in args:
            name = arg.get("name")
            if not name:
                continue
            resolved[name] = {"name": name, "value": arg.get("value")}
        return resolved
