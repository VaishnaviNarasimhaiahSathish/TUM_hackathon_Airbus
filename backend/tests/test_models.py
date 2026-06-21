"""Tests for the Phase 1 eVTOL state model."""

import unittest

from backend.models import AltitudeLevel, EVTOLAgent, EVTOLStatus, HealthStatus, MissionType


class EVTOLAgentTests(unittest.TestCase):
    def test_default_agent_state_matches_the_operational_contract(self):
        agent = EVTOLAgent(evtol_id="E1", current_node="Munich Airport")

        self.assertIsNone(agent.target_node)
        self.assertIsNone(agent.assigned_origin)
        self.assertIsNone(agent.assigned_destination)
        self.assertEqual(agent.current_route, [])
        self.assertIsNone(agent.current_edge)
        self.assertEqual(agent.battery_level, 100.0)
        self.assertEqual(agent.speed_kmh, 100.0)
        self.assertEqual(agent.altitude_level, AltitudeLevel.INBOUND)
        self.assertEqual(agent.altitude_m, 300)
        self.assertEqual(agent.status, EVTOLStatus.IDLE)
        self.assertEqual(agent.health_status, HealthStatus.NORMAL)
        self.assertEqual(agent.communication_neighbors, [])
        self.assertEqual(agent.local_traffic_view, {})
        self.assertEqual(agent.local_noise_view, {})
        self.assertEqual(agent.local_weather_view, {})
        self.assertEqual(agent.local_vertiport_queue_view, {})

    def test_agent_state_serializes_for_future_dashboard_and_snapshots(self):
        agent = EVTOLAgent(
            evtol_id="E2",
            current_node="Marienplatz",
            target_node="TUM Main Campus",
            assigned_origin="Marienplatz",
            assigned_destination="TUM Main Campus",
            mission_type=MissionType.MEDICAL_TRANSFER,
            cargo_description="Organ preservation kit",
            mission_target="TUM Main Campus",
            current_route=["Marienplatz", "TUM Main Campus"],
            current_edge=("Marienplatz", "TUM Main Campus"),
            battery_level=82.0,
            speed_kmh=140.0,
            altitude_level=AltitudeLevel.OUTBOUND,
            status=EVTOLStatus.FLYING,
            estimated_arrival_time=12,
            health_status=HealthStatus.DEGRADED,
            communication_neighbors=[
                {
                    "neighbor_id": "E1",
                    "reasons": ["same_edge"],
                    "distance_km": 1.2,
                    "last_seen_tick": 4,
                }
            ],
            local_traffic_view={"Marienplatz|TUM Main Campus": 0.4},
            local_noise_view={"Marienplatz|TUM Main Campus": 0.6},
            local_weather_view={"central": 0.2},
            local_vertiport_queue_view={"TUM Main Campus": 1},
            route_cost_breakdown={"distance": 4.2, "weather": 0.0},
            last_reroute_tick=8,
            reroute_count=1,
            emergency_reason="battery_failure",
            last_decision_reason="Continuing along the assigned corridor.",
        )

        self.assertEqual(
            agent.to_dict(),
            {
                "evtol_id": "E2",
                "current_node": "Marienplatz",
                "target_node": "TUM Main Campus",
                "assigned_origin": "Marienplatz",
                "assigned_destination": "TUM Main Campus",
                "mission_type": "medical_transfer",
                "cargo_description": "Organ preservation kit",
                "mission_target": "TUM Main Campus",
                "current_route": ["Marienplatz", "TUM Main Campus"],
                "current_edge": ["Marienplatz", "TUM Main Campus"],
                "battery_level": 82.0,
                "speed_kmh": 140.0,
                "altitude_level": "outbound",
                "altitude_m": 600,
                "status": "flying",
                "estimated_arrival_time": 12,
                "health_status": "degraded",
                "communication_neighbors": [
                    {
                        "neighbor_id": "E1",
                        "reasons": ["same_edge"],
                        "distance_km": 1.2,
                        "last_seen_tick": 4,
                    }
                ],
                "local_traffic_view": {"Marienplatz|TUM Main Campus": 0.4},
                "local_noise_view": {"Marienplatz|TUM Main Campus": 0.6},
                "local_weather_view": {"central": 0.2},
                "local_vertiport_queue_view": {"TUM Main Campus": 1},
                "route_cost_breakdown": {"distance": 4.2, "weather": 0.0},
                "last_reroute_tick": 8,
                "reroute_count": 1,
                "emergency_reason": "battery_failure",
                "last_decision_reason": "Continuing along the assigned corridor.",
            },
        )

    def test_agents_do_not_share_mutable_default_state(self):
        first_agent = EVTOLAgent(evtol_id="E1", current_node="Munich Airport")
        second_agent = EVTOLAgent(evtol_id="E2", current_node="Marienplatz")

        first_agent.current_route.append("Allianz Arena")
        first_agent.local_weather_view["north"] = 0.7

        self.assertEqual(second_agent.current_route, [])
        self.assertEqual(second_agent.local_weather_view, {})

    def test_invalid_battery_and_empty_identifiers_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "battery_level"):
            EVTOLAgent(evtol_id="E1", current_node="Munich Airport", battery_level=101)

        with self.assertRaisesRegex(ValueError, "evtol_id"):
            EVTOLAgent(evtol_id="", current_node="Munich Airport")

        with self.assertRaisesRegex(ValueError, "current_node"):
            EVTOLAgent(evtol_id="E1", current_node="")

        with self.assertRaisesRegex(ValueError, "speed_kmh"):
            EVTOLAgent(evtol_id="E1", current_node="Munich Airport", speed_kmh=0)


if __name__ == "__main__":
    unittest.main()
