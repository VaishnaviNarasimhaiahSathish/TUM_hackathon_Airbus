"""Deterministic edge and landing-window reservation bulletin board."""

from dataclasses import dataclass
from enum import Enum

from backend.models import EVTOLAgent, EVTOLStatus


class ReservationResource(str, Enum):
    EDGE = "edge"
    LANDING = "landing"


def priority_tuple(agent: EVTOLAgent, eta_tick: int) -> tuple[int, float, int, int, str]:
    """Return the agreed deterministic priority order; lower tuples win."""
    return (
        0 if agent.status == EVTOLStatus.EMERGENCY else 1,
        agent.battery_level,
        0 if agent.status == EVTOLStatus.FLYING else 1,
        eta_tick,
        agent.evtol_id,
    )


@dataclass(frozen=True, slots=True)
class ReservationRequest:
    """Request exclusive use of one edge or landing target during a time window."""

    request_id: str
    agent_id: str
    resource: ReservationResource
    resource_key: str
    start_tick: int
    end_tick: int
    priority: tuple[int, float, int, int, str]


@dataclass(frozen=True, slots=True)
class ReservationDecision:
    """Approval or denial returned by the shared coordination bulletin board."""

    request_id: str
    approved: bool
    reason: str
    conflicting_agent_id: str | None = None


class ReservationTable:
    """Stores non-overlapping edge/landing windows for the current simulation."""

    def __init__(
        self,
        *,
        edge_capacity: int = 1,
        landing_capacity: int = 1,
    ) -> None:
        if edge_capacity < 1 or landing_capacity < 1:
            raise ValueError("Reservation capacities must be at least one")
        self._reservations: list[ReservationRequest] = []
        self.edge_capacity = edge_capacity
        self.landing_capacity = landing_capacity

    @property
    def reservations(self) -> list[ReservationRequest]:
        return list(self._reservations)

    def release_expired(self, current_tick: int) -> None:
        self._reservations = [
            reservation
            for reservation in self._reservations
            if reservation.end_tick >= current_tick
        ]

    def release_agent(self, agent_id: str, resource_key: str | None = None) -> None:
        self._reservations = [
            reservation
            for reservation in self._reservations
            if not (
                reservation.agent_id == agent_id
                and (resource_key is None or reservation.resource_key == resource_key)
            )
        ]

    def request(self, request: ReservationRequest, current_tick: int) -> ReservationDecision:
        """Approve a free window or deny it to the lower-priority requester."""
        self.release_expired(current_tick)

        for reservation in self._reservations:
            if reservation.agent_id == request.agent_id and reservation.resource_key == request.resource_key:
                return ReservationDecision(
                    request_id=request.request_id,
                    approved=True,
                    reason="Reservation already active for this aircraft.",
                )

        conflicts = [
            reservation
            for reservation in self._reservations
            if reservation.resource == request.resource
            and reservation.resource_key == request.resource_key
            and request.start_tick <= reservation.end_tick
            and reservation.start_tick <= request.end_tick
        ]
        capacity = (
            self.edge_capacity
            if request.resource == ReservationResource.EDGE
            else self.landing_capacity
        )
        if len(conflicts) >= capacity:
            conflict = min(conflicts, key=lambda reservation: reservation.priority)
            return ReservationDecision(
                request_id=request.request_id,
                approved=False,
                reason="Conflicting reservation already has corridor/landing priority.",
                conflicting_agent_id=conflict.agent_id,
            )

        self._reservations.append(request)
        return ReservationDecision(
            request_id=request.request_id,
            approved=True,
            reason="Reservation granted.",
        )
