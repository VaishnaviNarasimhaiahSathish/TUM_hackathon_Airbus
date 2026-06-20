"""Tests for the three-agent Folium fleet replay."""

import tempfile
import unittest
from pathlib import Path

from backend.fleet_scenario import run_three_agent_fleet_scenario
from backend.fleet_ui import create_fleet_replay


class FleetUiTests(unittest.TestCase):
    def test_fleet_replay_contains_aircraft_and_live_constraint_controls(self):
        result = run_three_agent_fleet_scenario(random_seed=11)

        with tempfile.TemporaryDirectory() as directory:
            output_file = Path(directory) / "fleet.html"
            created_file = create_fleet_replay(result, str(output_file))
            html = Path(created_file).read_text(encoding="utf-8")

        self.assertIn("3-eVTOL Fleet Replay", html)
        self.assertIn("fleet-play-pause", html)
        self.assertIn("max traffic", html)
        self.assertIn("max noise", html)
        self.assertIn("active messages", html)
        self.assertIn("active reservations", html)
        for agent in result.agents:
            self.assertIn(agent.evtol_id, html)
