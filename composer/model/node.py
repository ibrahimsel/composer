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


@dataclass
class Node:
    stack: Any
    manifest: Optional[Dict[str, Any]] = None
    pkg: str = ""
    exec: str = ""
    name: str = ""
    namespace: str = ""
    output: str = "screen"
    param: List[Dict[str, Any]] = field(default_factory=list)
    remap: List[Dict[str, str]] = field(default_factory=list)
    args: Any = None
    action: str = ""

    def __post_init__(self) -> None:
        manifest = self.manifest or {}
        self.pkg = str(manifest.get("pkg", self.pkg))
        self.exec = str(manifest.get("exec", self.exec))
        self.name = str(manifest.get("name", self.name))
        self.namespace = str(manifest.get("namespace", self.namespace))
        self.output = str(manifest.get("output", self.output))
        self.param = list(manifest.get("param", self.param) or [])
        self.remap = list(manifest.get("remap", self.remap) or [])
        self.args = manifest.get("args", self.args)
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
            "pkg": self.pkg,
            "exec": self.exec,
            "name": self.name,
            "namespace": self.namespace,
            "output": self.output,
            "param": self.param,
            "remap": self.remap,
            "args": self.args,
            "action": self.action,
        }

    def __hash__(self) -> int:
        return hash((self.pkg, self.exec, self.name, self.namespace))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Node):
            return False
        return (
            self.pkg == other.pkg
            and self.exec == other.exec
            and self.name == other.name
            and self.namespace == other.namespace
        )
