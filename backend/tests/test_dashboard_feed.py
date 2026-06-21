"""Tests for the backend-to-React dashboard data contract."""

import unittest

from backend.dashboard_feed import FleetDashboardFeed, build_dashboard_snapshot


class DashboardFeedTests(unittest.TestCase):
    def test_snapshot_exposes_thirty_agents_and_complete_twin_data(self):
        result = FleetDashboardFeed(random_seed=30).result
        snapshot = build_dashboard_snapshot(result, tick_index=0)

        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(len(snapshot["nodes"]), 21)
        self.assertEqual(len(snapshot["edges"]), 33)
        self.assertEqual(len(snapshot["agents"]), 30)
        self.assertEqual(snapshot["metrics"]["agent_count"], 30)
        self.assertEqual(snapshot["simulation"]["tick"], 0)

        agent = snapshot["agents"][0]
        self.assertIn(agent["status"], {"in_flight", "at_pad", "charging", "emergency"})
        self.assertIn("decision_reason", agent)
        self.assertIn("communication_neighbors", agent)
        self.assertIn("local_traffic_view", agent)
        self.assertIn("current_route", agent)
        self.assertIn("assigned_origin", agent)
        self.assertIn("assigned_destination", agent)
        self.assertIn("mission_type", agent)
        self.assertIn("cargo_description", agent)
        self.assertIn("emergency_reason", agent)
        self.assertTrue(any(agent["mission"] == "Medical" for agent in snapshot["agents"]))
        self.assertTrue(
            all(agent["from"] != agent["to"] for agent in snapshot["agents"])
        )

        edge = snapshot["edges"][0]
        self.assertIn("traffic_density", edge)
        self.assertIn("noise_level", edge)
        self.assertIn("active_agent_ids", edge)

    def test_scripted_operational_events_are_prioritized_as_dashboard_alerts(self):
        result = FleetDashboardFeed(random_seed=30).result
        snapshot = build_dashboard_snapshot(result, tick_index=18)

        self.assertTrue(
            any("Severe weather closed" in alert["message"] for alert in snapshot["alerts"])
        )

    def test_technical_failure_is_labeled_separately_from_battery_recovery(self):
        result = FleetDashboardFeed(random_seed=30).result
        snapshot = build_dashboard_snapshot(result, tick_index=45)
        technical_agent = next(agent for agent in snapshot["agents"] if agent["id"] == "E04")

        self.assertEqual(technical_agent["mission"], "Technical Failure")
        self.assertEqual(technical_agent["emergency_reason"], "technical_failure")
        self.assertTrue(
            any("technical failure route" in alert["message"] for alert in snapshot["alerts"])
        )

    def test_feed_accepts_a_deterministic_tick_request(self):
        feed = FleetDashboardFeed(random_seed=11, replay_seconds_per_tick=5.0)
        snapshot = feed.snapshot(tick_index=2)

        self.assertEqual(snapshot["simulation"]["tick_index"], 2)
        self.assertEqual(snapshot["simulation"]["tick"], 2)


if __name__ == "__main__":
    unittest.main()
