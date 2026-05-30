#Coded by Nathan
import numpy as np
from matplotlib import pyplot as plt
import matplotlib.colors as mcolors
from pykrige.ok3d import OrdinaryKriging3D
from pyproj import CRS, Transformer
import plotly.graph_objects as go

data = np.array( #this is fake data to test it. ALSO, get data at every centimeter, dont do increments of 5 bc then its too uncertain
    
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
depth = data[:, 2] 
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


#z scale of 10, this means moisture vertically changes 10 times faster than horizontally 
ok3d = OrdinaryKriging3D(
    utm_x, 
    utm_y, 
    depth, 
    moisture, 
    anisotropy_scaling_z=10,
    variogram_model="exponential",
   
)
ok3d.display_variogram_model()

k3d1, ss3d = ok3d.execute("grid", gridx, gridy, gridz)

zg, yg, xg = np.meshgrid(gridz, gridy, gridx, indexing="ij")
fig, axes = plt.subplots(2, 3, figsize=(18, 10))



print("All depths must be between (in centimeters) ", depth.min(), " and ", depth.max())
entered_depth_1 = float(input("Enter depth for the first slicing: "))
entered_depth_2 = float(input("Enter depth for the second slicing: "))
entered_depth_3 = float(input("Enter depth for the third slicing: "))
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
        cmap='viridis'
    )
    axes[0,i].set_title(f"Depth (Z) Slice = {gridz[idx]:.2f}")
    axes[0,i].set_xlabel("UTM Easting (meters)")
    axes[0,i].set_ylabel("UTM Northing (meters)")

    im2 = axes[1,i].imshow(
        variance_slice_data, 
        extent=[gridx.min(), gridx.max(), gridy.min(), gridy.max()],
        origin='lower', 
        cmap='inferno'
    )
    axes[1,i].set_title(f"Uncertainty at Depth (Z) Slice = {gridz[idx]:.2f}")
    axes[1,i].set_xlabel("UTM Easting (meters)")
    axes[1,i].set_ylabel("UTM Northing (meters)")

fig.colorbar(im, ax=axes[0, :].tolist(), label="Predicted Moisture (%)")
fig.colorbar(im2, ax=axes[1, :].tolist(), label="GPR Variance")

plt.show()

#this is plotting the entire 3d cube

print("\nGenerating stylized interactive 3D volumetric plot...")


zg_mesh, yg_mesh, xg_mesh = np.meshgrid(gridz, gridy, gridx, indexing="ij")

x_flat = xg_mesh.flatten()
y_flat = yg_mesh.flatten()
z_flat = zg_mesh.flatten()  
values_flat = k3d1.flatten()

fig_3d = go.Figure()

fig_3d.add_trace(
    go.Volume(
        x=x_flat,
        y=y_flat,
        z=z_flat,
        value=values_flat,
        isomin=values_flat.min(),
        isomax=values_flat.max(),
        opacity=0.7,
        surface_count=45,
        colorscale="Turbo",
        caps=dict(
            x_show=False,
            y_show=False,
            z_show=False
        ),
        colorbar=dict(title="Soil Moisture (%)")
    )
)


fig_3d.add_trace(
    go.Scatter3d(
        x=utm_x,
        y=utm_y,
        z=depth,
        mode="markers",
        marker=dict(
            size=4,
            color=moisture,
            colorscale="Turbo",
            line=dict(color='black', width=1)  
        ),
        name="Samples"
    )
)
fig_3d.update_layout(
    title="3D Moisture Simulation",
    autosize=True,
    scene=dict(
        domain=dict(
            x=[0, 1],
            y=[0, 1]
        ),
        xaxis=dict(
            visible=False,
            range=[utm_x.min(), utm_x.max()]
        ),
        yaxis=dict(
            visible=False,
            range=[utm_y.min(), utm_y.max()]
        ),
        zaxis=dict(
            title="Depth (m)",
            autorange="reversed", 
            range=[depth.max(), depth.min()]
        ),
        aspectmode="manual",
        aspectratio=dict(
            x=1,
            y=1,
            z=0.45
        ),
        bgcolor="rgb(92,64,51)",
        camera=dict(
            center=dict(
                x=0,
                y=0,
                z=0
            ),
            eye=dict(
                x=1.45,
                y=1.45,
                z=0.9
            ),
            up=dict(
                x=0,
                y=0,
                z=1
            ),
            projection=dict(
                type="perspective"
            )
        )
    ),
    paper_bgcolor="rgb(92,64,51)",
    plot_bgcolor="rgb(92,64,51)",
    font=dict(color="white"),
    margin=dict(
        l=0,
        r=0,
        t=60,
        b=0
    ),
    width=1400,
    height=900
)
fig_3d.show()

raw_lat = float(input("Enter latitude: "))
raw_lon = float(input("Enter longitude: "))

user_utm_x, user_utm_y = transformer.transform(raw_lon, raw_lat)

target_x = np.array([user_utm_x])
target_y = np.array([user_utm_y])
target_z = np.array([depth.min()])

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