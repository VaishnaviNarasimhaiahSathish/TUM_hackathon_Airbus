"""Dynamic, explainable route planning over the static Munich airspace graph."""

from dataclasses import dataclass, field

import networkx as nx

from backend.graph import MunichAirspaceDigitalTwin


def edge_key(start: str, end: str) -> str:
    """Return a direction-independent identifier for a bidirectional corridor."""
    return "|".join(sorted((start, end)))


@dataclass(slots=True)
class EdgeCondition:
    """Live constraints layered over one otherwise-static air corridor."""

    traffic_density: float = 0.0
    noise_level: float = 0.0
    weather_risk: float = 0.0
    blocked: bool = False
    reservation_risk: float = 0.0
    updated_tick: int = 0


@dataclass(slots=True)
class DynamicAirspaceState:
    """Canonical dynamic edge constraints used by planners and scenarios."""

    conditions: dict[str, EdgeCondition] = field(default_factory=dict)

    def get(self, start: str, end: str) -> EdgeCondition:
        return self.conditions.setdefault(edge_key(start, end), EdgeCondition())

    def update_edge(
        self,
        start: str,
        end: str,
        *,
        traffic_density: float | None = None,
        noise_level: float | None = None,
        weather_risk: float | None = None,
        blocked: bool | None = None,
        reservation_risk: float | None = None,
        updated_tick: int | None = None,
    ) -> EdgeCondition:
        """Apply one partial live update and return the resulting condition."""
        condition = self.get(start, end)
        for attribute, value in {
            "traffic_density": traffic_density,
            "noise_level": noise_level,
            "weather_risk": weather_risk,
            "blocked": blocked,
            "reservation_risk": reservation_risk,
            "updated_tick": updated_tick,
        }.items():
            if value is not None:
                setattr(condition, attribute, value)
        return condition


@dataclass(frozen=True, slots=True)
class RouteCostWeights:
    """Named weights keep normal and emergency route choices explainable."""

    distance: float
    battery: float
    weather: float
    traffic: float
    noise: float
    queue: float
    reservation: float

    @classmethod
    def normal(cls) -> "RouteCostWeights":
        return cls(
            distance=1.0,
            battery=0.8,
            weather=12.0,
            traffic=8.0,
            noise=5.0,
            queue=6.0,
            reservation=10.0,
        )

    @classmethod
    def emergency(cls) -> "RouteCostWeights":
        return cls(
            distance=1.0,
            battery=4.0,
            weather=30.0,
            traffic=12.0,
            noise=1.0,
            queue=18.0,
            reservation=20.0,
        )


@dataclass(slots=True)
class RoutePlan:
    """A selected route with total distance, cost, and transparent factors."""

    path: list[str]
    distance_km: float
    total_cost: float
    cost_breakdown: dict[str, float]
    reason: str


def _edge_cost_breakdown(
    twin: MunichAirspaceDigitalTwin,
    start: str,
    end: str,
    dynamic_state: DynamicAirspaceState,
    weights: RouteCostWeights,
) -> dict[str, float] | None:
    edge_data = twin.graph[start][end]
    condition = dynamic_state.get(start, end)
    if condition.blocked:
        return None

    destination = twin.nodes[end]
    queue_ratio = destination.current_load / max(destination.capacity, 1)
    energy_usage = edge_data["distance_km"]
    return {
        "distance": weights.distance * edge_data["distance_km"],
        "battery": weights.battery * energy_usage,
        "weather": weights.weather * condition.weather_risk,
        "traffic": weights.traffic * condition.traffic_density,
        "noise": weights.noise * max(condition.noise_level, edge_data["noise_penalty"] / 8),
        "queue": weights.queue * queue_ratio,
        "reservation": weights.reservation * condition.reservation_risk,
    }


def plan_dynamic_route(
    twin: MunichAirspaceDigitalTwin,
    start: str,
    destination: str,
    dynamic_state: DynamicAirspaceState,
    *,
    emergency: bool = False,
) -> RoutePlan:
    """Find the lowest dynamic-cost route, excluding blocked corridors."""
    if start not in twin.nodes or destination not in twin.nodes:
        raise ValueError("Route endpoints must be nodes in the airspace graph")

    weights = RouteCostWeights.emergency() if emergency else RouteCostWeights.normal()

    def weight(source: str, target: str, _edge_data: dict[str, object]) -> float | None:
        breakdown = _edge_cost_breakdown(
            twin,
            source,
            target,
            dynamic_state,
            weights,
        )
        return None if breakdown is None else sum(breakdown.values())

    try:
        path = nx.dijkstra_path(twin.graph, start, destination, weight=weight)
    except nx.NetworkXNoPath as error:
        raise ValueError(f"No safe dynamic route from {start} to {destination}") from error

    total_breakdown = {
        "distance": 0.0,
        "battery": 0.0,
        "weather": 0.0,
        "traffic": 0.0,
        "noise": 0.0,
        "queue": 0.0,
        "reservation": 0.0,
    }
    distance_km = 0.0
    for source, target in zip(path[:-1], path[1:]):
        breakdown = _edge_cost_breakdown(twin, source, target, dynamic_state, weights)
        if breakdown is None:
            raise RuntimeError("Selected route unexpectedly contains a blocked corridor")
        distance_km += twin.graph[source][target]["distance_km"]
        for factor, value in breakdown.items():
            total_breakdown[factor] += value

    route_kind = "emergency safety" if emergency else "dynamic normal"
    return RoutePlan(
        path=path,
        distance_km=round(distance_km, 2),
        total_cost=round(sum(total_breakdown.values()), 2),
        cost_breakdown={key: round(value, 2) for key, value in total_breakdown.items()},
        reason=f"Selected the lowest {route_kind}-cost route.",
    )


def evaluate_dynamic_path(
    twin: MunichAirspaceDigitalTwin,
    path: list[str],
    dynamic_state: DynamicAirspaceState,
    *,
    emergency: bool = False,
) -> RoutePlan:
    """Evaluate a known route with the same dynamic factors as the planner."""
    if len(path) < 2:
        return RoutePlan(path=list(path), distance_km=0.0, total_cost=0.0, cost_breakdown={}, reason="Already at destination.")

    weights = RouteCostWeights.emergency() if emergency else RouteCostWeights.normal()
    total_breakdown = {
        "distance": 0.0,
        "battery": 0.0,
        "weather": 0.0,
        "traffic": 0.0,
        "noise": 0.0,
        "queue": 0.0,
        "reservation": 0.0,
    }
    distance_km = 0.0
    for source, target in zip(path[:-1], path[1:]):
        if not twin.graph.has_edge(source, target):
            raise ValueError(f"Path contains no corridor: {source} -> {target}")
        breakdown = _edge_cost_breakdown(twin, source, target, dynamic_state, weights)
        if breakdown is None:
            return RoutePlan(
                path=list(path),
                distance_km=0.0,
                total_cost=float("inf"),
                cost_breakdown={"blocked": float("inf")},
                reason="Current route contains a blocked corridor.",
            )
        distance_km += twin.graph[source][target]["distance_km"]
        for factor, value in breakdown.items():
            total_breakdown[factor] += value

    return RoutePlan(
        path=list(path),
        distance_km=round(distance_km, 2),
        total_cost=round(sum(total_breakdown.values()), 2),
        cost_breakdown={key: round(value, 2) for key, value in total_breakdown.items()},
        reason="Evaluated the existing dynamic route.",
    )
