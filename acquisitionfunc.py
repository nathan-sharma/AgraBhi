# Coded by Nathan
import sys
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import matplotlib.colors as mcolors
from pykrige.ok3d import OrdinaryKriging3D
from pyproj import CRS, Transformer
import math
import pandas as pd

CSV_PATH = os.path.expanduser("~/Drone/drone_app/data.csv")

def calculate_optimal_target():
    if not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0:
        print("Optimization aborted: data.csv does not exist or is empty.")
        return None

    df = pd.read_csv(CSV_PATH)
    

    df = df[(df['Latitude'] != 0.0) & (df['Longitude'] != 0.0)]
    

    if len(df) < 3:
        print(f"Can't find the best point: Only {len(df)} points were logged. You need at least 3.")
        return None

  
    data = df[['Latitude', 'Longitude', 'Depth_cm', 'Moisture']].to_numpy()

    lat = data[:, 0] 
    lon = data[:, 1] 
    moisture = data[:, 3] 
    depth = data[:, 2] /100
    num_points = 50 

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
    gridz = np.linspace(depth.min(), depth.max(), num_points)

    ok3d = OrdinaryKriging3D(
        utm_x, 
        utm_y, 
        depth, 
        moisture, 
        anisotropy_scaling_z=500, #should be greater than 1, since z values are smaller relative to x and y values.
        variogram_model="gaussian",
    )

    k3d1, ss3d = ok3d.execute("grid", gridx, gridy, gridz)
    target_depth = 0.05
    depth_idx = int(round((target_depth- depth.min()) / ((depth.max() - depth.min()) / (num_points - 1))))
    variance_slice = ss3d[depth_idx, :, :]
    max_variance = np.max(variance_slice)
    min_variance = np.min(variance_slice)

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))

    print("All depths must be between (in centimeters) ", 100*depth.min(), " and ", 100*depth.max())
    
    # Headless configuration slicing layout
    entered_depth_1 = 5.0
    entered_depth_2 = 10.0
    entered_depth_3 = 15.0
    
    entered_depth_1 /=100
    entered_depth_2 /=100 
    entered_depth_3 /=100
    ind1 = int(round((entered_depth_1 - depth.min()) / ((depth.max() - depth.min()) / (num_points - 1))))
    ind2 = int(round((entered_depth_2 - depth.min()) / ((depth.max() - depth.min()) / (num_points - 1))))
    ind3 = int(round((entered_depth_3 - depth.min()) / ((depth.max() - depth.min()) / (num_points - 1))))
    slice_indices = [ind1, ind2, ind3]
    for i, idx in enumerate(slice_indices):
        slice_data = k3d1[idx, :, :]
        variance_slice_data = ss3d[idx, :, :]
        
        im = axes[0,i].imshow(
            slice_data, 
            extent=[gridx.min(), gridx.max(), gridy.min(), gridy.max()],
            origin='lower', 
            cmap='viridis', 
            vmin = 10.0, 
            vmax = 14.0
        )
        axes[0,i].set_title(f"Depth (Z) Slice = {gridz[idx]:.2f}")
        axes[0,i].set_xlabel("UTM Easting (meters)")
        axes[0,i].set_ylabel("UTM Northing (meters)")

        im2 = axes[1,i].imshow(
            variance_slice_data, 
            extent=[gridx.min(), gridx.max(), gridy.min(), gridy.max()],
            origin='lower', 
            cmap='inferno', 
            vmin = 0, 
            vmax = 7.0
        )
        axes[1,i].set_title(f"Uncertainty at Depth (Z) Slice = {gridz[idx]:.2f}")
        axes[1,i].set_xlabel("UTM Easting (meters)")
        axes[1,i].set_ylabel("UTM Northing (meters)")

    fig.colorbar(im, ax=axes[0, :].tolist(), label="Predicted Moisture (%)")
    fig.colorbar(im2, ax=axes[1, :].tolist(), label="GPR Variance")

    plt.savefig(os.path.expanduser("~/Drone/drone_app/optimization_plots.png"))
    plt.close(fig)

    gps_coords = data[:, :2]
    N=2
    _, unique_indices = np.unique(gps_coords, axis=0, return_index=True)
    unique_indices = np.sort(unique_indices)
    unique_utm_x = utm_x[unique_indices]
    unique_utm_y = utm_y[unique_indices]

    unique_moisture_vals = []
    for idx in unique_indices:
        lat_val = data[idx, 0]
        lon_val = data[idx, 1]
        row = np.where((data[:, 0] == lat_val) & (data[:, 1] == lon_val) & (data[:, 2] == 5))[0]
        if len(row) > 0:
            unique_moisture_vals.append(data[row[0], 3])
        else:
            unique_moisture_vals.append(data[idx, 3])
            
    unique_moisture_vals = np.array(unique_moisture_vals)

    all_grid_variances = []
    for current_y in gridy:
        for current_x in gridx:
            distances_loop = np.sqrt((unique_utm_x - current_x)**2 + (unique_utm_y - current_y)**2)
            closest_N_idx = np.argsort(distances_loop)[:N] 
            closest_moistures = unique_moisture_vals[closest_N_idx]
            if len(closest_moistures) > 1:
                grid_variance = np.var(closest_moistures, ddof=1)
            else:
                grid_variance = 0.0
            all_grid_variances.append(grid_variance)

    global_min_variance = np.min(all_grid_variances)
    global_max_variance = np.max(all_grid_variances)

    if global_max_variance == global_min_variance:
        global_max_variance += 1e-6

    home_lat = 27.59437
    home_lon = -97.89413
    home_utm_x, home_utm_y = transformer.transform(home_lon, home_lat)

    rover_location_lat = 27.59413
    rover_location_lon = -97.89429
    rover_utm_x, rover_utm_y = transformer.transform(rover_location_lon, rover_location_lat)

    field_diagonal = 38.0
    rover_battery_percentage = 80.0
    gamma = 0.0008
    target_z_value = 0.05

    _, ss3d_full = ok3d.execute("grid", gridx, gridy, np.array([target_z_value]))

    kriging_variance_grid = ss3d_full[0, :, :]

    best_acquisition = -float('inf')
    best_pixel_coords = (None, None) 
    best_grid_idx = (None, None)     
    best_rover_distance = None 
    best_home_distance = None

    for y_idx, current_y in enumerate(gridy):
        for x_idx, current_x in enumerate(gridx):
            point_variance = kriging_variance_grid[y_idx, x_idx]
            
            if (max_variance - min_variance) == 0:
                normalized_kriging_variance = 0.0
            else:
                normalized_kriging_variance = (point_variance - min_variance) / (max_variance - min_variance)
                
            distances_loop = np.sqrt((unique_utm_x - current_x)**2 + (unique_utm_y - current_y)**2)
            closest_unique_positions = np.argsort(distances_loop)[:N] 
            
            closest_moisture_values = unique_moisture_vals[closest_unique_positions]
            if len(closest_moisture_values) > 1:
                moisture_variance = np.var(closest_moisture_values, ddof=1)
            else:
                moisture_variance = 0.0
                
            normalized_moisture_variance = (moisture_variance - global_min_variance) / (global_max_variance - global_min_variance)
        
            if normalized_kriging_variance > 1.001:
                continue
            if normalized_moisture_variance > 1.001:
                normalized_moisture_variance = 1.0
                
            closest_distance_meters = distances_loop[closest_unique_positions[0]]
            squared_distance = closest_distance_meters ** 2
            rbf_kernel_value = np.exp(-gamma * squared_distance)
            
            home_distance = math.sqrt((current_x - home_utm_x)**2 + (current_y - home_utm_y)**2)
            rover_distance = math.sqrt((current_x - rover_utm_x)**2 + (current_y - rover_utm_y)**2)
            
            acquisition_value = (
                normalized_kriging_variance + 
                (normalized_moisture_variance * rbf_kernel_value) - 
                ((100 - rover_battery_percentage) / 100.0) * (rover_distance + home_distance) / (2.0 * field_diagonal)
            )
            
            if acquisition_value > best_acquisition:
                best_acquisition = acquisition_value
                best_pixel_coords = (current_x, current_y)
                best_grid_idx = (y_idx, x_idx)
                best_kriging_var = point_variance
                best_moisture_var = moisture_variance
                best_norm_kriging_var = normalized_kriging_variance
                best_norm_moisture_var = normalized_moisture_variance
                best_rbf_kernel = rbf_kernel_value
                best_rover_distance = rover_distance 
                best_home_distance = home_distance

    transformer_back = Transformer.from_crs(crs_utm, crs_wgs84, always_xy=True)
    best_lon, best_lat = transformer_back.transform(best_pixel_coords[0], best_pixel_coords[1])
    best_utm_x, best_utm_y = best_pixel_coords[0], best_pixel_coords[1]
    target_x = np.array([best_utm_x])
    target_y = np.array([best_utm_y])
    target_z = np.array(0.05)

    predicted_moisture, kriging_variance = ok3d.execute(
        "points", 
        target_x, 
        target_y, 
        target_z
    )
    point_prediction = predicted_moisture[0]

    print("This point has the highest A(x) value. Latitude " + str(best_lat) + ", Longitude " + str(best_lon))
    print("Predicted moisture (assuming depth of 5cm): " + str(point_prediction))
    print("Grid index position:  Row " + str(best_grid_idx[0]) + ", Column " + str(best_grid_idx[1]) )
    print("A(x): " + str(best_acquisition))
    print("Components of A(x): ")
    print("Kriging Variance: " + str(best_kriging_var))
    print("Normalized Kriging Variance: " + str(best_norm_kriging_var)) 
    print("Variance of " + str(N) + " closest points: " + str(best_moisture_var)) 
    print("Normalized Variance of " + str(N) + " closest points: " + str(best_norm_moisture_var)) 
    print("RBF Kernel to closest sampled point: " + str(best_rbf_kernel)) 
    print("Rover's distance to this point in meters: " + str(best_rover_distance)) 
    print("Point's distance from charging station/home in meters: " + str(best_home_distance))

    return {
        "best_lat": float(best_lat),
        "best_lon": float(best_lon),
        "predicted_moisture": float(point_prediction),
        "acquisition_value": float(best_acquisition)
    }