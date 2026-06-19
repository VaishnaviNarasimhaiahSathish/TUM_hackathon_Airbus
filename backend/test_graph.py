from graph import MunichAirspaceDigitalTwin


def print_section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main():
    print_section("BUILDING MUNICH AIRSPACE DIGITAL TWIN")

    twin = MunichAirspaceDigitalTwin()
    twin.build_world()

    stats = twin.get_network_stats()

    print("Digital twin created successfully.")
    print(f"Total nodes: {stats['total_nodes']}")
    print(f"Pads: {stats['pads']}")
    print(f"Hospitals: {stats['hospitals']}")
    print(f"Charging hubs: {stats['charging_hubs']}")
    print(f"Air corridors: {stats['total_routes']}")

    print_section("LOCATIONS")

    for node in twin.nodes.values():
        print(
            f"{node.id:02d}. {node.name} | "
            f"type={node.node_type} | "
            f"lat={node.lat}, lon={node.lon}"
        )

    print_section("AIR CORRIDORS")

    for route in twin.routes:
        print(
            f"{route.start} <--> {route.end} | "
            f"type={route.route_type} | "
            f"distance={route.distance} km"
        )

    print_section("SAMPLE SHORTEST PATHS")

    sample_queries = [
        ("Munich Airport", "TUM Klinikum Rechts der Isar"),
        ("Allianz Arena", "München Klinik Neuperlach"),
        ("Munich Central Station (Hauptbahnhof)", "Großhadern Clinic"),
        ("Marienplatz", "Charging Hub D - Großhadern Zone"),
    ]

    highlighted_path = None

    for index, (start, end) in enumerate(sample_queries, start=1):
        path, distance = twin.find_shortest_path(start, end)

        print(f"\nQuery {index}")
        print(f"From: {start}")
        print(f"To:   {end}")
        print(f"Path: {' -> '.join(path)}")
        print(f"Total air distance: {distance} km")

        if index == 1:
            highlighted_path = path

    print_section("EXPORTING WORLD JSON")

    twin.export_world_json()
    print("world.json created at: backend/world.json")

    print_section("CREATING RICH INTERACTIVE MAP")

    map_file = twin.create_interactive_map(
        filename="backend/munich_airspace_map.html",
        highlight_path=highlighted_path,
    )

    print(f"Map created at: {map_file}")
    print("Open backend/munich_airspace_map.html in your browser.")

    print_section("DONE")


if __name__ == "__main__":
    main()