"""Thirty-aircraft operational scenario with scripted safety disruptions.

This module keeps the original three-aircraft demonstration untouched while
providing the dashboard with a larger, deterministic operating picture.  All
aircraft have a concrete origin and destination, and the replay includes
traffic queues, a weather closure, hospital-to-hospital medical transfers, and
charging-station diversions for both critical-battery and technical incidents.
"""

from collections import Counter
from dataclasses import dataclass
from math import ceil
from random import Random

from backend.communication import CommunicationConfig, MessageBus
from backend.emergency import (
    divert_to_charging_if_needed,
    reroute_if_needed,
    resume_mission_after_charging,
)
from backend.fleet_scenario import (
    TICK_SECONDS,
    EdgeLiveState,
    FleetScenarioResult,
    FleetTick,
    FlightState,
    _advance_agent,
    _build_edge_states,
    _fleet_positions,
    _publish_edge_conditions,
    _publish_flight_updates,
    _refresh_local_views,
    _request_next_reservations,
    _select_altitude_level,
    _snapshot_fleet,
    edge_key,
)
from backend.graph import MunichAirspaceDigitalTwin
from backend.models import (
    AltitudeLevel,
    EVTOLAgent,
    EVTOLStatus,
    HealthStatus,
    MissionType,
)
from backend.planner import DynamicAirspaceState, RoutePlan, plan_dynamic_route
from backend.reservations import ReservationTable


OPERATIONAL_FLEET_SIZE = 30
MEDICAL_TRANSFER_COUNT = 4
MAX_OPERATIONAL_TICKS = 1800
CHARGING_TICKS = 4
CHARGE_PER_TICK_PERCENT = 18.0
BATTERY_PERCENT_PER_KM = 1.0
WEATHER_EVENT_TICK = 18
WEATHER_CLEAR_TICK = 75
TECHNICAL_FAILURE_TICK = 45
BATTERY_FAILURE_TICK = 10


@dataclass(frozen=True, slots=True)
class MissionDefinition:
    """One concrete mission assigned before the deterministic replay starts."""

    origin: str
    destination: str
    mission_type: MissionType
    cargo_description: str | None = None


def _route_distance(twin: MunichAirspaceDigitalTwin, path: list[str]) -> float:
    return round(
        sum(twin.graph[start][end]["distance_km"] for start, end in zip(path[:-1], path[1:])),
        2,
    )


def _select_distinct_pairs(
    slots: list[str],
    count: int,
    random_generator: Random,
    *,
    label: str,
) -> list[tuple[str, str]]:
    """Allocate origin/destination pairs without exceeding node capacity."""
    if count > len(slots):
        raise ValueError(f"Fleet size exceeds combined {label} capacity")

    origin_slots = list(slots)
    destination_slots = list(slots)
    random_generator.shuffle(origin_slots)
    random_generator.shuffle(destination_slots)
    pairs: list[tuple[str, str]] = []
    for origin in origin_slots[:count]:
        destination_index = next(
            (index for index, destination in enumerate(destination_slots) if destination != origin),
            None,
        )
        if destination_index is None:
            raise RuntimeError(f"Could not allocate a distinct {label} destination")
        pairs.append((origin, destination_slots.pop(destination_index)))
    return pairs


def _select_capacity_safe_missions(
    twin: MunichAirspaceDigitalTwin,
    random_generator: Random,
    fleet_size: int,
) -> list[MissionDefinition]:
    """Create pad and hospital missions without exceeding endpoint capacity."""
    if fleet_size < 1:
        raise ValueError("fleet_size must be at least one")

    medical_count = min(MEDICAL_TRANSFER_COUNT, fleet_size)
    transit_count = fleet_size - medical_count
    pads = [node for node in twin.nodes.values() if node.node_type == "pad"]
    hospitals = [node for node in twin.nodes.values() if node.node_type == "hospital"]
    pad_slots = [node.name for node in pads for _ in range(node.capacity)]
    hospital_slots = [node.name for node in hospitals for _ in range(node.capacity)]

    missions = [
        MissionDefinition(origin, destination, MissionType.AUTONOMOUS_TRANSIT)
        for origin, destination in _select_distinct_pairs(
            pad_slots,
            transit_count,
            random_generator,
            label="pad",
        )
    ]
    medical_payloads = ("Organ preservation container", "Emergency medical kit")
    missions.extend(
        MissionDefinition(
            origin,
            destination,
            MissionType.MEDICAL_TRANSFER,
            medical_payloads[index % len(medical_payloads)],
        )
        for index, (origin, destination) in enumerate(
            _select_distinct_pairs(
                hospital_slots,
                medical_count,
                random_generator,
                label="hospital",
            )
        )
    )
    random_generator.shuffle(missions)
    return missions


def _set_scaled_departure_occupancy(
    twin: MunichAirspaceDigitalTwin,
    missions: list[MissionDefinition],
) -> None:
    """Make dashboard occupancy match all defined mission starts."""
    origin_counts = Counter(mission.origin for mission in missions)
    for node in twin.nodes.values():
        node.current_load = origin_counts[node.name]
        twin.sync_node_to_graph(node.name)


def _sync_remaining_route(
    state: FlightState,
    twin: MunichAirspaceDigitalTwin,
) -> None:
    """Replace a waiting flight state's remaining path after a new decision."""
    state.path = [state.agent.current_node, *state.agent.current_route]
    state.route_index = 0
    state.edge_progress_km = 0.0
    state.route_distance_km = _route_distance(twin, state.path)


def _nearest_charging_plan(
    agent: EVTOLAgent,
    twin: MunichAirspaceDigitalTwin,
    dynamic_state: DynamicAirspaceState,
) -> tuple[str, RoutePlan] | None:
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
                emergency=True,
            )
        except ValueError:
            continue
        candidates.append((plan.distance_km, node.name, plan))
    if not candidates:
        return None
    _, charging_hub, plan = min(candidates, key=lambda item: (item[0], item[1]))
    return charging_hub, plan


def _divert_failure_to_charging_station(
    state: FlightState,
    twin: MunichAirspaceDigitalTwin,
    dynamic_state: DynamicAirspaceState,
    current_tick: int,
) -> bool:
    """Route a controllable technical fault to the nearest maintenance charger."""
    agent = state.agent
    if agent.health_status != HealthStatus.FAILURE or agent.current_edge is not None:
        return False
    selected = _nearest_charging_plan(agent, twin, dynamic_state)
    if selected is None:
        agent.status = EVTOLStatus.EMERGENCY
        agent.last_decision_reason = (
            "Technical failure: no reachable charging/maintenance station is available; holding."
        )
        return False

    charging_hub, plan = selected
    if agent.mission_target is None:
        agent.mission_target = agent.target_node
    agent.target_node = charging_hub
    agent.current_route = list(plan.path[1:])
    agent.route_cost_breakdown = dict(plan.cost_breakdown)
    agent.altitude_level = AltitudeLevel.EMERGENCY
    agent.speed_kmh = AltitudeLevel.EMERGENCY.cruise_speed_kmh
    agent.status = EVTOLStatus.EMERGENCY
    agent.emergency_reason = "technical_failure"
    agent.last_reroute_tick = current_tick
    agent.reroute_count += 1
    agent.last_decision_reason = (
        f"Technical failure: diverting to charging/maintenance station at {charging_hub}; "
        "original mission is paused."
    )
    _sync_remaining_route(state, twin)
    return True


def _update_dynamic_constraints(
    dynamic_state: DynamicAirspaceState,
    edge_states: list[EdgeLiveState],
    current_tick: int,
) -> None:
    for edge in edge_states:
        dynamic_state.update_edge(
            edge.start,
            edge.end,
            traffic_density=edge.traffic_density,
            noise_level=edge.noise_level,
            updated_tick=current_tick,
        )


def _select_weather_corridor(
    twin: MunichAirspaceDigitalTwin,
    flight_states: list[FlightState],
) -> tuple[str, str] | None:
    """Select an in-use non-leaf corridor so weather causes real rerouting."""
    candidate_counts: Counter[str] = Counter()
    candidates: dict[str, tuple[str, str]] = {}
    for state in flight_states:
        if state.agent.current_edge is not None:
            start, end = state.agent.current_edge
        elif state.route_index < len(state.path) - 1:
            start, end = state.path[state.route_index], state.path[state.route_index + 1]
        else:
            continue
        if twin.graph.degree(start) <= 1 or twin.graph.degree(end) <= 1:
            continue
        key = edge_key(start, end)
        candidate_counts[key] += 1
        candidates[key] = (start, end)
    if not candidate_counts:
        return None
    return candidates[max(candidate_counts, key=lambda key: (candidate_counts[key], key))]


def _apply_scripted_events(
    *,
    current_tick: int,
    twin: MunichAirspaceDigitalTwin,
    dynamic_state: DynamicAirspaceState,
    flight_states: list[FlightState],
    event_log: list[dict[str, object]],
    weather_corridor: tuple[str, str] | None,
) -> tuple[str, str] | None:
    """Create one weather, technical, and battery incident per replay run."""
    if current_tick == WEATHER_EVENT_TICK:
        weather_corridor = _select_weather_corridor(twin, flight_states)
        if weather_corridor is not None:
            dynamic_state.update_edge(
                *weather_corridor,
                weather_risk=0.9,
                blocked=True,
                updated_tick=current_tick,
            )
            event_log.append(
                {
                    "tick": current_tick,
                    "type": "weather_closure",
                    "level": "warning",
                    "message": f"Severe weather closed {weather_corridor[0]} to {weather_corridor[1]}; affected aircraft must reroute.",
                }
            )
    if current_tick == WEATHER_CLEAR_TICK and weather_corridor is not None:
        dynamic_state.update_edge(
            *weather_corridor,
            weather_risk=0.1,
            blocked=False,
            updated_tick=current_tick,
        )
        event_log.append(
            {
                "tick": current_tick,
                "type": "weather_clear",
                "level": "info",
                "message": f"Weather restriction cleared on {weather_corridor[0]} to {weather_corridor[1]}.",
            }
        )
    if current_tick == TECHNICAL_FAILURE_TICK:
        battery_fault_agent_ids = {
            str(event["agent_id"])
            for event in event_log
            if event["type"] == "critical_battery" and "agent_id" in event
        }
        candidate = next(
            (
                state
                for state in flight_states
                if state.agent.mission_type == MissionType.AUTONOMOUS_TRANSIT
                and state.agent.status not in {EVTOLStatus.IDLE, EVTOLStatus.CHARGING}
                and not twin.nodes[state.agent.current_node].charging_available
                and state.agent.evtol_id not in battery_fault_agent_ids
            ),
            None,
        )
        if candidate is not None:
            candidate.agent.health_status = HealthStatus.FAILURE
            candidate.agent.status = EVTOLStatus.EMERGENCY
            candidate.agent.altitude_level = AltitudeLevel.EMERGENCY
            candidate.agent.speed_kmh = AltitudeLevel.EMERGENCY.cruise_speed_kmh
            candidate.agent.emergency_reason = "technical_failure"
            candidate.agent.last_decision_reason = (
                "Technical failure detected; charging/maintenance diversion pending at next safe node."
            )
            event_log.append(
                {
                    "tick": current_tick,
                    "type": "technical_failure",
                    "level": "critical",
                    "agent_id": candidate.agent.evtol_id,
                    "message": (
                        f"{candidate.agent.evtol_id} reported a technical failure and is diverting "
                        "to the nearest reachable charging/maintenance station."
                    ),
                }
            )
    if current_tick == BATTERY_FAILURE_TICK:
        candidate = _select_battery_fault_candidate(
            flight_states,
            twin,
            dynamic_state,
        )
        if candidate is not None:
            candidate.agent.battery_level = min(candidate.agent.battery_level, 14.0)
            candidate.agent.emergency_reason = "critical_battery"
            candidate.agent.last_decision_reason = (
                "Critical battery fault detected during autonomous transit; charging diversion "
                "pending at next safe node."
            )
            event_log.append(
                {
                    "tick": current_tick,
                    "type": "critical_battery",
                    "level": "critical",
                    "agent_id": candidate.agent.evtol_id,
                    "message": (
                        f"{candidate.agent.evtol_id} autonomous-transit battery fault set to "
                        "critical level; emergency charging diversion required."
                    ),
                }
            )
    return weather_corridor


def _apply_agent_decisions(
    *,
    current_tick: int,
    twin: MunichAirspaceDigitalTwin,
    dynamic_state: DynamicAirspaceState,
    flight_states: list[FlightState],
    message_bus: MessageBus,
    communication_config: CommunicationConfig,
) -> None:
    """Let each waiting aircraft react to safety and dynamic constraints."""
    for state in flight_states:
        agent = state.agent
        if agent.health_status == HealthStatus.FAILURE:
            if (
                agent.status == EVTOLStatus.IDLE
                and twin.nodes[agent.current_node].charging_available
                and agent.target_node == agent.current_node
                and agent.battery_level >= 80.0
            ):
                # Maintenance charging has completed; the aircraft remains grounded.
                continue
            if (
                agent.current_edge is None
                and agent.target_node == agent.current_node
                and twin.nodes[agent.current_node].charging_available
            ):
                agent.status = EVTOLStatus.CHARGING
                agent.current_route = []
                agent.last_decision_reason = (
                    f"Arrived at {agent.current_node}; technical inspection and maintenance charging started."
                )
                continue
            _divert_failure_to_charging_station(state, twin, dynamic_state, current_tick)
            continue
        if agent.status in {EVTOLStatus.IDLE, EVTOLStatus.CHARGING}:
            continue
        if agent.current_edge is None and agent.battery_level < 30.0:
            battery_decision = divert_to_charging_if_needed(
                agent,
                twin,
                dynamic_state,
                current_tick,
                message_bus=message_bus,
                communication_config=communication_config,
            )
            if battery_decision.applied:
                _sync_remaining_route(state, twin)
                continue
        if agent.current_edge is not None:
            continue
        reroute_decision = reroute_if_needed(
            agent,
            twin,
            dynamic_state,
            current_tick,
            message_bus=message_bus,
            communication_config=communication_config,
        )
        if reroute_decision.applied:
            _sync_remaining_route(state, twin)


def _select_battery_fault_candidate(
    flight_states: list[FlightState],
    twin: MunichAirspaceDigitalTwin,
    dynamic_state: DynamicAirspaceState,
) -> FlightState | None:
    """Choose an aircraft at a safe node with a reachable emergency charger."""
    candidates: list[tuple[float, FlightState]] = []
    for state in flight_states:
        agent = state.agent
        if (
            agent.mission_type != MissionType.AUTONOMOUS_TRANSIT
            or agent.cargo_description is not None
            or agent.current_edge is not None
            or agent.status in {EVTOLStatus.IDLE, EVTOLStatus.CHARGING}
            or agent.health_status == HealthStatus.FAILURE
        ):
            continue
        for node in twin.nodes.values():
            if not node.charging_available or node.available_slots <= 0:
                continue
            try:
                plan = plan_dynamic_route(twin, agent.current_node, node.name, dynamic_state, emergency=True)
            except ValueError:
                continue
            if plan.distance_km + 5.0 <= 14.0:
                candidates.append((plan.distance_km, state))
                break
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item[0], item[1].agent.evtol_id))[1]


def _advance_with_energy(
    *,
    state: FlightState,
    twin: MunichAirspaceDigitalTwin,
    reservation_table: ReservationTable,
    current_tick: int,
    charging_ticks: dict[str, int],
) -> None:
    """Consume battery during travel and turn emergency diversions into charging stops."""
    agent = state.agent
    was_final_edge = (
        agent.current_edge is not None and state.route_index == len(state.path) - 2
    )
    target_before_advance = agent.target_node
    if agent.current_edge is not None:
        start, end = agent.current_edge
        edge_distance = twin.graph[start][end]["distance_km"]
        remaining_distance = edge_distance - state.edge_progress_km
        travel_budget = agent.speed_kmh * TICK_SECONDS / 3600.0
        travelled = min(travel_budget, remaining_distance)
        agent.battery_level = round(max(0.0, agent.battery_level - travelled * BATTERY_PERCENT_PER_KM), 2)

    _advance_agent(state, twin, reservation_table, current_tick)

    if (
        was_final_edge
        and agent.status == EVTOLStatus.IDLE
        and target_before_advance is not None
        and twin.nodes[target_before_advance].charging_available
        and agent.mission_target is not None
    ):
        agent.status = EVTOLStatus.CHARGING
        charging_ticks[agent.evtol_id] = CHARGING_TICKS
        agent.last_decision_reason = f"Arrived at {target_before_advance}; emergency charging started."


def _process_charging(
    *,
    current_tick: int,
    twin: MunichAirspaceDigitalTwin,
    dynamic_state: DynamicAirspaceState,
    flight_states: list[FlightState],
    charging_ticks: dict[str, int],
) -> None:
    """Recharge battery faults, but hold technical faults for maintenance."""
    for state in flight_states:
        agent = state.agent
        if agent.status != EVTOLStatus.CHARGING:
            continue
        charging_ticks[agent.evtol_id] = charging_ticks.get(agent.evtol_id, CHARGING_TICKS) - 1
        agent.battery_level = round(min(90.0, agent.battery_level + CHARGE_PER_TICK_PERCENT), 2)
        if (
            agent.emergency_reason == "critical_battery"
            and agent.battery_level >= 30.0
        ):
            agent.emergency_reason = None
            agent.last_decision_reason = (
                f"Critical battery condition cleared at {agent.current_node}; "
                f"charging continues at {agent.battery_level:.0f}%."
            )
        else:
            agent.last_decision_reason = (
                f"Charging at {agent.current_node}; battery is {agent.battery_level:.0f}%."
            )
        if charging_ticks[agent.evtol_id] > 0 and agent.battery_level < 80.0:
            continue
        if agent.health_status == HealthStatus.FAILURE:
            agent.status = EVTOLStatus.IDLE
            agent.target_node = agent.current_node
            agent.current_route = []
            agent.current_edge = None
            agent.estimated_arrival_time = None
            agent.last_decision_reason = (
                f"Technical diversion complete at {agent.current_node}; aircraft is grounded for "
                "maintenance and its original mission is aborted."
            )
            charging_ticks.pop(agent.evtol_id, None)
            continue
        decision = resume_mission_after_charging(
            agent,
            twin,
            dynamic_state,
            current_tick,
            charged_battery_percent=agent.battery_level,
        )
        if decision.applied:
            twin.release_landing_slot(agent.current_node)
            _sync_remaining_route(state, twin)
            charging_ticks.pop(agent.evtol_id, None)


def run_operational_fleet_scenario(
    random_seed: int = 30,
    fleet_size: int = OPERATIONAL_FLEET_SIZE,
    max_ticks: int = MAX_OPERATIONAL_TICKS,
    require_completion: bool = True,
) -> FleetScenarioResult:
    """Run a 30-eVTOL scenario with congestion, weather, and emergency events."""
    twin = MunichAirspaceDigitalTwin()
    twin.build_world()
    random_generator = Random(random_seed)
    missions = _select_capacity_safe_missions(twin, random_generator, fleet_size)
    _set_scaled_departure_occupancy(twin, missions)

    dynamic_state = DynamicAirspaceState()
    flight_states: list[FlightState] = []
    initial_routes: dict[str, list[str]] = {}
    initial_distances: dict[str, float] = {}
    initial_costs: dict[str, float] = {}
    for index, mission in enumerate(missions, start=1):
        origin = mission.origin
        destination = mission.destination
        plan = plan_dynamic_route(twin, origin, destination, dynamic_state)
        altitude = _select_altitude_level(plan.distance_km, HealthStatus.NORMAL)
        agent = EVTOLAgent(
            evtol_id=f"E{index:02d}",
            current_node=origin,
            target_node=destination,
            assigned_origin=origin,
            assigned_destination=destination,
            mission_type=mission.mission_type,
            cargo_description=mission.cargo_description,
            current_route=list(plan.path[1:]),
            battery_level=98.0 - (index % 5) * 3.0,
            speed_kmh=altitude.cruise_speed_kmh,
            altitude_level=altitude,
            status=EVTOLStatus.ASSIGNED,
            route_cost_breakdown=dict(plan.cost_breakdown),
            last_decision_reason=(
                f"Medical transfer: {mission.cargo_description} from {origin} to {destination}."
                if mission.mission_type == MissionType.MEDICAL_TRANSFER
                else f"Defined autonomous transit: {origin} to {destination} via dynamic route."
            ),
        )
        state = FlightState(
            agent=agent,
            path=list(plan.path),
            route_distance_km=plan.distance_km,
            static_route_cost=plan.total_cost,
            departure_load_before=twin.nodes[origin].current_load,
            arrival_load_before=twin.nodes[destination].current_load,
        )
        flight_states.append(state)
        initial_routes[agent.evtol_id] = list(plan.path)
        initial_distances[agent.evtol_id] = plan.distance_km
        initial_costs[agent.evtol_id] = plan.total_cost

    communication_config = CommunicationConfig(tick_seconds=TICK_SECONDS)
    message_bus = MessageBus()
    reservation_table = ReservationTable(edge_capacity=3)
    reservation_log: list[dict[str, object]] = []
    event_log: list[dict[str, object]] = []
    charging_ticks: dict[str, int] = {}
    ticks: list[FleetTick] = []
    weather_corridor: tuple[str, str] | None = None
    congestion_logged = False

    for state in flight_states:
        twin.release_landing_slot(state.path[0])
        state.departure_load_after = twin.nodes[state.path[0]].current_load

    for tick in range(max_ticks + 1):
        reservation_table.release_expired(tick)
        weather_corridor = _apply_scripted_events(
            current_tick=tick,
            twin=twin,
            dynamic_state=dynamic_state,
            flight_states=flight_states,
            event_log=event_log,
            weather_corridor=weather_corridor,
        )
        _process_charging(
            current_tick=tick,
            twin=twin,
            dynamic_state=dynamic_state,
            flight_states=flight_states,
            charging_ticks=charging_ticks,
        )
        _apply_agent_decisions(
            current_tick=tick,
            twin=twin,
            dynamic_state=dynamic_state,
            flight_states=flight_states,
            message_bus=message_bus,
            communication_config=communication_config,
        )
        positions = _fleet_positions(flight_states, twin)
        _publish_flight_updates(
            flight_states=flight_states,
            positions=positions,
            current_tick=tick,
            config=communication_config,
            message_bus=message_bus,
        )
        previous_reservations = len(reservation_log)
        _request_next_reservations(
            flight_states=flight_states,
            twin=twin,
            current_tick=tick,
            reservation_table=reservation_table,
            reservation_log=reservation_log,
            message_bus=message_bus,
            config=communication_config,
        )
        if not congestion_logged:
            denied = [
                decision
                for decision in reservation_log[previous_reservations:]
                if not decision["approved"]
            ]
            if denied:
                congestion_logged = True
                event_log.append(
                    {
                        "tick": tick,
                        "type": "traffic_congestion",
                        "level": "warning",
                        "message": f"Traffic congestion: {len(denied)} corridor or landing requests queued by reservation priority.",
                    }
                )

        edge_states = _build_edge_states(twin, flight_states)
        _update_dynamic_constraints(dynamic_state, edge_states, tick)
        _publish_edge_conditions(
            flight_states=flight_states,
            edge_states=edge_states,
            current_tick=tick,
            config=communication_config,
            message_bus=message_bus,
        )
        from backend.fleet_scenario import _process_incoming_messages

        _process_incoming_messages(
            flight_states=flight_states,
            current_tick=tick,
            message_bus=message_bus,
        )
        _refresh_local_views(twin, flight_states, edge_states, current_tick=tick)
        ticks.append(
            _snapshot_fleet(
                tick,
                flight_states,
                twin,
                edge_states,
                message_bus,
                reservation_table,
            )
        )
        if all(state.agent.status == EVTOLStatus.IDLE for state in flight_states) and tick > 0:
            break
        for state in flight_states:
            _advance_with_energy(
                state=state,
                twin=twin,
                reservation_table=reservation_table,
                current_tick=tick,
                charging_ticks=charging_ticks,
            )
    else:
        if not require_completion:
            return FleetScenarioResult(
                airspace=twin,
                agents=[state.agent for state in flight_states],
                routes=initial_routes,
                route_distances_km=initial_distances,
                static_route_costs=initial_costs,
                ticks=ticks,
                tick_seconds=TICK_SECONDS,
                message_log=[message.to_dict() for message in message_bus.history],
                reservation_log=reservation_log,
                event_log=event_log,
            )
        raise RuntimeError("Operational fleet did not complete within the tick limit")

    return FleetScenarioResult(
        airspace=twin,
        agents=[state.agent for state in flight_states],
        routes=initial_routes,
        route_distances_km=initial_distances,
        static_route_costs=initial_costs,
        ticks=ticks,
        tick_seconds=TICK_SECONDS,
        message_log=[message.to_dict() for message in message_bus.history],
        reservation_log=reservation_log,
        event_log=event_log,
    )


def main() -> None:
    """Print the operational scenario summary for a quick backend smoke test."""
    result = run_operational_fleet_scenario()
    print(f"Completed {len(result.agents)} defined eVTOL missions in {result.ticks[-1].simulation_seconds / 60:.1f} minutes.")
    for event in result.event_log:
        print(f"T+{event['tick'] * TICK_SECONDS}s [{event['type']}]: {event['message']}")


if __name__ == "__main__":
    main()
