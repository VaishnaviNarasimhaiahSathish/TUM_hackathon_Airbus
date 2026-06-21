# Munich eVTOL Airspace Digital Twin — Project Context

## Purpose

This repository is an Airbus/TUM-style hackathon prototype for autonomous
eVTOLs operating in a Munich-inspired graph-based airspace. The objective is a
small, explainable multi-agent simulation: 2–3 aircraft initially, designed to
scale later.

The system should demonstrate local autonomous decisions, battery-aware route
planning, safe conflict resolution, rerouting under changing constraints, and
a central map/dashboard for monitoring. The dashboard observes the fleet; it
does not make aircraft decisions.

## Scope

In scope:

- Vertiports, hospitals, charging hubs, and air corridors.
- Autonomous eVTOL state and decisions.
- Weighted routing using distance, energy, weather, traffic, noise, queues,
  and closures.
- Battery safety, charging diversions, emergency behavior, local
  communication, reservations, conflict resolution, and rerouting.
- Deterministic demo scenarios and a Folium-based dashboard replay.

Explicitly out of scope:

- Passengers, passenger selection, demand matching, bidding, auctions, and
  pricing.
- Real-time external weather/traffic integrations.
- Continuous flight physics, reinforcement learning, microservices, and a
  production-grade operations platform.

## Current repository state

```text
backend/
  __init__.py        Python package marker
  graph.py           Static graph model, route lookup, JSON export, Folium map
  models.py          eVTOL state model and status enums
  communication.py   Local message protocol, TTL handling, neighbor discovery
  reservations.py    Deterministic edge/landing time-window bulletin board
  planner.py         Dynamic weighted route planning and cost breakdowns
  emergency.py       Battery, charging, hospital-dispatch, and reroute decisions
  emergency_scenario.py Deterministic C4/C5 console demonstration
  operational_scenario.py Scaled 30-eVTOL operational simulation and events
  dashboard_feed.py  UI-ready snapshots from the global digital twin replay
  api_server.py      Standard-library JSON API for the React dashboard
  fleet_scenario.py  Three-agent tick simulation with live traffic/noise
  fleet_ui.py        Animated Folium replay for the fleet simulation
  single_scenario.py One random pad-to-pad eVTOL demonstration
  test_graph.py      Manual smoke demo for the current static layer
  tests/             Standard-library tests
  world.json         Generated static graph snapshot
README.md            Setup and run instructions
requirements.txt     Runtime dependencies
context.md           This project brief
frontend/            Vite/React control-center dashboard
```

### Implemented static airspace layer

- Python 3.12 project.
- `networkx` provides an undirected graph: each corridor is currently usable
  in both directions.
- `folium`, `branca`, and Leaflet produce a standalone interactive HTML map.
- 21 Munich-inspired locations:
  - 10 pads/vertiports
  - 6 hospitals
  - 5 charging hubs
- 33 corridors:
  - 3 airport corridors
  - 12 city corridors
  - 11 medical corridors
  - 7 charging corridors

`backend/graph.py` currently contains:

- `AirNode`: location, type, capacity, current load, availability, priority,
  zone, demand score, weather zone, charging capability, and emergency-landing
  capability.
- `AirRoute`: endpoints, corridor type, air distance, battery cost, noise,
  weather, traffic, and total cost.
- `MunichAirspaceDigitalTwin`: graph construction, node occupancy helpers,
  static shortest-path lookup, JSON export, statistics, and Folium rendering.

The static path helper uses NetworkX weighted shortest path. Its existing total
cost is a static sum of distance, battery cost, noise penalty, weather penalty,
and traffic penalty. Dynamic simulation costs must be calculated separately;
do not silently overwrite the static graph data.

`backend/world.json` is generated from `graph.py`. The hard-coded node and
corridor data in `MunichAirspaceDigitalTwin.build_world()` is the source of
truth.

### Current UI

The project has two read-only dashboard surfaces. The original generated Folium
map has:

- OpenStreetMap, light, and dark base layers.
- Corridor layers by type.
- Node markers, labels, tooltips, and detailed popups.
- A sidebar with static network availability statistics.
- Lowest-cost-path highlighting.

The map output is `backend/munich_airspace_map.html`, which is intentionally
ignored by Git. Map tiles require network access in the browser; graph overlays
remain locally generated.

The single eVTOL scenario also generates
`backend/single_evtol_scenario_map.html`. It preserves the static map layers,
highlights E1's route, and adds a self-contained aircraft replay with
play/pause/restart controls.

The fleet scenario generates `backend/fleet_evtol_scenario_map.html`. It shows
three eVTOLs, their speed/altitude profiles, route overlays, and live corridor
traffic/noise values for every simulated tick.

`frontend/` is a Vite/React control-center dashboard. It receives a single
read-only snapshot from `GET /api/simulation`, rather than making its own
airspace or aircraft state. `backend/dashboard_feed.py` converts a global fleet
replay tick into UI-ready nodes, corridors, agent reports, local
communication/constraint views, decision reasons, alerts, weather-zone state,
and metrics. `backend/api_server.py` serves that contract with the Python
standard library; Vite proxies `/api` to it during local development.

### Frontend data contract

`GET /api/simulation` is the single frontend data source. It returns a
deterministic, looping replay tick every second by default; one replay tick
represents ten simulation seconds. Add `?tick=<index>` to inspect a fixed tick.

The payload contains:

- `simulation`: replay clock, tick count, and source metadata.
- `nodes`: all 21 digital-twin nodes with capacity, occupancy, charging, and
  emergency-landing capability.
- `edges`: all 33 corridors with active agents, traffic density, noise,
  weather/closure fields, and transparent cost fields.
- `agents`: all eVTOL positions, operational status, battery, speed,
  altitude, route, ETA, local communication/constraint views, and their latest
  decision reason. The default dashboard scenario supplies 30 eVTOL reports.
- `alerts`, `weather_zones`, and aggregate message/reservation metrics.

The React app polls this endpoint once per second. Its former `worldData.ts`
dataset is now an offline fallback only; it is not the live simulation source.

### Dependencies

Python runtime dependencies are declared in `requirements.txt`:

- `folium` for generated Leaflet/Folium replay maps.
- `branca`, imported directly by the Folium map template code.
- `networkx` for graph storage and weighted path finding.

The dashboard API uses `http.server` and other Python standard-library modules,
so it does not require a web-framework package. React, Leaflet, Recharts,
TypeScript, Vite, and their development tooling are declared in
`frontend/package.json`; do not add them to Python `requirements.txt`.

Run the integrated dashboard in two terminals:

```powershell
python -m backend.api_server
```

```powershell
cd frontend
npm install
npm run dev
```

## Phase 0 status

Phase 0 is implemented.

- `requirements.txt` declares `folium`, `branca`, and `networkx`.
- `backend` is now a Python package.
- The smoke demo uses a root-safe import and must be run as a module.
- `README.md` documents setup and the current demo.

Run from the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m backend.test_graph
```

The smoke demo prints static network data, refreshes `backend/world.json`, and
creates `backend/munich_airspace_map.html`.

## Phase 1 status

The eVTOL state model is implemented in `backend/models.py`.

- `EVTOLAgent` contains the agreed operational, route, battery, health, local
  view, communication, and decision-reason fields.
- `EVTOLStatus` and `HealthStatus` provide constrained status values.
- `to_dict()` produces a JSON-friendly snapshot for future simulation and UI
  layers.
- `backend/tests/test_models.py` verifies defaults, serialization, validation,
  and independent mutable state.

One scenario-specific demonstration is available in
`backend/single_scenario.py`: E1 selects a random occupied departure pad and a
different available destination pad, then follows the existing static route
cost. It moves one corridor per tick, releases the departure pad, and occupies
the final destination pad. Intermediate graph nodes are corridor junctions, not
landings. Supplying a random seed is supported only for reproducible tests.

Run it with:

```powershell
python -m backend.single_scenario
```

This is not a reusable simulation engine. It has no fleet, dynamic data,
battery consumption, rerouting, weather, traffic, local communication, or map
animation beyond this one recorded route. Those behaviours remain future
phases.

## Planned architecture

Keep `graph.py` and its visual style. Add small readable modules around it:

| Module | Responsibility |
| --- | --- |
| `backend/models.py` | eVTOL dataclasses, statuses, health state, serializable snapshots |
| `backend/constraints.py` | Dynamic weather, congestion, queues, closures, charging status, reservations |
| `backend/planner.py` | Weighted route planner and transparent cost breakdowns |
| `backend/simulation.py` | Deterministic simulation clock, local communication, decisions, movement, and history |
| `backend/scenarios.py` | Fixed-seed demo configurations and dynamic events |
| `backend/dashboard.py` | Folium dashboard rendering and replay UI |
| `backend/tests/` | Standard-library deterministic tests |

## eVTOL model contract

Phase 1 should use built-in dataclasses and enums rather than a heavy model
dependency. Each agent must include at least:

| Field | Meaning |
| --- | --- |
| `evtol_id` | Stable deterministic identifier, for example `E1` |
| `current_node` | Current graph node when not travelling |
| `target_node` | Immediate operational destination |
| `assigned_origin` | Immutable origin displayed for the current assigned mission |
| `assigned_destination` | Immutable planned destination displayed for the current assigned mission |
| `mission_type` | `autonomous_transit` or `medical_transfer` |
| `cargo_description` | Visible medical payload description for hospital transfers |
| `current_route` | Remaining ordered node sequence |
| `current_edge` | Corridor currently being flown, if any |
| `battery_level` | Percentage from 0 to 100 |
| `speed_kmh` | Current cruise speed assigned by the flight profile |
| `altitude_level` | `inbound`, `outbound`, or `emergency` |
| `altitude_m` | Derived nominal altitude for the selected level |
| `status` | `idle`, `assigned`, `flying`, `charging`, `repositioning`, or `emergency` |
| `estimated_arrival_time` | Simulation-time ETA |
| `health_status` | `normal`, `degraded`, or `failure` |
| `communication_neighbors` | Locally reachable eVTOL IDs |
| `local_traffic_view` | Locally observed traffic and reservations |
| `local_noise_view` | Locally observed normalized corridor noise values |
| `local_weather_view` | Locally observed weather risks |
| `local_vertiport_queue_view` | Locally observed queue/landing information |
| `last_decision_reason` | Human-readable explanation of the latest decision |

Useful supporting fields are `mission_target`, `edge_progress`,
`route_cost_breakdown`, `last_reroute_tick`, and `reroute_count`.
`emergency_reason` identifies the active or last safety incident, for example
`battery_failure` or `technical_failure`.

## Fleet simulation status

`backend/fleet_scenario.py` runs three concurrent, random pad-to-pad flights.
Each run uses unique origin/destination pads where possible and records one
snapshot per 10 simulated seconds.

Flight-profile policy:

| Level | Trigger | Nominal altitude | Cruise speed |
| --- | --- | ---: | ---: |
| `inbound` | Route shorter than 10 km | 300 m | 100 km/h |
| `outbound` | Route at least 10 km | 600 m | 140 km/h |
| `emergency` | Health failure; safety override | 900 m | 170 km/h |

Traffic and noise are simulated live values, not external feeds. Every tick,
the canonical edge state uses corridor type, active eVTOL count, static noise,
zone sensitivity, and the active altitude level. Each agent receives only
traffic/noise values for its active and adjacent corridors in its local views.

The fleet exchanges local `POSITION_UPDATE`, `ROUTE_INTENT`,
`EDGE_CONDITION_UPDATE`, `LANDING_INTENT`, `RESERVATION_REQUEST`, and
`RESERVATION_DECISION` messages. Messages expire after three simulation ticks;
neighbor discovery is limited to same/adjacent edges, shared lookahead route,
same landing window, or physical range. The dashboard observes this traffic but
does not issue normal routing decisions.

Before entering a corridor, each aircraft requests an edge time-window. Before
the final corridor, it also requests a landing time-window. Conflicts are
resolved in this order: emergency, lower battery, already flying, earlier ETA,
then eVTOL ID. A denied aircraft holds at its current safe node and retries on
the next tick.

This fleet demo does not yet use live traffic/noise to reroute, does not consume
battery, and does not inject emergency events into its normal map replay.
Those decisions are implemented and demonstrated separately in the C4/C5
safety-decision module so they can be integrated into the dashboard in a later
focused phase.

## 30-eVTOL operational scenario

`backend/operational_scenario.py` is the dashboard's default simulation. It
creates 30 named agents (`E01` through `E30`) with capacity-safe, defined
missions: 26 autonomous pad-to-pad transits and four hospital-to-hospital
medical transfers. Medical transfers carry a visible `cargo_description`,
alternating between an organ-preservation container and an emergency medical
kit. The shared digital twin starts with matching origin occupancy, releases
departures, and tracks final arrivals.

The deterministic run includes three visible operational situations:

- Traffic congestion: each corridor has three scalable airspace slots per
  time-window; excess requests queue under the existing safety/battery/ETA/ID
  priority rule.
- Weather: a frequently used non-leaf corridor receives a high-risk closure at
  tick 18. Waiting agents use dynamic route costs and reroute around it; the
  closure clears at tick 75.
- Emergencies: a critical battery fault at tick 10 is deliberately assigned to
  one autonomous pad-to-pad transit. It diverts to a reachable charging hub,
  recharges, and resumes its original transit mission. Medical transfers remain
  independent hospital-to-hospital cargo missions. A controllable technical
  failure at tick 45 affects a different non-medical eVTOL and diverts it to
  the nearest reachable charging/maintenance station. It remains grounded
  there for maintenance and its original mission is aborted.

`emergency_reason` represents an active safety condition, not historical
telemetry. The battery scenario sets it to `critical_battery` only at or below
15% battery and clears it once charging restores the eVTOL to at least 30%.
Technical failure remains distinct at every battery level: it is displayed as
`technical_failure` / `Technical Failure`, uses emergency routing to the
maintenance station, and is never labelled as a battery event.

Battery reduces by 1% per flown kilometre. The simulation completes with all
30 aircraft parked (including the technically failed aircraft at a maintenance
charger), while the event and reservation logs remain available to the
dashboard as alerts and metrics.

Run it with:

```powershell
python -m backend.operational_scenario
```

## C4/C5 safety-decision status

`backend/emergency.py` adds the safety-first decision layer, used by the
repeatable `backend/emergency_scenario.py` console demonstration.

- Battery policy: low battery is below 30%; critical battery is at or below
  15%. Energy use is a documented 1% per kilometre with a 10% normal or 5%
  emergency reserve.
- A low-battery agent diverts to a reachable, non-full charging hub, preserves
  its original `mission_target`, and sends `BATTERY_LOW_ALERT`,
  `CHARGING_INTENT`, and `CHARGING_DECISION` protocol messages.
- A critical-battery agent takes the same safety diversion using emergency
  status (900 m, 170 km/h), which gives it C3 emergency reservation priority.
- A hospital alert selects the fastest healthy agent at a safe graph node that
  can reach the hospital with reserve. It sends `EMERGENCY_DECLARED`; the
  responder sends `EMERGENCY_ROUTE_INTENT` only to local communication
  neighbors.
- `backend/planner.py` calculates named dynamic weights for distance, energy,
  weather, traffic, noise, destination queue, and reservation risk. Blocked
  corridors are hard exclusions.
- Rerouting happens only at a safe node. It is triggered by a blocked corridor,
  weather risk of 0.75 or greater, or a dynamic-cost improvement of at least
  15%. A three-tick cooldown and three-reroute limit prevent route thrashing;
  unsafe routes override those safeguards.

Run the deterministic decision demo from the repository root:

```powershell
python -m backend.emergency_scenario
```

## Simulation rules

### Decision order

On every deterministic tick, an agent should:

1. Enter emergency mode for health failure or critically unsafe battery.
2. Divert to a safe reachable charging hub for low, non-critical battery.
3. Calculate a route when it has a target but no valid route.
4. Check its upcoming edge for unsafe conditions, closures, queue risk, or
   conflicting reservations.
5. Reroute only when the existing route is unsafe or the alternative is
   materially better.
6. Move one explainable step along its route when permitted.
7. Update `last_decision_reason` for every state-changing decision.

### Weighted routing

Use Dijkstra/A* with a named weight configuration. The cost of a corridor must
be transparent:

```text
distance_weight × distance
+ battery_weight × estimated_energy_usage
+ weather_weight × weather_risk
+ traffic_weight × traffic_density
+ noise_weight × noise_penalty
+ queue_weight × destination_queue
+ emergency penalty, or exclusion, when restricted/blocked
```

Every selected plan should retain total cost, per-edge costs, and factor
breakdowns so the UI can explain its choice.

### Battery and charging

- Use a simple documented energy-per-kilometre model and a battery reserve.
- Charging hubs are nodes with `node_type == "charging_hub"`.
- Keep queue length distinct from node `current_load`, which is pad occupancy.
- A critical aircraft must prefer emergency safety over mission completion.

### Local communication and conflicts

Aircraft communicate only with agents on the same/adjacent corridor, near the
same node, or optionally within graph distance one or two. Local messages
contain ID, position, current/next edge, target, ETA, battery, status,
emergency flag, and intended move.

When two eVTOLs request the same edge or arrival slot, resolve priority in this
strict order:

1. Emergency aircraft
2. Lower battery
3. Already-flying aircraft
4. Earlier ETA
5. Lexicographically lower `evtol_id`

The losing aircraft waits, slows, or later reroutes, with the result recorded
in `last_decision_reason`.

### Rerouting safeguards

Trigger rerouting for weather escalation, blocked corridors, reservations,
unsafe battery, excessive destination queue, or degraded/failure health.

Avoid route thrashing with a reroute cooldown, maximum reroutes per mission,
and a meaningful-improvement threshold. An unsafe route always overrides the
threshold.

## Roadmap

| Phase | Deliverable |
| --- | --- |
| 0 | Reproducible package setup and root-safe static smoke demo — complete |
| 1 | eVTOL dataclass model plus one random static pad-to-pad scenario — complete |
| 2 | Weighted route planner with cost breakdown |
| 3 | Tick-based movement/history for the three-agent demo — complete |
| 4 / C4 | Battery thresholds, charging diversion, charging messages, and mission resumption — complete |
| C0–C3 | Typed local messages, TTL, neighbors, edge/landing reservations, deterministic priority — complete |
| 5 / C5 | Hospital emergency broadcasts, responder selection, dynamic weighted routing, and safe-node rerouting — complete |
| 6 | Dynamic traffic/noise data for the fleet demo — partial; weather/closures/rerouting await dashboard/fleet-loop integration |
| 7 | Multi-agent Folium replay with routes, altitude, speed, traffic, and noise — partial; decision panels remain |
| 8 | Repeatable demos plus route/battery/conflict/reroute tests |

## Implementation conventions

- Preserve the existing graph and Folium design unless a change is necessary.
- Prefer clear dataclasses, dictionaries, and small modules over frameworks.
- Use fixed seeds and scripted events for demos and tests.
- Start scenarios with 2–3 agents and an operational subset of roughly 6–10
  relevant nodes, while retaining the complete 21-node map.
- Use canonical undirected edge keys for dynamic constraints and reservations.
- Keep the dashboard read-only; simulation agents make the decisions.
- Do not add passenger-demand logic.
- For every future phase, report changed files, provide complete changed-file
  code, give exact run/test commands, and end with concise Git commands.
