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

"""Logging helpers for API components."""

from __future__ import annotations

import logging
from typing import Optional


def get_logger(name: str) -> logging.Logger:
    """Return a logger, preferring rclpy when available."""
    rclpy_logger = _get_rclpy_logger(name)
    if rclpy_logger is not None:
        return rclpy_logger

    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def _get_rclpy_logger(name: str) -> Optional[logging.Logger]:
    try:
        from rclpy.logging import get_logger as rclpy_get_logger
    except ImportError:
        return None

    return rclpy_get_logger(name)
