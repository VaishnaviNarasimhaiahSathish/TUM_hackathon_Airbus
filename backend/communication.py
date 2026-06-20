"""Local eVTOL communication primitives and neighbor-discovery rules."""

from dataclasses import dataclass, field
from enum import Enum
from math import atan2, cos, radians, sin, sqrt
from typing import Iterable

from backend.models import EVTOLAgent, EVTOLStatus


class MessageType(str, Enum):
    """Protocol messages required through communication phases C0-C5."""

    POSITION_UPDATE = "position_update"
    ROUTE_INTENT = "route_intent"
    RESERVATION_REQUEST = "reservation_request"
    RESERVATION_DECISION = "reservation_decision"
    EDGE_CONDITION_UPDATE = "edge_condition_update"
    LANDING_INTENT = "landing_intent"
    EMERGENCY_DECLARED = "emergency_declared"
    EMERGENCY_ROUTE_INTENT = "emergency_route_intent"
    BATTERY_LOW_ALERT = "battery_low_alert"
    CHARGING_INTENT = "charging_intent"
    CHARGING_DECISION = "charging_decision"
    REROUTE_INTENT = "reroute_intent"
    YIELD_ACK = "yield_ack"


class MessagePriority(str, Enum):
    """Delivery priority for local safety messages."""

    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class CommunicationConfig:
    """Tick-aligned protocol limits for the hackathon simulation."""

    tick_seconds: int = 10
    normal_range_km: float = 5.0
    emergency_range_km: float = 15.0
    normal_ttl_ticks: int = 3
    emergency_ttl_ticks: int = 1
    route_lookahead_edges: int = 3
    landing_eta_window_ticks: int = 3


@dataclass(frozen=True, slots=True)
class CommunicationMessage:
    """A typed, expiring protocol message delivered to one local recipient."""

    message_id: str
    schema_version: int
    sent_at_tick: int
    expires_at_tick: int
    sender_id: str
    receiver_scope: str
    receiver_id: str
    message_type: MessageType
    priority: MessagePriority
    payload: dict[str, object]
    correlation_id: str | None = None

    def is_valid(self, current_tick: int) -> bool:
        """Return whether the message remains usable at this simulation tick."""
        return current_tick <= self.expires_at_tick

    def to_dict(self) -> dict[str, object]:
        """Return a dashboard-friendly message record."""
        return {
            "message_id": self.message_id,
            "schema_version": self.schema_version,
            "sent_at_tick": self.sent_at_tick,
            "expires_at_tick": self.expires_at_tick,
            "sender_id": self.sender_id,
            "receiver_scope": self.receiver_scope,
            "receiver_id": self.receiver_id,
            "message_type": self.message_type.value,
            "priority": self.priority.value,
            "payload": dict(self.payload),
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True, slots=True)
class NeighborRecord:
    """Explain why one aircraft is a relevant local communication neighbor."""

    neighbor_id: str
    reasons: tuple[str, ...]
    distance_km: float
    last_seen_tick: int

    def to_dict(self) -> dict[str, object]:
        return {
            "neighbor_id": self.neighbor_id,
            "reasons": list(self.reasons),
            "distance_km": round(self.distance_km, 2),
            "last_seen_tick": self.last_seen_tick,
        }


class MessageBus:
    """In-memory local bus; the dashboard may observe but never controls it."""

    def __init__(self) -> None:
        self._sequence = 0
        self._pending_by_recipient: dict[str, list[CommunicationMessage]] = {}
        self.history: list[CommunicationMessage] = []

    def publish(
        self,
        *,
        sender_id: str,
        recipient_ids: Iterable[str],
        message_type: MessageType,
        priority: MessagePriority,
        payload: dict[str, object],
        sent_at_tick: int,
        ttl_ticks: int,
        receiver_scope: str = "local_broadcast",
        correlation_id: str | None = None,
    ) -> list[CommunicationMessage]:
        """Publish one equivalent local message to each explicit recipient."""
        messages: list[CommunicationMessage] = []
        for recipient_id in sorted(set(recipient_ids)):
            if recipient_id == sender_id:
                continue
            self._sequence += 1
            message = CommunicationMessage(
                message_id=f"MSG_{self._sequence:05d}",
                schema_version=1,
                sent_at_tick=sent_at_tick,
                expires_at_tick=sent_at_tick + ttl_ticks,
                sender_id=sender_id,
                receiver_scope=receiver_scope,
                receiver_id=recipient_id,
                message_type=message_type,
                priority=priority,
                payload=dict(payload),
                correlation_id=correlation_id,
            )
            self._pending_by_recipient.setdefault(recipient_id, []).append(message)
            self.history.append(message)
            messages.append(message)
        return messages

    def collect(self, recipient_id: str, current_tick: int) -> list[CommunicationMessage]:
        """Deliver non-expired messages once and discard expired/consumed ones."""
        pending = self._pending_by_recipient.pop(recipient_id, [])
        return [message for message in pending if message.is_valid(current_tick)]

    def active_history(self, current_tick: int) -> list[CommunicationMessage]:
        """Return messages that have not yet expired for dashboard display."""
        return [message for message in self.history if message.is_valid(current_tick)]


def _air_distance_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    """Return Haversine distance between two aircraft positions."""
    lat1, lon1 = first
    lat2, lon2 = second
    earth_radius_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return earth_radius_km * 2 * atan2(sqrt(a), sqrt(1 - a))


def _next_node(agent: EVTOLAgent) -> str | None:
    if agent.current_edge is not None:
        return agent.current_edge[1]
    return agent.current_route[0] if agent.current_route else None


def _edges_are_adjacent(
    first: tuple[str, str] | None,
    second: tuple[str, str] | None,
) -> bool:
    if first is None or second is None:
        return False
    return bool(set(first) & set(second))


def _routes_overlap(first: EVTOLAgent, second: EVTOLAgent, lookahead: int) -> bool:
    first_edges = {
        frozenset(edge)
        for edge in zip(first.current_route[:lookahead], first.current_route[1 : lookahead + 1])
    }
    second_edges = {
        frozenset(edge)
        for edge in zip(second.current_route[:lookahead], second.current_route[1 : lookahead + 1])
    }
    return bool(first_edges & second_edges)


def discover_neighbors(
    agents: Iterable[EVTOLAgent],
    positions: dict[str, tuple[float, float]],
    current_tick: int,
    config: CommunicationConfig,
) -> dict[str, list[NeighborRecord]]:
    """Discover only graph/position-relevant peers for each aircraft."""
    fleet = list(agents)
    discovered: dict[str, list[NeighborRecord]] = {agent.evtol_id: [] for agent in fleet}

    for index, first in enumerate(fleet):
        for second in fleet[index + 1 :]:
            distance_km = _air_distance_km(positions[first.evtol_id], positions[second.evtol_id])
            reasons: list[str] = []

            if first.current_node == second.current_node:
                reasons.append("same_node")
            if first.current_edge is not None and first.current_edge == second.current_edge:
                reasons.append("same_edge")
            if _edges_are_adjacent(first.current_edge, second.current_edge):
                reasons.append("adjacent_edge")
            if _next_node(first) is not None and _next_node(first) == _next_node(second):
                reasons.append("same_next_node")
            if (
                first.target_node is not None
                and first.target_node == second.target_node
                and first.estimated_arrival_time is not None
                and second.estimated_arrival_time is not None
                and abs(first.estimated_arrival_time - second.estimated_arrival_time)
                <= config.landing_eta_window_ticks
            ):
                reasons.append("landing_window_overlap")
            if _routes_overlap(first, second, config.route_lookahead_edges):
                reasons.append("route_overlap")

            emergency_pair = (
                first.status == EVTOLStatus.EMERGENCY
                or second.status == EVTOLStatus.EMERGENCY
            )
            range_limit = (
                config.emergency_range_km if emergency_pair else config.normal_range_km
            )
            if distance_km <= range_limit:
                reasons.append("emergency_range" if emergency_pair else "physical_range")

            if not reasons:
                continue

            first_record = NeighborRecord(
                neighbor_id=second.evtol_id,
                reasons=tuple(reasons),
                distance_km=distance_km,
                last_seen_tick=current_tick,
            )
            second_record = NeighborRecord(
                neighbor_id=first.evtol_id,
                reasons=tuple(reasons),
                distance_km=distance_km,
                last_seen_tick=current_tick,
            )
            discovered[first.evtol_id].append(first_record)
            discovered[second.evtol_id].append(second_record)

    return discovered
