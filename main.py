from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import pandas as pd
import googlemaps
import polyline
import folium
from datetime import datetime, timedelta, timezone

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
# Set up templates directory
templates = Jinja2Templates(directory="templates")

# Replace 'your_api_key' with your actual Google Maps API key
api_key = "AIzaSyAhfFedPc7NN9KKJxFXW6LpPQAfMJ2Obbg"
gmaps = googlemaps.Client(key=api_key)

# Define Indian Standard Time (IST) timezone
ist_timezone = timezone(timedelta(hours=5, minutes=30))

# Sample Python list for dropdown options
df = pd.read_csv("/Users/dicksonborges/Desktop/EG/fastapi/waypointss.csv")
destinations_list = pd.Series(df["waypoints"]).tolist()


# Function to calculate the midpoint of a list of coordinates
def calculate_midpoint(coordinates):
    latitudes = [coord[0] for coord in coordinates]
    longitudes = [coord[1] for coord in coordinates]
    return sum(latitudes) / len(coordinates), sum(longitudes) / len(coordinates)


# Function to calculate the arrival time considering driving limits and wait time
def calculate_arrival_time(start_time, driving_time):
    max_daily_driving_hours = 9
    rest_break_hours = 11
    end_time = start_time + timedelta(hours=float(driving_time))

    # Check if a rest break is needed
    if end_time.hour >= 21:
        end_time += timedelta(hours=11)  # Add 11 hours for a rest break

    return end_time


# Function to check if a route has sharp turns
def has_sharp_turns(route):
    for leg in route["legs"]:
        for step in leg["steps"]:
            if "maneuver" in step and "turn_type" in step["maneuver"]:
                turn_type = step["maneuver"]["turn_type"]
                if turn_type == "sharp_right" or turn_type == "sharp_left":
                    return True
    return False


# Function to generate and save a map with routes
def generate_and_save_map(start_location, end_location, waypoints):
    try:
        df = pd.read_csv("/Users/dicksonborges/Desktop/EG/fastapi/waypointss.csv")

        # Get coordinates for start location, end location, and waypoints
        start_coords = df[df["waypoints"] == start_location][
            ["Latitude", "Longitude"]
        ].values[0]
        end_coords = df[df["waypoints"] == end_location][
            ["Latitude", "Longitude"]
        ].values[0]
        waypoint_coords = [
            df[df["waypoints"] == wp][["Latitude", "Longitude"]].values[0]
            for wp in waypoints
        ]

        reordered_waypoints = [start_location] + [end_location] + waypoints

        # Request multiple routes for trucks
        directions_results = gmaps.directions(
            start_coords,
            end_coords,
            mode="driving",
            waypoints=[
                df[df["waypoints"] == wp][["Latitude", "Longitude"]].values[0]
                for wp in reordered_waypoints
            ],
            alternatives=True,
            avoid="narrow roads,tertiary,residential",
            departure_time="now",
        )

        # Create a Folium map centered around the starting location
        map_center = start_coords
        my_map = folium.Map(location=[map_center[0], map_center[1]], zoom_start=5)

        # Plot all waypoints on the map
        for waypoint, coord in zip(waypoints, waypoint_coords):
            folium.Marker(
                location=[coord[0], coord[1]],
                popup=waypoint,
                icon=folium.Icon(color="green"),
            ).add_to(my_map)

        # Print and plot routes
        if directions_results and len(directions_results) > 0:
            for i, route in enumerate(directions_results):
                route_coordinates = []

                for leg in route["legs"]:
                    for step in leg["steps"]:
                        route_coordinates.extend(
                            polyline.decode(step["polyline"]["points"])
                        )

                # Check for sharp turns in the route
                has_sharp = has_sharp_turns(route)

                # Calculate total distance for each route
                total_distance = route["legs"][0]["distance"]["text"]
                expected_duration = (
                    route["legs"][0]["duration"]["value"] / 3600
                )  # Convert seconds to hours

                print(f"Route {i + 1}: {total_distance}")

                if has_sharp:
                    print("Route has sharp turns.")

                # Calculate arrival time considering driving limits
                current_time = datetime.now(ist_timezone)
                arrival_time = calculate_arrival_time(current_time, expected_duration)

                # Find the midpoint of the route
                midpoint_location = calculate_midpoint(route_coordinates)

                # Add a PolyLine for each truck route
                folium.PolyLine(
                    locations=route_coordinates, color="blue", weight=5, opacity=1
                ).add_to(my_map)

                # Add a text label with the route number to the starting location
                folium.Marker(
                    location=[start_coords[0], start_coords[1]],
                    popup=f"Route {i + 1} - Start",
                    icon=folium.Icon(color="red"),
                ).add_to(my_map)

                # Print and plot ETA for each waypoint (excluding the start)
                eta_info = []
                for wp, wp_coord in zip(waypoints, waypoint_coords):
                    wp_distance = (
                        gmaps.distance_matrix([midpoint_location], [wp_coord])["rows"][
                            0
                        ]["elements"][0]["duration"]["value"]
                        / 3600
                    )
                    wp_eta = calculate_arrival_time(
                        arrival_time, wp_distance
                    )  # 5 minutes wait time

                    eta_info.append(
                        {"waypoint": wp, "eta": wp_eta.strftime("%Y-%m-%d %H:%M:%S")}
                    )

                    print(
                        f"Estimated Arrival Time at {wp}: {wp_eta.strftime('%Y-%m-%d %H:%M:%S')}"
                    )

                    folium.Marker(
                        location=[wp_coord[0], wp_coord[1]],
                        popup=f'ETA at {wp}: {wp_eta.strftime("%A, %B %d, %Y %I:%M %p")}',
                        icon=folium.Icon(color="green"),
                    ).add_to(my_map)

                    # Update arrival time for the next waypoint
                    arrival_time = wp_eta

                # Add markers for the ending locations
                folium.Marker(
                    location=[end_coords[0], end_coords[1]], popup="pickup"
                ).add_to(my_map)
                folium.Marker(
                    location=[start_coords[0], start_coords[1]], popup="Start"
                ).add_to(my_map)

        # Save the map as an HTML file or display it
        map_file_path = "./templates/map_with_routes.html"
        my_map.save(map_file_path)

        # For demonstration, you can print the values
        print(
            f"Start Location: {start_location}, End Location: {end_location}, Waypoints: {waypoints}"
        )

        return map_file_path, eta_info

    except Exception as e:
        print(f"Error: {e}")
        return None, None


# Define root path to render the form
@app.get("/", response_class=HTMLResponse)
async def read_form(request: Request):
    return templates.TemplateResponse(
        "index.html", {"request": request, "destinations_list": destinations_list}
    )


@app.post("/process_form")
async def process_form(
    start_location: str = Form(...),
    end_location: str = Form(...),
    num_destinations: int = Form(...),
    destinations: list = Form(...),
):
    map_file_path, eta_info = generate_and_save_map(
        start_location, end_location, destinations
    )
    if map_file_path:
        return FileResponse(map_file_path)
    else:
        return {
            "error": "Error generating map. Check Google Maps API key and input locations."
        }
