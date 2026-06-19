import json
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

import folium
import networkx as nx
from branca.element import MacroElement, Template
from folium.plugins import Fullscreen, MiniMap, MeasureControl


def calculate_air_distance_km(lat1, lon1, lat2, lon2):
    """
    Calculate straight-line flying distance between two coordinates.
    This is suitable for a basic eVTOL airspace simulation.
    """

    earth_radius_km = 6371.0

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    lat1 = radians(lat1)
    lat2 = radians(lat2)

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return round(earth_radius_km * c, 2)


class AirNode:
    def __init__(self, node_id, name, node_type, lat, lon, description=""):
        self.id = node_id
        self.name = name
        self.node_type = node_type
        self.lat = lat
        self.lon = lon
        self.description = description

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "type": self.node_type,
            "lat": self.lat,
            "lon": self.lon,
            "description": self.description,
        }


class AirRoute:
    def __init__(self, start, end, route_type="standard", distance=None):
        self.start = start
        self.end = end
        self.route_type = route_type
        self.distance = distance

    def to_dict(self):
        return {
            "start": self.start,
            "end": self.end,
            "route_type": self.route_type,
            "distance_km": self.distance,
        }


class RestrictMapBounds(MacroElement):
    """
    Hard-restricts panning to the chosen Munich bounding box.
    This prevents users from dragging too far away from Munich.
    """

    def __init__(self, bounds):
        super().__init__()
        self._name = "RestrictMapBounds"
        self.bounds = bounds

        self._template = Template(
            """
            {% macro script(this, kwargs) %}
                var bounds = L.latLngBounds(
                    [{{ this.bounds[0][0] }}, {{ this.bounds[0][1] }}],
                    [{{ this.bounds[1][0] }}, {{ this.bounds[1][1] }}]
                );
                {{ this._parent.get_name() }}.setMaxBounds(bounds);
                {{ this._parent.get_name() }}.options.maxBoundsViscosity = 1.0;
            {% endmacro %}
            """
        )


class MunichAirspaceDigitalTwin:
    def __init__(self):
        self.nodes = {}
        self.routes = []
        self.graph = nx.Graph()

    def add_node(self, air_node):
        self.nodes[air_node.name] = air_node

        self.graph.add_node(
            air_node.name,
            id=air_node.id,
            type=air_node.node_type,
            lat=air_node.lat,
            lon=air_node.lon,
            description=air_node.description,
        )

    def add_route(self, air_route):
        if air_route.start not in self.nodes:
            raise ValueError(f"Start node does not exist: {air_route.start}")

        if air_route.end not in self.nodes:
            raise ValueError(f"End node does not exist: {air_route.end}")

        start_node = self.nodes[air_route.start]
        end_node = self.nodes[air_route.end]

        distance = calculate_air_distance_km(
            start_node.lat,
            start_node.lon,
            end_node.lat,
            end_node.lon,
        )

        air_route.distance = distance
        self.routes.append(air_route)

        self.graph.add_edge(
            air_route.start,
            air_route.end,
            weight=distance,
            distance_km=distance,
            route_type=air_route.route_type,
        )

    def build_world(self):
        """
        Builds a Munich-focused airspace digital twin.

        Node types:
        - pad
        - hospital
        - charging_hub

        Route types:
        - airport_corridor
        - city_corridor
        - medical_corridor
        - charging_corridor
        """

        node_data = [
            # Pads
            (
                1,
                "Munich Airport",
                "pad",
                48.3538,
                11.7861,
                "Major airport pad and northern entry point for eVTOL traffic.",
            ),
            (
                2,
                "Munich Central Station (Hauptbahnhof)",
                "pad",
                48.1402,
                11.5584,
                "High passenger-transfer location near the city center.",
            ),
            (
                3,
                "Marienplatz",
                "pad",
                48.1374,
                11.5755,
                "Central Munich pad with high passenger demand.",
            ),
            (
                4,
                "TUM Main Campus",
                "pad",
                48.1486,
                11.5682,
                "University and technology district pad.",
            ),
            (
                5,
                "LMU Munich",
                "pad",
                48.1508,
                11.5806,
                "University district pad near Maxvorstadt.",
            ),
            (
                6,
                "Allianz Arena",
                "pad",
                48.2188,
                11.6247,
                "Event-based northern mobility pad.",
            ),
            (
                7,
                "Messe München",
                "pad",
                48.1356,
                11.6903,
                "Trade fair and business mobility pad.",
            ),
            (
                8,
                "Olympiapark",
                "pad",
                48.1739,
                11.5461,
                "Event and leisure mobility pad.",
            ),
            (
                9,
                "Schwabing",
                "pad",
                48.1665,
                11.5860,
                "Dense residential and business district pad.",
            ),
            (
                10,
                "Sendlinger Tor",
                "pad",
                48.1330,
                11.5668,
                "Inner-city transfer pad.",
            ),

            # Hospitals
            (
                11,
                "TUM Klinikum Rechts der Isar",
                "hospital",
                48.1355,
                11.5991,
                "Central medical landing point near Rechts der Isar.",
            ),
            (
                12,
                "Großhadern Clinic",
                "hospital",
                48.1113,
                11.4697,
                "Large hospital zone in southwest Munich.",
            ),
            (
                13,
                "München Klinik Schwabing",
                "hospital",
                48.1678,
                11.5826,
                "Hospital landing point in Schwabing.",
            ),
            (
                14,
                "Munich Clinic Bogenhausen",
                "hospital",
                48.1525,
                11.6215,
                "Hospital landing point in eastern Munich.",
            ),
            (
                15,
                "München Klinik Neuperlach",
                "hospital",
                48.1039,
                11.6460,
                "Southeast medical landing point.",
            ),
            (
                16,
                "Harlaching Hospital",
                "hospital",
                48.1027,
                11.5798,
                "Southern medical landing point.",
            ),

            # Charging hubs
            (
                17,
                "Charging Hub A - Airport",
                "charging_hub",
                48.3600,
                11.7800,
                "Airport charging hub for aircraft recharging between airport missions.",
            ),
            (
                18,
                "Charging Hub B - TUM Tech Area",
                "charging_hub",
                48.1525,
                11.5740,
                "Technology-district charging hub near TUM.",
            ),
            (
                19,
                "Charging Hub C - City Center",
                "charging_hub",
                48.1390,
                11.5810,
                "City-center charging hub near Marienplatz for high passenger turnover.",
            ),
            (
                20,
                "Charging Hub D - Großhadern Zone",
                "charging_hub",
                48.1090,
                11.4750,
                "Emergency logistics charging hub near Großhadern Clinic.",
            ),
        ]

        for node_id, name, node_type, lat, lon, description in node_data:
            self.add_node(
                AirNode(
                    node_id=node_id,
                    name=name,
                    node_type=node_type,
                    lat=lat,
                    lon=lon,
                    description=description,
                )
            )

        route_pairs = [
            # Airport corridors
            ("Munich Airport", "Charging Hub A - Airport", "charging_corridor"),
            ("Munich Airport", "Allianz Arena", "airport_corridor"),
            ("Munich Airport", "Munich Central Station (Hauptbahnhof)", "airport_corridor"),
            ("Munich Airport", "Messe München", "airport_corridor"),

            # Northern / event corridors
            ("Allianz Arena", "Schwabing", "city_corridor"),
            ("Allianz Arena", "Olympiapark", "city_corridor"),
            ("Olympiapark", "Munich Central Station (Hauptbahnhof)", "city_corridor"),
            ("Olympiapark", "LMU Munich", "city_corridor"),

            # University and central city corridors
            ("Schwabing", "LMU Munich", "city_corridor"),
            ("Schwabing", "München Klinik Schwabing", "medical_corridor"),
            ("Schwabing", "Munich Clinic Bogenhausen", "medical_corridor"),
            ("LMU Munich", "TUM Main Campus", "city_corridor"),
            ("LMU Munich", "Marienplatz", "city_corridor"),
            ("TUM Main Campus", "Marienplatz", "city_corridor"),
            ("TUM Main Campus", "TUM Klinikum Rechts der Isar", "medical_corridor"),
            ("TUM Main Campus", "Charging Hub B - TUM Tech Area", "charging_corridor"),

            # City-center corridors
            ("Marienplatz", "Munich Central Station (Hauptbahnhof)", "city_corridor"),
            ("Marienplatz", "Sendlinger Tor", "city_corridor"),
            ("Marienplatz", "Charging Hub C - City Center", "charging_corridor"),
            ("Marienplatz", "TUM Klinikum Rechts der Isar", "medical_corridor"),
            ("Marienplatz", "Messe München", "city_corridor"),

            # East / Messe corridors
            ("Messe München", "Munich Clinic Bogenhausen", "medical_corridor"),
            ("Messe München", "München Klinik Neuperlach", "medical_corridor"),
            ("Munich Clinic Bogenhausen", "TUM Klinikum Rechts der Isar", "medical_corridor"),

            # South / southwest hospital corridors
            ("Sendlinger Tor", "Harlaching Hospital", "medical_corridor"),
            ("Sendlinger Tor", "Großhadern Clinic", "medical_corridor"),
            ("Sendlinger Tor", "Munich Central Station (Hauptbahnhof)", "city_corridor"),
            ("Großhadern Clinic", "Charging Hub D - Großhadern Zone", "charging_corridor"),
            ("Großhadern Clinic", "Harlaching Hospital", "medical_corridor"),
            ("Harlaching Hospital", "München Klinik Neuperlach", "medical_corridor"),
        ]

        for start, end, route_type in route_pairs:
            self.add_route(AirRoute(start=start, end=end, route_type=route_type))

    def find_shortest_path(self, start, end):
        if start not in self.nodes:
            raise ValueError(f"Start location does not exist: {start}")

        if end not in self.nodes:
            raise ValueError(f"Destination location does not exist: {end}")

        path = nx.shortest_path(
            self.graph,
            source=start,
            target=end,
            weight="weight",
        )

        distance = nx.shortest_path_length(
            self.graph,
            source=start,
            target=end,
            weight="weight",
        )

        return path, round(distance, 2)

    def export_world_json(self, filename="backend/world.json"):
        world = {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [route.to_dict() for route in self.routes],
        }

        output_path = Path(filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(world, file, indent=4, ensure_ascii=False)

        return world

    def get_network_stats(self):
        counts = {
            "pad": 0,
            "hospital": 0,
            "charging_hub": 0,
        }

        for node in self.nodes.values():
            counts[node.node_type] = counts.get(node.node_type, 0) + 1

        return {
            "total_nodes": len(self.nodes),
            "total_routes": len(self.routes),
            "pads": counts["pad"],
            "hospitals": counts["hospital"],
            "charging_hubs": counts["charging_hub"],
        }

    def _get_marker_html(self, node):
        marker_style = {
            "pad": {
                "color": "#1f78b4",
                "emoji": "P",
            },
            "hospital": {
                "color": "#e31a1c",
                "emoji": "H",
            },
            "charging_hub": {
                "color": "#33a02c",
                "emoji": "C",
            },
        }

        style = marker_style.get(
            node.node_type,
            {
                "color": "#666666",
                "emoji": "?",
            },
        )

        return f"""
        <div style="
            background: {style['color']};
            color: white;
            border: 2px solid white;
            border-radius: 50%;
            width: 28px;
            height: 28px;
            line-height: 25px;
            text-align: center;
            font-weight: bold;
            font-size: 13px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.35);
        ">
            {style['emoji']}
        </div>
        """

    def _get_label_html(self, node):
        return f"""
        <div style="
            font-size: 11px;
            font-weight: 600;
            color: #1f2937;
            background: rgba(255,255,255,0.82);
            padding: 2px 5px;
            border-radius: 4px;
            border: 1px solid rgba(0,0,0,0.15);
            white-space: nowrap;
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
        ">
            {node.name}
        </div>
        """

    def create_interactive_map(
        self,
        filename="backend/munich_airspace_map.html",
        highlight_path=None,
    ):
        """
        Creates a rich Munich-focused Folium map.

        highlight_path:
            Optional list of node names.
            Example:
            ["Munich Airport", "Marienplatz", "TUM Klinikum Rechts der Isar"]
        """

        output_path = Path(filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Munich + airport bounds.
        # This includes Munich Airport but prevents zooming/panning far outside the project area.
        munich_bounds = [
            [48.06, 11.42],  # southwest
            [48.38, 11.82],  # northeast
        ]

        munich_map = folium.Map(
            location=[48.17, 11.62],
            zoom_start=11,
            min_zoom=10,
            max_zoom=18,
            tiles=None,
            max_bounds=True,
            control_scale=True,
        )

        # Tile layers
        folium.TileLayer(
            tiles="OpenStreetMap",
            name="OpenStreetMap",
            control=True,
        ).add_to(munich_map)

        folium.TileLayer(
            tiles="CartoDB positron",
            name="Light map",
            control=True,
        ).add_to(munich_map)

        folium.TileLayer(
            tiles="CartoDB dark_matter",
            name="Dark map",
            control=True,
        ).add_to(munich_map)

        munich_map.fit_bounds(munich_bounds)
        munich_map.add_child(RestrictMapBounds(munich_bounds))

        # Groups
        pads_group = folium.FeatureGroup(name="Pads", show=True)
        hospitals_group = folium.FeatureGroup(name="Hospitals", show=True)
        charging_group = folium.FeatureGroup(name="Charging Hubs", show=True)

        airport_routes_group = folium.FeatureGroup(name="Airport Corridors", show=True)
        city_routes_group = folium.FeatureGroup(name="City Corridors", show=True)
        medical_routes_group = folium.FeatureGroup(name="Medical Corridors", show=True)
        charging_routes_group = folium.FeatureGroup(name="Charging Corridors", show=True)
        labels_group = folium.FeatureGroup(name="Location Labels", show=True)
        highlighted_path_group = folium.FeatureGroup(name="Highlighted Shortest Path", show=True)

        route_style = {
            "airport_corridor": {
                "color": "#6366f1",
                "weight": 5,
                "dash_array": None,
            },
            "city_corridor": {
                "color": "#6b7280",
                "weight": 3,
                "dash_array": None,
            },
            "medical_corridor": {
                "color": "#ef4444",
                "weight": 4,
                "dash_array": "8, 6",
            },
            "charging_corridor": {
                "color": "#22c55e",
                "weight": 4,
                "dash_array": "4, 6",
            },
        }

        route_group_by_type = {
            "airport_corridor": airport_routes_group,
            "city_corridor": city_routes_group,
            "medical_corridor": medical_routes_group,
            "charging_corridor": charging_routes_group,
        }

        # Draw routes first so markers appear above them
        for route in self.routes:
            start_node = self.nodes[route.start]
            end_node = self.nodes[route.end]

            style = route_style.get(
                route.route_type,
                {
                    "color": "#555555",
                    "weight": 3,
                    "dash_array": None,
                },
            )

            route_popup = f"""
            <div style="font-family: Arial; width: 250px;">
                <h4 style="margin-bottom: 6px;">Air Corridor</h4>
                <b>From:</b> {route.start}<br>
                <b>To:</b> {route.end}<br>
                <b>Type:</b> {route.route_type}<br>
                <b>Air distance:</b> {route.distance} km
            </div>
            """

            polyline = folium.PolyLine(
                locations=[
                    [start_node.lat, start_node.lon],
                    [end_node.lat, end_node.lon],
                ],
                color=style["color"],
                weight=style["weight"],
                opacity=0.85,
                dash_array=style["dash_array"],
                tooltip=f"{route.start} ↔ {route.end} | {route.distance} km",
                popup=folium.Popup(route_popup, max_width=300),
            )

            polyline.add_to(route_group_by_type[route.route_type])

        # Highlight shortest path if provided
        if highlight_path and len(highlight_path) >= 2:
            for start, end in zip(highlight_path[:-1], highlight_path[1:]):
                if start in self.nodes and end in self.nodes:
                    start_node = self.nodes[start]
                    end_node = self.nodes[end]

                    folium.PolyLine(
                        locations=[
                            [start_node.lat, start_node.lon],
                            [end_node.lat, end_node.lon],
                        ],
                        color="#facc15",
                        weight=8,
                        opacity=0.95,
                        tooltip=f"Highlighted shortest path: {start} → {end}",
                    ).add_to(highlighted_path_group)

        # Add node markers
        for node in self.nodes.values():
            popup_html = f"""
            <div style="font-family: Arial; width: 260px;">
                <h3 style="margin-bottom: 4px;">{node.name}</h3>
                <b>Type:</b> {node.node_type}<br>
                <b>Latitude:</b> {node.lat}<br>
                <b>Longitude:</b> {node.lon}<br>
                <p style="margin-top: 8px;">{node.description}</p>
            </div>
            """

            marker = folium.Marker(
                location=[node.lat, node.lon],
                tooltip=node.name,
                popup=folium.Popup(popup_html, max_width=320),
                icon=folium.DivIcon(
                    html=self._get_marker_html(node),
                    icon_size=(28, 28),
                    icon_anchor=(14, 14),
                ),
            )

            if node.node_type == "pad":
                marker.add_to(pads_group)
            elif node.node_type == "hospital":
                marker.add_to(hospitals_group)
            elif node.node_type == "charging_hub":
                marker.add_to(charging_group)

            # Slight label offset
            folium.Marker(
                location=[node.lat + 0.002, node.lon + 0.002],
                icon=folium.DivIcon(
                    html=self._get_label_html(node),
                    icon_size=(180, 20),
                    icon_anchor=(0, 0),
                ),
            ).add_to(labels_group)

        # Add all groups
        airport_routes_group.add_to(munich_map)
        city_routes_group.add_to(munich_map)
        medical_routes_group.add_to(munich_map)
        charging_routes_group.add_to(munich_map)
        highlighted_path_group.add_to(munich_map)

        pads_group.add_to(munich_map)
        hospitals_group.add_to(munich_map)
        charging_group.add_to(munich_map)
        labels_group.add_to(munich_map)

        # Plugins
        Fullscreen(
            position="topright",
            title="Full screen",
            title_cancel="Exit full screen",
            force_separate_button=True,
        ).add_to(munich_map)

        MiniMap(
            toggle_display=True,
            minimized=True,
            position="bottomright",
        ).add_to(munich_map)

        MeasureControl(
            position="topleft",
            primary_length_unit="kilometers",
            secondary_length_unit="meters",
            primary_area_unit="sqmeters",
        ).add_to(munich_map)

        folium.LayerControl(collapsed=False).add_to(munich_map)

        stats = self.get_network_stats()

        sidebar_html = f"""
        <div style="
            position: fixed;
            top: 20px;
            left: 50px;
            z-index: 9999;
            width: 320px;
            background: rgba(255,255,255,0.96);
            padding: 16px;
            border-radius: 14px;
            border: 1px solid #d1d5db;
            box-shadow: 0 8px 24px rgba(0,0,0,0.22);
            font-family: Arial, sans-serif;
            color: #111827;
        ">
            <div style="font-size: 18px; font-weight: 800; margin-bottom: 4px;">
                Munich Airspace Digital Twin
            </div>
            <div style="font-size: 12px; color: #4b5563; margin-bottom: 12px;">
                Layer 3 shared environment for eVTOL simulation
            </div>

            <div style="
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 8px;
                margin-bottom: 12px;
            ">
                <div style="background:#eff6ff; padding:8px; border-radius:8px;">
                    <b>{stats["pads"]}</b><br><span style="font-size:12px;">Pads</span>
                </div>
                <div style="background:#fef2f2; padding:8px; border-radius:8px;">
                    <b>{stats["hospitals"]}</b><br><span style="font-size:12px;">Hospitals</span>
                </div>
                <div style="background:#f0fdf4; padding:8px; border-radius:8px;">
                    <b>{stats["charging_hubs"]}</b><br><span style="font-size:12px;">Charging Hubs</span>
                </div>
                <div style="background:#f9fafb; padding:8px; border-radius:8px;">
                    <b>{stats["total_routes"]}</b><br><span style="font-size:12px;">Air Corridors</span>
                </div>
            </div>

            <div style="font-size: 13px; line-height: 1.55;">
                <b>Legend</b><br>
                <span style="color:#1f78b4; font-weight:bold;">● P</span> Passenger / city pads<br>
                <span style="color:#e31a1c; font-weight:bold;">● H</span> Hospital landing points<br>
                <span style="color:#33a02c; font-weight:bold;">● C</span> Charging hubs<br>
                <span style="color:#6366f1;">━━</span> Airport corridor<br>
                <span style="color:#6b7280;">━━</span> City corridor<br>
                <span style="color:#ef4444;">- - -</span> Medical corridor<br>
                <span style="color:#22c55e;">- - -</span> Charging corridor<br>
                <span style="color:#facc15; font-weight:bold;">━━</span> Highlighted shortest path
            </div>

            <div style="
                margin-top: 12px;
                padding-top: 10px;
                border-top: 1px solid #e5e7eb;
                font-size: 12px;
                color: #4b5563;
            ">
                Map is restricted to the Munich + Airport operating region.
                Use layer control to hide/show corridors and labels.
            </div>
        </div>
        """

        munich_map.get_root().html.add_child(folium.Element(sidebar_html))

        title_html = """
        <div style="
            position: fixed;
            top: 20px;
            right: 70px;
            z-index: 9999;
            background: rgba(17,24,39,0.90);
            color: white;
            padding: 10px 14px;
            border-radius: 10px;
            font-family: Arial, sans-serif;
            font-size: 13px;
            box-shadow: 0 4px 14px rgba(0,0,0,0.25);
        ">
            <b>Phase 1:</b> Munich world only · No AI · No agents · No weather
        </div>
        """

        munich_map.get_root().html.add_child(folium.Element(title_html))

        munich_map.save(output_path)
        return str(output_path)