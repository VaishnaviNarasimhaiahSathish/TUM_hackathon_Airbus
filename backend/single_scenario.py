"""One random pad-to-pad eVTOL flight scenario using the static graph.

This is intentionally a small demonstration, not the future general simulation
engine. It uses the current static route cost, moves one corridor per tick, and
does not yet apply dynamic weather, traffic, battery consumption, rerouting, or
multi-agent conflict rules.
"""

from dataclasses import dataclass
from random import Random

from backend.graph import MunichAirspaceDigitalTwin
from backend.models import EVTOLAgent, EVTOLStatus


@dataclass(frozen=True, slots=True)
class FlightTick:
    """One completed corridor traversal in the deterministic demo."""

    tick: int
    start_node: str
    end_node: str
    decision_reason: str


@dataclass(slots=True)
class ScenarioResult:
    """Outcome and audit trail for the single eVTOL demonstration."""

    airspace: MunichAirspaceDigitalTwin
    agent: EVTOLAgent
    path: list[str]
    distance_km: float
    static_route_cost: float
    ticks: list[FlightTick]
    departure_load_before: int
    departure_load_after: int
    arrival_load_before: int
    arrival_load_after: int


def _select_random_pad_pair(
    twin: MunichAirspaceDigitalTwin,
    random_generator: Random,
) -> tuple[str, str]:
    """Select a departure pad and a different pad with a free landing slot."""
    departure_candidates = [
        node.name
        for node in twin.nodes.values()
        if node.node_type == "pad" and node.current_load > 0
    ]

    if not departure_candidates:
        raise RuntimeError("No occupied pad is available for departure")

    origin = random_generator.choice(departure_candidates)
    destination_candidates = [
        node.name
        for node in twin.nodes.values()
        if (
            node.node_type == "pad"
            and node.name != origin
            and node.available_slots > 0
        )
    ]

    if not destination_candidates:
        raise RuntimeError("No available destination pad exists for this departure")

    return origin, random_generator.choice(destination_candidates)


def run_random_pad_to_pad_scenario(
    random_seed: int | None = None,
) -> ScenarioResult:
    """Fly E1 between random valid pads on the existing static graph.

    Intermediate graph nodes are treated as corridor junctions. E1 releases a
    landing slot only at departure and occupies one only at the final landing;
    it does not land at intermediate nodes.

    ``random_seed`` is only for reproducible tests and demonstrations. Omit it
    during normal use to choose a new origin and destination every run.
    """
    twin = MunichAirspaceDigitalTwin()
    twin.build_world()
    origin, destination = _select_random_pad_pair(twin, Random(random_seed))

    path, distance_km, static_route_cost = twin.find_shortest_path(
        origin,
        destination,
    )

    agent = EVTOLAgent(
        evtol_id="E1",
        current_node=origin,
        target_node=destination,
        current_route=path[1:],
        battery_level=82.0,
        status=EVTOLStatus.ASSIGNED,
        estimated_arrival_time=len(path) - 1,
        last_decision_reason=(
            f"Selected the lowest static-cost route to {destination}."
        ),
    )

    departure_load_before = twin.nodes[origin].current_load
    if not twin.release_landing_slot(origin):
        raise RuntimeError(f"Unable to release departure slot at {origin}")
    departure_load_after = twin.nodes[origin].current_load

    arrival_load_before = twin.nodes[destination].current_load
    ticks: list[FlightTick] = []

    for tick_number, next_node in enumerate(list(agent.current_route), start=1):
        start_node = agent.current_node
        agent.status = EVTOLStatus.FLYING
        agent.current_edge = (start_node, next_node)
        agent.estimated_arrival_time = len(path) - 1
        agent.last_decision_reason = (
            f"Flying corridor {start_node} -> {next_node} "
            f"(leg {tick_number} of {len(path) - 1})."
        )

        ticks.append(
            FlightTick(
                tick=tick_number,
                start_node=start_node,
                end_node=next_node,
                decision_reason=agent.last_decision_reason,
            )
        )

        agent.current_node = next_node
        agent.current_route.pop(0)
        agent.current_edge = None

    if not twin.occupy_landing_slot(destination):
        raise RuntimeError(f"No landing slot available at {destination}")

    agent.status = EVTOLStatus.IDLE
    agent.estimated_arrival_time = len(ticks)
    agent.last_decision_reason = f"Arrived safely at {destination}."

    return ScenarioResult(
        airspace=twin,
        agent=agent,
        path=path,
        distance_km=distance_km,
        static_route_cost=static_route_cost,
        ticks=ticks,
        departure_load_before=departure_load_before,
        departure_load_after=departure_load_after,
        arrival_load_before=arrival_load_before,
        arrival_load_after=twin.nodes[destination].current_load,
    )


def main() -> None:
    """Print the result of the single eVTOL flight scenario."""
    from backend.scenario_ui import create_scenario_replay

    result = run_random_pad_to_pad_scenario()

    print("\n" + "=" * 70)
    print("SINGLE EVTOL FLIGHT SCENARIO")
    print("=" * 70)
    print(f"Agent: {result.agent.evtol_id}")
    print(f"Route: {' -> '.join(result.path)}")
    print(f"Distance: {result.distance_km} km")
    print(f"Static route cost: {result.static_route_cost}")
    print(f"Battery: {result.agent.battery_level}% (unchanged in this demo)")

    print("\nFlight ticks:")
    for tick in result.ticks:
        print(f"  Tick {tick.tick}: {tick.start_node} -> {tick.end_node}")

    print("\nPad occupancy:")
    print(
        f"  {result.path[0]}: {result.departure_load_before} -> "
        f"{result.departure_load_after}"
    )
    print(
        f"  {result.path[-1]}: {result.arrival_load_before} -> "
        f"{result.arrival_load_after}"
    )

    print("\nFinal agent state:")
    print(result.agent.to_dict())

    map_file = create_scenario_replay(result)
    print(f"\nAnimated scenario map: {map_file}")


if __name__ == "__main__":
    main()
