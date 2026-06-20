"""Tests for C4 battery/charging and C5 emergency/rerouting decisions."""

import unittest

from backend.communication import MessageBus, MessageType
from backend.emergency import (
    HospitalAlert,
    begin_charging_if_arrived,
    dispatch_hospital_alert,
    divert_to_charging_if_needed,
    reroute_if_needed,
    resume_mission_after_charging,
)
from backend.graph import MunichAirspaceDigitalTwin
from backend.models import AltitudeLevel, EVTOLAgent, EVTOLStatus
from backend.planner import DynamicAirspaceState, edge_key, plan_dynamic_route
from backend.emergency_scenario import run_emergency_decision_demo


class EmergencyDecisionTests(unittest.TestCase):
    def setUp(self):
        self.twin = MunichAirspaceDigitalTwin()
        self.twin.build_world()
        self.dynamic_state = DynamicAirspaceState()
        self.messe_node = next(
            node.name for node in self.twin.nodes.values() if node.id == 7
        )

    def test_low_battery_diverts_to_reachable_charger_and_preserves_mission(self):
        agent = EVTOLAgent(
            evtol_id="E1",
            current_node="Marienplatz",
            target_node=self.messe_node,
            current_route=[self.messe_node],
            battery_level=24.0,
            status=EVTOLStatus.ASSIGNED,
            communication_neighbors=[{"neighbor_id": "E2"}],
        )
        bus = MessageBus()

        decision = divert_to_charging_if_needed(
            agent,
            self.twin,
            self.dynamic_state,
            current_tick=4,
            message_bus=bus,
        )

        self.assertTrue(decision.applied)
        self.assertEqual(decision.action, "charge_diversion")
        self.assertEqual(agent.status, EVTOLStatus.REPOSITIONING)
        self.assertEqual(agent.target_node, "Charging Hub C - City Center")
        self.assertEqual(agent.mission_target, self.messe_node)
        self.assertEqual(agent.current_route[-1], "Charging Hub C - City Center")
        self.assertIn("battery_low_alert", {message.message_type.value for message in bus.history})
        self.assertIn("charging_intent", {message.message_type.value for message in bus.history})
        self.assertIn("charging_decision", {message.message_type.value for message in bus.history})

        repeated = divert_to_charging_if_needed(
            agent,
            self.twin,
            self.dynamic_state,
            current_tick=5,
            message_bus=bus,
        )
        self.assertFalse(repeated.applied)
        self.assertEqual(repeated.action, "continue_charge_diversion")

    def test_critical_battery_uses_emergency_profile_for_charging_diversion(self):
        agent = EVTOLAgent(
            evtol_id="E1",
            current_node="Marienplatz",
            target_node=self.messe_node,
            battery_level=14.0,
        )

        decision = divert_to_charging_if_needed(
            agent,
            self.twin,
            self.dynamic_state,
            current_tick=1,
        )

        self.assertTrue(decision.applied)
        self.assertEqual(decision.action, "emergency_charge_diversion")
        self.assertEqual(agent.status, EVTOLStatus.EMERGENCY)
        self.assertEqual(agent.altitude_level, AltitudeLevel.EMERGENCY)

    def test_charging_completion_restores_saved_mission(self):
        agent = EVTOLAgent(
            evtol_id="E1",
            current_node="Charging Hub C - City Center",
            target_node="Charging Hub C - City Center",
            mission_target=self.messe_node,
            battery_level=12.0,
            status=EVTOLStatus.REPOSITIONING,
        )

        self.assertTrue(begin_charging_if_arrived(agent, self.twin).applied)
        decision = resume_mission_after_charging(
            agent,
            self.twin,
            self.dynamic_state,
            current_tick=8,
        )

        self.assertTrue(decision.applied)
        self.assertEqual(agent.status, EVTOLStatus.ASSIGNED)
        self.assertEqual(agent.battery_level, 90.0)
        self.assertEqual(agent.target_node, self.messe_node)
        self.assertIsNone(agent.mission_target)

    def test_hospital_alert_selects_nearest_safe_responder_and_broadcasts(self):
        nearby = EVTOLAgent(
            evtol_id="E2",
            current_node="Marienplatz",
            target_node=self.messe_node,
            battery_level=80.0,
            status=EVTOLStatus.ASSIGNED,
            communication_neighbors=[{"neighbor_id": "E1"}],
        )
        distant = EVTOLAgent(
            evtol_id="E1",
            current_node="Munich Airport",
            target_node="Allianz Arena",
            battery_level=80.0,
            status=EVTOLStatus.ASSIGNED,
        )
        bus = MessageBus()
        alert = HospitalAlert(
            alert_id="H-17",
            hospital_node="TUM Klinikum Rechts der Isar",
            created_tick=6,
        )

        dispatch = dispatch_hospital_alert(
            alert,
            [distant, nearby],
            self.twin,
            self.dynamic_state,
            message_bus=bus,
        )

        self.assertEqual(dispatch.responder_id, "E2")
        self.assertEqual(nearby.status, EVTOLStatus.EMERGENCY)
        self.assertEqual(nearby.target_node, alert.hospital_node)
        self.assertEqual(nearby.mission_target, self.messe_node)
        self.assertEqual(nearby.altitude_level, AltitudeLevel.EMERGENCY)
        message_types = {message.message_type for message in bus.history}
        self.assertIn(MessageType.EMERGENCY_DECLARED, message_types)
        self.assertIn(MessageType.EMERGENCY_ROUTE_INTENT, message_types)

    def test_blocked_corridor_is_excluded_and_agent_reroutes(self):
        original = plan_dynamic_route(
            self.twin,
            "Munich Airport",
            "TUM Main Campus",
            self.dynamic_state,
        )
        blocked_edge = original.path[:2]
        self.dynamic_state.update_edge(*blocked_edge, blocked=True, updated_tick=3)
        agent = EVTOLAgent(
            evtol_id="E1",
            current_node="Munich Airport",
            target_node="TUM Main Campus",
            current_route=original.path[1:],
            battery_level=80.0,
            status=EVTOLStatus.ASSIGNED,
        )

        decision = reroute_if_needed(
            agent,
            self.twin,
            self.dynamic_state,
            current_tick=3,
        )

        self.assertTrue(decision.applied)
        self.assertEqual(decision.action, "reroute")
        self.assertNotEqual(agent.current_route, original.path[1:])
        rerouted_edges = zip([agent.current_node, *agent.current_route][:-1], [agent.current_node, *agent.current_route][1:])
        self.assertNotIn(edge_key(*blocked_edge), {edge_key(*edge) for edge in rerouted_edges})
        self.assertIn("Unsafe route avoided", agent.last_decision_reason)

    def test_deterministic_demo_exercises_each_c4_c5_decision(self):
        result = run_emergency_decision_demo()

        self.assertTrue(result.charging_decision.applied)
        self.assertEqual(result.dispatch_result.responder_id, "E2")
        self.assertTrue(result.reroute_decision.applied)


if __name__ == "__main__":
    unittest.main()
