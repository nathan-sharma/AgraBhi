#coded by Nathan
#for diff model edit all fields marked with change
import numpy as np 
import matplotlib.pyplot as plt
from scipy.spatial.distance import cdist 
from pykrige.ok import OrdinaryKriging 
import regression 
from regression import spatial_residuals_linear, spatial_residuals_quadratic, spatial_residuals_cubic, spatial_residuals_log, spatial_residuals_exp, coefficients_linear, coefficients_quadratic, coefficients_cubic, x, y, a_log, b_log, a_exp, b_exp, measured_data
data = spatial_residuals_linear #change
lat, lon, z = data[:, 0], data[:, 1], data[:, 2] # Y, X, and Residual z
elevation = measured_data[:, 2]
n = len(z)
num_points = 200
grid_x = np.linspace(lon.min(), lon.max(), num_points)
grid_y = np.linspace(lat.min(), lat.max(), num_points)
OK_res = OrdinaryKriging( 
    lon, lat, z, variogram_model='spherical',  
    verbose=False, enable_plotting=False
)
z_kriged, _ = OK_res.execute("grid", grid_x, grid_y)
def cubic_trend(x_val):
    a, b, c, d = coefficients_cubic
    return a * x_val**3 + b * x_val**2 + c * x_val + d
def linear_trend(x_val):
    a, b = coefficients_linear
    return a * x_val + b
def quadratic_trend(x_val): 
    a, b, c = coefficients_quadratic 
    return a * x_val**2 + b * x_val + c 
def log_trend(x_val): 
    return a_log * np.log(x_val) + b_log 
def exp_trend(x_val): 
    return a_exp * np.exp(x * b_exp)

linear_trend_1D = linear_trend(x) 
quadratic_trend_1D = quadratic_trend(x)
cubic_trend_1D = cubic_trend(x)
log_trend_1D = log_trend(x) 
exp_trend_1D = exp_trend(x) 

trend_OK = OrdinaryKriging(
    lon, lat, linear_trend_1D, #change 
    variogram_model='spherical', nlags=5
)
cubic_trend_kriged, _ = trend_OK.execute("grid", grid_x, grid_y)

final_map = cubic_trend_kriged + z_kriged

map_min, map_max = final_map.min(), final_map.max()
moisture = measured_data[:, 3] 
differences = []
for i in range(n): 
    actual_value = moisture[i]
    target_lat = lat[i]
    target_lon = lon[i]
    target_elevation = elevation[i]
    training_lats = np.delete(lat, i, axis=0)
    training_lon = np.delete(lon, i, axis=0)
    training_residuals = np.delete(z, i, axis=0)
    current_residual = actual_value - linear_trend(target_elevation)
    OK_loop = OrdinaryKriging( 
    training_lon, training_lats, training_residuals, variogram_model='gaussian',  
    verbose=False, enable_plotting=False,
)
    residual_pred, _ = OK_loop.execute('points', [target_lon], [target_lat])
    prediction = residual_pred[0] + linear_trend(target_elevation) #change
    diff = actual_value - prediction 
    differences.append(diff) 
    print(f"{i:<8} | {actual_value:<8.2f} | {prediction:<10.2f} | {diff:<10.2f}")
print("-" * 50) 
rmse_value = np.sqrt(np.mean(np.array(differences)**2)) 
mean_error = np.mean(np.array(differences))
print("RMSE score: " + str(rmse_value))
print("Mean Error: " + str(mean_error))
plt.figure(figsize=(10, 8))
plt.contourf(
    grid_x, grid_y, final_map, 
    levels=100, cmap='YlGnBu', 
    vmin=map_min, vmax=map_max
)
plt.colorbar(label='Final Predicted Moisture Value')
plt.scatter(lon, lat, c=y, marker='o', edgecolors='black', label='Original Moisture Data')
plt.title('Final Regression Kriging Map')
plt.xlabel('Longitude')
plt.ylabel('Latitude')
plt.legend()
plt.grid(True)
plt.show()
input_lon = float(input("Enter longitude for point to be predicted: "))
input_lat = float(input("Enter latitude for point to be predicted: "))
input_elev = float(input("Enter elevation in meters for point to be predicted: "))

OK_input = OrdinaryKriging( 
    lon, lat, z, variogram_model='linear',  
    verbose=False, enable_plotting=False,
)
residual_pred, residual_variance = OK_input.execute('points', [input_lon], [input_lat])

sigma_squared = residual_variance[0]
sigma = np.sqrt(sigma_squared) 

prediction = residual_pred[0] + linear_trend(input_elev) #change
print("Predicted moisture value at " + str(input_lat) + "," + str(input_lon) + " with " + str(input_elev) + " m elevation is " + str(prediction) + " % GWC.")
print("Standard deviation/uncertainty: +/- " + str(sigma) + " % GWC.")




