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

"""Tests for the Composer FastAPI service."""

from __future__ import annotations

import os
import sys
import unittest

from fastapi.testclient import TestClient

TEST_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if TEST_ROOT not in sys.path:
    sys.path.insert(0, TEST_ROOT)

from api.app import create_app  # noqa: E402


class TestComposerApi(unittest.TestCase):
    """Validate core API workflows with in-memory storage."""

    def setUp(self):
        app = create_app(seed_data=True, seed_count=8)
        self.client = TestClient(app)

    def test_list_vehicles_pagination(self):
        response = self.client.get(
            "/api/v1/vehicles", params={"page": 1, "limit": 5}
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("data", payload)
        self.assertLessEqual(len(payload["data"]), 5)
        self.assertIn("metadata", payload)
        self.assertIn("totalItems", payload["metadata"])

    def test_desired_state_idempotent(self):
        payload = {
            "stackVersion": "autonomy-core:1.2.0",
            "selector": "model=vehicle-v3",
            "comment": "test",
        }
        headers = {"Idempotency-Key": "dsr-test-1"}
        response = self.client.post(
            "/api/v1/desired-states", json=payload, headers=headers
        )
        self.assertEqual(response.status_code, 200)
        first_id = response.json()["data"]["id"]

        response = self.client.post(
            "/api/v1/desired-states", json=payload, headers=headers
        )
        self.assertEqual(response.status_code, 200)
        second_id = response.json()["data"]["id"]

        self.assertEqual(first_id, second_id)

    def test_rollout_pause_and_rollback(self):
        payload = {
            "stackVersion": "autonomy-core:1.2.0",
            "selector": "model=vehicle-v3",
            "canaryPerGroup": 1,
            "wavePercent": 50,
        }
        response = self.client.post("/api/v1/rollouts", json=payload)
        self.assertEqual(response.status_code, 200)
        rollout_id = response.json()["data"]["id"]

        response = self.client.post(f"/api/v1/rollouts/{rollout_id}/pause")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "paused")

        response = self.client.post(f"/api/v1/rollouts/{rollout_id}/rollback")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "rolled_back")

    def test_reconcile_report_updates_vehicle(self):
        list_response = self.client.get("/api/v1/vehicles")
        self.assertEqual(list_response.status_code, 200)
        vehicle_id = list_response.json()["data"][0]["id"]

        report_payload = {
            "vehicleId": vehicle_id,
            "actualStack": "autonomy-core:1.2.0",
            "actualRevision": "rev-123",
            "status": "converged",
            "reasonCodes": [],
        }
        report_response = self.client.post(
            "/api/v1/reports/reconcile", json=report_payload
        )
        self.assertEqual(report_response.status_code, 200)

        vehicle_response = self.client.get(f"/api/v1/vehicles/{vehicle_id}")
        self.assertEqual(vehicle_response.status_code, 200)
        self.assertEqual(
            vehicle_response.json()["data"]["status"], "converged"
        )


if __name__ == "__main__":
    unittest.main()
