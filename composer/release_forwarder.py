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

"""Release forwarder for simplified composer - validates and forwards releases to Symphony."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .release_model import ReleasePayload, compose_solution, validate_release_payload


class ForwardStatus(Enum):
    """Status of a forward operation."""

    SUCCESS = "success"
    VALIDATION_ERROR = "validation_error"
    FORWARD_ERROR = "forward_error"


@dataclass
class ForwardResult:
    """Result of a release forward operation."""

    status: ForwardStatus
    message: str
    solution_name: str | None = None
    targets: list[str] | None = None


class ReleaseForwarder:
    """Validates release metadata and forwards to Symphony for deployment."""

    def __init__(self, logger: Any) -> None:
        """Initialize the release forwarder.

        Args:
            logger: Logger instance for logging operations.
        """
        self._logger = logger

    def validate_and_forward(
        self,
        payload: dict[str, Any],
        targets: list[str] | None = None,
    ) -> ForwardResult:
        """Validate release metadata and create Symphony solution.

        Args:
            payload: Raw release payload dictionary.
            targets: Optional list of target device names.

        Returns:
            ForwardResult with status and details.
        """
        # Step 1: Validate release metadata
        try:
            release = validate_release_payload(payload)
        except ValueError as exc:
            self._logger.error(f"Release validation failed: {exc}")
            return ForwardResult(
                status=ForwardStatus.VALIDATION_ERROR,
                message=str(exc),
            )

        # Step 2: Create Symphony solution
        try:
            solution_name = f"{release.name}-{release.version}"
            # Validate solution can be composed (result used by Symphony integration)
            compose_solution(release, solution_name)
            self._logger.info(
                f"Created Symphony solution '{solution_name}' for release "
                f"{release.name}:{release.version}"
            )
        except Exception as exc:
            self._logger.error(f"Failed to compose solution: {exc}")
            return ForwardResult(
                status=ForwardStatus.FORWARD_ERROR,
                message=f"Solution composition failed: {exc}",
            )

        return ForwardResult(
            status=ForwardStatus.SUCCESS,
            message="Release validated and solution created",
            solution_name=solution_name,
            targets=targets,
        )

    def validate_only(self, payload: dict[str, Any]) -> ForwardResult:
        """Validate release metadata without forwarding.

        Args:
            payload: Raw release payload dictionary.

        Returns:
            ForwardResult with validation status.
        """
        try:
            release = validate_release_payload(payload)
            self._logger.info(f"Release validated: {release.name}:{release.version}")
            return ForwardResult(
                status=ForwardStatus.SUCCESS,
                message=f"Release {release.name}:{release.version} is valid",
            )
        except ValueError as exc:
            self._logger.error(f"Release validation failed: {exc}")
            return ForwardResult(
                status=ForwardStatus.VALIDATION_ERROR,
                message=str(exc),
            )

    def extract_release_info(
        self, payload: dict[str, Any]
    ) -> ReleasePayload | None:
        """Extract and validate release info from payload.

        Args:
            payload: Raw release payload dictionary.

        Returns:
            ReleasePayload if valid, None otherwise.
        """
        try:
            return validate_release_payload(payload)
        except ValueError as exc:
            self._logger.warning(f"Invalid release payload: {exc}")
            return None
