"""Tests for the single-scenario Folium replay output."""

import tempfile
import unittest
from pathlib import Path

from backend.scenario_ui import create_scenario_replay
from backend.single_scenario import run_random_pad_to_pad_scenario


class ScenarioUiTests(unittest.TestCase):
    def test_replay_html_contains_the_agent_and_playback_controls(self):
        result = run_random_pad_to_pad_scenario(random_seed=7)

        with tempfile.TemporaryDirectory() as directory:
            output_file = Path(directory) / "scenario.html"
            created_file = create_scenario_replay(result, str(output_file))
            html = Path(created_file).read_text(encoding="utf-8")

        self.assertIn("E1 Flight Replay", html)
        self.assertIn("evtol-play-pause", html)
        self.assertIn(result.path[0], html)
        self.assertIn(result.path[-1], html)
