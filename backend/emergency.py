"""Battery-safety, charging, emergency-dispatch, and rerouting decisions.

The functions in this module modify only an aircraft's *intent* while it is at
a graph node.  C0-C3's reservation layer still controls whether it may enter
the next corridor.  Keeping the two concerns separate makes safety decisions
easy to inspect and prevents an eVTOL from changing route halfway through a
corridor in this hackathon simulation.
"""

from dataclasses import dataclass
from math import ceil
from typing import Iterable

from backend.communication import (
    CommunicationConfig,
    MessageBus,
    MessagePriority,
    MessageType,
)
from backend.graph import MunichAirspaceDigitalTwin
from backend.models import AltitudeLevel, EVTOLAgent, EVTOLStatus, HealthStatus
from backend.planner import (
    DynamicAirspaceState,
    RoutePlan,
    evaluate_dynamic_path,
    plan_dynamic_route,
)


@dataclass(frozen=True, slots=True)
class BatteryPolicy:
    """Small, documented battery model suitable for deterministic demos."""

    low_battery_percent: float = 30.0
    critical_battery_percent: float = 15.0
    energy_percent_per_km: float = 1.0
    normal_reserve_percent: float = 10.0
    emergency_reserve_percent: float = 5.0


@dataclass(frozen=True, slots=True)
class DecisionResult:
    """Explain one autonomous decision without hiding the selected route."""

    applied: bool
    action: str
    reason: str
    plan: RoutePlan | None = None


@dataclass(frozen=True, slots=True)
class HospitalAlert:
    """A hospital-originated request for one eVTOL emergency response."""

    alert_id: str
    hospital_node: str
    created_tick: int
    description: str = "Hospital requested urgent eVTOL response."


@dataclass(frozen=True, slots=True)
class EmergencyDispatchResult:
    """The responder selected for a hospital alert, if one was safely reachable."""

    alert: HospitalAlert
    responder_id: str | None
    reason: str
    plan: RoutePlan | None = None


REROUTE_WEATHER_RISK_THRESHOLD = 0.75
REROUTE_COST_IMPROVEMENT_THRESHOLD = 0.15
REROUTE_COOLDOWN_TICKS = 3
MAX_REROUTES_PER_MISSION = 3


def _select_profile(distance_km: float, *, emergency: bool) -> AltitudeLevel:
    if emergency:
        return AltitudeLevel.EMERGENCY
    return AltitudeLevel.OUTBOUND if distance_km >= 10.0 else AltitudeLevel.INBOUND


def _apply_plan(
    agent: EVTOLAgent,
    plan: RoutePlan,
    *,
    target_node: str,
    emergency: bool,
    current_tick: int,
    reason: str,
) -> None:
    """Copy an explainable route plan into one agent's operational state."""
    profile = _select_profile(plan.distance_km, emergency=emergency)
    agent.target_node = target_node
    agent.current_route = list(plan.path[1:])
    agent.speed_kmh = profile.cruise_speed_kmh
    agent.altitude_level = profile
    agent.route_cost_breakdown = dict(plan.cost_breakdown)
    agent.last_reroute_tick = current_tick
    agent.reroute_count += 1
    agent.last_decision_reason = reason


def _reachable_with_reserve(
    agent: EVTOLAgent,
    plan: RoutePlan,
    policy: BatteryPolicy,
    *,
    emergency: bool,
) -> bool:
    reserve = (
        policy.emergency_reserve_percent
        if emergency
        else policy.normal_reserve_percent
    )
    required_percent = plan.distance_km * policy.energy_percent_per_km + reserve
    return agent.battery_level >= required_percent


def _neighbor_ids(agent: EVTOLAgent) -> list[str]:
    return [
        str(entry["neighbor_id"])
        for entry in agent.communication_neighbors
        if "neighbor_id" in entry
    ]


def _publish_charging_messages(
    *,
    agent: EVTOLAgent,
    charging_hub: str,
    plan: RoutePlan,
    current_tick: int,
    emergency: bool,
    message_bus: MessageBus | None,
    config: CommunicationConfig,
) -> None:
    """Publish local low-battery awareness and charging-station intent."""
    if message_bus is None:
        return

    neighbors = _neighbor_ids(agent)
    priority = MessagePriority.CRITICAL if emergency else MessagePriority.HIGH
    ttl = config.emergency_ttl_ticks if emergency else config.normal_ttl_ticks
    if neighbors:
        message_bus.publish(
            sender_id=agent.evtol_id,
            recipient_ids=neighbors,
            message_type=MessageType.BATTERY_LOW_ALERT,
            priority=priority,
            payload={
                "battery_level": agent.battery_level,
                "charging_hub": charging_hub,
                "emergency": emergency,
            },
            sent_at_tick=current_tick,
            ttl_ticks=ttl,
        )

    station_id = f"CHARGING_STATION:{charging_hub}"
    message_bus.publish(
        sender_id=agent.evtol_id,
        recipient_ids=[station_id],
        message_type=MessageType.CHARGING_INTENT,
        priority=priority,
        payload={
            "charging_hub": charging_hub,
            "eta_tick": current_tick + ceil(plan.distance_km / agent.speed_kmh * 3600 / config.tick_seconds),
            "battery_level": agent.battery_level,
        },
        sent_at_tick=current_tick,
        ttl_ticks=ttl,
        receiver_scope="infrastructure",
    )
    message_bus.publish(
        sender_id=station_id,
        recipient_ids=[agent.evtol_id],
        message_type=MessageType.CHARGING_DECISION,
        priority=priority,
        payload={"charging_hub": charging_hub, "accepted": True},
        sent_at_tick=current_tick,
        ttl_ticks=ttl,
        receiver_scope="direct",
    )


def divert_to_charging_if_needed(
    agent: EVTOLAgent,
    twin: MunichAirspaceDigitalTwin,
    dynamic_state: DynamicAirspaceState,
    current_tick: int,
    *,
    policy: BatteryPolicy = BatteryPolicy(),
    message_bus: MessageBus | None = None,
    communication_config: CommunicationConfig = CommunicationConfig(),
) -> DecisionResult:
    """Divert a low-battery eVTOL to the best safely reachable charging hub.

    Low battery means ``battery < 30%``.  At ``<= 15%`` the same diversion is
    treated as a safety emergency: the aircraft receives the emergency flight
    profile and reservation priority, while still heading to a charging hub.
    """
    if agent.battery_level >= policy.low_battery_percent:
        return DecisionResult(False, "continue_mission", "Battery is above the diversion threshold.")
    current_target = twin.nodes.get(agent.target_node) if agent.target_node else None
    if (
        current_target is not None
        and current_target.charging_available
        and agent.status in {EVTOLStatus.REPOSITIONING, EVTOLStatus.EMERGENCY, EVTOLStatus.CHARGING}
    ):
        return DecisionResult(
            False,
            "continue_charge_diversion",
            f"Charging diversion to {current_target.name} is already in progress.",
        )
    if agent.current_edge is not None:
        return DecisionResult(
            False,
            "defer_until_node",
            "Low battery detected while flying; divert after reaching the next safe node.",
        )

    emergency = agent.battery_level <= policy.critical_battery_percent
    candidates: list[tuple[float, str, RoutePlan]] = []
    for node in twin.nodes.values():
        if not node.charging_available or node.available_slots <= 0:
            continue
        try:
            plan = plan_dynamic_route(
                twin,
                agent.current_node,
                node.name,
                dynamic_state,
                emergency=emergency,
            )
        except ValueError:
            continue
        if _reachable_with_reserve(agent, plan, policy, emergency=emergency):
            candidates.append((plan.total_cost, node.name, plan))

    if not candidates:
        agent.status = EVTOLStatus.EMERGENCY if emergency else EVTOLStatus.ASSIGNED
        agent.last_decision_reason = (
            "No reachable charging hub has a free slot; holding at the current safe node."
        )
        return DecisionResult(False, "hold_for_charging", agent.last_decision_reason)

    _, charging_hub, plan = min(candidates, key=lambda item: (item[0], item[1]))
    if agent.target_node != charging_hub and agent.mission_target is None:
        agent.mission_target = agent.target_node
    _apply_plan(
        agent,
        plan,
        target_node=charging_hub,
        emergency=emergency,
        current_tick=current_tick,
        reason=(
            f"{'Critical' if emergency else 'Low'} battery ({agent.battery_level:.1f}%); "
            f"diverting to {charging_hub} with {plan.distance_km:.2f} km required."
        ),
    )
    agent.status = EVTOLStatus.EMERGENCY if emergency else EVTOLStatus.REPOSITIONING
    _publish_charging_messages(
        agent=agent,
        charging_hub=charging_hub,
        plan=plan,
        current_tick=current_tick,
        emergency=emergency,
        message_bus=message_bus,
        config=communication_config,
    )
    return DecisionResult(True, "emergency_charge_diversion" if emergency else "charge_diversion", agent.last_decision_reason, plan)


def begin_charging_if_arrived(agent: EVTOLAgent, twin: MunichAirspaceDigitalTwin) -> DecisionResult:
    """Switch an eVTOL that reached a charging hub into the charging state."""
    node = twin.nodes.get(agent.current_node)
    if node is None or not node.charging_available or agent.target_node != agent.current_node:
        return DecisionResult(False, "not_at_charger", "Aircraft is not at its selected charging hub.")
    agent.status = EVTOLStatus.CHARGING
    agent.current_route = []
    agent.last_decision_reason = f"Arrived at {node.name}; charging has started."
    return DecisionResult(True, "begin_charging", agent.last_decision_reason)


def resume_mission_after_charging(
    agent: EVTOLAgent,
    twin: MunichAirspaceDigitalTwin,
    dynamic_state: DynamicAirspaceState,
    current_tick: int,
    *,
    charged_battery_percent: float = 90.0,
) -> DecisionResult:
    """Complete a simple recharge and restore the pre-diversion mission."""
    if agent.status != EVTOLStatus.CHARGING or agent.mission_target is None:
        return DecisionResult(False, "no_saved_mission", "No charged diversion mission is ready to resume.")
    if not 0.0 <= charged_battery_percent <= 100.0:
        raise ValueError("charged_battery_percent must be between 0 and 100")
    plan = plan_dynamic_route(twin, agent.current_node, agent.mission_target, dynamic_state)
    agent.battery_level = charged_battery_percent
    restored_target = agent.mission_target
    agent.mission_target = None
    _apply_plan(
        agent,
        plan,
        target_node=restored_target,
        emergency=False,
        current_tick=current_tick,
        reason=f"Charging completed at {agent.current_node}; resuming mission to {restored_target}.",
    )
    agent.status = EVTOLStatus.ASSIGNED
    return DecisionResult(True, "resume_mission", agent.last_decision_reason, plan)


def dispatch_hospital_alert(
    alert: HospitalAlert,
    agents: Iterable[EVTOLAgent],
    twin: MunichAirspaceDigitalTwin,
    dynamic_state: DynamicAirspaceState,
    *,
    message_bus: MessageBus | None = None,
    communication_config: CommunicationConfig = CommunicationConfig(),
) -> EmergencyDispatchResult:
    """Select and dispatch the fastest safely reachable responder to a hospital.

    The hospital creates the alert; the selected aircraft switches to
    ``emergency`` status, causing C3 reservation priority to take effect on
    its next corridor request.  Agents already inside a corridor are not
    reassigned until their next safe node in this discrete model.
    """
    hospital = twin.nodes.get(alert.hospital_node)
    if hospital is None or not hospital.emergency_landing:
        raise ValueError("Hospital alert must target an emergency-landing hospital node")
    if hospital.available_slots <= 0:
        return EmergencyDispatchResult(alert, None, "Hospital landing capacity is currently full.")

    policy = BatteryPolicy()
    candidates: list[tuple[float, float, str, EVTOLAgent, RoutePlan]] = []
    for agent in agents:
        if (
            agent.current_edge is not None
            or agent.health_status == HealthStatus.FAILURE
            or agent.battery_level < policy.low_battery_percent
        ):
            continue
        try:
            plan = plan_dynamic_route(
                twin,
                agent.current_node,
                alert.hospital_node,
                dynamic_state,
                emergency=True,
            )
        except ValueError:
            continue
        if not _reachable_with_reserve(agent, plan, policy, emergency=True):
            continue
        response_seconds = plan.distance_km / AltitudeLevel.EMERGENCY.cruise_speed_kmh * 3600
        candidates.append((response_seconds, plan.total_cost, agent.evtol_id, agent, plan))

    if not candidates:
        return EmergencyDispatchResult(
            alert,
            None,
            "No healthy eVTOL at a safe node can reach the hospital with reserve battery.",
        )

    _, _, _, responder, plan = min(candidates, key=lambda item: item[:3])
    if responder.mission_target is None and responder.target_node != alert.hospital_node:
        responder.mission_target = responder.target_node
    _apply_plan(
        responder,
        plan,
        target_node=alert.hospital_node,
        emergency=True,
        current_tick=alert.created_tick,
        reason=(
            f"Hospital alert {alert.alert_id}: responding to {alert.hospital_node} "
            f"via emergency route ({plan.distance_km:.2f} km)."
        ),
    )
    responder.status = EVTOLStatus.EMERGENCY

    if message_bus is not None:
        hospital_sender = f"HOSPITAL:{alert.hospital_node}"
        message_bus.publish(
            sender_id=hospital_sender,
            recipient_ids=[responder.evtol_id],
            message_type=MessageType.EMERGENCY_DECLARED,
            priority=MessagePriority.CRITICAL,
            payload={
                "alert_id": alert.alert_id,
                "hospital_node": alert.hospital_node,
                "description": alert.description,
                "responder_id": responder.evtol_id,
            },
            sent_at_tick=alert.created_tick,
            ttl_ticks=communication_config.emergency_ttl_ticks,
            receiver_scope="emergency_dispatch",
            correlation_id=alert.alert_id,
        )
        neighbors = _neighbor_ids(responder)
        if neighbors:
            message_bus.publish(
                sender_id=responder.evtol_id,
                recipient_ids=neighbors,
                message_type=MessageType.EMERGENCY_ROUTE_INTENT,
                priority=MessagePriority.CRITICAL,
                payload={
                    "target_node": alert.hospital_node,
                    "route": list(plan.path),
                    "emergency": True,
                },
                sent_at_tick=alert.created_tick,
                ttl_ticks=communication_config.emergency_ttl_ticks,
                correlation_id=alert.alert_id,
            )

    return EmergencyDispatchResult(alert, responder.evtol_id, responder.last_decision_reason, plan)


def _route_hazards(path: list[str], dynamic_state: DynamicAirspaceState) -> list[str]:
    hazards: list[str] = []
    for start, end in zip(path[:-1], path[1:]):
        condition = dynamic_state.get(start, end)
        if condition.blocked:
            hazards.append(f"{start} -> {end} is blocked")
        elif condition.weather_risk >= REROUTE_WEATHER_RISK_THRESHOLD:
            hazards.append(f"{start} -> {end} weather risk is {condition.weather_risk:.2f}")
    return hazards


def reroute_if_needed(
    agent: EVTOLAgent,
    twin: MunichAirspaceDigitalTwin,
    dynamic_state: DynamicAirspaceState,
    current_tick: int,
    *,
    message_bus: MessageBus | None = None,
    communication_config: CommunicationConfig = CommunicationConfig(),
    improvement_threshold: float = REROUTE_COST_IMPROVEMENT_THRESHOLD,
) -> DecisionResult:
    """Reroute at a node only for unsafe or meaningfully cheaper dynamic paths."""
    if agent.target_node is None:
        return DecisionResult(False, "no_target", "No target is assigned, so no route can be evaluated.")
    if agent.current_edge is not None:
        return DecisionResult(False, "defer_until_node", "Will evaluate rerouting after the current corridor.")
    if agent.current_node == agent.target_node:
        return DecisionResult(False, "already_arrived", "Aircraft is already at its target node.")

    existing_path = [agent.current_node, *agent.current_route]
    try:
        current_plan = evaluate_dynamic_path(
            twin,
            existing_path,
            dynamic_state,
            emergency=agent.status == EVTOLStatus.EMERGENCY,
        )
    except ValueError:
        current_plan = RoutePlan(
            path=existing_path,
            distance_km=0.0,
            total_cost=float("inf"),
            cost_breakdown={"invalid_route": float("inf")},
            reason="Existing route is invalid and must be replaced.",
        )
    hazards = _route_hazards(existing_path, dynamic_state)
    unsafe = bool(hazards)
    cooldown_active = (
        agent.last_reroute_tick is not None
        and current_tick - agent.last_reroute_tick < REROUTE_COOLDOWN_TICKS
    )
    if not unsafe and cooldown_active:
        return DecisionResult(False, "reroute_cooldown", "Current dynamic route is safe; reroute cooldown is active.", current_plan)
    if not unsafe and agent.reroute_count >= MAX_REROUTES_PER_MISSION:
        return DecisionResult(False, "reroute_limit", "Current dynamic route is safe; reroute limit reached.", current_plan)

    try:
        candidate = plan_dynamic_route(
            twin,
            agent.current_node,
            agent.target_node,
            dynamic_state,
            emergency=agent.status == EVTOLStatus.EMERGENCY,
        )
    except ValueError:
        agent.last_decision_reason = (
            "Holding at the current safe node because no safe dynamic route is available."
        )
        return DecisionResult(False, "hold_no_safe_route", agent.last_decision_reason, current_plan)

    if candidate.path == existing_path:
        reason = (
            "Current dynamic route is the best available route."
            if not unsafe
            else "Current route is unsafe and no alternate safe route is available; holding."
        )
        agent.last_decision_reason = reason
        return DecisionResult(False, "keep_route" if not unsafe else "hold_no_alternative", reason, candidate)

    improvement = (
        1.0
        if current_plan.total_cost == float("inf")
        else (current_plan.total_cost - candidate.total_cost) / max(current_plan.total_cost, 0.01)
    )
    if not unsafe and improvement < improvement_threshold:
        agent.last_decision_reason = (
            f"Alternative route improves dynamic cost by only {improvement:.0%}; keeping current route."
        )
        return DecisionResult(False, "keep_route", agent.last_decision_reason, current_plan)

    reason_prefix = "Unsafe route avoided" if unsafe else f"Dynamic cost improved by {improvement:.0%}"
    _apply_plan(
        agent,
        candidate,
        target_node=agent.target_node,
        emergency=agent.status == EVTOLStatus.EMERGENCY,
        current_tick=current_tick,
        reason=f"{reason_prefix}; rerouted via {' -> '.join(candidate.path)}.",
    )
    if message_bus is not None and _neighbor_ids(agent):
        message_bus.publish(
            sender_id=agent.evtol_id,
            recipient_ids=_neighbor_ids(agent),
            message_type=MessageType.REROUTE_INTENT,
            priority=MessagePriority.HIGH if unsafe else MessagePriority.NORMAL,
            payload={"route": list(candidate.path), "target_node": agent.target_node, "unsafe": unsafe},
            sent_at_tick=current_tick,
            ttl_ticks=communication_config.normal_ttl_ticks,
        )
    return DecisionResult(True, "reroute", agent.last_decision_reason, candidate)
