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

"""Uvicorn entrypoint for the Composer FastAPI service."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """Run the FastAPI service with uvicorn."""
    host = os.getenv("MUTO_API_HOST", "0.0.0.0")
    port = int(os.getenv("MUTO_API_PORT", "8080"))
    reload_enabled = os.getenv("MUTO_API_RELOAD", "false").lower() == "true"

    uvicorn.run("api.app:app", host=host, port=port, reload=reload_enabled)


if __name__ == "__main__":
    main()
