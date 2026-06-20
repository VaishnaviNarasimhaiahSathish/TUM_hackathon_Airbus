"""Folium replay UI for the three-agent eVTOL fleet scenario."""

import json
import re
from pathlib import Path

from backend.fleet_scenario import FleetScenarioResult


DEFAULT_OUTPUT_FILE = "backend/fleet_evtol_scenario_map.html"

ALTITUDE_STYLES = {
    "inbound": {"color": "#2563eb", "label": "Inbound"},
    "outbound": {"color": "#7c3aed", "label": "Outbound"},
    "emergency": {"color": "#dc2626", "label": "Emergency"},
}


def _build_replay_payload(result: FleetScenarioResult) -> dict[str, object]:
    """Convert simulation history into compact JavaScript-ready replay data."""
    frames = []
    for tick in result.ticks:
        active_edges = []
        for edge_state in tick.edge_states:
            if not edge_state.active_agent_ids:
                continue
            start = result.airspace.nodes[edge_state.start]
            end = result.airspace.nodes[edge_state.end]
            edge_data = edge_state.to_dict()
            edge_data["coordinates"] = [[start.lat, start.lon], [end.lat, end.lon]]
            active_edges.append(edge_data)

        frames.append(
            {
                "tick": tick.tick,
                "simulation_seconds": tick.simulation_seconds,
                "agents": [agent.to_dict() for agent in tick.agents],
                "active_edges": active_edges,
                "active_message_count": tick.active_message_count,
                "active_reservation_count": tick.active_reservation_count,
            }
        )

    routes = {}
    for evtol_id, route in result.routes.items():
        routes[evtol_id] = [
            [result.airspace.nodes[node_name].lat, result.airspace.nodes[node_name].lon]
            for node_name in route
        ]

    return {"frames": frames, "routes": routes}


def _build_replay_script(map_name: str, result: FleetScenarioResult) -> str:
    """Create an animated Leaflet fleet overlay after Folium has rendered."""
    payload = json.dumps(_build_replay_payload(result))
    altitude_styles = json.dumps(ALTITUDE_STYLES)

    return f"""
<script>
(function () {{
    const map = {map_name};
    const replay = {payload};
    const altitudeStyles = {altitude_styles};
    const markers = {{}};
    const activeEdgeLayers = [];
    let frameIndex = 0;
    let timer = null;
    let isPlaying = false;

    function agentIcon(agent) {{
        const style = altitudeStyles[agent.altitude_level];
        return L.divIcon({{
            className: "",
            iconSize: [44, 46],
            iconAnchor: [22, 22],
            html: `
                <div style="
                    width:34px;height:34px;border-radius:50%;
                    display:flex;align-items:center;justify-content:center;
                    background:${{style.color}};color:white;border:2px solid white;
                    box-shadow:0 3px 10px rgba(0,0,0,.4);font-size:18px;
                ">&#9992;</div>
                <div style="
                    margin-top:2px;padding:1px 4px;border-radius:4px;
                    background:rgba(15,23,42,.9);color:white;text-align:center;
                    font:700 11px Arial,sans-serif;
                ">${{agent.evtol_id}}</div>
            `,
        }});
    }}

    function trafficColor(value) {{
        if (value >= 0.75) return "#dc2626";
        if (value >= 0.45) return "#f59e0b";
        return "#16a34a";
    }}

    const firstFrame = replay.frames[0];
    firstFrame.agents.forEach(function (agent) {{
        markers[agent.evtol_id] = L.marker([agent.lat, agent.lon], {{
            icon: agentIcon(agent),
            zIndexOffset: 1000,
        }}).addTo(map);
    }});

    Object.entries(replay.routes).forEach(function ([evtolId, coordinates]) {{
        const firstAgent = firstFrame.agents.find((agent) => agent.evtol_id === evtolId);
        L.polyline(coordinates, {{
            color: altitudeStyles[firstAgent.altitude_level].color,
            weight: 3,
            opacity: 0.70,
            dashArray: "7, 8",
        }}).addTo(map);
    }});

    const replayControl = L.control({{ position: "bottomright" }});
    replayControl.onAdd = function () {{
        const container = L.DomUtil.create("div");
        container.style.cssText = [
            "width:355px", "padding:12px", "border-radius:12px",
            "background:rgba(255,255,255,.96)",
            "border:1px solid #cbd5e1", "box-shadow:0 6px 18px rgba(0,0,0,.24)",
            "font-family:Arial,sans-serif", "color:#0f172a",
        ].join(";");
        container.innerHTML = `
            <div style="font-size:15px;font-weight:800;">3-eVTOL Fleet Replay</div>
            <div id="fleet-time" style="margin:5px 0;font-size:12px;"></div>
            <div id="fleet-metrics" style="font-size:12px;margin-bottom:7px;"></div>
            <div id="fleet-agent-rows" style="font-size:11px;line-height:1.45;margin-bottom:8px;"></div>
            <div style="font-size:10px;color:#475569;margin-bottom:8px;">
                <span style="color:#2563eb;font-weight:700;">&#9679;</span> Inbound 300 m / 100 km/h &nbsp;
                <span style="color:#7c3aed;font-weight:700;">&#9679;</span> Outbound 600 m / 140 km/h &nbsp;
                <span style="color:#dc2626;font-weight:700;">&#9679;</span> Emergency 900 m / 170 km/h
            </div>
            <button id="fleet-play-pause" style="margin-right:6px;">Pause</button>
            <button id="fleet-restart">Restart</button>
        `;
        L.DomEvent.disableClickPropagation(container);
        return container;
    }};
    replayControl.addTo(map);

    const timeLabel = document.getElementById("fleet-time");
    const metricsLabel = document.getElementById("fleet-metrics");
    const agentRows = document.getElementById("fleet-agent-rows");
    const playPauseButton = document.getElementById("fleet-play-pause");
    const restartButton = document.getElementById("fleet-restart");

    function clearActiveEdges() {{
        while (activeEdgeLayers.length) {{
            map.removeLayer(activeEdgeLayers.pop());
        }}
    }}

    function renderFrame() {{
        const frame = replay.frames[frameIndex];
        frame.agents.forEach(function (agent) {{
            const marker = markers[agent.evtol_id];
            marker.setLatLng([agent.lat, agent.lon]);
            marker.setIcon(agentIcon(agent));
            marker.bindPopup(`
                <b>${{agent.evtol_id}}</b><br>
                ${{agent.altitude_level}} &middot; ${{agent.altitude_m}} m<br>
                ${{agent.speed_kmh.toFixed(0)}} km/h<br>
                ${{agent.decision_reason}}
            `);
        }});

        clearActiveEdges();
        frame.active_edges.forEach(function (edge) {{
            const layer = L.polyline(edge.coordinates, {{
                color: trafficColor(edge.traffic_density),
                weight: 8,
                opacity: 0.65,
            }}).addTo(map);
            activeEdgeLayers.push(layer);
        }});

        const maxTraffic = frame.active_edges.length
            ? Math.max(...frame.active_edges.map((edge) => edge.traffic_density))
            : 0;
        const maxNoise = frame.active_edges.length
            ? Math.max(...frame.active_edges.map((edge) => edge.noise_level))
            : 0;
        timeLabel.innerHTML = `<b>Simulation time:</b> ${{frame.simulation_seconds}} s &middot; tick ${{frame.tick}}`;
        metricsLabel.innerHTML = `<b>Live corridor state:</b> ${{frame.active_edges.length}} active &middot; ` +
            `max traffic ${{maxTraffic.toFixed(2)}} &middot; max noise ${{maxNoise.toFixed(2)}}<br>` +
            `<b>Protocol:</b> ${{frame.active_message_count}} active messages &middot; ` +
            `${{frame.active_reservation_count}} active reservations`;
        agentRows.innerHTML = frame.agents.map(function (agent) {{
            const style = altitudeStyles[agent.altitude_level];
            return `<div><span style="color:${{style.color}};font-weight:800;">&#9679;</span> ` +
                `<b>${{agent.evtol_id}}</b> — ${{agent.status}}, ${{agent.altitude_level}} ` +
                `(${{agent.altitude_m}} m), ${{agent.speed_kmh.toFixed(0)}} km/h, ` +
                `${{agent.neighbor_count}} neighbors</div>`;
        }}).join("");
    }}

    function stopPlayback() {{
        window.clearInterval(timer);
        timer = null;
        isPlaying = false;
        playPauseButton.textContent = frameIndex === replay.frames.length - 1 ? "Complete" : "Play";
        playPauseButton.disabled = frameIndex === replay.frames.length - 1;
    }}

    function advanceFrame() {{
        if (frameIndex >= replay.frames.length - 1) {{
            stopPlayback();
            return;
        }}
        frameIndex += 1;
        renderFrame();
    }}

    function startPlayback() {{
        if (isPlaying || frameIndex >= replay.frames.length - 1) {{
            return;
        }}
        isPlaying = true;
        playPauseButton.textContent = "Pause";
        playPauseButton.disabled = false;
        timer = window.setInterval(advanceFrame, 500);
    }}

    playPauseButton.addEventListener("click", function () {{
        if (isPlaying) {{
            stopPlayback();
        }} else {{
            startPlayback();
        }}
    }});

    restartButton.addEventListener("click", function () {{
        stopPlayback();
        frameIndex = 0;
        renderFrame();
        startPlayback();
    }});

    renderFrame();
    window.setTimeout(startPlayback, 700);
}})();
</script>
"""


def create_fleet_replay(
    result: FleetScenarioResult,
    filename: str = DEFAULT_OUTPUT_FILE,
) -> str:
    """Render a standalone animated replay for the three-agent fleet."""
    output_path = Path(filename)
    result.airspace.create_interactive_map(filename=str(output_path))

    html = output_path.read_text(encoding="utf-8")
    map_match = re.search(r"var (map_[a-z0-9]+) = L\.map", html)
    if map_match is None:
        raise RuntimeError("Unable to locate the Folium map variable for the replay")

    replay_script = _build_replay_script(map_match.group(1), result)
    output_path.write_text(
        html.replace("</html>", f"{replay_script}</html>"),
        encoding="utf-8",
    )
    return str(output_path)
