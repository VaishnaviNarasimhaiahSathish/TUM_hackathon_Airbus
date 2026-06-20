"""Tests for the backend-to-React dashboard data contract."""

import unittest

from backend.dashboard_feed import FleetDashboardFeed, build_dashboard_snapshot
from backend.fleet_scenario import run_three_agent_fleet_scenario


class DashboardFeedTests(unittest.TestCase):
    def test_snapshot_exposes_three_agents_and_complete_twin_data(self):
        result = run_three_agent_fleet_scenario(random_seed=11)
        snapshot = build_dashboard_snapshot(result, tick_index=0)

        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(len(snapshot["nodes"]), 21)
        self.assertEqual(len(snapshot["edges"]), 33)
        self.assertEqual(len(snapshot["agents"]), 3)
        self.assertEqual(snapshot["metrics"]["agent_count"], 3)
        self.assertEqual(snapshot["simulation"]["tick"], 0)

        agent = snapshot["agents"][0]
        self.assertIn(agent["status"], {"in_flight", "at_pad", "charging", "emergency"})
        self.assertIn("decision_reason", agent)
        self.assertIn("communication_neighbors", agent)
        self.assertIn("local_traffic_view", agent)
        self.assertIn("current_route", agent)

        edge = snapshot["edges"][0]
        self.assertIn("traffic_density", edge)
        self.assertIn("noise_level", edge)
        self.assertIn("active_agent_ids", edge)

    def test_feed_accepts_a_deterministic_tick_request(self):
        feed = FleetDashboardFeed(random_seed=11, replay_seconds_per_tick=5.0)
        snapshot = feed.snapshot(tick_index=2)

        self.assertEqual(snapshot["simulation"]["tick_index"], 2)
        self.assertEqual(snapshot["simulation"]["tick"], 2)


if __name__ == "__main__":
    unittest.main()
