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

"""Seed data for the Composer FastAPI service."""

from __future__ import annotations

from datetime import timedelta
import random
from typing import Any, Dict, List
from uuid import uuid4

from api.models import (
    AuditLogEntry,
    CanaryStatus,
    HealthReport,
    Release,
    ReconcileReport,
    Rollout,
    RolloutCanary,
    RolloutGates,
    RolloutProgress,
    RolloutStatus,
    RolloutWave,
    SafetySnapshot,
    TimelineEvent,
    TimelineEventType,
    Vehicle,
    VehicleStatus,
)
from api.utils import model_dump, now


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def build_seed_data(vehicle_count: int) -> Dict[str, Any]:
    """Build deterministic seed data for demos and tests."""
    rng = random.Random(42)
    base_time = now()

    releases = [
        model_dump(
            Release(
                id=_generate_id("rel"),
                stack="autonomy-core",
                version="1.0.0",
                digest="sha256:abc123",
                compatibility="vehicle-v3",
                signaturePresent=True,
                createdAt=base_time - timedelta(days=10),
            )
        ),
        model_dump(
            Release(
                id=_generate_id("rel"),
                stack="autonomy-core",
                version="1.1.0",
                digest="sha256:def456",
                compatibility="vehicle-v4",
                signaturePresent=True,
                createdAt=base_time - timedelta(days=5),
            )
        ),
        model_dump(
            Release(
                id=_generate_id("rel"),
                stack="perception",
                version="0.9.0",
                digest="sha256:789abc",
                compatibility="vehicle-v3",
                signaturePresent=False,
                createdAt=base_time - timedelta(days=2),
            )
        ),
    ]

    desired_state_id = _generate_id("dsr")

    vehicles: List[Dict[str, Any]] = []
    reconcile_reports: List[Dict[str, Any]] = []
    health_reports: List[Dict[str, Any]] = []
    desired_by_vehicle: Dict[str, str] = {}

    models = ["vehicle-v3", "vehicle-v4"]
    regions = ["us-west", "us-east", "eu-central"]
    rings = ["1", "2"]
    statuses = [
        VehicleStatus.CONVERGED,
        VehicleStatus.APPLYING,
        VehicleStatus.BLOCKED,
        VehicleStatus.FAILED,
        VehicleStatus.OFFLINE,
        VehicleStatus.PENDING,
    ]

    for index in range(vehicle_count):
        vehicle_id = f"vehicle-{index:03d}"
        status = statuses[index % len(statuses)]
        tags = {
            "model": models[index % len(models)],
            "region": regions[index % len(regions)],
            "ring": rings[index % len(rings)],
        }
        last_seen = base_time - timedelta(minutes=index * 5)
        reason_codes: List[str] = []
        if status == VehicleStatus.BLOCKED:
            reason_codes = ["REQUIRE_STATIONARY"]
        elif status == VehicleStatus.FAILED:
            reason_codes = ["CONTAINER_IMAGE_PULL_FAILED"]
        elif status == VehicleStatus.OFFLINE:
            reason_codes = ["HEARTBEAT_TIMEOUT"]

        safety_snapshot = SafetySnapshot(
            moving=status == VehicleStatus.BLOCKED,
            autonomyMode=(
                "auto" if status == VehicleStatus.BLOCKED else "manual"
            ),
            battery=rng.randint(20, 95),
            window=True,
        )

        timeline_event = TimelineEvent(
            timestamp=last_seen,
            event=_event_for_status(status),
            details=reason_codes[0] if reason_codes else None,
            reasonCodes=reason_codes or None,
        )

        vehicle = Vehicle(
            id=vehicle_id,
            tags=tags,
            desiredStack="autonomy-core:1.1.0",
            desiredRevision=desired_state_id,
            actualStack="autonomy-core:1.0.0",
            actualRevision="rev-" + uuid4().hex[:8],
            status=status,
            lastSeenAt=last_seen,
            reasonCodes=reason_codes,
            safetySnapshot=safety_snapshot,
            timeline=[timeline_event],
            desiredState={
                "id": desired_state_id,
                "stackVersion": "autonomy-core:1.1.0",
            },
            latestReport={},
        )
        vehicles.append(model_dump(vehicle))
        desired_by_vehicle[vehicle_id] = desired_state_id

        reconcile_reports.append(
            model_dump(
                ReconcileReport(
                    vehicleId=vehicle_id,
                    actualStack=vehicle.actualStack,
                    actualRevision=vehicle.actualRevision,
                    status=status,
                    reasonCodes=reason_codes,
                    lastSeenAt=last_seen,
                    safetySnapshot=safety_snapshot,
                    raw={},
                )
            )
        )
        health_reports.append(
            model_dump(
                HealthReport(
                    vehicleId=vehicle_id,
                    lastSeenAt=last_seen,
                    safetySnapshot=safety_snapshot,
                    raw={},
                )
            )
        )

    rollout_targets = [
        vehicle["id"] for vehicle in vehicles[: max(1, vehicle_count // 3)]
    ]
    rollout = Rollout(
        id=_generate_id("rol"),
        stackVersion="autonomy-core:1.1.0",
        selector="model=vehicle-v3 AND ring=1",
        createdAt=base_time - timedelta(hours=3),
        createdBy="seed",
        status=RolloutStatus.ACTIVE,
        canary=RolloutCanary(
            perGroup=1,
            status={"vehicle-v3-us-west": CanaryStatus.CONVERGED},
        ),
        wave=RolloutWave(percent=50, status=None),
        progress=RolloutProgress(
            total=len(rollout_targets),
            converged=len(rollout_targets) // 2,
            applying=1,
            blocked=1,
            failed=0,
        ),
        gates=RolloutGates(
            canaryHealthy=True,
            failureThreshold=True,
            safetyChecks=True,
        ),
    )

    audit_log = [
        model_dump(
            AuditLogEntry(
                id=_generate_id("audit"),
                timestamp=base_time - timedelta(hours=2),
                actor="seed",
                action="create_deployment",
                details={
                    "rolloutId": rollout.id,
                    "stackVersion": rollout.stackVersion,
                },
            )
        ),
        model_dump(
            AuditLogEntry(
                id=_generate_id("audit"),
                timestamp=base_time - timedelta(hours=1),
                actor="seed",
                action="rollback",
                details={"rolloutId": rollout.id, "reason": "demo"},
            )
        ),
    ]

    desired_states = [
        {
            "id": desired_state_id,
            "stackVersion": "autonomy-core:1.1.0",
            "selector": "model=vehicle-v3",
            "vehicleList": None,
            "safetyPolicy": {"requireStationary": True, "minBattery": 35},
            "createdAt": (base_time - timedelta(hours=4)).isoformat(),
            "createdBy": "seed",
            "comment": "seeded desired state",
            "spec": {},
        }
    ]

    rollouts = [model_dump(rollout) | {"targets": rollout_targets}]

    return {
        "vehicles": vehicles,
        "releases": releases,
        "desired_states": desired_states,
        "rollouts": rollouts,
        "audit_log": audit_log,
        "reconcile_reports": reconcile_reports,
        "health_reports": health_reports,
        "desired_by_vehicle": desired_by_vehicle,
    }


def _event_for_status(status: VehicleStatus) -> TimelineEventType:
    if status == VehicleStatus.CONVERGED:
        return TimelineEventType.READY
    if status == VehicleStatus.APPLYING:
        return TimelineEventType.APPLY_START
    if status == VehicleStatus.BLOCKED:
        return TimelineEventType.BLOCKED
    if status == VehicleStatus.FAILED:
        return TimelineEventType.FAILED
    if status == VehicleStatus.OFFLINE:
        return TimelineEventType.BLOCKED
    return TimelineEventType.DESIRED_NOTIFIED
