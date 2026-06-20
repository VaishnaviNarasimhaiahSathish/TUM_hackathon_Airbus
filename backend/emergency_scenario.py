"""Deterministic console demonstration for the C4/C5 safety decisions."""

from dataclasses import dataclass

from backend.communication import MessageBus
from backend.emergency import (
    DecisionResult,
    EmergencyDispatchResult,
    HospitalAlert,
    dispatch_hospital_alert,
    divert_to_charging_if_needed,
    reroute_if_needed,
)
from backend.graph import MunichAirspaceDigitalTwin
from backend.models import EVTOLAgent, EVTOLStatus
from backend.planner import DynamicAirspaceState, plan_dynamic_route


@dataclass(slots=True)
class EmergencyScenarioResult:
    """Inspectable outcomes from the deterministic C4/C5 console demo."""

    agents: list[EVTOLAgent]
    charging_decision: DecisionResult
    dispatch_result: EmergencyDispatchResult
    reroute_decision: DecisionResult
    message_log: list[dict[str, object]]


def run_emergency_decision_demo() -> EmergencyScenarioResult:
    """Exercise low battery, hospital dispatch, and weather/closure rerouting."""
    twin = MunichAirspaceDigitalTwin()
    twin.build_world()
    dynamic_state = DynamicAirspaceState()
    message_bus = MessageBus()
    messe_node = next(node.name for node in twin.nodes.values() if node.id == 7)

    low_battery_agent = EVTOLAgent(
        evtol_id="E1",
        current_node="Marienplatz",
        target_node=messe_node,
        current_route=[messe_node],
        battery_level=24.0,
        status=EVTOLStatus.ASSIGNED,
        communication_neighbors=[{"neighbor_id": "E2"}],
    )
    charging_decision = divert_to_charging_if_needed(
        low_battery_agent,
        twin,
        dynamic_state,
        current_tick=0,
        message_bus=message_bus,
    )

    hospital_responder = EVTOLAgent(
        evtol_id="E2",
        current_node="TUM Main Campus",
        target_node="Munich Airport",
        current_route=["Munich Airport"],
        battery_level=82.0,
        status=EVTOLStatus.ASSIGNED,
        communication_neighbors=[{"neighbor_id": "E3"}],
    )
    reroute_agent = EVTOLAgent(
        evtol_id="E3",
        current_node="Munich Airport",
        target_node="TUM Main Campus",
        battery_level=76.0,
        status=EVTOLStatus.ASSIGNED,
        communication_neighbors=[{"neighbor_id": "E2"}],
    )
    dispatch_result = dispatch_hospital_alert(
        HospitalAlert(
            alert_id="HOSPITAL-001",
            hospital_node="TUM Klinikum Rechts der Isar",
            created_tick=1,
            description="Urgent medical transfer request.",
        ),
        [low_battery_agent, hospital_responder, reroute_agent],
        twin,
        dynamic_state,
        message_bus=message_bus,
    )

    original_plan = plan_dynamic_route(
        twin,
        reroute_agent.current_node,
        reroute_agent.target_node,
        dynamic_state,
    )
    reroute_agent.current_route = original_plan.path[1:]
    reroute_agent.route_cost_breakdown = dict(original_plan.cost_breakdown)
    dynamic_state.update_edge(
        original_plan.path[0],
        original_plan.path[1],
        weather_risk=0.9,
        blocked=True,
        updated_tick=2,
    )
    reroute_decision = reroute_if_needed(
        reroute_agent,
        twin,
        dynamic_state,
        current_tick=2,
        message_bus=message_bus,
    )

    return EmergencyScenarioResult(
        agents=[low_battery_agent, hospital_responder, reroute_agent],
        charging_decision=charging_decision,
        dispatch_result=dispatch_result,
        reroute_decision=reroute_decision,
        message_log=[message.to_dict() for message in message_bus.history],
    )


def main() -> None:
    """Print the C4/C5 choices without changing the normal fleet replay."""
    result = run_emergency_decision_demo()
    print("\n" + "=" * 70)
    print("C4/C5 EVTOL SAFETY DECISION DEMO")
    print("=" * 70)
    print(f"Charging: {result.charging_decision.reason}")
    print(f"Hospital: {result.dispatch_result.reason}")
    print(f"Rerouting: {result.reroute_decision.reason}")
    print(f"Protocol messages emitted: {len(result.message_log)}")
    for agent in result.agents:
        print(
            f"{agent.evtol_id}: {agent.status.value} | target={agent.target_node} | "
            f"route={' -> '.join(agent.current_route) or 'complete'}"
        )


if __name__ == "__main__":
    main()
