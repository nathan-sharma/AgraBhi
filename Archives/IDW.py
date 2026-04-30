#coded by Nathan
import math
import numpy as np 
import matplotlib.pyplot as plt
from scipy.spatial.distance import cdist 
measured_data = [
    # in the form lat, lon, elevation, moisture
    [29.77, -95.68, 30.0, 15.2], [29.77, -95.67, 30.0, 20.5], [29.77, -95.66, 30.0, 25.8],
    [29.76, -95.68, 25.0, 45.1], [29.76, -95.67, 25.0, 50.4], [29.76, -95.66, 25.0, 55.7],
    [29.75, -95.68, 20.0, 80.3], [29.75, -95.67, 20.0, 85.6], [29.75, -95.66, 20.0, 92.1]
]
all_latitudes = [lat for lat, lon, elev, moisture in measured_data] 
all_longnitudes = [lon for lat, lon, elev, moisture in measured_data ]
all_moisture = [moisture for lat, lon, elev, moisture in measured_data]
points_list = [[lon,lat] for lat, lon, elev, moisture in measured_data]
grid_points = np.array(points_list)
measured_data = np.array(measured_data)
coords = measured_data[:, 0:2] 
values = measured_data[:, 3] 
power_parameter = 2
n = len(values) 
differences = [] 
print(f"{'Point':<8} | {'Actual':<8} | {'Predicted':<10} | {'Error (Diff)':<10}")
print("-" * 50) 
for i in range(n): 
    target_coord = coords[i].reshape(1, 2)
    actual_value = values[i]
    training_coords = np.delete(coords, i, axis=0)
    training_values = np.delete(values, i, axis=0)
    dists = cdist(target_coord, training_coords, metric='euclidean')
    weights = 1/dists**power_parameter
    prediction = np.sum(weights*training_values)/np.sum(weights) 
    diff = actual_value - prediction 
    differences.append(diff) 
    print(f"{i:<8} | {actual_value:<8.2f} | {prediction:<10.2f} | {diff:<10.2f}")
print("-" * 50) 
rmse_value = np.sqrt(np.mean(np.array(differences)**2)) 
mean_error = np.mean(np.array(differences))
print("RMSE score: " + str(rmse_value))
print("Mean Error score: " + str(mean_error))
grid_points = np.array(points_list) 
min_moisture = min(all_moisture) 
max_moisture = max(all_moisture) 
grid_resolution = 75 
long_minimum  = min(all_longnitudes)
long_maximum = max(all_longnitudes) 
lat_minimum = min(all_latitudes) 
lat_maximum = max(all_latitudes) 
xi = np.linspace(long_minimum, long_maximum, grid_resolution)
yi = np.linspace(lat_minimum, lat_maximum, grid_resolution) 
XI, YI = np.meshgrid(xi, yi)
predicted_points = np.vstack([XI.flatten(), YI.flatten()]).T 
distances = cdist(predicted_points, grid_points, metric='euclidean')
distances[distances == 0] = 1e-14 
weights = 1/(distances**power_parameter)
moisture_values = np.array(all_moisture)
interpolated = np.sum(weights * moisture_values, axis = 1)/np.sum(weights, axis = 1)
interpolated_matrix = interpolated.reshape(grid_resolution, grid_resolution) 
plt.pcolormesh( 
    XI,
    YI,  
    interpolated_matrix, 
    cmap = 'plasma_r', 
    vmin = min_moisture, 
    vmax = max_moisture, 
)
plt.scatter ( 
    all_longnitudes, 
    all_latitudes, 
    marker = 's', 
    c = all_moisture, 
    cmap = 'plasma_r',
    s = 200, 
    vmin = min_moisture, 
    vmax = max_moisture)
plt.colorbar(label = 'Moisture') 
plt.xlabel('Longitude') 
plt.ylabel('Latitude') 
plt.title('IDW Heatmap')
plt.show() 
