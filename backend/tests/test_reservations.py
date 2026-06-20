"""Tests for deterministic edge and landing reservation decisions."""

import unittest

from backend.models import EVTOLAgent, EVTOLStatus
from backend.reservations import (
    ReservationRequest,
    ReservationResource,
    ReservationTable,
    priority_tuple,
)


class ReservationTests(unittest.TestCase):
    def test_lower_battery_aircraft_wins_when_requests_are_priority_sorted(self):
        low_battery = EVTOLAgent(
            evtol_id="E2",
            current_node="Marienplatz",
            battery_level=30.0,
            status=EVTOLStatus.FLYING,
        )
        normal_battery = EVTOLAgent(
            evtol_id="E1",
            current_node="Marienplatz",
            battery_level=70.0,
            status=EVTOLStatus.FLYING,
        )
        table = ReservationTable()

        first = ReservationRequest(
            request_id="R1",
            agent_id=low_battery.evtol_id,
            resource=ReservationResource.EDGE,
            resource_key="Marienplatz|TUM Main Campus",
            start_tick=5,
            end_tick=8,
            priority=priority_tuple(low_battery, eta_tick=5),
        )
        second = ReservationRequest(
            request_id="R2",
            agent_id=normal_battery.evtol_id,
            resource=ReservationResource.EDGE,
            resource_key="Marienplatz|TUM Main Campus",
            start_tick=5,
            end_tick=8,
            priority=priority_tuple(normal_battery, eta_tick=5),
        )

        self.assertTrue(table.request(first, current_tick=5).approved)
        decision = table.request(second, current_tick=5)
        self.assertFalse(decision.approved)
        self.assertEqual(decision.conflicting_agent_id, "E2")

    def test_expired_reservation_releases_the_resource(self):
        table = ReservationTable()
        request = ReservationRequest(
            request_id="R1",
            agent_id="E1",
            resource=ReservationResource.LANDING,
            resource_key="landing|TUM Main Campus",
            start_tick=1,
            end_tick=2,
            priority=(1, 70.0, 0, 1, "E1"),
        )

        self.assertTrue(table.request(request, current_tick=1).approved)
        table.release_expired(current_tick=3)
        self.assertEqual(table.reservations, [])
