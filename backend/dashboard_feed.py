"""Read-only dashboard data contract for the React control-center frontend."""

from dataclasses import dataclass, field
from time import monotonic

from backend.fleet_scenario import FleetScenarioResult, run_three_agent_fleet_scenario
from backend.graph import calculate_air_distance_km


UI_STATUS_BY_OPERATIONAL_STATUS = {
    "flying": "in_flight",
    "repositioning": "in_flight",
    "charging": "charging",
    "emergency": "emergency",
    "idle": "at_pad",
    "assigned": "at_pad",
}

WEATHER_ZONE_ORDER = (
    "north",
    "central",
    "east",
    "west",
    "south",
    "southeast",
    "northwest",
)


def _edge_key(start: str, end: str) -> str:
    return "|".join(sorted((start, end)))


def _flight_progress(
    result: FleetScenarioResult,
    frame: object,
) -> float:
    """Estimate within-edge progress from the recorded aircraft location."""
    current_edge = frame.current_edge
    if current_edge is None:
        return 1.0 if frame.current_node == frame.target_node else 0.0

    start, end = current_edge
    start_node = result.airspace.nodes[start]
    edge_distance = result.airspace.graph[start][end]["distance_km"]
    travelled = calculate_air_distance_km(
        start_node.lat,
        start_node.lon,
        frame.lat,
        frame.lon,
    )
    return round(min(max(travelled / max(edge_distance, 0.01), 0.0), 1.0), 3)


def _mission_label(result: FleetScenarioResult, frame: object) -> str:
    """Expose operational intent without inventing passenger-demand data."""
    if frame.status == "emergency":
        return "Emergency Response"
    target = result.airspace.nodes.get(frame.target_node) if frame.target_node else None
    if target is not None and target.charging_available:
        return "Charging Diversion"
    return "Autonomous Transit"


def _agent_payload(result: FleetScenarioResult, frame: object) -> dict[str, object]:
    current_edge = list(frame.current_edge) if frame.current_edge else None
    return {
        "id": frame.evtol_id,
        "evtol_id": frame.evtol_id,
        "status": UI_STATUS_BY_OPERATIONAL_STATUS[frame.status],
        "operational_status": frame.status,
        "battery": round(frame.battery_level, 1),
        "mission": _mission_label(result, frame),
        "from": frame.current_edge[0] if frame.current_edge else frame.current_node,
        "to": frame.target_node or frame.current_node,
        "progress": _flight_progress(result, frame),
        "lat": round(frame.lat, 6),
        "lon": round(frame.lon, 6),
        "altitude_m": frame.altitude_m,
        "speed_kmh": round(frame.speed_kmh, 1),
        "current_node": frame.current_node,
        "target_node": frame.target_node,
        "mission_target": frame.mission_target,
        "current_edge": current_edge,
        "current_route": list(frame.current_route),
        "estimated_arrival_tick": frame.estimated_arrival_time,
        "health_status": frame.health_status,
        "neighbor_count": frame.neighbor_count,
        "communication_neighbors": list(frame.communication_neighbors),
        "local_traffic_view": dict(frame.local_traffic_view),
        "local_noise_view": dict(frame.local_noise_view),
        "local_weather_view": dict(frame.local_weather_view),
        "local_vertiport_queue_view": dict(frame.local_vertiport_queue_view),
        "route_cost_breakdown": dict(frame.route_cost_breakdown),
        "decision_reason": frame.decision_reason,
    }


def _edge_payloads(result: FleetScenarioResult, tick: object) -> list[dict[str, object]]:
    dynamic_by_key = {
        _edge_key(edge.start, edge.end): edge for edge in tick.edge_states
    }
    payloads: list[dict[str, object]] = []
    for start, end, edge_data in result.airspace.graph.edges(data=True):
        dynamic = dynamic_by_key[_edge_key(start, end)]
        weather_risk = 0.0
        traffic_penalty = round(dynamic.traffic_density * 8.0, 2)
        weather_penalty = round(weather_risk * 12.0, 2)
        total_cost = round(
            edge_data["distance_km"]
            + edge_data["battery_cost"]
            + edge_data["noise_penalty"]
            + traffic_penalty
            + weather_penalty,
            2,
        )
        payloads.append(
            {
                "start": start,
                "end": end,
                "route_type": edge_data["route_type"],
                "distance_km": edge_data["distance_km"],
                "battery_consumption_rate": 1.0,
                "battery_cost": edge_data["battery_cost"],
                "noise_penalty": edge_data["noise_penalty"],
                "noise_level": round(dynamic.noise_level, 2),
                "weather_penalty": weather_penalty,
                "weather_risk": weather_risk,
                "blocked": False,
                "current_aircraft_count": len(dynamic.active_agent_ids),
                "active_agent_ids": list(dynamic.active_agent_ids),
                "traffic_density": round(dynamic.traffic_density, 2),
                "traffic_penalty_per_aircraft": 8.0,
                "traffic_penalty": traffic_penalty,
                "total_cost": total_cost,
            }
        )
    return payloads


def _weather_zone_payload(
    result: FleetScenarioResult,
    edge_payloads: list[dict[str, object]],
) -> list[dict[str, object]]:
    risk_by_zone = {zone: 0.0 for zone in WEATHER_ZONE_ORDER}
    for edge in edge_payloads:
        risk = float(edge["weather_risk"])
        for node_name in (str(edge["start"]), str(edge["end"])):
            zone = result.airspace.nodes[node_name].weather_zone
            risk_by_zone[zone] = max(risk_by_zone.get(zone, 0.0), risk)

    payloads: list[dict[str, object]] = []
    for zone in WEATHER_ZONE_ORDER:
        risk = risk_by_zone[zone]
        if risk >= 0.75:
            label, condition, wind, visibility = "high", "Simulated restriction", 45, 3
        elif risk >= 0.3:
            label, condition, wind, visibility = "medium", "Simulated caution", 25, 10
        else:
            label, condition, wind, visibility = "low", "Simulated baseline", 8, 18
        payloads.append(
            {
                "zone": zone,
                "condition": condition,
                "risk": label,
                "weather_risk": round(risk, 2),
                "wind_kmh": wind,
                "visibility_km": visibility,
            }
        )
    return payloads


def _alert_payloads(
    result: FleetScenarioResult,
    tick: object,
    agents: list[dict[str, object]],
    edges: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Translate live agent and corridor conditions into UI alerts."""
    alerts: list[dict[str, object]] = []
    time_label = f"T+{tick.simulation_seconds:04d}s"
    for agent in agents:
        if agent["operational_status"] == "emergency":
            alerts.append(
                {
                    "id": f"emergency-{agent['id']}-{tick.tick}",
                    "level": "critical",
                    "message": f"{agent['id']} emergency route to {agent['to']}: {agent['decision_reason']}",
                    "time": time_label,
                }
            )
        elif float(agent["battery"]) < 30.0:
            alerts.append(
                {
                    "id": f"battery-{agent['id']}-{tick.tick}",
                    "level": "warning",
                    "message": f"{agent['id']} battery is low ({agent['battery']}%). {agent['decision_reason']}",
                    "time": time_label,
                }
            )

    for edge in edges:
        if float(edge["traffic_density"]) >= 0.7:
            alerts.append(
                {
                    "id": f"traffic-{edge['start']}-{edge['end']}-{tick.tick}",
                    "level": "warning",
                    "message": f"High traffic on {edge['start']} to {edge['end']} ({edge['traffic_density']}).",
                    "time": time_label,
                }
            )

    for message in result.message_log:
        if message["sent_at_tick"] != tick.tick:
            continue
        message_type = message["message_type"]
        if message_type not in {"emergency_declared", "battery_low_alert", "reroute_intent"}:
            continue
        alerts.append(
            {
                "id": str(message["message_id"]),
                "level": "critical" if message_type == "emergency_declared" else "warning",
                "message": f"{message_type.replace('_', ' ').title()} from {message['sender_id']}.",
                "time": time_label,
            }
        )

    if not alerts:
        alerts.append(
            {
                "id": f"nominal-{tick.tick}",
                "level": "info",
                "message": "Autonomous agents are operating within current constraints.",
                "time": time_label,
            }
        )
    return alerts[:20]


def build_dashboard_snapshot(
    result: FleetScenarioResult,
    tick_index: int,
) -> dict[str, object]:
    """Create one frontend-ready snapshot from the global digital twin replay."""
    if not result.ticks:
        raise ValueError("Fleet scenario has no recorded ticks")
    bounded_index = min(max(tick_index, 0), len(result.ticks) - 1)
    tick = result.ticks[bounded_index]
    agents = [_agent_payload(result, frame) for frame in tick.agents]
    edges = _edge_payloads(result, tick)
    nodes = [dict(node) for node in tick.node_states]
    active_reservations = tick.active_reservation_count
    average_battery = sum(float(agent["battery"]) for agent in agents) / max(len(agents), 1)
    alerts = _alert_payloads(result, tick, agents, edges)

    return {
        "schema_version": 1,
        "simulation": {
            "tick": tick.tick,
            "tick_index": bounded_index,
            "simulation_seconds": tick.simulation_seconds,
            "tick_seconds": result.tick_seconds,
            "total_ticks": len(result.ticks),
            "replay_complete": bounded_index == len(result.ticks) - 1,
            "source": "backend global digital twin / local-agent replay",
        },
        "nodes": nodes,
        "edges": edges,
        "agents": agents,
        "alerts": alerts,
        "weather_zones": _weather_zone_payload(result, edges),
        "metrics": {
            "agent_count": len(agents),
            "in_flight_count": sum(agent["status"] == "in_flight" for agent in agents),
            "emergency_count": sum(agent["status"] == "emergency" for agent in agents),
            "charging_count": sum(agent["status"] == "charging" for agent in agents),
            "average_battery_percent": round(average_battery, 1),
            "active_message_count": tick.active_message_count,
            "active_reservation_count": active_reservations,
        },
    }


@dataclass(slots=True)
class FleetDashboardFeed:
    """Owns one deterministic global replay and advances it by wall-clock time."""

    random_seed: int = 11
    replay_seconds_per_tick: float = 1.0
    result: FleetScenarioResult = field(init=False)
    _started_at: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.replay_seconds_per_tick <= 0:
            raise ValueError("replay_seconds_per_tick must be greater than zero")
        self.result = run_three_agent_fleet_scenario(random_seed=self.random_seed)
        self._started_at = monotonic()

    def snapshot(self, tick_index: int | None = None) -> dict[str, object]:
        """Return a requested tick or the current looping live-replay tick."""
        if tick_index is None:
            elapsed_ticks = int((monotonic() - self._started_at) / self.replay_seconds_per_tick)
            tick_index = elapsed_ticks % len(self.result.ticks)
        return build_dashboard_snapshot(self.result, tick_index)
