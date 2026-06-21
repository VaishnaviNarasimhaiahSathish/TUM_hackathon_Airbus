"""Core data structures for autonomous eVTOL agents.

This module intentionally contains state only. Route planning, simulation ticks,
communication, battery decisions, and graph integration are added in later
phases.
"""

from dataclasses import dataclass, field
from enum import Enum


Edge = tuple[str, str]


class EVTOLStatus(str, Enum):
    """Operational state of an eVTOL."""

    IDLE = "idle"
    ASSIGNED = "assigned"
    FLYING = "flying"
    CHARGING = "charging"
    REPOSITIONING = "repositioning"
    EMERGENCY = "emergency"


class HealthStatus(str, Enum):
    """Health state used by later safety and emergency decisions."""

    NORMAL = "normal"
    DEGRADED = "degraded"
    FAILURE = "failure"


class MissionType(str, Enum):
    """Operational mission category without passenger-demand modelling."""

    AUTONOMOUS_TRANSIT = "autonomous_transit"
    MEDICAL_TRANSFER = "medical_transfer"


class AltitudeLevel(str, Enum):
    """Simulation flight levels with their nominal altitude and cruise speed."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"
    EMERGENCY = "emergency"

    @property
    def altitude_m(self) -> int:
        """Return the nominal altitude used by this simulation level."""
        return {
            AltitudeLevel.INBOUND: 300,
            AltitudeLevel.OUTBOUND: 600,
            AltitudeLevel.EMERGENCY: 900,
        }[self]

    @property
    def cruise_speed_kmh(self) -> float:
        """Return the nominal cruise speed used by this simulation level."""
        return {
            AltitudeLevel.INBOUND: 100.0,
            AltitudeLevel.OUTBOUND: 140.0,
            AltitudeLevel.EMERGENCY: 170.0,
        }[self]


@dataclass(slots=True)
class EVTOLAgent:
    """Serializable state for one autonomous eVTOL.

    ``estimated_arrival_time`` is expressed as a future simulation tick. Local
    view dictionaries are intentionally empty at creation and will be populated
    by later communication and dynamic-constraint phases.
    """

    evtol_id: str
    current_node: str
    target_node: str | None = None
    assigned_origin: str | None = None
    assigned_destination: str | None = None
    mission_type: MissionType = MissionType.AUTONOMOUS_TRANSIT
    cargo_description: str | None = None
    mission_target: str | None = None
    current_route: list[str] = field(default_factory=list)
    current_edge: Edge | None = None
    battery_level: float = 100.0
    speed_kmh: float = 100.0
    altitude_level: AltitudeLevel = AltitudeLevel.INBOUND
    status: EVTOLStatus = EVTOLStatus.IDLE
    estimated_arrival_time: int | None = None
    health_status: HealthStatus = HealthStatus.NORMAL
    communication_neighbors: list[dict[str, object]] = field(default_factory=list)
    local_traffic_view: dict[str, float] = field(default_factory=dict)
    local_noise_view: dict[str, float] = field(default_factory=dict)
    local_weather_view: dict[str, float] = field(default_factory=dict)
    local_vertiport_queue_view: dict[str, int] = field(default_factory=dict)
    route_cost_breakdown: dict[str, float] = field(default_factory=dict)
    last_reroute_tick: int | None = None
    reroute_count: int = 0
    emergency_reason: str | None = None
    last_decision_reason: str = "Initialized and awaiting assignment."

    def __post_init__(self) -> None:
        """Reject invalid state while remaining independent of the graph."""
        if not self.evtol_id.strip():
            raise ValueError("evtol_id must be a non-empty string")

        if not self.current_node.strip():
            raise ValueError("current_node must be a non-empty string")

        if not 0.0 <= self.battery_level <= 100.0:
            raise ValueError("battery_level must be between 0 and 100")

        if self.speed_kmh <= 0:
            raise ValueError("speed_kmh must be greater than 0")

        if self.estimated_arrival_time is not None and self.estimated_arrival_time < 0:
            raise ValueError("estimated_arrival_time cannot be negative")

        if self.reroute_count < 0:
            raise ValueError("reroute_count cannot be negative")

        if any(not node.strip() for node in self.current_route):
            raise ValueError("current_route cannot contain empty node names")

        if self.current_edge is not None and (
            len(self.current_edge) != 2
            or any(not node.strip() for node in self.current_edge)
        ):
            raise ValueError("current_edge must contain exactly two non-empty node names")

    @property
    def altitude_m(self) -> int:
        """Expose the nominal altitude of the selected simulation flight level."""
        return self.altitude_level.altitude_m

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly snapshot without exposing mutable internals."""
        return {
            "evtol_id": self.evtol_id,
            "current_node": self.current_node,
            "target_node": self.target_node,
            "assigned_origin": self.assigned_origin,
            "assigned_destination": self.assigned_destination,
            "mission_type": self.mission_type.value,
            "cargo_description": self.cargo_description,
            "mission_target": self.mission_target,
            "current_route": list(self.current_route),
            "current_edge": list(self.current_edge) if self.current_edge else None,
            "battery_level": self.battery_level,
            "speed_kmh": self.speed_kmh,
            "altitude_level": self.altitude_level.value,
            "altitude_m": self.altitude_m,
            "status": self.status.value,
            "estimated_arrival_time": self.estimated_arrival_time,
            "health_status": self.health_status.value,
            "communication_neighbors": list(self.communication_neighbors),
            "local_traffic_view": dict(self.local_traffic_view),
            "local_noise_view": dict(self.local_noise_view),
            "local_weather_view": dict(self.local_weather_view),
            "local_vertiport_queue_view": dict(self.local_vertiport_queue_view),
            "route_cost_breakdown": dict(self.route_cost_breakdown),
            "last_reroute_tick": self.last_reroute_tick,
            "reroute_count": self.reroute_count,
            "emergency_reason": self.emergency_reason,
            "last_decision_reason": self.last_decision_reason,
        }
