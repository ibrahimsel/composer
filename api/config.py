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

"""Configuration helpers for the Composer FastAPI service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _parse_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    app_name: str = "Eclipse Muto Fleet Backend API"
    api_version: str = "1.0.0"
    seed_enabled: bool = os.getenv("MUTO_API_SEED", "true").lower() == "true"
    seed_count: int = int(os.getenv("MUTO_API_SEED_COUNT", "12"))
    default_page_size: int = int(os.getenv("MUTO_API_PAGE_SIZE", "20"))
    max_page_size: int = int(os.getenv("MUTO_API_MAX_PAGE_SIZE", "200"))
    cors_origins: List[str] = field(
        default_factory=lambda: _parse_csv(os.getenv("MUTO_API_CORS_ORIGINS", "*"))
    )
    cors_allow_credentials: bool = os.getenv("MUTO_API_CORS_CREDENTIALS", "false").lower() == "true"
