"""Tests for the deterministic thirty-aircraft operational simulation."""

import unittest

from backend.models import EVTOLStatus, HealthStatus, MissionType
from backend.operational_scenario import (
    MEDICAL_TRANSFER_COUNT,
    OPERATIONAL_FLEET_SIZE,
    run_operational_fleet_scenario,
)


class OperationalScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_operational_fleet_scenario(max_ticks=600)

    def test_thirty_defined_missions_complete(self):
        self.assertEqual(len(self.result.agents), OPERATIONAL_FLEET_SIZE)
        self.assertEqual(len(self.result.routes), OPERATIONAL_FLEET_SIZE)
        self.assertTrue(all(agent.status == EVTOLStatus.IDLE for agent in self.result.agents))
        self.assertTrue(
            all(route[0] != route[-1] for route in self.result.routes.values())
        )

    def test_medical_transfers_are_hospital_to_hospital_with_visible_cargo(self):
        medical_agents = [
            agent
            for agent in self.result.agents
            if agent.mission_type == MissionType.MEDICAL_TRANSFER
        ]

        self.assertEqual(len(medical_agents), MEDICAL_TRANSFER_COUNT)
        for agent in medical_agents:
            initial_route = self.result.routes[agent.evtol_id]
            self.assertEqual(self.result.airspace.nodes[initial_route[0]].node_type, "hospital")
            self.assertEqual(self.result.airspace.nodes[initial_route[-1]].node_type, "hospital")
            self.assertIsNotNone(agent.cargo_description)

    def test_congestion_weather_and_emergency_events_are_observable(self):
        event_types = {event["type"] for event in self.result.event_log}
        self.assertTrue(
            {"traffic_congestion", "weather_closure", "technical_failure", "critical_battery"}
            <= event_types
        )
        self.assertTrue(any(not decision["approved"] for decision in self.result.reservation_log))
        self.assertTrue(any(agent.reroute_count > 0 for agent in self.result.agents))

    def test_technical_and_battery_emergencies_are_separate_transit_scenarios(self):
        failure_event = next(
            event for event in self.result.event_log if event["type"] == "technical_failure"
        )
        battery_event = next(
            event for event in self.result.event_log if event["type"] == "critical_battery"
        )
        failure_agent = next(
            agent for agent in self.result.agents if agent.evtol_id == failure_event["agent_id"]
        )
        battery_agent = next(
            agent for agent in self.result.agents if agent.evtol_id == battery_event["agent_id"]
        )

        self.assertEqual(failure_agent.health_status, HealthStatus.FAILURE)
        self.assertNotEqual(failure_agent.evtol_id, battery_agent.evtol_id)
        self.assertTrue(self.result.airspace.nodes[failure_agent.current_node].charging_available)
        self.assertEqual(failure_agent.target_node, failure_agent.current_node)
        self.assertIsNotNone(failure_agent.mission_target)
        self.assertEqual(battery_agent.health_status, HealthStatus.NORMAL)
        self.assertEqual(battery_agent.mission_type, MissionType.AUTONOMOUS_TRANSIT)
        self.assertEqual(self.result.airspace.nodes[battery_agent.current_node].node_type, "pad")
        self.assertIsNone(battery_agent.cargo_description)
        self.assertGreater(battery_agent.battery_level, 30.0)
        self.assertGreaterEqual(battery_agent.reroute_count, 1)

    def test_critical_battery_reason_clears_after_safe_charge_recovery(self):
        battery_event = next(
            event for event in self.result.event_log if event["type"] == "critical_battery"
        )
        recovery_frame = next(
            frame
            for frame in self.result.ticks[14].agents
            if frame.evtol_id == battery_event["agent_id"]
        )

        self.assertEqual(recovery_frame.status, EVTOLStatus.CHARGING.value)
        self.assertGreaterEqual(recovery_frame.battery_level, 30.0)
        self.assertIsNone(recovery_frame.emergency_reason)


if __name__ == "__main__":
    unittest.main()
