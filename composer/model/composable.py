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

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from composer.model import node


@dataclass
class ComposableNode:
    stack: Any
    manifest: Optional[Dict[str, Any]] = None
    package: str = ""
    plugin: str = ""
    name: str = ""
    namespace: str = ""
    param: List[Dict[str, Any]] = field(default_factory=list)
    remap: List[Dict[str, str]] = field(default_factory=list)
    action: str = ""

    def __post_init__(self) -> None:
        manifest = self.manifest or {}
        self.package = str(manifest.get("pkg", manifest.get("package", self.package)))
        self.plugin = str(manifest.get("plugin", self.plugin))
        self.name = str(manifest.get("name", self.name))
        self.namespace = str(manifest.get("namespace", self.namespace))
        self.param = list(manifest.get("param", self.param) or [])
        self.remap = list(manifest.get("remap", self.remap) or [])
        self.action = str(manifest.get("action", self.action))

    def resolve_namespace(self) -> str:
        namespace = self.namespace or ""
        if not namespace.startswith("/"):
            namespace = f"/{namespace}"
        if not namespace.endswith("/"):
            namespace = f"{namespace}/"
        return f"{namespace}/"

    def toManifest(self) -> Dict[str, Any]:
        return {
            "package": self.package,
            "plugin": self.plugin,
            "name": self.name,
            "namespace": self.namespace,
            "param": self.param,
            "remap": self.remap,
            "action": self.action,
        }


@dataclass
class Container:
    stack: Any
    manifest: Optional[Dict[str, Any]] = None
    package: str = ""
    executable: str = ""
    name: str = ""
    namespace: str = ""
    nodes: List[ComposableNode] = field(default_factory=list)
    output: str = "screen"
    remap: List[Dict[str, str]] = field(default_factory=list)
    action: str = ""

    def __post_init__(self) -> None:
        manifest = self.manifest or {}
        self.package = str(manifest.get("package", self.package))
        self.executable = str(manifest.get("executable", self.executable))
        self.name = str(manifest.get("name", self.name))
        self.namespace = str(manifest.get("namespace", self.namespace))
        self.output = str(manifest.get("output", self.output))
        self.remap = list(manifest.get("remap", self.remap) or [])
        self.action = str(manifest.get("action", self.action))
        nodes = manifest.get("node") or manifest.get("nodes") or []
        self.nodes = [ComposableNode(self.stack, node_manifest) for node_manifest in nodes]

    def resolve_namespace(self) -> str:
        namespace = self.namespace or ""
        if not namespace.startswith("/"):
            namespace = f"/{namespace}"
        if not namespace.endswith("/"):
            namespace = f"{namespace}/"
        return f"{namespace}/"

    def toManifest(self) -> Dict[str, Any]:
        return {
            "package": self.package,
            "executable": self.executable,
            "name": self.name,
            "namespace": self.namespace,
            "node": [n.toManifest() for n in self.nodes],
            "output": self.output,
            "remap": self.remap,
            "action": self.action,
        }

    def __hash__(self) -> int:
        return hash((self.package, self.name, self.namespace, self.executable))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Container):
            return False
        return (
            self.package == other.package
            and self.name == other.name
            and self.namespace == other.namespace
            and self.executable == other.executable
        )
