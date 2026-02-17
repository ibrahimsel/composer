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

"""
Graph Reconciliation Manager for the Muto Composer.

Subscribes to graph drift reports from the Daemon, publishes desired state
after deployments, handles multi-sample stabilization for workspace/native
stacks, and drives reconciliation actions (node restarts, full redeploys)
based on criticality policies.
"""

import fnmatch
import threading
import time
from typing import Any

from rclpy.qos import QoSDurabilityPolicy, QoSProfile, QoSReliabilityPolicy

from muto_composer.events import (
    BaseComposeEvent,
    EventBus,
    EventType,
    GraphDriftDetectedEvent,
    GraphStateUpdatedEvent,
    ReconciliationActionEvent,
    StackRequestEvent,
)


class GraphReconciliationManager:
    """
    Manages graph reconciliation between desired and actual ROS 2 graph state.

    Responsibilities:
    - Publishes DesiredState to the Daemon after successful deployments
    - Pauses drift detection during version transitions
    - Learns baselines via multi-sample stabilization for workspace/native stacks
    - Drives reconciliation actions based on criticality policies
    - Serves ReconcileNow service for on-demand reconciliation
    """

    # Default configuration
    DEFAULT_STABILIZATION_SAMPLES = 3
    DEFAULT_STABILIZATION_SEC = 15.0
    DEFAULT_RECONCILIATION_COOLDOWN_SEC = 30.0
    DEFAULT_RECONCILIATION_MAX_RETRIES = 3
    DEFAULT_IGNORED_PREFIXES = ["/_", "/rosout", "/muto"]

    def __init__(self, node, event_bus: EventBus, logger):
        self._node = node
        self._event_bus = event_bus
        self._logger = logger

        # Configuration (could be ROS params in the future)
        self._stabilization_samples = self.DEFAULT_STABILIZATION_SAMPLES
        self._stabilization_sec = self.DEFAULT_STABILIZATION_SEC
        self._cooldown_sec = self.DEFAULT_RECONCILIATION_COOLDOWN_SEC
        self._max_retries = self.DEFAULT_RECONCILIATION_MAX_RETRIES
        self._ignored_prefixes = list(self.DEFAULT_IGNORED_PREFIXES)

        # State
        self._archived_baseline: dict[str, Any] | None = None
        self._current_desired_state: dict[str, Any] | None = None
        self._active_stack_payload: dict[str, Any] | None = None
        self._criticality_map: dict[str, str] = {}
        self._retry_counts: dict[str, int] = {}  # FQN -> retry count
        self._last_restart_time: dict[str, float] = {}  # FQN -> timestamp
        self._stabilization_active = False
        self._paused = False
        self._managed_reconciliation_launchers: dict[str, Any] = {}  # FQN -> Ros2LaunchParent
        self._lock = threading.Lock()

        # Set up ROS 2 interfaces
        self._setup_ros_interfaces()

        # Subscribe to EventBus events
        self._subscribe_to_events()

        self._logger.info("GraphReconciliationManager initialized")

    def _setup_ros_interfaces(self):
        """Set up ROS 2 publishers, subscribers, and services."""
        try:
            from muto_msgs.msg import DesiredState, GraphDrift, GraphSnapshot, NodeState
            from muto_msgs.srv import GetGraphState, ReconcileNow
        except ImportError:
            self._logger.warning(
                "muto_msgs not available, graph reconciliation disabled"
            )
            self._ros_available = False
            return

        self._ros_available = True
        self._DesiredState = DesiredState
        self._GraphDrift = GraphDrift
        self._GraphSnapshot = GraphSnapshot
        self._NodeState = NodeState
        self._GetGraphState = GetGraphState
        self._ReconcileNow = ReconcileNow

        # Publisher for desired state -> Daemon
        desired_qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._desired_state_pub = self._node.create_publisher(
            DesiredState, "/muto/daemon/desired_state", desired_qos
        )

        # Subscriber for drift reports <- Daemon
        drift_qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._drift_sub = self._node.create_subscription(
            GraphDrift, "/muto/graph_drift", self._on_graph_drift, drift_qos
        )

        # Subscriber for graph state <- Daemon (for stabilization)
        state_qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._state_sub = self._node.create_subscription(
            GraphSnapshot, "/muto/graph_state", self._on_graph_state, state_qos
        )

        # Service client for on-demand graph state query
        self._get_state_client = self._node.create_client(
            GetGraphState, "/muto/get_graph_state"
        )

        # Service server for on-demand reconciliation
        self._reconcile_srv = self._node.create_service(
            ReconcileNow, "/muto/reconcile_now", self._handle_reconcile_now
        )

    def _subscribe_to_events(self):
        """Subscribe to EventBus events for orchestration lifecycle."""
        self._event_bus.subscribe(
            EventType.ORCHESTRATION_STARTED, self._on_orchestration_started
        )
        self._event_bus.subscribe(
            EventType.ORCHESTRATION_COMPLETED, self._on_orchestration_completed
        )
        self._event_bus.subscribe(
            EventType.ORCHESTRATION_FAILED, self._on_orchestration_failed
        )

    # ── Orchestration lifecycle handlers ──────────────────────────────

    def _on_orchestration_started(self, event: BaseComposeEvent):
        """Pause drift detection and archive current baseline."""
        self._logger.info(
            f"Orchestration started ({event.orchestration_id}), "
            "pausing drift detection"
        )
        with self._lock:
            self._paused = True
            self._archived_baseline = self._current_desired_state
            self._active_stack_payload = getattr(event, "stack_payload", None)

        # Publish paused desired state to Daemon
        if self._ros_available:
            self._publish_desired_state(paused=True)

    def _on_orchestration_completed(self, event: BaseComposeEvent):
        """Extract desired state and publish or start stabilization."""
        self._logger.info(
            f"Orchestration completed ({event.orchestration_id}), "
            "resolving desired state"
        )

        stack_payload = getattr(event, "stack_payload", None) or self._active_stack_payload
        if not stack_payload:
            # Try final_stack_state from OrchestrationCompletedEvent
            stack_payload = getattr(event, "final_stack_state", None)

        content_type = self._get_content_type(stack_payload)

        if content_type in ("stack/declarative", "stack/json", "stack/legacy", "stack/ditto"):
            # Known manifest — extract nodes directly
            self._resolve_declarative_desired_state(stack_payload)
        elif content_type in ("stack/workspace", "stack/archive", "stack/native"):
            # Need to learn from live graph
            self._start_stabilization(stack_payload)
        else:
            # Legacy or unknown — try to extract, fall back to stabilization
            if self._try_extract_nodes_from_payload(stack_payload):
                self._logger.info("Extracted nodes from legacy payload")
            else:
                self._start_stabilization(stack_payload)

    def _on_orchestration_failed(self, event: BaseComposeEvent):
        """Restore archived baseline on failure."""
        self._logger.warning(
            f"Orchestration failed ({event.orchestration_id}), "
            "restoring previous baseline"
        )
        with self._lock:
            if self._archived_baseline:
                self._current_desired_state = self._archived_baseline
                self._archived_baseline = None
            self._paused = False
            self._active_stack_payload = None

        # Re-publish the restored baseline
        if self._ros_available and self._current_desired_state:
            self._publish_desired_state(paused=False)

    # ── Desired state resolution ──────────────────────────────────────

    def _get_content_type(self, payload: dict | None) -> str:
        """Extract content_type from stack payload."""
        if not payload:
            return ""
        metadata = payload.get("metadata", {})
        if isinstance(metadata, dict):
            return metadata.get("content_type", "")
        return ""

    def _resolve_declarative_desired_state(self, payload: dict):
        """Extract desired nodes from a declarative/JSON/legacy manifest."""
        nodes = []
        criticality_map = {}

        # Extract from metadata-style manifest (stack/declarative, stack/json)
        launch_spec = payload.get("launch", {})
        if isinstance(launch_spec, dict):
            for node_spec in launch_spec.get("node", []):
                fqn = self._build_fqn(
                    node_spec.get("name", ""),
                    node_spec.get("namespace", ""),
                )
                nodes.append({
                    "name": node_spec.get("name", ""),
                    "node_namespace": node_spec.get("namespace", "/"),
                    "fully_qualified_name": fqn,
                    "package_name": node_spec.get("pkg", ""),
                    "executable": node_spec.get("exec", ""),
                })
                crit = node_spec.get("criticality", "standard")
                criticality_map[fqn] = crit

        # Extract from legacy Ditto-style manifest (composable + node arrays)
        for node_spec in payload.get("node", []):
            if isinstance(node_spec, dict):
                fqn = self._build_fqn(
                    node_spec.get("name", ""),
                    node_spec.get("namespace", ""),
                )
                nodes.append({
                    "name": node_spec.get("name", ""),
                    "node_namespace": node_spec.get("namespace", "/"),
                    "fully_qualified_name": fqn,
                    "package_name": node_spec.get("pkg", node_spec.get("package", "")),
                    "executable": node_spec.get("exec", node_spec.get("executable", "")),
                })

        for container in payload.get("composable", []):
            if isinstance(container, dict):
                container_fqn = self._build_fqn(
                    container.get("name", ""),
                    container.get("namespace", ""),
                )
                nodes.append({
                    "name": container.get("name", ""),
                    "node_namespace": container.get("namespace", "/"),
                    "fully_qualified_name": container_fqn,
                    "package_name": container.get("package", ""),
                    "executable": container.get("executable", ""),
                })
                for comp_node in container.get("node", []):
                    if isinstance(comp_node, dict):
                        comp_fqn = self._build_fqn(
                            comp_node.get("name", ""),
                            container.get("namespace", ""),
                        )
                        nodes.append({
                            "name": comp_node.get("name", ""),
                            "node_namespace": container.get("namespace", "/"),
                            "fully_qualified_name": comp_fqn,
                            "package_name": comp_node.get("pkg", ""),
                            "executable": "",
                        })

        # Apply criticality_map from top-level payload
        top_crit_map = payload.get("criticality_map", {})
        if isinstance(top_crit_map, dict):
            criticality_map.update(top_crit_map)

        stack_name = self._extract_stack_name(payload)
        stack_id = self._extract_stack_id(payload)
        stack_version = self._extract_stack_version(payload)

        with self._lock:
            self._current_desired_state = {
                "stack_name": stack_name,
                "stack_id": stack_id,
                "stack_version": stack_version,
                "nodes": nodes,
                "ignored_prefixes": list(self._ignored_prefixes),
            }
            self._criticality_map = criticality_map
            self._retry_counts.clear()
            self._last_restart_time.clear()
            self._paused = False
            self._active_stack_payload = payload

        self._publish_desired_state(paused=False)
        self._event_bus.publish_sync(GraphStateUpdatedEvent(
            stack_name=stack_name,
            stack_id=stack_id,
            stack_version=stack_version,
            desired_nodes=nodes,
            status="converged",
        ))

    def _try_extract_nodes_from_payload(self, payload: dict | None) -> bool:
        """Try to extract nodes from a payload, return True if successful."""
        if not payload:
            return False
        # Check for node or composable arrays
        has_nodes = bool(payload.get("node")) or bool(payload.get("composable"))
        has_launch_nodes = bool(
            payload.get("launch", {}).get("node")
            if isinstance(payload.get("launch"), dict)
            else False
        )
        if has_nodes or has_launch_nodes:
            self._resolve_declarative_desired_state(payload)
            return True
        return False

    # ── Multi-sample stabilization ────────────────────────────────────

    def _start_stabilization(self, payload: dict | None):
        """Start multi-sample stabilization for workspace/native stacks."""
        self._logger.info(
            f"Starting multi-sample stabilization "
            f"({self._stabilization_samples} samples, "
            f"{self._stabilization_sec}s interval)"
        )
        with self._lock:
            self._stabilization_active = True

        thread = threading.Thread(
            target=self._stabilization_worker,
            args=(payload,),
            daemon=True,
        )
        thread.start()

    def _stabilization_worker(self, payload: dict | None):
        """Background worker that collects graph samples and computes baseline."""
        samples: list[set[str]] = []

        for i in range(self._stabilization_samples):
            if i > 0:
                time.sleep(self._stabilization_sec)

            fqns = self._probe_actual_nodes()
            if fqns is not None:
                samples.append(fqns)
                self._logger.info(
                    f"Stabilization sample {i + 1}/{self._stabilization_samples}: "
                    f"{len(fqns)} nodes"
                )
            else:
                self._logger.warning(
                    f"Stabilization sample {i + 1} failed (service unavailable)"
                )

        if not samples:
            self._logger.error("Stabilization failed: no samples collected")
            with self._lock:
                self._stabilization_active = False
                self._paused = False
            return

        # Baseline = intersection of all samples (stable nodes)
        baseline_fqns = samples[0]
        for sample in samples[1:]:
            baseline_fqns = baseline_fqns & sample

        # Log transient nodes
        all_fqns = set()
        for sample in samples:
            all_fqns |= sample
        transient = all_fqns - baseline_fqns
        if transient:
            self._logger.info(
                f"Transient nodes excluded from baseline: {sorted(transient)}"
            )

        # Filter out system/ignored nodes
        baseline_fqns = {
            fqn for fqn in baseline_fqns
            if not self._matches_ignored_prefix(fqn)
        }

        # Build desired state from baseline (no package/executable info)
        nodes = []
        for fqn in sorted(baseline_fqns):
            name, ns = self._split_fqn(fqn)
            nodes.append({
                "name": name,
                "node_namespace": ns,
                "fully_qualified_name": fqn,
                "package_name": "",
                "executable": "",
            })

        stack_name = self._extract_stack_name(payload) if payload else "learned-baseline"
        stack_id = self._extract_stack_id(payload) if payload else ""
        stack_version = self._extract_stack_version(payload) if payload else ""

        # Apply criticality_map from payload
        criticality_map = {}
        if payload:
            top_crit_map = payload.get("criticality_map", {})
            if isinstance(top_crit_map, dict):
                criticality_map = top_crit_map

        with self._lock:
            self._current_desired_state = {
                "stack_name": stack_name,
                "stack_id": stack_id,
                "stack_version": stack_version,
                "nodes": nodes,
                "ignored_prefixes": list(self._ignored_prefixes),
            }
            self._criticality_map = criticality_map
            self._retry_counts.clear()
            self._last_restart_time.clear()
            self._stabilization_active = False
            self._paused = False
            self._active_stack_payload = payload

        self._publish_desired_state(paused=False)
        self._logger.info(
            f"Stabilization complete: baseline has {len(nodes)} nodes"
        )
        self._event_bus.publish_sync(GraphStateUpdatedEvent(
            stack_name=stack_name,
            stack_id=stack_id,
            stack_version=stack_version,
            desired_nodes=nodes,
            status="converged",
        ))

    def _probe_actual_nodes(self) -> set[str] | None:
        """Query the Daemon's GetGraphState service for current graph."""
        if not self._ros_available:
            return None

        if not self._get_state_client.wait_for_service(timeout_sec=5.0):
            return None

        request = self._GetGraphState.Request()
        request.stack_name = ""
        future = self._get_state_client.call_async(request)

        # Spin until result (with timeout)
        start = time.time()
        while not future.done() and (time.time() - start) < 10.0:
            time.sleep(0.1)

        if not future.done():
            return None

        try:
            response = future.result()
            if response.success:
                return {
                    n.fully_qualified_name
                    for n in response.snapshot.actual_nodes
                }
        except Exception as e:
            self._logger.warning(f"GetGraphState call failed: {e}")

        return None

    # ── Drift handling & reconciliation ───────────────────────────────

    def _on_graph_drift(self, msg):
        """Handle GraphDrift messages from the Daemon."""
        with self._lock:
            if self._paused or self._stabilization_active:
                return
            if not self._current_desired_state:
                return

        missing = list(msg.missing_nodes)
        unexpected = list(msg.unexpected_nodes)

        if not missing and not unexpected:
            return

        self._logger.warning(
            f"Graph drift detected: {len(missing)} missing, "
            f"{len(unexpected)} unexpected"
        )

        # Publish internal event
        self._event_bus.publish_sync(GraphDriftDetectedEvent(
            missing_nodes=missing,
            unexpected_nodes=unexpected,
            stack_name=self._current_desired_state.get("stack_name", ""),
        ))

        # Reconcile missing nodes
        for fqn in missing:
            self._reconcile_missing_node(fqn)

    def _on_graph_state(self, msg):
        """Handle GraphSnapshot messages (used during stabilization)."""
        # Could track latest snapshot for diagnostics; stabilization uses
        # the GetGraphState service directly for reliability.
        pass

    def _reconcile_missing_node(self, fqn: str):
        """Attempt to restart a missing node based on criticality policy."""
        criticality = self._get_node_criticality(fqn)

        if criticality == "safety":
            self._logger.error(
                f"SAFETY node missing: {fqn} — alert only, no auto-restart"
            )
            self._event_bus.publish_sync(ReconciliationActionEvent(
                action_type="alert",
                node_fqn=fqn,
                criticality="safety",
                success=True,
                details="Safety node lost, manual intervention required",
            ))
            return

        # Check retry limit (read under lock, act outside)
        with self._lock:
            retries = self._retry_counts.get(fqn, 0)
            retries_exhausted = retries >= self._max_retries

        if retries_exhausted:
            self._logger.error(
                f"Retries exhausted for {fqn} ({retries}/{self._max_retries}), "
                "triggering full redeploy"
            )
            self._trigger_full_redeploy(fqn)
            return

        # Check cooldown for mission-critical nodes
        if criticality == "mission":
            with self._lock:
                last_time = self._last_restart_time.get(fqn, 0.0)
            elapsed = time.time() - last_time
            if elapsed < self._cooldown_sec:
                self._logger.info(
                    f"Mission node {fqn} in cooldown "
                    f"({elapsed:.0f}s / {self._cooldown_sec:.0f}s)"
                )
                return

        # Attempt restart
        node_info = self._find_node_info(fqn)
        pkg = node_info.get("package_name", "") if node_info else ""
        exe = node_info.get("executable", "") if node_info else ""

        self._event_bus.publish_sync(BaseComposeEvent(
            event_type=EventType.RECONCILIATION_STARTED,
            source_component="graph_reconciliation",
            stack_name=self._current_desired_state.get("stack_name", ""),
        ))

        if pkg and exe:
            success = self._restart_node_direct(fqn, pkg, exe)
        else:
            success = self._restart_via_full_relaunch()

        with self._lock:
            self._retry_counts[fqn] = self._retry_counts.get(fqn, 0) + 1
            self._last_restart_time[fqn] = time.time()

        self._event_bus.publish_sync(ReconciliationActionEvent(
            action_type="restart" if (pkg and exe) else "relaunch",
            node_fqn=fqn,
            criticality=criticality,
            success=success,
            details=f"pkg={pkg}, exe={exe}" if pkg else "full relaunch",
        ))

        if success:
            self._event_bus.publish_sync(BaseComposeEvent(
                event_type=EventType.RECONCILIATION_COMPLETED,
                source_component="graph_reconciliation",
            ))
        else:
            self._event_bus.publish_sync(BaseComposeEvent(
                event_type=EventType.RECONCILIATION_FAILED,
                source_component="graph_reconciliation",
            ))

    def _restart_node_direct(self, fqn: str, pkg: str, exe: str) -> bool:
        """Restart a node via Ros2LaunchParent with a single-node LaunchDescription."""
        self._logger.info(
            f"Restarting node {fqn} via LaunchDescription (pkg={pkg}, exe={exe})"
        )
        try:
            from launch import LaunchDescription
            from launch_ros.actions import Node as LaunchNode

            from muto_composer.workflow.launcher import Ros2LaunchParent

            name, ns = self._split_fqn(fqn)

            ld = LaunchDescription([
                LaunchNode(
                    package=pkg,
                    executable=exe,
                    name=name,
                    namespace=ns if ns != "/" else "",
                    output="screen",
                ),
            ])

            launcher = Ros2LaunchParent([])
            launcher.start(ld)

            # Track the launcher so kill actions can clean it up
            with self._lock:
                self._managed_reconciliation_launchers[fqn] = launcher

            self._logger.info(f"Node {fqn} restart launched via Ros2LaunchParent")
            return True
        except Exception as e:
            self._logger.error(f"Failed to restart {fqn}: {e}")
            return False

    def _restart_via_full_relaunch(self) -> bool:
        """Trigger full launch-file relaunch when pkg/exe unknown."""
        self._logger.info(
            "Package/executable unknown, requesting full relaunch via event bus"
        )
        with self._lock:
            payload = self._active_stack_payload

        if not payload:
            self._logger.error("No active stack payload for relaunch")
            return False

        stack_name = self._extract_stack_name(payload)
        self._event_bus.publish_sync(StackRequestEvent(
            event_type=EventType.STACK_REQUEST,
            source_component="graph_reconciliation",
            stack_name=stack_name,
            action="start",
            stack_payload=payload,
        ))
        return True

    def _trigger_full_redeploy(self, fqn: str):
        """Trigger a full stack redeploy after retries exhausted."""
        self._logger.warning(f"Triggering full redeploy due to {fqn} restart failures")

        with self._lock:
            payload = self._active_stack_payload
            # Reset retry counter so the redeploy gets a fresh set
            self._retry_counts.clear()

        if not payload:
            self._logger.error("No active stack payload for redeploy")
            return

        stack_name = self._extract_stack_name(payload)
        self._event_bus.publish_sync(StackRequestEvent(
            event_type=EventType.STACK_REQUEST,
            source_component="graph_reconciliation",
            stack_name=stack_name,
            action="apply",
            stack_payload=payload,
        ))

    # ── ReconcileNow service ──────────────────────────────────────────

    def _handle_reconcile_now(self, request, response):
        """Handle ReconcileNow service requests."""
        with self._lock:
            desired = self._current_desired_state
            paused = self._paused

        if not desired:
            response.success = False
            response.error_message = "No desired state available"
            return response

        if paused:
            response.success = False
            response.error_message = "Drift detection is paused (deployment in progress)"
            return response

        # Probe current state
        actual_fqns = self._probe_actual_nodes()
        if actual_fqns is None:
            response.success = False
            response.error_message = "Failed to probe graph state"
            return response

        # Compute drift
        desired_fqns = {n["fully_qualified_name"] for n in desired.get("nodes", [])}
        ignored = desired.get("ignored_prefixes", [])

        missing = sorted(desired_fqns - actual_fqns)
        unexpected = sorted(
            fqn for fqn in (actual_fqns - desired_fqns)
            if not any(fqn.startswith(p) for p in ignored)
        )

        response.detected_drift.missing_nodes = missing
        response.detected_drift.unexpected_nodes = unexpected

        if not request.dry_run and missing:
            actions = []
            for fqn in missing:
                self._reconcile_missing_node(fqn)
                actions.append(f"restart:{fqn}")
            response.actions_taken = actions

        response.success = True
        return response

    # ── Desired state publishing ──────────────────────────────────────

    def _publish_desired_state(self, paused: bool = False):
        """Publish DesiredState message to the Daemon."""
        if not self._ros_available:
            return

        msg = self._DesiredState()
        msg.timestamp = self._node.get_clock().now().to_msg()
        msg.paused = paused

        with self._lock:
            desired = self._current_desired_state

        if desired:
            msg.stack_name = desired.get("stack_name", "")
            msg.stack_id = desired.get("stack_id", "")
            msg.stack_version = desired.get("stack_version", "")
            msg.ignored_prefixes = desired.get("ignored_prefixes", [])

            for node_info in desired.get("nodes", []):
                ns = self._NodeState()
                ns.name = node_info.get("name", "")
                ns.node_namespace = node_info.get("node_namespace", "/")
                ns.fully_qualified_name = node_info.get("fully_qualified_name", "")
                ns.package_name = node_info.get("package_name", "")
                ns.executable = node_info.get("executable", "")
                msg.desired_nodes.append(ns)

        self._desired_state_pub.publish(msg)
        self._logger.info(
            f"Published DesiredState: stack={msg.stack_name}, "
            f"nodes={len(msg.desired_nodes)}, paused={paused}"
        )

    # ── Utility methods ───────────────────────────────────────────────

    def _build_fqn(self, name: str, namespace: str) -> str:
        """Build a fully-qualified node name from name and namespace."""
        if not namespace or namespace == "/":
            return f"/{name}"
        ns = namespace.rstrip("/")
        if not ns.startswith("/"):
            ns = f"/{ns}"
        return f"{ns}/{name}"

    def _split_fqn(self, fqn: str) -> tuple[str, str]:
        """Split an FQN into (name, namespace)."""
        if "/" not in fqn or fqn == "/":
            return (fqn.lstrip("/"), "/")
        last_slash = fqn.rfind("/")
        name = fqn[last_slash + 1:]
        ns = fqn[:last_slash] or "/"
        return (name, ns)

    def _matches_ignored_prefix(self, fqn: str) -> bool:
        """Check if an FQN matches any ignored prefix."""
        for prefix in self._ignored_prefixes:
            if fqn.startswith(prefix):
                return True
        return False

    def _get_node_criticality(self, fqn: str) -> str:
        """Look up criticality for a node FQN using exact match then glob."""
        # Exact match first
        if fqn in self._criticality_map:
            return self._criticality_map[fqn]
        # Glob/prefix match
        for pattern, crit in self._criticality_map.items():
            if fnmatch.fnmatch(fqn, pattern):
                return crit
        return "standard"

    def _find_node_info(self, fqn: str) -> dict | None:
        """Find node info dict for an FQN in current desired state."""
        with self._lock:
            desired = self._current_desired_state
        if not desired:
            return None
        for node in desired.get("nodes", []):
            if node.get("fully_qualified_name") == fqn:
                return node
        return None

    def _extract_stack_name(self, payload: dict | None) -> str:
        """Extract stack name from payload."""
        if not payload:
            return ""
        metadata = payload.get("metadata", {})
        if isinstance(metadata, dict) and metadata.get("name"):
            return metadata["name"]
        return payload.get("name", payload.get("stackId", ""))

    def _extract_stack_id(self, payload: dict | None) -> str:
        """Extract stack ID from payload."""
        if not payload:
            return ""
        return payload.get("stackId", "")

    def _extract_stack_version(self, payload: dict | None) -> str:
        """Extract stack version from payload."""
        if not payload:
            return ""
        metadata = payload.get("metadata", {})
        if isinstance(metadata, dict):
            return metadata.get("version", "")
        return ""

    # ── Public API for testing ────────────────────────────────────────

    @property
    def current_desired_state(self) -> dict[str, Any] | None:
        with self._lock:
            return self._current_desired_state

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    @property
    def is_stabilization_active(self) -> bool:
        with self._lock:
            return self._stabilization_active

    @property
    def criticality_map(self) -> dict[str, str]:
        return self._criticality_map

    @property
    def retry_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._retry_counts)
