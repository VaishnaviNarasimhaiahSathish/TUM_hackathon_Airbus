"""Three-agent eVTOL fleet simulation with live traffic and noise values.

The module intentionally uses a deterministic tick model rather than external
data feeds. It is a hackathon-ready stand-in for a future U-space/vertiport
integration: every tick updates canonical edge traffic/noise and then copies
only local corridor data into each eVTOL's local views.
"""

from dataclasses import dataclass, field
from math import ceil
from random import Random

from backend.communication import (
    CommunicationConfig,
    MessageBus,
    MessagePriority,
    MessageType,
    discover_neighbors,
)
from backend.graph import MunichAirspaceDigitalTwin
from backend.models import AltitudeLevel, EVTOLAgent, EVTOLStatus, HealthStatus
from backend.reservations import (
    ReservationRequest,
    ReservationResource,
    ReservationTable,
    priority_tuple,
)


FLEET_SIZE = 3
TICK_SECONDS = 10
LONG_ROUTE_THRESHOLD_KM = 10.0
MAX_SIMULATION_TICKS = 360

BASE_TRAFFIC_BY_ROUTE_TYPE = {
    "airport_corridor": 0.15,
    "city_corridor": 0.20,
    "medical_corridor": 0.10,
    "charging_corridor": 0.08,
}

ZONE_NOISE_SENSITIVITY = {
    "residential": 0.22,
    "commercial": 0.14,
    "educational": 0.10,
    "event": 0.08,
    "airport": 0.04,
    "medical": 0.06,
}

ALTITUDE_NOISE_IMPACT = {
    AltitudeLevel.INBOUND: 0.18,
    AltitudeLevel.OUTBOUND: 0.08,
    AltitudeLevel.EMERGENCY: 0.28,
}


def edge_key(start: str, end: str) -> str:
    """Create a direction-independent key for a bidirectional corridor."""
    return "|".join(sorted((start, end)))


@dataclass(slots=True)
class EdgeLiveState:
    """Dynamic, canonical traffic/noise state for one graph corridor."""

    start: str
    end: str
    traffic_density: float
    noise_level: float
    active_agent_ids: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "key": edge_key(self.start, self.end),
            "start": self.start,
            "end": self.end,
            "traffic_density": round(self.traffic_density, 2),
            "noise_level": round(self.noise_level, 2),
            "active_agent_ids": list(self.active_agent_ids),
        }


@dataclass(slots=True)
class AgentFrame:
    """One UI-ready position and state snapshot for an eVTOL."""

    evtol_id: str
    lat: float
    lon: float
    current_node: str
    target_node: str | None
    assigned_origin: str | None
    assigned_destination: str | None
    mission_target: str | None
    mission_type: str
    cargo_description: str | None
    status: str
    speed_kmh: float
    altitude_level: str
    altitude_m: int
    battery_level: float
    health_status: str
    emergency_reason: str | None
    current_edge: tuple[str, str] | None
    current_route: list[str]
    estimated_arrival_time: int | None
    neighbor_count: int
    communication_neighbors: list[dict[str, object]]
    local_traffic_view: dict[str, float]
    local_noise_view: dict[str, float]
    local_weather_view: dict[str, float]
    local_vertiport_queue_view: dict[str, int]
    route_cost_breakdown: dict[str, float]
    decision_reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "evtol_id": self.evtol_id,
            "lat": self.lat,
            "lon": self.lon,
            "current_node": self.current_node,
            "target_node": self.target_node,
            "assigned_origin": self.assigned_origin,
            "assigned_destination": self.assigned_destination,
            "mission_target": self.mission_target,
            "mission_type": self.mission_type,
            "cargo_description": self.cargo_description,
            "status": self.status,
            "speed_kmh": self.speed_kmh,
            "altitude_level": self.altitude_level,
            "altitude_m": self.altitude_m,
            "battery_level": self.battery_level,
            "health_status": self.health_status,
            "emergency_reason": self.emergency_reason,
            "current_edge": list(self.current_edge) if self.current_edge else None,
            "current_route": list(self.current_route),
            "estimated_arrival_time": self.estimated_arrival_time,
            "neighbor_count": self.neighbor_count,
            "communication_neighbors": list(self.communication_neighbors),
            "local_traffic_view": dict(self.local_traffic_view),
            "local_noise_view": dict(self.local_noise_view),
            "local_weather_view": dict(self.local_weather_view),
            "local_vertiport_queue_view": dict(self.local_vertiport_queue_view),
            "route_cost_breakdown": dict(self.route_cost_breakdown),
            "decision_reason": self.decision_reason,
        }


@dataclass(slots=True)
class FleetTick:
    """A complete simulation snapshot after one ten-second simulation tick."""

    tick: int
    simulation_seconds: int
    agents: list[AgentFrame]
    node_states: list[dict[str, object]]
    edge_states: list[EdgeLiveState]
    active_message_count: int
    active_reservation_count: int


@dataclass(slots=True)
class FlightState:
    """Internal movement state that supplements the public agent model."""

    agent: EVTOLAgent
    path: list[str]
    route_distance_km: float
    static_route_cost: float
    route_index: int = 0
    edge_progress_km: float = 0.0
    departure_load_before: int = 0
    departure_load_after: int = 0
    arrival_load_before: int = 0
    arrival_load_after: int | None = None
    landing_reserved: bool = False


@dataclass(slots=True)
class FleetScenarioResult:
    """Replay data and final fleet state for the three-agent demonstration."""

    airspace: MunichAirspaceDigitalTwin
    agents: list[EVTOLAgent]
    routes: dict[str, list[str]]
    route_distances_km: dict[str, float]
    static_route_costs: dict[str, float]
    ticks: list[FleetTick]
    tick_seconds: int
    message_log: list[dict[str, object]]
    reservation_log: list[dict[str, object]]
    event_log: list[dict[str, object]] = field(default_factory=list)


def _select_altitude_level(
    route_distance_km: float,
    health_status: HealthStatus,
) -> AltitudeLevel:
    """Assign a flight profile from route length, unless safety overrides it."""
    if health_status == HealthStatus.FAILURE:
        return AltitudeLevel.EMERGENCY
    if route_distance_km >= LONG_ROUTE_THRESHOLD_KM:
        return AltitudeLevel.OUTBOUND
    return AltitudeLevel.INBOUND


def _select_fleet_pad_pairs(
    twin: MunichAirspaceDigitalTwin,
    random_generator: Random,
) -> list[tuple[str, str]]:
    """Choose distinct valid pad pairs so three aircraft have clear demos."""
    departures = [
        node.name
        for node in twin.nodes.values()
        if node.node_type == "pad" and node.current_load > 0
    ]
    destinations = [
        node.name
        for node in twin.nodes.values()
        if node.node_type == "pad" and node.available_slots > 0
    ]

    if len(departures) < FLEET_SIZE or len(destinations) < FLEET_SIZE:
        raise RuntimeError("Not enough available pads to initialise the fleet")

    long_route_pairs = []
    for origin in departures:
        for destination in destinations:
            if origin == destination:
                continue
            _, distance_km, _ = twin.find_shortest_path(origin, destination)
            if distance_km >= LONG_ROUTE_THRESHOLD_KM:
                long_route_pairs.append((origin, destination))

    if not long_route_pairs:
        raise RuntimeError("No long pad-to-pad route is available for the fleet")

    selected_pairs = [random_generator.choice(long_route_pairs)]
    used_pads: set[str] = set(selected_pairs[0])

    for _ in range(FLEET_SIZE - 1):
        origin_options = [name for name in departures if name not in used_pads]
        if not origin_options:
            raise RuntimeError("Could not select distinct fleet departure pads")

        origin = random_generator.choice(origin_options)
        destination_options = [
            name
            for name in destinations
            if name != origin and name not in used_pads
        ]
        if not destination_options:
            raise RuntimeError("Could not select distinct fleet destination pads")

        destination = random_generator.choice(destination_options)
        selected_pairs.append((origin, destination))
        used_pads.update((origin, destination))

    return selected_pairs


def _set_active_edge(state: FlightState) -> None:
    """Set the next corridor as the agent's active movement edge."""
    if state.route_index >= len(state.path) - 1:
        state.agent.current_edge = None
        state.agent.current_route = []
        return

    start = state.path[state.route_index]
    end = state.path[state.route_index + 1]
    state.agent.current_node = start
    state.agent.current_edge = (start, end)
    state.agent.current_route = state.path[state.route_index + 1 :]


def _remaining_distance_from_airspace(
    state: FlightState,
    twin: MunichAirspaceDigitalTwin,
) -> float:
    """Calculate remaining distance using the graph's per-corridor distances."""
    if state.agent.current_edge is None:
        return 0.0

    start, end = state.agent.current_edge
    remaining_distance = twin.graph[start][end]["distance_km"] - state.edge_progress_km

    for index in range(state.route_index + 1, len(state.path) - 1):
        leg_start = state.path[index]
        leg_end = state.path[index + 1]
        remaining_distance += twin.graph[leg_start][leg_end]["distance_km"]

    return max(remaining_distance, 0.0)


def _position_for_state(
    state: FlightState,
    twin: MunichAirspaceDigitalTwin,
) -> tuple[float, float]:
    """Return the current interpolated latitude/longitude of one aircraft."""
    if state.agent.current_edge is None:
        node = twin.nodes[state.agent.current_node]
        return node.lat, node.lon

    start_name, end_name = state.agent.current_edge
    start = twin.nodes[start_name]
    end = twin.nodes[end_name]
    edge_distance = twin.graph[start_name][end_name]["distance_km"]
    progress = min(state.edge_progress_km / edge_distance, 1.0)
    return (
        start.lat + (end.lat - start.lat) * progress,
        start.lon + (end.lon - start.lon) * progress,
    )


def _build_edge_states(
    twin: MunichAirspaceDigitalTwin,
    flight_states: list[FlightState],
) -> list[EdgeLiveState]:
    """Create sensible live traffic/noise values from active aircraft movement."""
    active_by_edge: dict[str, list[EVTOLAgent]] = {}
    for state in flight_states:
        if state.agent.current_edge is None:
            continue
        key = edge_key(*state.agent.current_edge)
        active_by_edge.setdefault(key, []).append(state.agent)

    edge_states: list[EdgeLiveState] = []
    for start, end, edge_data in twin.graph.edges(data=True):
        key = edge_key(start, end)
        active_agents = active_by_edge.get(key, [])
        base_traffic = BASE_TRAFFIC_BY_ROUTE_TYPE.get(edge_data["route_type"], 0.10)
        traffic_density = min(1.0, base_traffic + 0.35 * len(active_agents))

        static_noise = edge_data["noise_penalty"] / 8.0
        zone_sensitivity = max(
            ZONE_NOISE_SENSITIVITY.get(twin.nodes[start].zone_type, 0.08),
            ZONE_NOISE_SENSITIVITY.get(twin.nodes[end].zone_type, 0.08),
        )
        altitude_noise = sum(
            ALTITUDE_NOISE_IMPACT[agent.altitude_level]
            for agent in active_agents
        )
        noise_level = min(
            1.0,
            static_noise * 0.55
            + traffic_density * 0.35
            + zone_sensitivity
            + altitude_noise,
        )

        edge_states.append(
            EdgeLiveState(
                start=start,
                end=end,
                traffic_density=traffic_density,
                noise_level=noise_level,
                active_agent_ids=[agent.evtol_id for agent in active_agents],
            )
        )

    return edge_states


def _refresh_local_views(
    twin: MunichAirspaceDigitalTwin,
    flight_states: list[FlightState],
    edge_states: list[EdgeLiveState],
    current_tick: int,
) -> None:
    """Copy nearby canonical state into each agent's local traffic/noise views."""
    states_by_key = {edge_key(state.start, state.end): state for state in edge_states}

    for flight_state in flight_states:
        agent = flight_state.agent
        nearby_keys = {
            edge_key(agent.current_node, neighbor)
            for neighbor in twin.graph.neighbors(agent.current_node)
        }
        if agent.current_edge is not None:
            nearby_keys.add(edge_key(*agent.current_edge))

        for key in nearby_keys:
            if key not in states_by_key:
                continue
            agent.local_traffic_view.setdefault(key, states_by_key[key].traffic_density)
            agent.local_noise_view.setdefault(key, states_by_key[key].noise_level)
        if agent.target_node is not None:
            agent.local_vertiport_queue_view = {
                agent.target_node: twin.nodes[agent.target_node].current_load
            }

        if agent.current_edge is None:
            continue

        current_key = edge_key(*agent.current_edge)
        current_state = states_by_key[current_key]
        remaining_ticks = ceil(
            _remaining_distance_from_airspace(flight_state, twin)
            / agent.speed_kmh
            * 3600
            / TICK_SECONDS
        )
        agent.estimated_arrival_time = current_tick + remaining_ticks
        if agent.emergency_reason == "technical_failure":
            agent.last_decision_reason = (
                f"Technical failure: controlled flight toward {agent.target_node}; "
                f"maintenance diversion follows at the next safe node. Local traffic "
                f"{current_state.traffic_density:.2f}, noise {current_state.noise_level:.2f}."
            )
        else:
            agent.last_decision_reason = (
                f"Flying at {agent.altitude_level.value} level "
                f"({agent.altitude_m} m, {agent.speed_kmh:.0f} km/h); "
                f"local traffic {current_state.traffic_density:.2f}, "
                f"noise {current_state.noise_level:.2f}."
            )


def _advance_agent(
    state: FlightState,
    twin: MunichAirspaceDigitalTwin,
    reservation_table: ReservationTable,
    tick: int,
) -> None:
    """Advance one eVTOL according to its speed for one ten-second tick."""
    agent = state.agent
    if agent.current_edge is None:
        return

    travel_budget_km = agent.speed_kmh * TICK_SECONDS / 3600.0
    start, end = agent.current_edge
    edge_distance = twin.graph[start][end]["distance_km"]
    remaining_edge_distance = edge_distance - state.edge_progress_km

    if travel_budget_km < remaining_edge_distance:
        state.edge_progress_km += travel_budget_km
        return

    state.route_index += 1
    state.edge_progress_km = 0.0
    agent.current_node = end
    reservation_table.release_agent(agent.evtol_id, edge_key(start, end))

    if state.route_index >= len(state.path) - 1:
        destination = state.path[-1]
        if not twin.occupy_landing_slot(destination):
            raise RuntimeError(f"No landing slot available at {destination}")
        state.arrival_load_after = twin.nodes[destination].current_load
        reservation_table.release_agent(agent.evtol_id)
        agent.current_edge = None
        agent.current_route = []
        agent.status = EVTOLStatus.IDLE
        agent.estimated_arrival_time = tick
        agent.last_decision_reason = f"Arrived safely at {destination}."
        return

    agent.current_edge = None
    agent.current_route = state.path[state.route_index + 1 :]
    agent.status = EVTOLStatus.ASSIGNED
    agent.last_decision_reason = "Reached a corridor junction; requesting the next edge reservation."


def _snapshot_fleet(
    tick: int,
    flight_states: list[FlightState],
    twin: MunichAirspaceDigitalTwin,
    edge_states: list[EdgeLiveState],
    message_bus: MessageBus,
    reservation_table: ReservationTable,
) -> FleetTick:
    """Capture UI-ready positions and dynamic edge data for one tick."""
    agent_frames: list[AgentFrame] = []
    for state in flight_states:
        lat, lon = _position_for_state(state, twin)
        agent = state.agent
        agent_frames.append(
            AgentFrame(
                evtol_id=agent.evtol_id,
                lat=lat,
                lon=lon,
                current_node=agent.current_node,
                target_node=agent.target_node,
                assigned_origin=agent.assigned_origin or state.path[0],
                assigned_destination=(
                    agent.assigned_destination
                    or agent.mission_target
                    or agent.target_node
                ),
                mission_target=agent.mission_target,
                mission_type=agent.mission_type.value,
                cargo_description=agent.cargo_description,
                status=agent.status.value,
                speed_kmh=agent.speed_kmh,
                altitude_level=agent.altitude_level.value,
                altitude_m=agent.altitude_m,
                battery_level=agent.battery_level,
                health_status=agent.health_status.value,
                emergency_reason=agent.emergency_reason,
                current_edge=agent.current_edge,
                current_route=list(agent.current_route),
                estimated_arrival_time=agent.estimated_arrival_time,
                neighbor_count=len(agent.communication_neighbors),
                communication_neighbors=list(agent.communication_neighbors),
                local_traffic_view=dict(agent.local_traffic_view),
                local_noise_view=dict(agent.local_noise_view),
                local_weather_view=dict(agent.local_weather_view),
                local_vertiport_queue_view=dict(agent.local_vertiport_queue_view),
                route_cost_breakdown=dict(agent.route_cost_breakdown),
                decision_reason=agent.last_decision_reason,
            )
        )

    return FleetTick(
        tick=tick,
        simulation_seconds=tick * TICK_SECONDS,
        agents=agent_frames,
        node_states=[node.to_dict() for node in twin.nodes.values()],
        edge_states=edge_states,
        active_message_count=len(message_bus.active_history(tick)),
        active_reservation_count=len(reservation_table.reservations),
    )


def _fleet_positions(
    flight_states: list[FlightState],
    twin: MunichAirspaceDigitalTwin,
) -> dict[str, tuple[float, float]]:
    """Return the current physical position of every eVTOL for neighbor checks."""
    return {
        state.agent.evtol_id: _position_for_state(state, twin)
        for state in flight_states
    }


def _publish_flight_updates(
    *,
    flight_states: list[FlightState],
    positions: dict[str, tuple[float, float]],
    current_tick: int,
    config: CommunicationConfig,
    message_bus: MessageBus,
) -> None:
    """Discover local peers and publish route/position messages to them."""
    agents = [state.agent for state in flight_states]
    neighbor_map = discover_neighbors(agents, positions, current_tick, config)

    for state in flight_states:
        agent = state.agent
        neighbors = neighbor_map[agent.evtol_id]
        agent.communication_neighbors = [neighbor.to_dict() for neighbor in neighbors]
        recipient_ids = [neighbor.neighbor_id for neighbor in neighbors]
        if not recipient_ids:
            continue

        message_bus.publish(
            sender_id=agent.evtol_id,
            recipient_ids=recipient_ids,
            message_type=MessageType.POSITION_UPDATE,
            priority=MessagePriority.NORMAL,
            payload={
                "current_node": agent.current_node,
                "current_edge": list(agent.current_edge) if agent.current_edge else None,
                "next_node": agent.current_route[0] if agent.current_route else None,
                "target_node": agent.target_node,
                "battery_level": agent.battery_level,
                "status": agent.status.value,
                "speed_kmh": agent.speed_kmh,
                "altitude_level": agent.altitude_level.value,
            },
            sent_at_tick=current_tick,
            ttl_ticks=config.normal_ttl_ticks,
        )

        if current_tick == 0:
            message_bus.publish(
                sender_id=agent.evtol_id,
                recipient_ids=recipient_ids,
                message_type=MessageType.ROUTE_INTENT,
                priority=MessagePriority.NORMAL,
                payload={
                    "route": list(state.path[state.route_index :]),
                    "target_node": agent.target_node,
                    "eta_tick": agent.estimated_arrival_time,
                },
                sent_at_tick=current_tick,
                ttl_ticks=config.normal_ttl_ticks,
            )


def _publish_edge_conditions(
    *,
    flight_states: list[FlightState],
    edge_states: list[EdgeLiveState],
    current_tick: int,
    config: CommunicationConfig,
    message_bus: MessageBus,
) -> None:
    """Publish active-corridor traffic/noise observations to local peers."""
    edge_by_key = {edge_key(state.start, state.end): state for state in edge_states}
    for flight_state in flight_states:
        agent = flight_state.agent
        if agent.current_edge is None:
            continue
        recipients = [entry["neighbor_id"] for entry in agent.communication_neighbors]
        if not recipients:
            continue
        condition = edge_by_key[edge_key(*agent.current_edge)]
        message_bus.publish(
            sender_id=agent.evtol_id,
            recipient_ids=recipients,
            message_type=MessageType.EDGE_CONDITION_UPDATE,
            priority=MessagePriority.NORMAL,
            payload={
                "edge_key": edge_key(*agent.current_edge),
                "traffic_density": condition.traffic_density,
                "noise_level": condition.noise_level,
                "weather_risk": 0.0,
                "blocked": False,
            },
            sent_at_tick=current_tick,
            ttl_ticks=config.normal_ttl_ticks,
        )

        if len(agent.current_route) <= 2 and agent.target_node is not None:
            message_bus.publish(
                sender_id=agent.evtol_id,
                recipient_ids=recipients,
                message_type=MessageType.LANDING_INTENT,
                priority=MessagePriority.HIGH,
                payload={
                    "target_node": agent.target_node,
                    "eta_tick": agent.estimated_arrival_time,
                },
                sent_at_tick=current_tick,
                ttl_ticks=config.normal_ttl_ticks,
            )


def _process_incoming_messages(
    *,
    flight_states: list[FlightState],
    current_tick: int,
    message_bus: MessageBus,
) -> None:
    """Apply non-expired local condition messages to each agent's views."""
    for flight_state in flight_states:
        agent = flight_state.agent
        agent.local_traffic_view = {}
        agent.local_noise_view = {}
        agent.local_weather_view = {}
        for message in message_bus.collect(agent.evtol_id, current_tick):
            if message.message_type == MessageType.EDGE_CONDITION_UPDATE:
                edge = str(message.payload["edge_key"])
                agent.local_traffic_view[edge] = float(message.payload["traffic_density"])
                agent.local_noise_view[edge] = float(message.payload["noise_level"])
                agent.local_weather_view[edge] = float(message.payload["weather_risk"])
            elif message.message_type == MessageType.LANDING_INTENT:
                target = str(message.payload["target_node"])
                eta_tick = message.payload.get("eta_tick")
                if eta_tick is not None:
                    agent.local_vertiport_queue_view[target] = int(eta_tick)


def _next_edge(state: FlightState) -> tuple[str, str] | None:
    """Return the next untraversed corridor for a waiting eVTOL."""
    if state.route_index >= len(state.path) - 1:
        return None
    return state.path[state.route_index], state.path[state.route_index + 1]


def _edge_duration_ticks(
    state: FlightState,
    twin: MunichAirspaceDigitalTwin,
) -> int:
    """Estimate a conservative time-slot duration for the next edge."""
    next_edge = _next_edge(state)
    if next_edge is None:
        return 1
    distance_km = twin.graph[next_edge[0]][next_edge[1]]["distance_km"]
    return max(1, ceil(distance_km / state.agent.speed_kmh * 3600 / TICK_SECONDS))


def _request_next_reservations(
    *,
    flight_states: list[FlightState],
    twin: MunichAirspaceDigitalTwin,
    current_tick: int,
    reservation_table: ReservationTable,
    reservation_log: list[dict[str, object]],
    message_bus: MessageBus,
    config: CommunicationConfig,
) -> None:
    """Resolve all waiting edge/landing intents using the shared bulletin board."""
    waiting_states = [
        state
        for state in flight_states
        if state.agent.current_edge is None and _next_edge(state) is not None
    ]
    waiting_states.sort(
        key=lambda state: priority_tuple(state.agent, current_tick)
    )

    for state in waiting_states:
        agent = state.agent
        start, end = _next_edge(state)  # guarded by waiting_states above
        duration_ticks = _edge_duration_ticks(state, twin)
        edge_resource_key = edge_key(start, end)
        request_id = f"EDGE_{current_tick}_{agent.evtol_id}_{state.route_index}"
        request = ReservationRequest(
            request_id=request_id,
            agent_id=agent.evtol_id,
            resource=ReservationResource.EDGE,
            resource_key=edge_resource_key,
            start_tick=current_tick,
            end_tick=current_tick + duration_ticks,
            priority=priority_tuple(agent, current_tick),
        )
        message_bus.publish(
            sender_id=agent.evtol_id,
            recipient_ids=["RESERVATION_TABLE"],
            message_type=MessageType.RESERVATION_REQUEST,
            priority=MessagePriority.NORMAL,
            payload={
                "resource": "edge",
                "resource_key": edge_resource_key,
                "start_tick": request.start_tick,
                "end_tick": request.end_tick,
            },
            sent_at_tick=current_tick,
            ttl_ticks=config.normal_ttl_ticks,
            receiver_scope="infrastructure",
            correlation_id=request_id,
        )
        decision = reservation_table.request(request, current_tick)
        reservation_log.append(
            {
                "tick": current_tick,
                "agent_id": agent.evtol_id,
                "resource": "edge",
                "resource_key": edge_resource_key,
                "approved": decision.approved,
                "reason": decision.reason,
                "conflicting_agent_id": decision.conflicting_agent_id,
            }
        )
        message_bus.publish(
            sender_id="RESERVATION_TABLE",
            recipient_ids=[agent.evtol_id],
            message_type=MessageType.RESERVATION_DECISION,
            priority=MessagePriority.HIGH if not decision.approved else MessagePriority.NORMAL,
            payload={
                "resource": "edge",
                "resource_key": edge_resource_key,
                "approved": decision.approved,
                "reason": decision.reason,
                "conflicting_agent_id": decision.conflicting_agent_id,
            },
            sent_at_tick=current_tick,
            ttl_ticks=config.normal_ttl_ticks,
            receiver_scope="direct",
            correlation_id=request_id,
        )
        if not decision.approved:
            agent.status = EVTOLStatus.ASSIGNED
            agent.last_decision_reason = (
                f"Holding at {agent.current_node}; edge reservation denied because "
                f"{decision.conflicting_agent_id} has priority."
            )
            continue

        is_final_edge = state.route_index == len(state.path) - 2
        if is_final_edge:
            landing_request_id = f"LANDING_{current_tick}_{agent.evtol_id}_{end}"
            landing_request = ReservationRequest(
                request_id=landing_request_id,
                agent_id=agent.evtol_id,
                resource=ReservationResource.LANDING,
                resource_key=f"landing|{end}",
                start_tick=current_tick + duration_ticks,
                end_tick=current_tick + duration_ticks + 1,
                priority=priority_tuple(agent, current_tick + duration_ticks),
            )
            message_bus.publish(
                sender_id=agent.evtol_id,
                recipient_ids=["RESERVATION_TABLE"],
                message_type=MessageType.RESERVATION_REQUEST,
                priority=MessagePriority.HIGH,
                payload={
                    "resource": "landing",
                    "resource_key": landing_request.resource_key,
                    "start_tick": landing_request.start_tick,
                    "end_tick": landing_request.end_tick,
                },
                sent_at_tick=current_tick,
                ttl_ticks=config.normal_ttl_ticks,
                receiver_scope="infrastructure",
                correlation_id=landing_request_id,
            )
            landing_decision = reservation_table.request(landing_request, current_tick)
            reservation_log.append(
                {
                    "tick": current_tick,
                    "agent_id": agent.evtol_id,
                    "resource": "landing",
                    "resource_key": landing_request.resource_key,
                    "approved": landing_decision.approved,
                    "reason": landing_decision.reason,
                    "conflicting_agent_id": landing_decision.conflicting_agent_id,
                }
            )
            message_bus.publish(
                sender_id="RESERVATION_TABLE",
                recipient_ids=[agent.evtol_id],
                message_type=MessageType.RESERVATION_DECISION,
                priority=(
                    MessagePriority.NORMAL
                    if landing_decision.approved
                    else MessagePriority.HIGH
                ),
                payload={
                    "resource": "landing",
                    "resource_key": landing_request.resource_key,
                    "approved": landing_decision.approved,
                    "reason": landing_decision.reason,
                    "conflicting_agent_id": landing_decision.conflicting_agent_id,
                },
                sent_at_tick=current_tick,
                ttl_ticks=config.normal_ttl_ticks,
                receiver_scope="direct",
                correlation_id=landing_request_id,
            )
            if not landing_decision.approved:
                reservation_table.release_agent(agent.evtol_id, edge_resource_key)
                agent.status = EVTOLStatus.ASSIGNED
                agent.last_decision_reason = (
                    f"Holding at {agent.current_node}; landing reservation at {end} "
                    f"is held by {landing_decision.conflicting_agent_id}."
                )
                continue
            state.landing_reserved = True

        _set_active_edge(state)
        agent.status = EVTOLStatus.FLYING
        agent.last_decision_reason = (
            f"Reserved {start} -> {end}; flying at {agent.altitude_level.value} "
            f"level ({agent.altitude_m} m)."
        )


def run_three_agent_fleet_scenario(
    random_seed: int | None = None,
) -> FleetScenarioResult:
    """Run three concurrent random pad-to-pad eVTOL flights to completion."""
    twin = MunichAirspaceDigitalTwin()
    twin.build_world()
    random_generator = Random(random_seed)
    pad_pairs = _select_fleet_pad_pairs(twin, random_generator)

    flight_states: list[FlightState] = []
    for index, (origin, destination) in enumerate(pad_pairs, start=1):
        path, route_distance_km, static_route_cost = twin.find_shortest_path(
            origin,
            destination,
        )
        altitude_level = _select_altitude_level(route_distance_km, HealthStatus.NORMAL)
        agent = EVTOLAgent(
            evtol_id=f"E{index}",
            current_node=origin,
            target_node=destination,
            current_route=path[1:],
            battery_level=82.0 - (index - 1) * 12.0,
            speed_kmh=altitude_level.cruise_speed_kmh,
            altitude_level=altitude_level,
            status=EVTOLStatus.ASSIGNED,
            last_decision_reason=(
                f"Selected a {altitude_level.value} profile for the "
                f"{route_distance_km:.2f} km route to {destination}."
            ),
        )
        flight_states.append(
            FlightState(
                agent=agent,
                path=path,
                route_distance_km=route_distance_km,
                static_route_cost=static_route_cost,
                departure_load_before=twin.nodes[origin].current_load,
                arrival_load_before=twin.nodes[destination].current_load,
            )
        )

    communication_config = CommunicationConfig(tick_seconds=TICK_SECONDS)
    message_bus = MessageBus()
    reservation_table = ReservationTable()
    reservation_log: list[dict[str, object]] = []
    ticks: list[FleetTick] = []
    for state in flight_states:
        if not twin.release_landing_slot(state.path[0]):
            raise RuntimeError(f"Unable to release departure slot at {state.path[0]}")
        state.departure_load_after = twin.nodes[state.path[0]].current_load

    for tick in range(MAX_SIMULATION_TICKS + 1):
        reservation_table.release_expired(tick)
        positions = _fleet_positions(flight_states, twin)
        _publish_flight_updates(
            flight_states=flight_states,
            positions=positions,
            current_tick=tick,
            config=communication_config,
            message_bus=message_bus,
        )
        _request_next_reservations(
            flight_states=flight_states,
            twin=twin,
            current_tick=tick,
            reservation_table=reservation_table,
            reservation_log=reservation_log,
            message_bus=message_bus,
            config=communication_config,
        )

        edge_states = _build_edge_states(twin, flight_states)
        _publish_edge_conditions(
            flight_states=flight_states,
            edge_states=edge_states,
            current_tick=tick,
            config=communication_config,
            message_bus=message_bus,
        )
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
            _advance_agent(state, twin, reservation_table, tick)
    else:
        raise RuntimeError("Fleet did not complete within the simulation tick limit")

    return FleetScenarioResult(
        airspace=twin,
        agents=[state.agent for state in flight_states],
        routes={state.agent.evtol_id: list(state.path) for state in flight_states},
        route_distances_km={
            state.agent.evtol_id: state.route_distance_km for state in flight_states
        },
        static_route_costs={
            state.agent.evtol_id: state.static_route_cost for state in flight_states
        },
        ticks=ticks,
        tick_seconds=TICK_SECONDS,
        message_log=[message.to_dict() for message in message_bus.history],
        reservation_log=reservation_log,
    )


def main() -> None:
    """Print the three-agent simulation and generate its animated replay map."""
    from backend.fleet_ui import create_fleet_replay

    result = run_three_agent_fleet_scenario()

    print("\n" + "=" * 70)
    print("THREE-AGENT EVTOL FLEET SCENARIO")
    print("=" * 70)
    for agent in result.agents:
        route = " -> ".join(result.routes[agent.evtol_id])
        print(f"{agent.evtol_id}: {route}")
        print(
            f"  {agent.altitude_level.value} | {agent.altitude_m} m | "
            f"{agent.speed_kmh:.0f} km/h | battery {agent.battery_level:.0f}%"
        )

    print(
        f"\nSimulation completed in "
        f"{result.ticks[-1].simulation_seconds / 60:.1f} minutes."
    )
    print(
        f"Messages: {len(result.message_log)} | "
        f"Reservation decisions: {len(result.reservation_log)}"
    )
    map_file = create_fleet_replay(result)
    print(f"Animated fleet map: {map_file}")


if __name__ == "__main__":
    main()
