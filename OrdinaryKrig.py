from pyproj import CRS, Transformer
import matplotlib.pyplot as plt
import numpy as np

import pykrige.kriging_tools as kt
from pykrige.ok import OrdinaryKriging

data = np.array(
    [
#we'll paste our farm data in here

]

    
)
num_points = 80
depth = int(input("Enter a depth to see the heatmap for: "))
condition = (data[:, 3] == depth)
filtered_data = data[condition]
lat = filtered_data[:,1]
lon = filtered_data[:,2]
moisture = filtered_data[:,4]
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

OK = OrdinaryKriging(
   utm_x, 
   utm_y, 
   moisture,
    variogram_model="gaussian",
    verbose=False,
    enable_plotting=True,
)



z, ss = OK.execute("grid", gridx, gridy)

raw_lat = float(input("Enter latitude: "))
raw_lon = float(input("Enter longitude: "))

user_utm_x, user_utm_y = transformer.transform(raw_lon, raw_lat)

target_x = np.array([user_utm_x])
target_y = np.array([user_utm_y])

predicted_moisture, kriging_variance = OK.execute(
    "points", 
    target_x, 
    target_y
)

print("Predicted moisture: " + str(predicted_moisture))
print("Kriging variance: " + str(kriging_variance))
plt.imshow(z, extent=[gridx.min(), gridx.max(), gridy.min(), gridy.max()], origin='lower', cmap='viridis')


plt.colorbar(label='Moisture (%)')
plt.xlabel('UTM X (m)')
plt.ylabel('UTM Y (m)')
plt.title('Moisture Heatmap via Ordinary Kriging')

plt.show()
