"""Tests for the single random pad-to-pad eVTOL flight scenario."""

import unittest

from backend.models import EVTOLStatus
from backend.single_scenario import run_random_pad_to_pad_scenario


class SingleScenarioTests(unittest.TestCase):
    def test_random_scenario_uses_two_distinct_valid_pads(self):
        result = run_random_pad_to_pad_scenario(random_seed=7)

        origin = result.path[0]
        destination = result.path[-1]

        self.assertNotEqual(origin, destination)
        self.assertEqual(result.airspace.nodes[origin].node_type, "pad")
        self.assertEqual(result.airspace.nodes[destination].node_type, "pad")
        self.assertGreater(result.distance_km, 0)
        self.assertGreater(result.static_route_cost, 0)
        self.assertEqual(len(result.ticks), len(result.path) - 1)
        self.assertEqual(result.ticks[0].start_node, origin)
        self.assertEqual(result.ticks[-1].end_node, destination)

    def test_seeded_scenario_selection_is_reproducible(self):
        first_result = run_random_pad_to_pad_scenario(random_seed=42)
        second_result = run_random_pad_to_pad_scenario(random_seed=42)

        self.assertEqual(first_result.path, second_result.path)

    def test_scenario_updates_only_departure_and_destination_pad_occupancy(self):
        result = run_random_pad_to_pad_scenario(random_seed=7)

        self.assertEqual(result.departure_load_after, result.departure_load_before - 1)
        self.assertEqual(result.arrival_load_after, result.arrival_load_before + 1)

    def test_scenario_finishes_with_the_agent_safely_at_its_destination(self):
        result = run_random_pad_to_pad_scenario(random_seed=7)

        self.assertEqual(result.agent.current_node, result.path[-1])
        self.assertEqual(result.agent.target_node, result.path[-1])
        self.assertEqual(result.agent.current_route, [])
        self.assertIsNone(result.agent.current_edge)
        self.assertEqual(result.agent.status, EVTOLStatus.IDLE)
        self.assertEqual(result.agent.battery_level, 82.0)
        self.assertEqual(
            result.agent.last_decision_reason,
            f"Arrived safely at {result.path[-1]}.",
        )
