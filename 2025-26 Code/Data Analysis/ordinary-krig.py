#coded by Nathan
import numpy as np 
import matplotlib.pyplot as plt
from scipy.spatial.distance import cdist 
from pykrige.ok import OrdinaryKriging 
data = np.array([
    #Lat, lon, elevation, moisture
    [29.77, -95.68, 30.0, 15.2], [29.77, -95.67, 30.0, 20.5], [29.77, -95.66, 30.0, 25.8],
    [29.76, -95.68, 25.0, 45.1], [29.76, -95.67, 25.0, 50.4], [29.76, -95.66, 25.0, 55.7],
    [29.75, -95.68, 20.0, 80.3], [29.75, -95.67, 20.0, 85.6], [29.75, -95.66, 20.0, 92.1]
])
lat = data[:, 0] 
lon = data[:, 1] 
moisture = data[:, 3] 
n = len(moisture)
differences = []
print(f"{'Point':<8} | {'Actual':<8} | {'Predicted':<10} | {'Error (Diff)':<10}")
print("-" * 50) 

for i in range(n): 
    actual_value = moisture[i]
    target_lat = lat[i]
    target_lon = lon[i]
    training_lats = np.delete(lat, i, axis=0)
    training_lon = np.delete(lon, i, axis=0)
    training_moisture = np.delete(moisture, i, axis=0)
    OK_loop = OrdinaryKriging( 
    training_lon, training_lats, training_moisture, variogram_model='gaussian',  
    verbose=False, enable_plotting=False,
)
    predict, _ = OK_loop.execute('points', [target_lon], [target_lat])
    prediction = predict[0]
    diff = actual_value - prediction 
    differences.append(diff) 
    print(f"{i:<8} | {actual_value:<8.2f} | {prediction:<10.2f} | {diff:<10.2f}")
print("-" * 50) 
rmse_value = np.sqrt(np.mean(np.array(differences)**2))
mean_error = np.mean(np.array(differences))
print("RMSE score: " + str(rmse_value))
print("Mean Error: " + str(mean_error))
num_points = 200
grid_x = np.linspace(lon.min(), lon.max(), num_points)
grid_y = np.linspace(lat.min(), lat.max(), num_points)
OK_res = OrdinaryKriging( 
    lon, lat, moisture, variogram_model='linear',  
    verbose=False, enable_plotting=False,
)
z_kriged, sigmasq = OK_res.execute("grid", grid_x, grid_y)
OK_res.display_variogram_model() 

experimental_lags = OK_res.lags 
experimental_semivariances = OK_res.semivariance
params = OK_res.variogram_model_parameters
theoretical_semivariances = OK_res.variogram_function(params, experimental_lags)
residual_sum_of_squares = np.sum((experimental_semivariances - theoretical_semivariances)**2)
print(OK_res.variogram_model + " RSS score: " + str(residual_sum_of_squares))

plt.figure(figsize=(12, 9))
plt.contourf(
    grid_x, grid_y, z_kriged, 
    levels=100, cmap='YlGnBu',
)
plt.colorbar(label='Final Predicted Moisture Value')
plt.scatter(lon, lat, c=moisture, marker='o', edgecolors='black', label='Original Moisture Data')
plt.title('Ordinary Kriging Map')
plt.xlabel('Longitude')
plt.ylabel('Latitude')
plt.legend()
plt.grid(True)
plt.show()
input_lon = float(input("Enter longitude for point to be predicted: "))
input_lat = float(input("Enter latitude for point to be predicted: "))
pred, variance = OK_res.execute('points', [input_lon], [input_lat])
sigma_squared = variance[0]
sigma = np.sqrt(sigma_squared) 
prediction = pred[0] 
print("Predicted moisture value at " + str(input_lat) + "," + str(input_lon) + " is " + str(prediction) + " % GWC.")
print("Standard deviation/uncertainty: +/- " + str(sigma) + " % GWC.")
