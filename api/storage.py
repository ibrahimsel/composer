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

"""In-memory storage for the Composer FastAPI service."""

from __future__ import annotations

from copy import deepcopy
import threading
from typing import Any, Dict, List, Optional
from uuid import uuid4

from api.logging import get_logger

from api.models import (
    AuditLogEntry,
    DeploymentConfig,
    DesiredState,
    DesiredStateRequest,
    HealthReport,
    Release,
    ReleaseRequest,
    ReconcileReport,
    Rollout,
    RolloutCanary,
    RolloutGates,
    RolloutProgress,
    RolloutStatus,
    RolloutWave,
    SafetyPolicy,
    TimelineEvent,
    TimelineEventType,
    Vehicle,
    VehicleEventRequest,
    VehicleStatus,
    VehicleStatusUpdate,
    VehicleUpdateRequest,
)
from api.seed import build_seed_data
from api.utils import model_dump, now, parse_selector, selector_matches


class InMemoryStore:
    """Thread-safe in-memory data store."""

    def __init__(self, seed_data: bool = True, seed_count: int = 12) -> None:
        self._lock = threading.RLock()
        self._logger = get_logger(__name__)
        self._vehicles: Dict[str, Dict[str, Any]] = {}
        self._releases: Dict[str, Dict[str, Any]] = {}
        self._desired_states: Dict[str, Dict[str, Any]] = {}
        self._rollouts: Dict[str, Dict[str, Any]] = {}
        self._rollout_targets: Dict[str, List[str]] = {}
        self._reconcile_reports: Dict[str, Dict[str, Any]] = {}
        self._health_reports: Dict[str, Dict[str, Any]] = {}
        self._audit_log: List[Dict[str, Any]] = []
        self._desired_by_vehicle: Dict[str, str] = {}
        self._idempotency: Dict[str, Dict[str, str]] = {
            "vehicles": {},
            "releases": {},
            "desired_states": {},
            "rollouts": {},
        }

        if seed_data:
            self._seed(seed_count)

    def _seed(self, seed_count: int) -> None:
        seed = build_seed_data(seed_count)
        with self._lock:
            for vehicle in seed["vehicles"]:
                self._vehicles[vehicle["id"]] = vehicle

            for release in seed["releases"]:
                key = self._release_key(release["stack"], release["version"])
                self._releases[key] = release

            for desired_state in seed["desired_states"]:
                self._desired_states[desired_state["id"]] = desired_state

            for rollout in seed["rollouts"]:
                self._rollouts[rollout["id"]] = rollout
                targets = rollout.get("targets", [])
                self._rollout_targets[rollout["id"]] = targets

            self._audit_log.extend(seed["audit_log"])

            for report in seed["reconcile_reports"]:
                self._reconcile_reports[report["vehicleId"]] = report

            for report in seed["health_reports"]:
                self._health_reports[report["vehicleId"]] = report

            for vehicle_id, revision in seed["desired_by_vehicle"].items():
                self._desired_by_vehicle[vehicle_id] = revision

        self._logger.info(f"Seeded in-memory API with {seed_count} vehicles")

    def _generate_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:12]}"

    def _release_key(self, stack: str, version: str) -> str:
        return f"{stack}:{version}"

    def list_vehicles(
        self,
        model: Optional[str] = None,
        region: Optional[str] = None,
        ring: Optional[str] = None,
        status: Optional[VehicleStatus] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            vehicles = list(self._vehicles.values())

        filtered: List[Dict[str, Any]] = []
        for vehicle in vehicles:
            tags = vehicle.get("tags", {})
            if model and tags.get("model") != model:
                continue
            if region and tags.get("region") != region:
                continue
            if ring and tags.get("ring") != ring:
                continue
            if status and vehicle.get("status") != status.value:
                continue
            if search and search.lower() not in vehicle.get("id", "").lower():
                continue
            filtered.append(deepcopy(vehicle))

        filtered.sort(key=lambda item: item["id"])
        return filtered

    def get_vehicle(self, vehicle_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            vehicle = self._vehicles.get(vehicle_id)
            return deepcopy(vehicle) if vehicle else None

    def create_vehicle(
        self, payload: Dict[str, Any], idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        with self._lock:
            if idempotency_key:
                existing_id = self._idempotency["vehicles"].get(
                    idempotency_key
                )
                if existing_id:
                    return deepcopy(self._vehicles[existing_id])

            vehicle_id = payload["id"]
            if vehicle_id in self._vehicles:
                raise ValueError("Vehicle already exists")

            vehicle = model_dump(Vehicle(**payload))
            self._vehicles[vehicle_id] = vehicle

            if idempotency_key:
                self._idempotency["vehicles"][idempotency_key] = vehicle_id

            return deepcopy(vehicle)

    def update_vehicle(
        self, vehicle_id: str, updates: VehicleUpdateRequest
    ) -> Dict[str, Any]:
        with self._lock:
            vehicle = self._vehicles.get(vehicle_id)
            if not vehicle:
                raise KeyError("Vehicle not found")

            data = model_dump(updates, exclude_unset=True)
            vehicle.update(data)
            self._vehicles[vehicle_id] = vehicle
            return deepcopy(vehicle)

    def update_vehicle_status(
        self, vehicle_id: str, status_update: VehicleStatusUpdate
    ) -> Dict[str, Any]:
        with self._lock:
            vehicle = self._vehicles.get(vehicle_id)
            if not vehicle:
                raise KeyError("Vehicle not found")

            vehicle["status"] = status_update.status.value
            vehicle["reasonCodes"] = status_update.reasonCodes
            vehicle["safetySnapshot"] = (
                model_dump(status_update.safetySnapshot)
                if status_update.safetySnapshot
                else None
            )
            vehicle["lastSeenAt"] = (
                status_update.lastSeenAt or now()
            ).isoformat()
            self._vehicles[vehicle_id] = vehicle
            return deepcopy(vehicle)

    def add_vehicle_event(
        self, vehicle_id: str, event_request: VehicleEventRequest
    ) -> Dict[str, Any]:
        with self._lock:
            vehicle = self._vehicles.get(vehicle_id)
            if not vehicle:
                raise KeyError("Vehicle not found")

            event_time = event_request.timestamp or now()
            timeline_event = TimelineEvent(
                timestamp=event_time,
                event=event_request.event,
                details=event_request.details,
                reasonCodes=event_request.reasonCodes,
            )
            timeline_entry = model_dump(timeline_event)

            vehicle.setdefault("timeline", []).append(timeline_entry)
            vehicle["lastSeenAt"] = event_time.isoformat()

            status_map = {
                TimelineEventType.DESIRED_NOTIFIED: VehicleStatus.PENDING,
                TimelineEventType.APPLY_START: VehicleStatus.APPLYING,
                TimelineEventType.READY: VehicleStatus.CONVERGED,
                TimelineEventType.FAILED: VehicleStatus.FAILED,
                TimelineEventType.BLOCKED: VehicleStatus.BLOCKED,
            }
            new_status = status_map.get(event_request.event)
            if new_status:
                vehicle["status"] = new_status.value
            if event_request.reasonCodes is not None:
                vehicle["reasonCodes"] = event_request.reasonCodes

            self._vehicles[vehicle_id] = vehicle
            return deepcopy(vehicle)

    def list_releases(
        self, stack: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            releases = list(self._releases.values())

        if stack:
            releases = [
                release
                for release in releases
                if release["stack"] == stack
            ]

        releases.sort(key=lambda item: (item["stack"], item["version"]))
        return [deepcopy(item) for item in releases]

    def get_release(
        self, stack: str, version: str
    ) -> Optional[Dict[str, Any]]:
        key = self._release_key(stack, version)
        with self._lock:
            release = self._releases.get(key)
            return deepcopy(release) if release else None

    def create_release(
        self, payload: ReleaseRequest, idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        with self._lock:
            if idempotency_key:
                existing_id = self._idempotency["releases"].get(
                    idempotency_key
                )
                if existing_id:
                    return deepcopy(self._releases[existing_id])

            release = Release(
                id=self._generate_id("rel"),
                stack=payload.stack,
                version=payload.version,
                digest=payload.digest,
                compatibility=payload.compatibility,
                signaturePresent=payload.signaturePresent or False,
                createdAt=now(),
            )
            release_payload = model_dump(release)
            key = self._release_key(payload.stack, payload.version)
            self._releases[key] = release_payload

            if idempotency_key:
                self._idempotency["releases"][idempotency_key] = key

            return deepcopy(release_payload)

    def list_rollouts(
        self, status: Optional[RolloutStatus] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            rollouts = list(self._rollouts.values())

        if status:
            rollouts = [
                rollout
                for rollout in rollouts
                if rollout["status"] == status.value
            ]

        rollouts.sort(key=lambda item: item["createdAt"], reverse=True)
        return [deepcopy(item) for item in rollouts]

    def get_rollout(self, rollout_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            rollout = self._rollouts.get(rollout_id)
            return deepcopy(rollout) if rollout else None

    def create_rollout(
        self, payload: DeploymentConfig, idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        with self._lock:
            if idempotency_key:
                existing_id = self._idempotency["rollouts"].get(
                    idempotency_key
                )
                if existing_id:
                    return deepcopy(self._rollouts[existing_id])

            targets = self._resolve_targets(
                payload.selector, payload.vehicleList
            )
            rollout = Rollout(
                id=self._generate_id("rol"),
                stackVersion=payload.stackVersion,
                selector=payload.selector,
                createdAt=now(),
                createdBy="system",
                status=RolloutStatus.ACTIVE,
                canary=RolloutCanary(
                    perGroup=payload.canaryPerGroup,
                    status={},
                ),
                wave=RolloutWave(
                    percent=payload.wavePercent,
                    status=None,
                ),
                progress=self._rollout_progress(targets),
                gates=RolloutGates(),
            )
            rollout_payload = model_dump(rollout)

            self._rollouts[rollout_payload["id"]] = rollout_payload
            self._rollout_targets[rollout_payload["id"]] = targets
            if idempotency_key:
                self._idempotency["rollouts"][idempotency_key] = (
                    rollout_payload["id"]
                )

            self._apply_desired_state_targets(
                rollout_id=rollout_payload["id"],
                stack_version=payload.stackVersion,
                selector=payload.selector,
                vehicle_list=payload.vehicleList,
                safety_policy=payload.safetyPolicy,
                comment=payload.comment,
            )
            self._audit(
                "system",
                "create_deployment",
                {"rolloutId": rollout_payload["id"]},
            )

            return deepcopy(rollout_payload)

    def pause_rollout(self, rollout_id: str) -> Dict[str, Any]:
        with self._lock:
            rollout = self._rollouts.get(rollout_id)
            if not rollout:
                raise KeyError("Rollout not found")
            rollout["status"] = RolloutStatus.PAUSED.value
            self._rollouts[rollout_id] = rollout
            self._audit("system", "pause_rollout", {"rolloutId": rollout_id})
            return deepcopy(rollout)

    def rollback_rollout(self, rollout_id: str) -> Dict[str, Any]:
        with self._lock:
            rollout = self._rollouts.get(rollout_id)
            if not rollout:
                raise KeyError("Rollout not found")
            rollout["status"] = RolloutStatus.ROLLED_BACK.value
            self._rollouts[rollout_id] = rollout

            for vehicle_id in self._rollout_targets.get(rollout_id, []):
                vehicle = self._vehicles.get(vehicle_id)
                if vehicle:
                    vehicle["status"] = VehicleStatus.ROLLED_BACK.value
                    self._vehicles[vehicle_id] = vehicle

            self._audit("system", "rollback", {"rolloutId": rollout_id})
            return deepcopy(rollout)

    def create_desired_state(
        self,
        payload: DesiredStateRequest,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if idempotency_key:
                existing_id = self._idempotency["desired_states"].get(
                    idempotency_key
                )
                if existing_id:
                    return deepcopy(self._desired_states[existing_id])

            desired_state = DesiredState(
                id=self._generate_id("dsr"),
                stackVersion=payload.stackVersion,
                selector=payload.selector,
                vehicleList=payload.vehicleList,
                safetyPolicy=payload.safetyPolicy,
                createdAt=now(),
                createdBy="system",
                comment=payload.comment,
                spec={},
            )
            desired_state_payload = model_dump(desired_state)

            self._desired_states[
                desired_state_payload["id"]
            ] = desired_state_payload
            if idempotency_key:
                self._idempotency["desired_states"][idempotency_key] = (
                    desired_state_payload["id"]
                )

            self._apply_desired_state_targets(
                rollout_id=None,
                stack_version=payload.stackVersion,
                selector=payload.selector,
                vehicle_list=payload.vehicleList,
                safety_policy=payload.safetyPolicy,
                comment=payload.comment,
                desired_state_id=desired_state_payload["id"],
            )
            self._audit(
                "system",
                "create_desired_state",
                {"desiredStateId": desired_state_payload["id"]},
            )

            return deepcopy(desired_state_payload)

    def get_desired_state(self, revision: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            desired_state = self._desired_states.get(revision)
            return deepcopy(desired_state) if desired_state else None

    def get_latest_desired_state(
        self, vehicle_id: str
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            revision = self._desired_by_vehicle.get(vehicle_id)
            if not revision:
                return None
            desired_state = self._desired_states.get(revision)
            return deepcopy(desired_state) if desired_state else None

    def get_reconcile_report(
        self, vehicle_id: str
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            report = self._reconcile_reports.get(vehicle_id)
            return deepcopy(report) if report else None

    def get_health_report(self, vehicle_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            report = self._health_reports.get(vehicle_id)
            return deepcopy(report) if report else None

    def set_reconcile_report(self, report: ReconcileReport) -> Dict[str, Any]:
        payload = model_dump(report)
        payload["lastSeenAt"] = (report.lastSeenAt or now()).isoformat()

        with self._lock:
            self._reconcile_reports[report.vehicleId] = payload
            vehicle = self._vehicles.get(report.vehicleId)
            if vehicle:
                vehicle["actualStack"] = report.actualStack
                vehicle["actualRevision"] = report.actualRevision
                vehicle["status"] = report.status.value
                vehicle["reasonCodes"] = report.reasonCodes
                vehicle["lastSeenAt"] = payload["lastSeenAt"]
                vehicle["safetySnapshot"] = (
                    model_dump(report.safetySnapshot)
                    if report.safetySnapshot
                    else None
                )
                vehicle["latestReport"] = payload
                self._vehicles[report.vehicleId] = vehicle

        return deepcopy(payload)

    def set_health_report(self, report: HealthReport) -> Dict[str, Any]:
        payload = model_dump(report)
        payload["lastSeenAt"] = (report.lastSeenAt or now()).isoformat()

        with self._lock:
            self._health_reports[report.vehicleId] = payload
            vehicle = self._vehicles.get(report.vehicleId)
            if vehicle:
                vehicle["lastSeenAt"] = payload["lastSeenAt"]
                vehicle["safetySnapshot"] = (
                    model_dump(report.safetySnapshot)
                    if report.safetySnapshot
                    else None
                )
                self._vehicles[report.vehicleId] = vehicle

        return deepcopy(payload)

    def list_audit_log(
        self, actor: Optional[str] = None, action: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            entries = list(self._audit_log)

        filtered: List[Dict[str, Any]] = []
        for entry in entries:
            if actor and entry.get("actor") != actor:
                continue
            if action and entry.get("action") != action:
                continue
            filtered.append(deepcopy(entry))

        filtered.sort(key=lambda item: item["timestamp"], reverse=True)
        return filtered

    def _apply_desired_state_targets(
        self,
        rollout_id: Optional[str],
        stack_version: str,
        selector: Optional[str],
        vehicle_list: Optional[List[str]],
        safety_policy: Optional[SafetyPolicy],
        comment: Optional[str],
        desired_state_id: Optional[str] = None,
    ) -> None:
        targets = self._resolve_targets(selector, vehicle_list)
        if not desired_state_id:
            desired_state_id = self._generate_id("dsr")
            desired_state = DesiredState(
                id=desired_state_id,
                stackVersion=stack_version,
                selector=selector,
                vehicleList=vehicle_list,
                safetyPolicy=safety_policy,
                createdAt=now(),
                createdBy="system",
                comment=comment,
                spec={"sourceRollout": rollout_id},
            )
            self._desired_states[desired_state_id] = model_dump(desired_state)

        for vehicle_id in targets:
            vehicle = self._vehicles.get(vehicle_id)
            if not vehicle:
                continue
            vehicle["desiredStack"] = stack_version
            vehicle["desiredRevision"] = desired_state_id
            vehicle["desiredState"] = self._desired_states[desired_state_id]
            vehicle["status"] = VehicleStatus.PENDING.value

            timeline_event = TimelineEvent(
                timestamp=now(),
                event=TimelineEventType.DESIRED_NOTIFIED,
                details=stack_version,
            )
            timeline = vehicle.setdefault("timeline", [])
            timeline.append(model_dump(timeline_event))

            self._vehicles[vehicle_id] = vehicle
            self._desired_by_vehicle[vehicle_id] = desired_state_id

    def _resolve_targets(
        self, selector: Optional[str], vehicle_list: Optional[List[str]]
    ) -> List[str]:
        if vehicle_list:
            return [
                vehicle_id
                for vehicle_id in vehicle_list
                if vehicle_id in self._vehicles
            ]

        if not selector:
            return []

        terms = parse_selector(selector)
        targets: List[str] = []
        for vehicle in self._vehicles.values():
            if selector_matches(vehicle.get("tags", {}), terms):
                targets.append(vehicle["id"])
        return targets

    def _rollout_progress(self, targets: List[str]) -> RolloutProgress:
        total = len(targets)
        return RolloutProgress(
            total=total,
            converged=0,
            applying=0,
            blocked=0,
            failed=0,
        )

    def _audit(self, actor: str, action: str, details: Dict[str, Any]) -> None:
        entry = AuditLogEntry(
            id=self._generate_id("audit"),
            timestamp=now(),
            actor=actor,
            action=action,
            details=details,
        )
        with self._lock:
            self._audit_log.append(model_dump(entry))
