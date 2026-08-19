import numpy as np
from pykrige.ok import OrdinaryKriging 
from pyproj import CRS, Transformer

data = np.array([
    #lat, lon, depth, moisture
    [27.59506, -97.89397, 5,  9],
    [27.59505, -97.89222, 5,  7],
    [27.59572, -97.89357, 5, 10],
    [27.59578, -97.89339, 5, 11],
    [27.59538, -97.89216, 5,  8],
    [27.59640, -97.89269, 5, 18],
    [27.59469, -97.89278, 5, 10],
    [27.59625, -97.89193, 5, 15],
    [27.59675, -97.89415, 5, 12],
    [27.59693, -97.89320, 5, 13],
    [27.59577, -97.89288, 5, 13],
    [27.59613, -97.89477, 5,  9],
    [27.59641, -97.89375, 5, 14],
    [27.59702, -97.89211, 5, 15],
    [27.59593, -97.89164, 5,  9]
])

def acquisition_function(data, a=0.8, model="gaussian"):
    
    if len(data) < 3:
        raise ValueError("Not enough points.")

    lat = data[:, 0] 
    lon = data[:, 1] 
    moisture = data[:, 3] 
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
    print(f"Best Point (Lat: {best_lat}, Lon: {best_lon})")
    print(f"  1. Kriging Variance:         {best_components['kriging_var']:.4f}")
    print(f"  2.  Moisture gradient (raw):       {best_components['raw_gradient_magnitude']:.4f}")
    print(f"   3. Kriging Variane (raw):       {best_components['raw_kriging_var']:.4f}")
    print(f"   4. Normalized gradient       {best_components['moisture_gradient']:.4f}")
    print(f" Total:                {best_acquisition:.4f}")

    return {
        "best_lat": float(best_lat),
        "best_lon": float(best_lon),
        "predicted_moisture": float(point_prediction),
        "acquisition_value": float(best_acquisition),
        "mean_kriging_variance": float(mean_kriging_variance), 
    }

results = acquisition_function(data, a=0.8, model="spherical")

print(results)
