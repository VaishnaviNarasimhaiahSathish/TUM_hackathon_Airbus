"""Folium replay UI for the deterministic single-eVTOL scenario."""

import json
import re
from pathlib import Path

from backend.single_scenario import ScenarioResult


DEFAULT_OUTPUT_FILE = "backend/single_evtol_scenario_map.html"
SAMPLES_PER_CORRIDOR = 10


def _build_animation_frames(result: ScenarioResult) -> list[dict[str, object]]:
    """Interpolate the agent position along each straight-line graph corridor."""
    if len(result.path) < 2:
        raise ValueError("A replay requires a route containing at least one corridor")

    frames: list[dict[str, object]] = []

    for leg_number, (start_name, end_name) in enumerate(
        zip(result.path[:-1], result.path[1:]),
        start=1,
    ):
        start = result.airspace.nodes[start_name]
        end = result.airspace.nodes[end_name]

        for sample in range(SAMPLES_PER_CORRIDOR):
            progress = sample / SAMPLES_PER_CORRIDOR
            frames.append(
                {
                    "lat": start.lat + (end.lat - start.lat) * progress,
                    "lon": start.lon + (end.lon - start.lon) * progress,
                    "leg": leg_number,
                    "from": start_name,
                    "to": end_name,
                }
            )

    destination = result.airspace.nodes[result.path[-1]]
    frames.append(
        {
            "lat": destination.lat,
            "lon": destination.lon,
            "leg": len(result.path) - 1,
            "from": result.path[-2],
            "to": result.path[-1],
        }
    )
    return frames


def _build_replay_script(map_name: str, result: ScenarioResult) -> str:
    """Create a small Leaflet overlay without changing the shared base map."""
    frames = json.dumps(_build_animation_frames(result))
    agent_id = json.dumps(result.agent.evtol_id)
    route = json.dumps(" → ".join(result.path))
    destination = json.dumps(result.path[-1])
    total_legs = len(result.path) - 1

    return f"""
<script>
(function () {{
    const map = {map_name};
    const frames = {frames};
    const agentId = {agent_id};
    const route = {route};
    const destination = {destination};
    const totalLegs = {total_legs};
    let frameIndex = 0;
    let timer = null;
    let isPlaying = false;

    const aircraftIcon = L.divIcon({{
        className: "",
        iconSize: [42, 42],
        iconAnchor: [21, 21],
        html: `
            <div style="
                width:34px;height:34px;border-radius:50%;
                display:flex;align-items:center;justify-content:center;
                background:#06b6d4;color:#082f49;border:2px solid white;
                box-shadow:0 3px 10px rgba(0,0,0,.4);font-size:19px;
            ">✈</div>
            <div style="
                margin-top:2px;padding:1px 4px;border-radius:4px;
                background:rgba(8,47,73,.9);color:white;text-align:center;
                font:700 11px Arial,sans-serif;
            ">${{agentId}}</div>
        `,
    }});

    const marker = L.marker([frames[0].lat, frames[0].lon], {{
        icon: aircraftIcon,
        zIndexOffset: 1000,
    }}).addTo(map);

    const replayControl = L.control({{ position: "bottomright" }});
    replayControl.onAdd = function () {{
        const container = L.DomUtil.create("div");
        container.style.cssText = [
            "width:330px", "padding:12px", "border-radius:12px",
            "background:rgba(255,255,255,.96)",
            "border:1px solid #cbd5e1", "box-shadow:0 6px 18px rgba(0,0,0,.24)",
            "font-family:Arial,sans-serif", "color:#0f172a",
        ].join(";");
        container.innerHTML = `
            <div style="font-size:15px;font-weight:800;">E1 Flight Replay</div>
            <div id="evtol-replay-status" style="margin:6px 0;font-size:12px;"></div>
            <div style="font-size:11px;color:#475569;line-height:1.35;margin-bottom:8px;">
                ${{route}}
            </div>
            <button id="evtol-play-pause" style="margin-right:6px;">Pause</button>
            <button id="evtol-restart">Restart</button>
        `;
        L.DomEvent.disableClickPropagation(container);
        return container;
    }};
    replayControl.addTo(map);

    const status = document.getElementById("evtol-replay-status");
    const playPauseButton = document.getElementById("evtol-play-pause");
    const restartButton = document.getElementById("evtol-restart");

    function renderFrame() {{
        const frame = frames[frameIndex];
        marker.setLatLng([frame.lat, frame.lon]);
        status.innerHTML = `<b>Status:</b> flying &middot; Leg ${{frame.leg}}/${{totalLegs}}<br>` +
            `<b>Corridor:</b> ${{frame.from}} &rarr; ${{frame.to}}`;
    }}

    function stopPlayback() {{
        window.clearInterval(timer);
        timer = null;
        isPlaying = false;
        playPauseButton.textContent = frameIndex === frames.length - 1 ? "Arrived" : "Play";
        playPauseButton.disabled = frameIndex === frames.length - 1;
    }}

    function advanceFrame() {{
        if (frameIndex >= frames.length - 1) {{
            stopPlayback();
            status.innerHTML = `<b>Status:</b> arrived safely at ${{destination}}`;
            return;
        }}
        frameIndex += 1;
        renderFrame();
    }}

    function startPlayback() {{
        if (isPlaying || frameIndex >= frames.length - 1) {{
            return;
        }}
        isPlaying = true;
        playPauseButton.textContent = "Pause";
        playPauseButton.disabled = false;
        timer = window.setInterval(advanceFrame, 300);
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


def create_scenario_replay(
    result: ScenarioResult,
    filename: str = DEFAULT_OUTPUT_FILE,
) -> str:
    """Render the existing Folium map with a self-contained E1 replay overlay."""
    output_path = Path(filename)
    result.airspace.create_interactive_map(
        filename=str(output_path),
        highlight_path=result.path,
    )

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
