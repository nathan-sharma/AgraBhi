import sys
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import matplotlib.colors as  mcolors
from pykrige.ok import OrdinaryKriging  
from pyproj import CRS, Transformer
import math
import pandas as pd

CSV_PATH = os.path.expanduser("~/Drone/drone_app/data.csv")

def _execute_optimization_math(data_matrix, battery_pct, rover_pos_lat, rover_pos_lon, a=0.8, model="gaussian"):
    mask_5cm = (data_matrix[:, 2] == 5)
    filtered_data = data_matrix[mask_5cm]
    if len(filtered_data) < 3:
        raise ValueError("Cannot calculate 2D Kriging: Less than 3 data points found at 5cm depth.")

    lat = filtered_data[:, 0] 
    lon = filtered_data[:, 1] 
    moisture = filtered_data[:, 3] 
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

    _, unique_idx = np.unique(filtered_data[:, :2], axis=0, return_index=True)
    clean_5cm_data = filtered_data[unique_idx]

    unique_utm_x, unique_utm_y = transformer.transform(clean_5cm_data[:, 1], clean_5cm_data[:, 0])
    unique_moisture_vals = clean_5cm_data[:, 3]

    dx = gridx[1] - gridx[0]
    dy = gridy[1] - gridy[0]
    
    grad_y, grad_x = np.gradient(k2d_predicted, dy, dx)
    gradient_magnitude_grid = np.sqrt(grad_x**2 + grad_y**2)

    global_min_gradient = np.min(gradient_magnitude_grid)
    global_max_gradient = np.max(gradient_magnitude_grid)
    if global_max_gradient == global_min_gradient:
        global_max_gradient += 1e-6

    home_lat = 27.59496
    home_lon = -97.89311
    home_utm_x, home_utm_y = transformer.transform(home_lon, home_lat)

    rover_utm_x, rover_utm_y = transformer.transform(rover_pos_lon, rover_pos_lat)

    field_diagonal = 275
    gamma = 0.000024 

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

            acquisition_value = a*comp_kriging + (1-a)*comp_gradient
            
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
    try:
        empirical_lags = ok2d.lags.tolist()
        empirical_variances = ok2d.variogram_values.tolist()
    except Exception:
        empirical_lags = []
        empirical_variances = []
    print("\n" + "="*60)
    print(f"Best Point (Lat: {best_lat}, Lon: {best_lon}) [2D - 5cm Mode]")
    print(f"  1. Normalized Kriging Variance:         {best_components['kriging_var']:.4f}")
    print(f"  2. Gradient raw:      {best_components['raw_gradient_magnitude']:.4f}")
    print(f"   3. Kriging variance raw:     {best_components['raw_kriging_var']:.4f}")
    print(f"   4. Normalized gradient:     {best_components['moisture_gradient']:.4f}")
    print(f"  A(x,y):                {best_acquisition:.4f}")

    return {
        "best_lat": float(best_lat),
        "best_lon": float(best_lon),
        "predicted_moisture": float(point_prediction),
        "acquisition_value": float(best_acquisition),
        "mean_kriging_variance": float(mean_kriging_variance), 
        "variogram_lags": empirical_lags,
        "variogram_values": empirical_variances
    }

def calculate_optimal_target(battery_pct=100.0, a=0.8, model="gaussian"): 
    if not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0:
        print("Optimization aborted: data.csv does not exist or is empty.")
        return None

    df = pd.read_csv(CSV_PATH)
    df = df[(df['Latitude'] != 0.0) & (df['Longitude'] != 0.0)]
    
    df_5cm = df[df['Depth_cm'] == 5]
    if len(df_5cm) < 3:
        print(f"Can't find the best point: Only {len(df_5cm)} valid GPS point(s) logged at 5cm depth. Need at least 3.")
        return None

    data = df[['Latitude', 'Longitude', 'Depth_cm', 'Moisture']].to_numpy()
    rover_location_lat = 27.59413
    rover_location_lon = -97.89429
    return _execute_optimization_math(data, battery_pct, rover_location_lat, rover_location_lon, a=a, model=model)

def calculate_swarm_targets(swarm_state_list, a=0.8, model="gaussian"):
    if not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0:
        return None

    df = pd.read_csv(CSV_PATH)
    df = df[(df['Latitude'] != 0.0) & (df['Longitude'] != 0.0)]
    
    df_5cm = df[df['Depth_cm'] == 5]
    if len(df_5cm) < 3:
        return None
    running_data = df[['Latitude', 'Longitude', 'Depth_cm', 'Moisture']].to_numpy()
    calculated_assignments = {}

    for rover_id, state in swarm_state_list.items():
        try:
            res = _execute_optimization_math(
                data_matrix=running_data,
                battery_pct=state["battery"],
                rover_pos_lat=state["lat"],
                rover_pos_lon=state["lon"], 
                a=a, 
                model=model
            )
        except ValueError:
            return None
        
        assigned_lat = res["best_lat"]
        assigned_lon = res["best_lon"]
        simulated_moisture = res["predicted_moisture"]
        
        calculated_assignments[rover_id] = {
            "target_lat": assigned_lat,
            "target_lon": assigned_lon,
            "predicted_moisture": simulated_moisture,
            "acquisition_value": res["acquisition_value"], 
            "mean_kriging_variance": res["mean_kriging_variance"], 
            "variogram_lags": res.get("variogram_lags", []),
            "variogram_values": res.get("variogram_values", [])
        }
        
        simulated_measurement_row = np.array([[assigned_lat, assigned_lon, 5, simulated_moisture]])
        running_data = np.vstack([running_data, simulated_measurement_row])
        
    return calculated_assignments

def predict_moisture_at_location(target_lat, target_lon, target_depth_cm=5.0, variogram_model="gaussian"):
    if target_depth_cm != 5.0:
        return None

    if not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0:
        return None
    df = pd.read_csv(CSV_PATH)
    df = df[(df['Latitude'] != 0.0) & (df['Longitude'] != 0.0)]
    
    df_5cm = df[df['Depth_cm'] == 5]
    if len(df_5cm) < 3:
        return None

    data = df_5cm[['Latitude', 'Longitude', 'Depth_cm', 'Moisture']].to_numpy()
    lat = data[:, 0] 
    lon = data[:, 1] 
    moisture = data[:, 3] 

    mean_lon = np.mean(lon)
    mean_lat = np.mean(lat)
    utm_zone = int((mean_lon + 180) / 6) + 1
    hemisphere = "north" if mean_lat >= 0 else "south"
    
    crs_wgs84 = CRS.from_epsg(4326)
    crs_utm = CRS.from_string(f"+proj=utm +zone={utm_zone} +{hemisphere} +datum=WGS84 +units=m +no_defs")
    transformer = Transformer.from_crs(crs_wgs84, crs_utm, always_xy=True)
    utm_x, utm_y = transformer.transform(lon, lat)

    ok2d = OrdinaryKriging(utm_x, utm_y, moisture, variogram_model=variogram_model, verbose=False, enable_plotting=False)
    target_utm_x, target_utm_y = transformer.transform(target_lon, target_lat)

    try:
        predicted_moisture, _ = ok2d.execute("points", np.array([target_utm_x]), np.array([target_utm_y]))
        return float(predicted_moisture[0])
    except Exception:
        return None
