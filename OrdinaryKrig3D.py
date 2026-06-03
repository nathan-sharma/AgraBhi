#Coded by Nathan
import numpy as np
from matplotlib import pyplot as plt
import matplotlib.colors as mcolors
from pykrige.ok3d import OrdinaryKriging3D
from pyproj import CRS, Transformer
import plotly.graph_objects as go

data = np.array( #this is fake data to test it. 
    
    [
        [27.59422, -97.89437, 1, 9.8],
        [27.59422, -97.89437, 5, 10.6],
        [27.59422, -97.89437, 10, 13.6],
        [27.59422, -97.89437, 15, 15],
        [27.59422, -97.89437, 20, 20],
        [27.59413, -97.89411, 1, 10.3],
[27.59413, -97.89411, 5, 11.5],
[27.59413, -97.89411, 10, 19.3],
[27.59413, -97.89411, 15, 17.3],
[27.59413, -97.89411, 20, 8.3],
 
[27.59405, -97.89453, 1, 8.4],
[27.59405, -97.89453, 5, 9.3],
[27.59405, -97.89453, 10, 11.3],
[27.59405, -97.89453, 15, 16.2],
[27.59405, -97.89453, 20, 17.3],
    ]
)

lat = data[:, 0] 
lon = data[:, 1] 
moisture = data[:, 3] 
depth = data[:, 2] /100
num_points = 50 

#scale this to UTM meters so we can safely use the distance formula
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
    variogram_model="spherical",
   
)
ok3d.display_variogram_model()

k3d1, ss3d = ok3d.execute("grid", gridx, gridy, gridz)

fig, axes = plt.subplots(2, 3, figsize=(18, 10))



print("All depths must be between (in centimeters) ", 100*depth.min(), " and ", 100*depth.max())
entered_depth_1 = float(input("Enter depth for the first slicing: "))
entered_depth_2 = float(input("Enter depth for the second slicing: "))
entered_depth_3 = float(input("Enter depth for the third slicing: "))
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

plt.show()

raw_lat = float(input("Enter latitude: "))
raw_lon = float(input("Enter longitude: "))

user_utm_x, user_utm_y = transformer.transform(raw_lon, raw_lat)

target_x = np.array([user_utm_x])
target_y = np.array([user_utm_y])
target_z = np.array(0.05) #specific depth for predicted moisture at the user inputted location

predicted_moisture, kriging_variance = ok3d.execute(
    "points", 
    target_x, 
    target_y, 
    target_z
)

point_prediction = predicted_moisture[0]
point_variance = kriging_variance[0]
point_std_dev = np.sqrt(point_variance)
print("Prediction results for inputted location:")
print("Location: Lat: " + str(raw_lat) + "Lon: " + str(raw_lon))
print("Prediction: " + str(point_prediction) + "% VWC")
print("Kriging Variance: " + str(point_variance)) 
print("Uncertainty/Standard deviation: " + str(point_std_dev) + "% VWC")
