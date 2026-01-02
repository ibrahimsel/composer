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

"""Pydantic models for the Composer FastAPI service."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class VehicleStatus(str, Enum):
    """Vehicle lifecycle states."""

    CONVERGED = "converged"
    APPLYING = "applying"
    BLOCKED = "blocked"
    FAILED = "failed"
    OFFLINE = "offline"
    PENDING = "pending"
    ROLLED_BACK = "rolled_back"


class TimelineEventType(str, Enum):
    """Timeline event types for vehicle history."""

    DESIRED_NOTIFIED = "desired_notified"
    APPLY_START = "apply_start"
    READY = "ready"
    FAILED = "failed"
    BLOCKED = "blocked"


class RolloutStatus(str, Enum):
    """Rollout lifecycle statuses."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"


class CanaryStatus(str, Enum):
    """Canary stage status."""

    PENDING = "pending"
    CONVERGED = "converged"
    FAILED = "failed"


class WaveStatus(str, Enum):
    """Wave stage status."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class ApiMetadata(BaseModel):
    """Pagination metadata for list responses."""

    page: Optional[int] = None
    totalPages: Optional[int] = None
    totalItems: Optional[int] = None


class SafetySnapshot(BaseModel):
    """Vehicle safety inputs captured at a moment in time."""

    moving: Optional[bool] = None
    autonomyMode: Optional[str] = None
    battery: Optional[int] = Field(default=None, ge=0, le=100)
    window: Optional[bool] = None


class TimelineEvent(BaseModel):
    """Event entry in a vehicle timeline."""

    timestamp: datetime
    event: TimelineEventType
    details: Optional[str] = None
    reasonCodes: Optional[List[str]] = None


class Vehicle(BaseModel):
    """Vehicle state snapshot."""

    id: str
    tags: Dict[str, str] = Field(default_factory=dict)
    desiredStack: Optional[str] = None
    desiredRevision: Optional[str] = None
    actualStack: Optional[str] = None
    actualRevision: Optional[str] = None
    status: VehicleStatus = VehicleStatus.PENDING
    lastSeenAt: Optional[datetime] = None
    reasonCodes: List[str] = Field(default_factory=list)
    safetySnapshot: Optional[SafetySnapshot] = None
    timeline: List[TimelineEvent] = Field(default_factory=list)
    desiredState: Dict[str, Any] = Field(default_factory=dict)
    latestReport: Dict[str, Any] = Field(default_factory=dict)


class VehicleCreateRequest(BaseModel):
    """Payload for creating a vehicle."""

    id: str
    tags: Dict[str, str] = Field(default_factory=dict)
    desiredStack: Optional[str] = None
    desiredRevision: Optional[str] = None
    actualStack: Optional[str] = None
    actualRevision: Optional[str] = None
    status: Optional[VehicleStatus] = None
    lastSeenAt: Optional[datetime] = None
    reasonCodes: List[str] = Field(default_factory=list)
    safetySnapshot: Optional[SafetySnapshot] = None


class VehicleUpdateRequest(BaseModel):
    """Payload for patching a vehicle."""

    tags: Optional[Dict[str, str]] = None
    desiredStack: Optional[str] = None
    desiredRevision: Optional[str] = None
    actualStack: Optional[str] = None
    actualRevision: Optional[str] = None
    status: Optional[VehicleStatus] = None
    lastSeenAt: Optional[datetime] = None
    reasonCodes: Optional[List[str]] = None
    safetySnapshot: Optional[SafetySnapshot] = None


class VehicleStatusUpdate(BaseModel):
    """Payload for updating vehicle status from agents."""

    status: VehicleStatus
    reasonCodes: List[str] = Field(default_factory=list)
    safetySnapshot: Optional[SafetySnapshot] = None
    lastSeenAt: Optional[datetime] = None


class VehicleEventRequest(BaseModel):
    """Payload for adding a timeline event."""

    event: TimelineEventType
    details: Optional[str] = None
    reasonCodes: Optional[List[str]] = None
    timestamp: Optional[datetime] = None


class Release(BaseModel):
    """Release metadata."""

    id: str
    stack: str
    version: str
    digest: Optional[str] = None
    compatibility: Optional[str] = None
    signaturePresent: bool = False
    createdAt: datetime


class ReleaseRequest(BaseModel):
    """Payload for creating a release."""

    stack: str
    version: str
    digest: Optional[str] = None
    compatibility: Optional[str] = None
    signaturePresent: Optional[bool] = None


class RolloutCanary(BaseModel):
    """Canary rollout configuration and status."""

    perGroup: Optional[int] = None
    status: Dict[str, CanaryStatus] = Field(default_factory=dict)


class RolloutWave(BaseModel):
    """Wave rollout configuration and status."""

    percent: Optional[int] = Field(default=None, ge=0, le=100)
    status: Optional[WaveStatus] = None


class RolloutProgress(BaseModel):
    """Rollout progress summary."""

    total: int = 0
    converged: int = 0
    applying: int = 0
    blocked: int = 0
    failed: int = 0


class RolloutGates(BaseModel):
    """Rollout gating checks."""

    canaryHealthy: bool = True
    failureThreshold: bool = True
    safetyChecks: bool = True


class Rollout(BaseModel):
    """Rollout state."""

    id: str
    stackVersion: str
    selector: Optional[str] = None
    createdAt: datetime
    createdBy: str
    status: RolloutStatus
    canary: RolloutCanary
    wave: RolloutWave
    progress: RolloutProgress
    gates: RolloutGates


class SafetyPolicy(BaseModel):
    """Safety policy used by desired states and rollouts."""

    applyWindow: Optional[str] = None
    requireStationary: Optional[bool] = None
    denyAutonomousMode: Optional[bool] = None
    minBattery: Optional[int] = Field(default=None, ge=0, le=100)


class DeploymentConfig(BaseModel):
    """Request body for creating rollouts."""

    stackVersion: str
    selector: Optional[str] = None
    vehicleList: Optional[List[str]] = None
    safetyPolicy: Optional[SafetyPolicy] = None
    canaryPerGroup: Optional[int] = None
    wavePercent: Optional[int] = Field(default=None, ge=0, le=100)
    comment: Optional[str] = None


class DesiredStateRequest(BaseModel):
    """Request body for desired states."""

    stackVersion: str
    selector: Optional[str] = None
    vehicleList: Optional[List[str]] = None
    safetyPolicy: Optional[SafetyPolicy] = None
    comment: Optional[str] = None


class DesiredState(BaseModel):
    """Desired state resource."""

    id: str
    stackVersion: str
    selector: Optional[str] = None
    vehicleList: Optional[List[str]] = None
    safetyPolicy: Optional[SafetyPolicy] = None
    createdAt: datetime
    createdBy: str
    comment: Optional[str] = None
    spec: Dict[str, Any] = Field(default_factory=dict)


class ReconcileReport(BaseModel):
    """Reconcile report payload."""

    vehicleId: str
    actualStack: Optional[str] = None
    actualRevision: Optional[str] = None
    status: VehicleStatus
    reasonCodes: List[str] = Field(default_factory=list)
    lastSeenAt: Optional[datetime] = None
    safetySnapshot: Optional[SafetySnapshot] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


class HealthReport(BaseModel):
    """Health report payload."""

    vehicleId: str
    lastSeenAt: Optional[datetime] = None
    safetySnapshot: Optional[SafetySnapshot] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


class AuditLogEntry(BaseModel):
    """Audit log entry."""

    id: str
    timestamp: datetime
    actor: str
    action: str
    details: Dict[str, Any] = Field(default_factory=dict)
    correlationId: Optional[str] = None
