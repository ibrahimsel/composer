#
# Copyright (c) 2025 Composiv.ai
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# http://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0
#

"""Release model helpers for Symphony payload composition."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ReleasePayload:
    name: str
    version: str
    artifact_uri: str
    checksum: str
    start_command: str
    stop_command: Optional[str] = None
    working_directory: Optional[str] = None
    environment: Optional[Dict[str, str]] = None


def validate_release_payload(payload: Dict[str, Any]) -> ReleasePayload:
    required = ["name", "version", "artifact_uri", "checksum", "start_command"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"Release payload missing fields: {', '.join(missing)}")
    environment = payload.get("environment") or {}
    return ReleasePayload(
        name=str(payload["name"]),
        version=str(payload["version"]),
        artifact_uri=str(payload["artifact_uri"]),
        checksum=str(payload["checksum"]),
        start_command=str(payload["start_command"]),
        stop_command=payload.get("stop_command"),
        working_directory=payload.get("working_directory"),
        environment={str(k): str(v) for k, v in environment.items()},
    )


def encode_payload(payload: Dict[str, Any]) -> str:
    data = json.dumps(payload).encode("utf-8")
    return base64.b64encode(data).decode("utf-8")


def compose_solution(
    release: ReleasePayload,
    solution_name: str,
    component_name: Optional[str] = None,
) -> Dict[str, Any]:
    component_payload = {
        "name": release.name,
        "version": release.version,
        "artifact_uri": release.artifact_uri,
        "checksum": release.checksum,
        "start_command": release.start_command,
        "stop_command": release.stop_command,
        "working_directory": release.working_directory,
        "environment": release.environment or {},
    }
    return {
        "metadata": {"namespace": "default", "name": solution_name},
        "spec": {
            "displayName": solution_name,
            "rootResource": solution_name,
            "version": "1",
            "components": [
                {
                    "name": component_name or solution_name,
                    "type": "muto-agent",
                    "properties": {
                        "type": "stack",
                        "content-type": "application/json",
                        "data": encode_payload(component_payload),
                    },
                }
            ],
        },
    }
