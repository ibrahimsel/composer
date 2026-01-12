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

import subprocess
from typing import Any, Dict, Optional


class Param:
    def __init__(self, stack: Any, manifest: Optional[Dict[str, Any]] = None) -> None:
        self.stack = stack
        self.manifest = manifest or {}
        self.name = str(self.manifest.get("name", ""))
        self.source = str(self.manifest.get("from", ""))
        self.command = str(self.manifest.get("command", ""))
        self.value = self._resolve_value(self.manifest)

    def _resolve_value(self, manifest: Dict[str, Any]) -> Any:
        if "value" in manifest:
            return self._parse_value(manifest.get("value"))
        if manifest.get("command"):
            return self._parse_value(self._execute_command(manifest["command"]))
        if manifest.get("from"):
            return manifest.get("from")
        return None

    def _parse_value(self, value: Any) -> Any:
        if isinstance(value, str):
            upper = value.upper()
            if upper == "TRUE":
                return True
            if upper == "FALSE":
                return False
            if value.isdigit():
                return int(value)
        return value

    def _execute_command(self, command: str) -> str:
        result = subprocess.run(
            command,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
