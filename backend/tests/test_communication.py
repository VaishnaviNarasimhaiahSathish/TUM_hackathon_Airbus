"""Tests for local eVTOL protocol messages and neighbor discovery."""

import unittest

from backend.communication import (
    CommunicationConfig,
    MessageBus,
    MessagePriority,
    MessageType,
    discover_neighbors,
)
from backend.models import EVTOLAgent, EVTOLStatus


class CommunicationTests(unittest.TestCase):
    def test_messages_are_delivered_once_and_expire_after_ttl(self):
        bus = MessageBus()
        bus.publish(
            sender_id="E1",
            recipient_ids=["E2"],
            message_type=MessageType.POSITION_UPDATE,
            priority=MessagePriority.NORMAL,
            payload={"current_node": "Marienplatz"},
            sent_at_tick=4,
            ttl_ticks=2,
        )

        self.assertEqual(len(bus.collect("E2", current_tick=5)), 1)
        self.assertEqual(bus.collect("E2", current_tick=5), [])

        bus.publish(
            sender_id="E1",
            recipient_ids=["E2"],
            message_type=MessageType.POSITION_UPDATE,
            priority=MessagePriority.NORMAL,
            payload={"current_node": "Marienplatz"},
            sent_at_tick=4,
            ttl_ticks=1,
        )
        self.assertEqual(bus.collect("E2", current_tick=6), [])

    def test_neighbor_discovery_uses_route_overlap_beyond_physical_range(self):
        first = EVTOLAgent(
            evtol_id="E1",
            current_node="Munich Airport",
            current_route=["Allianz Arena", "Schwabing", "LMU Munich"],
            current_edge=("Munich Airport", "Allianz Arena"),
            status=EVTOLStatus.FLYING,
        )
        second = EVTOLAgent(
            evtol_id="E2",
            current_node="Olympiapark",
            current_route=["Allianz Arena", "Schwabing", "LMU Munich"],
            current_edge=("Olympiapark", "Allianz Arena"),
            status=EVTOLStatus.FLYING,
        )

        neighbors = discover_neighbors(
            [first, second],
            {"E1": (48.35, 11.78), "E2": (48.17, 11.54)},
            current_tick=3,
            config=CommunicationConfig(),
        )

        self.assertEqual(neighbors["E1"][0].neighbor_id, "E2")
        self.assertIn("route_overlap", neighbors["E1"][0].reasons)
        self.assertEqual(neighbors["E2"][0].neighbor_id, "E1")
