"""Tests for the three-agent speed/altitude fleet simulation."""

import unittest

from backend.fleet_scenario import run_three_agent_fleet_scenario
from backend.models import AltitudeLevel, EVTOLStatus


class FleetScenarioTests(unittest.TestCase):
    def test_fleet_has_three_distinct_pad_to_pad_flights(self):
        result = run_three_agent_fleet_scenario(random_seed=11)

        self.assertEqual(len(result.agents), 3)
        self.assertEqual(len(result.routes), 3)
        origins = [route[0] for route in result.routes.values()]
        destinations = [route[-1] for route in result.routes.values()]

        self.assertEqual(len(set(origins + destinations)), 6)
        for evtol_id, route in result.routes.items():
            self.assertNotEqual(route[0], route[-1])
            self.assertEqual(result.airspace.nodes[route[0]].node_type, "pad")
            self.assertEqual(result.airspace.nodes[route[-1]].node_type, "pad")
            self.assertGreater(result.route_distances_km[evtol_id], 0)

    def test_profile_matches_route_distance_and_speed(self):
        result = run_three_agent_fleet_scenario(random_seed=11)

        for agent in result.agents:
            distance = result.route_distances_km[agent.evtol_id]
            expected_level = (
                AltitudeLevel.OUTBOUND
                if distance >= 10.0
                else AltitudeLevel.INBOUND
            )
            self.assertEqual(agent.altitude_level, expected_level)
            self.assertEqual(agent.speed_kmh, expected_level.cruise_speed_kmh)
            self.assertEqual(agent.altitude_m, expected_level.altitude_m)

    def test_live_edge_state_changes_with_active_fleet_traffic(self):
        result = run_three_agent_fleet_scenario(random_seed=11)

        first_active_edges = [
            edge for edge in result.ticks[0].edge_states if edge.active_agent_ids
        ]
        self.assertTrue(first_active_edges)
        self.assertTrue(any(edge.traffic_density > 0.2 for edge in first_active_edges))
        self.assertTrue(any(edge.noise_level > 0.2 for edge in first_active_edges))
        self.assertTrue(
            any(agent.local_traffic_view for agent in result.agents)
        )
        self.assertTrue(any(agent.local_noise_view for agent in result.agents))

    def test_fleet_exchanges_local_messages_and_uses_reservations(self):
        result = run_three_agent_fleet_scenario(random_seed=11)

        message_types = {message["message_type"] for message in result.message_log}
        self.assertEqual(result.tick_seconds, 10)
        self.assertIn("position_update", message_types)
        self.assertIn("reservation_request", message_types)
        self.assertIn("reservation_decision", message_types)
        self.assertTrue(result.reservation_log)
        self.assertTrue(
            any(
                frame.neighbor_count > 0
                for tick in result.ticks
                for frame in tick.agents
            )
        )

    def test_fleet_finishes_at_each_assigned_destination(self):
        result = run_three_agent_fleet_scenario(random_seed=11)

        for agent in result.agents:
            self.assertEqual(agent.status, EVTOLStatus.IDLE)
            self.assertEqual(agent.current_node, agent.target_node)
            self.assertEqual(agent.current_route, [])
            self.assertIsNone(agent.current_edge)
