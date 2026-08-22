
#the locations we enter manually here are simulating the locations the rovers will send to the computer 
#the computer then assigns each rover to an optimal location, minimizing total distance traveled
#the alpha weight is supposed to be 0.2 + 0.6*(current mean kriging variance)/(initial mean kriging variance), we'll code something separately later to calculate alpha for every round of calculations, for now we're using 0.4 as a placeholder

import numpy as np
from pykrige.ok import OrdinaryKriging
from pyproj import CRS, Transformer
import math
from itertools import permutations

data = np.array([
    #lat, lon, moisture
    [27.59506, -97.89397, 9],
    [27.59505, -97.89222, 7],
    [27.59572, -97.89357, 10],
    [27.59578, -97.89339, 11],
    [27.59538, -97.89216, 8],
    [27.59640, -97.89269, 18],
    [27.59469, -97.89278, 10],
    [27.59625, -97.89193, 15],
    [27.59675, -97.89415, 12],
    [27.59693, -97.89320, 13],
    [27.59577, -97.89288, 13],
    [27.59613, -97.89477, 9],
    [27.59641, -97.89375, 14],
    [27.59702, -97.89211, 15],
    [27.59593, -97.89164, 9]
])

alpha=0.4 #placeholder value
def acquisition_function(data, a=alpha, model="spherical"):

    if len(data) < 3:
        raise ValueError("Not enough points.")

    lat = data[:, 0]
    lon = data[:, 1]
    moisture = data[:, 2]
    num_points = 80

    mean_lon = np.mean(lon)
    mean_lat = np.mean(lat)
    utm_zone = int((mean_lon + 180) / 6) + 1
    hemisphere = "north" if mean_lat >= 0 else "south"
    crs_wgs84 = CRS.from_epsg(4326)
    crs_utm = CRS.from_string(f"+proj=utm +zone={utm_zone} +{hemisphere} +datum=WGS84 +units=m +no_defs")
    transformer = Transformer.from_crs(crs_wgs84, crs_utm, always_xy=True)
    utm_x, utm_y = transformer.transform(lon, lat)
    gridx = np.linspace(utm_x.min(), utm_x.max(), num_points)
    gridy = np.linspace(utm_y.min(), utm_y.max(), num_points)

    ok2d = OrdinaryKriging(
        utm_x,
        utm_y,
        moisture,
        variogram_model=model,
        verbose=False,
        enable_plotting=False
    )

    k2d_predicted, kriging_variance_grid = ok2d.execute("grid", gridx, gridy)
    mean_kriging_variance = np.mean(kriging_variance_grid)
    max_variance = np.max(kriging_variance_grid)
    min_variance = np.min(kriging_variance_grid)

    dx = gridx[1] - gridx[0]
    dy = gridy[1] - gridy[0]

    grad_y, grad_x = np.gradient(k2d_predicted, dy, dx)
    gradient_magnitude_grid = np.sqrt(grad_x**2 + grad_y**2)

    global_min_gradient = np.min(gradient_magnitude_grid)
    global_max_gradient = np.max(gradient_magnitude_grid)
    if global_max_gradient == global_min_gradient:
        global_max_gradient += 1e-6

    best_acquisition = -float('inf')
    best_pixel_coords = (None, None)

    best_components = {
        "kriging_var": 0.0,
        "moisture_gradient": 0.0,
        "battery_distance_penalty": 0.0,
        "raw_kriging_var": 0.0,
        "raw_gradient_magnitude": 0.0,
    }
    for y_idx, current_y in enumerate(gridy):
        for x_idx, current_x in enumerate(gridx):
            point_variance = kriging_variance_grid[y_idx, x_idx]

            if (max_variance - min_variance) == 0:
                normalized_kriging_variance = 0.0
            else:
                normalized_kriging_variance = (point_variance - min_variance) / (max_variance - min_variance)

            gradient_magnitude = gradient_magnitude_grid[y_idx, x_idx]

            if (global_max_gradient - global_min_gradient) == 0:
                normalized_gradient = 0.0
            else:
                normalized_gradient = (gradient_magnitude - global_min_gradient) / (global_max_gradient - global_min_gradient)
            if normalized_kriging_variance > 1.001:
                continue

            comp_kriging = normalized_kriging_variance
            comp_gradient = normalized_gradient

            acquisition_value = a * comp_kriging + (1 - a) * comp_gradient

            if acquisition_value > best_acquisition:
                best_acquisition = acquisition_value
                best_pixel_coords = (current_x, current_y)
                best_components["kriging_var"] = comp_kriging
                best_components["raw_kriging_var"] = point_variance
                best_components["moisture_gradient"] = comp_gradient
                best_components["raw_gradient_magnitude"] = gradient_magnitude

    transformer_back = Transformer.from_crs(crs_utm, crs_wgs84, always_xy=True)
    best_lon, best_lat = transformer_back.transform(best_pixel_coords[0], best_pixel_coords[1])

    target_x = np.array([best_pixel_coords[0]])
    target_y = np.array([best_pixel_coords[1]])

    predicted_moisture, _ = ok2d.execute("points", target_x, target_y)
    point_prediction = predicted_moisture[0]
    return {
        "alpha": float(a),
        "raw_kriging_var": float(best_components['raw_kriging_var']),
        "normalized_kriging_var": float(best_components['kriging_var']),
        "raw_gradient": float(best_components['raw_gradient_magnitude']),
        "normalized_gradient": float(best_components['moisture_gradient']),
        "mean_kriging_variance": float(mean_kriging_variance),
        "best_lat": float(best_lat),
        "best_lon": float(best_lon),
        "predicted_moisture": float(point_prediction),
        "acquisition_value": float(best_acquisition),
    }

def hallucinate_dataset(data, iterations=3, a=alpha, model="spherical", verbose=True):

    augmented_data = data.copy()
    results = []

    for i in range(iterations):
        result = acquisition_function(augmented_data, a=a, model=model)
        results.append(result)

        new_point = np.array([[
            result["best_lat"],
            result["best_lon"],
            result["predicted_moisture"],
        ]])
        augmented_data = np.vstack([augmented_data, new_point])

    return results, augmented_data

if __name__ == "__main__":
    results, final_data = hallucinate_dataset(data, iterations=3, a=alpha, model="spherical")

    best_lat_1, best_lon_1 = results[0]["best_lat"], results[0]["best_lon"]
    best_lat_2, best_lon_2 = results[1]["best_lat"], results[1]["best_lon"]
    best_lat_3, best_lon_3 = results[2]["best_lat"], results[2]["best_lon"]

    print(f"best_lat_1 = {best_lat_1}, best_lon_1 = {best_lon_1}")
    print(f"best_lat_2 = {best_lat_2}, best_lon_2 = {best_lon_2}")
    print(f"best_lat_3 = {best_lat_3}, best_lon_3 = {best_lon_3}")

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
 
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def get_input_coordinate(label):
    while True:
        try:
            raw = input(f"Enter {label} as 'lat, lon': ").strip()
            lat_str, lon_str = raw.split(",")
            lat, lon = float(lat_str.strip()), float(lon_str.strip())
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                print("  -> lat must be -90..90 and lon must be -180..180. Try again.")
                continue
            return lat, lon
        except ValueError:
            print("  -> Couldn't parse that. Format example: 29.76, -95.37")

def assign_points(inputs, bests):
    best_assignment = None
    best_total_distance = float("inf")
    for perm in permutations(range(len(bests))):
        total = 0
        pairing = []
        for input_idx, best_idx in enumerate(perm):
            in_lat, in_lon = inputs[input_idx]
            b_name, b_lat, b_lon = bests[best_idx]
            d = haversine_distance(in_lat, in_lon, b_lat, b_lon)
            total += d
            pairing.append((input_idx, b_name, b_lat, b_lon, d))
 
        if total < best_total_distance:
            best_total_distance = total
            best_assignment = pairing
 
    return best_assignment, best_total_distance

best_points = [
    ("best_1", best_lat_1, best_lon_1),
    ("best_2", best_lat_2, best_lon_2),
    ("best_3", best_lat_3, best_lon_3),
]

user_inputs = []
for i in range(1, 4):
    lat, lon = get_input_coordinate(f"rover {i} location")
    user_inputs.append((lat, lon))

assignment, total_distance = assign_points(user_inputs, best_points)


sorted_assignment = sorted(assignment, key=lambda x: x[0])

input_1_idx, input_1_best, input_1_best_lat, input_1_best_lon, input_1_dist = sorted_assignment[0]
input_2_idx, input_2_best, input_2_best_lat, input_2_best_lon, input_2_dist = sorted_assignment[1]
input_3_idx, input_3_best, input_3_best_lat, input_3_best_lon, input_3_dist = sorted_assignment[2]

input_1_lat, input_1_lon = user_inputs[input_1_idx]
input_2_lat, input_2_lon = user_inputs[input_2_idx]
input_3_lat, input_3_lon = user_inputs[input_3_idx]
results = acquisition_function(data, a=alpha, model="spherical")
print("Mean kriging variance right now: " + str(results['mean_kriging_variance']))
print(f"Rover 1 ({input_1_lat:.6f}, {input_1_lon:.6f})  needs to go to  ({input_1_best_lat:.6f}, {input_1_best_lon:.6f})  (distance: {input_1_dist:.1f} m)")
print(f"Rover 2 ({input_2_lat:.6f}, {input_2_lon:.6f}) needs to go to ({input_2_best_lat:.6f}, {input_2_best_lon:.6f})  (distance: {input_2_dist:.1f} m)")
print(f"Rover 3 ({input_3_lat:.6f}, {input_3_lon:.6f}) needs to go to ({input_3_best_lat:.6f}, {input_3_best_lon:.6f})  (distance: {input_3_dist:.1f} m)")