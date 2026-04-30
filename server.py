import serial, pynmea2, time, os, math
from flask import Flask, render_template, jsonify
logged_data_list = []
import requests
import RPi.GPIO as GPIO
import threading
from flask import Flask, render_template, jsonify, request, send_file
app = Flask(__name__)
import json
from flask_cors import CORS
CORS(app)
#import changes started here 4/11
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pykrige.ok import OrdinaryKriging
from pyproj import Transformer
import io
import base64

# --- State Management ---
current_latitude = "N/A"
current_longitude = "N/A"
current_moisture = "N/A"
sample_ID = 0
last_lat = None
last_lon = None 
landing_event_flag = False
SPRINKLER_FILE = "sprinklers.json"
points = []  # For history in session

try:
    serMoisture = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
    serGps = serial.Serial('/dev/ttyAMA0', 115200, timeout=1)
except Exception as e:
    print(f"Serial Error: {e}")
    serMoisture = serGps = None


def load_sprinklers():
    if os.path.exists(SPRINKLER_FILE):
        with open(SPRINKLER_FILE, 'r') as f:
            return json.load(f)
    return []


def save_sprinklers(data):
    with open(SPRINKLER_FILE, 'w') as f:
        json.dump(data, f)


# --- New Routes ---
@app.route("/heatmap_page")
def heatmap_page():
    return render_template("heatmap.html")

#4/11 change started here
@app.route("/heatmap", methods=["POST"])
def generate_heatmap():
    try:
        import pandas as pd
        import numpy as np
        import matplotlib.pyplot as plt
        from pykrige.ok import OrdinaryKriging
        from pyproj import Transformer
        import io, base64, os

        csv_path = os.path.expanduser("~/Drone/drone_app/data.csv")
        if not os.path.exists(csv_path):
            return jsonify({"error": "No data file found"})

        df = pd.read_csv(csv_path)
        sprinklers = load_sprinklers()
        
        body = request.get_json(force=True, silent=True) or {}
        reg_type = body.get("regression", "cubic")
        var_type = body.get("variogram", "spherical")
        uncertainty_mode = body.get("uncertainty_mode", "kriging_only")


        # 1. Load Data & Mask
        lat = pd.to_numeric(df[df.columns[1]], errors="coerce")
        lon = pd.to_numeric(df[df.columns[2]], errors="coerce")
        moisture = pd.to_numeric(df[df.columns[3]], errors="coerce")
        spr_dist_recorded = pd.to_numeric(df[df.columns[7]], errors="coerce")

        mask = (~np.isnan(lat) & ~np.isnan(lon) & ~np.isnan(moisture) & ~np.isnan(spr_dist_recorded))
        lat, lon, moisture, spr_dist_recorded = lat[mask].values, lon[mask].values, moisture[mask].values, spr_dist_recorded[mask].values

        # 2. Regression Trend
        reg_map = {"linear": 1, "quadratic": 2, "cubic": 3}
        deg = reg_map.get(reg_type, 3)
        coeffs = np.polyfit(spr_dist_recorded, moisture, deg)
        trend = np.polyval(coeffs, spr_dist_recorded)
        residuals = moisture - trend

        # --- REGRESSION PLOT ---
        plt.figure()
        plt.scatter(spr_dist_recorded, moisture, s=10)
        x_line = np.linspace(np.min(spr_dist_recorded), np.max(spr_dist_recorded), 100)
        plt.plot(x_line, np.polyval(coeffs, x_line), color="red")
        plt.title("Moisture vs Sprinkler Distance")
        plt.xlabel("Distance")
        plt.ylabel("Moisture")
        buf1 = io.BytesIO()
        plt.savefig(buf1, format="png", bbox_inches="tight")
        buf1.seek(0)
        reg_img = base64.b64encode(buf1.read()).decode()
        plt.close()

        # 3. Coordinate Transform & Kriging
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32615", always_xy=True)
        x_m, y_m = transformer.transform(lon, lat)
        
        OK = OrdinaryKriging(x_m, y_m, residuals, variogram_model=var_type, nlags=6, verbose=False, enable_plotting=False)
        
        grid_x = np.linspace(lon.min(), lon.max(), 100)
        grid_y = np.linspace(lat.min(), lat.max(), 100)
        z, ss = OK.execute("grid", grid_x, grid_y)
        #uncertainty = np.sqrt(np.nan_to_num(ss))
        kriging_uncertainty = np.sqrt(np.nan_to_num(ss))

        # 4. PIXEL-LEVEL TREND (Calculated against all sprinklers)
        grid_lon, grid_lat = np.meshgrid(grid_x, grid_y)
        grid_x_m, grid_y_m = transformer.transform(grid_lon, grid_lat)
        spr_coords_m = [transformer.transform(s['lon'], s['lat']) for s in sprinklers]
# --- DISTANCE TO NEAREST SAMPLED POINT (NOT SPRINKLER) ---
        sample_coords_m = list(zip(x_m, y_m))

        grid_dist_to_sample = np.zeros_like(grid_x_m)

        for i in range(grid_x_m.shape[0]):
            for j in range(grid_x_m.shape[1]):
                px, py = grid_x_m[i, j], grid_y_m[i, j]

                if sample_coords_m:
                    dists = [np.sqrt((px - sx)**2 + (py - sy)**2) for sx, sy in sample_coords_m]
                    grid_dist_to_sample[i, j] = min(dists)
                else:
                    grid_dist_to_sample[i, j] = 0


        grid_dist_to_closest = np.zeros_like(grid_x_m)
        for i in range(grid_x_m.shape[0]):
            for j in range(grid_x_m.shape[1]):
                px, py = grid_x_m[i, j], grid_y_m[i, j]
                dists = [np.sqrt((px - sx)**2 + (py - sy)**2) for sx, sy in spr_coords_m]
                grid_dist_to_closest[i, j] = min(dists) if dists else 0

        final_map = z + np.polyval(coeffs, grid_dist_to_closest)

        # 5. VARIOGRAM PLOT & RSS (Restored Full Logic)
        dists, semivars = [], []
        for i in range(len(x_m)):
            for j in range(i + 1, len(x_m)):
                h = np.sqrt((x_m[i]-x_m[j])**2 + (y_m[i]-y_m[j])**2)
                gamma = 0.5 * (residuals[i] - residuals[j])**2
                dists.append(h)
                semivars.append(gamma)

        dists, semivars = np.array(dists), np.array(semivars)
        max_dist = np.percentile(dists, 90)
        bins = np.linspace(0, max_dist, 12)
        bin_centers, bin_values = [], []

        for i in range(len(bins) - 1):
            b_mask = (dists >= bins[i]) & (dists < bins[i+1])
            if np.sum(b_mask) > 5:
                bin_centers.append(np.mean(dists[b_mask]))
                bin_values.append(np.mean(semivars[b_mask]))

        bin_centers, bin_values = np.array(bin_centers), np.array(bin_values)
        sill, rang, nugget = np.var(residuals), max_dist * 0.6, 0

        def v_model_func(h):
            if var_type == "linear": return nugget + (sill/rang)*h
            if var_type == "exponential": return nugget + sill*(1-np.exp(-h/rang))
            if var_type == "gaussian": return nugget + sill*(1-np.exp(-(h**2)/(rang**2)))
            return np.where(h<=rang, nugget+sill*(1.5*(h/rang)-0.5*(h/rang)**3), nugget+sill)

        x_v = np.linspace(0, max_dist, 200)
        y_v = v_model_func(x_v)
        # RSS SCORE CALCULATION
        rss_score = float(np.mean((bin_values - v_model_func(bin_centers))**2))

        plt.figure(figsize=(6,5))
        plt.scatter(bin_centers, bin_values, color="black", label="Binned Data")
        plt.plot(x_v, y_v, color="red", label=f"{var_type} model")
        plt.title(f"Variogram")
        plt.xlabel("Distance (m)")
        plt.ylabel("Semivariance")
        plt.legend()
        buf3 = io.BytesIO()
        plt.savefig(buf3, format="png", bbox_inches="tight")
        buf3.seek(0)
        var_img = base64.b64encode(buf3.read()).decode()
        plt.close()

        # 6. HEATMAP PLOT
        plt.figure(figsize=(6, 5))
        plt.contourf(grid_x, grid_y, final_map, levels=100, cmap="YlGnBu")
        plt.scatter(lon, lat, c="red", s=10)
        plt.axis("off")
        buf2 = io.BytesIO()
        plt.savefig(buf2, format="png", bbox_inches="tight")
        buf2.seek(0)
        heat_img = base64.b64encode(buf2.read()).decode()
        plt.close()

        # 7. Statistics
        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((moisture - np.mean(moisture))**2)
        r2 = 1 - (ss_res / ss_tot)

       #max_idx = np.unravel_index(np.argmax(uncertainty), uncertainty.shape)
# -------------------------------
# UNCERTAINTY MODES
        if uncertainty_mode == "kriging_only":
            score_map = kriging_uncertainty
            max_idx = np.unravel_index(np.argmax(score_map), score_map.shape)

        elif uncertainty_mode == "variance_distance":
            score_map = kriging_uncertainty * grid_dist_to_sample
            max_idx = np.unravel_index(np.argmax(score_map), score_map.shape)

        elif uncertainty_mode == "top10_farthest":
            flat_indices = np.argsort(kriging_uncertainty.ravel())[::-1][:10]

            best_idx = None
            best_dist = -1

            for idx in flat_indices:
                i, j = np.unravel_index(idx, kriging_uncertainty.shape)
                dist = grid_dist_to_sample[i, j]

                if dist > best_dist:
                    best_dist = dist
                    best_idx = (i, j)

            max_idx = best_idx
            score_map = kriging_uncertainty  # IMPORTANT: still define it

        else:
            score_map = kriging_uncertainty
            max_idx = np.unravel_index(np.argmax(score_map), score_map.shape)


        return jsonify({
            "image": heat_img,
            "regression_plot": reg_img,
            "variogram_plot": var_img,
            "regression_r2": float(r2),
            "variogram_fit_error": rss_score,
            "max_uncertainty": {
                "lat": float(grid_lat[max_idx]),
                "lon": float(grid_lon[max_idx]),
"value": float(score_map[max_idx])
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)})
#4/11 change ended here

#4/11 change ended here
@app.route("/heartbeat")
def heartbeat():
    return jsonify({"ip": request.host.split(":")[0]})

@app.route("/covariates")
def covariates_page():
    return render_template("sprinklers.html")


@app.route("/get_sprinklers")
def get_sprinklers():
    return jsonify(load_sprinklers())


@app.route("/add_sprinkler", methods=['POST'])
def add_sprinkler():
    try:
        data = request.get_json()

        if not data:
            return "No data received", 400

        sprinklers = load_sprinklers()
        sprinklers.append(data)
        save_sprinklers(sprinklers)
        return "OK", 200
    except Exception as e:
        print(f"Error: {e}")
        return str(e), 500


@app.route("/delete_sprinkler/<int:index>", methods=['DELETE'])
def delete_sprinkler(index):
    sprinklers = load_sprinklers()
    if 0 <= index < len(sprinklers):
        sprinklers.pop(index)
        save_sprinklers(sprinklers)
    return "OK"

@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.get_json()
        input_lon, input_lat = float(data["lon"]), float(data["lat"])
        sprinklers = load_sprinklers()
        df = pd.read_csv(os.path.expanduser("~/Drone/drone_app/data.csv"))

        # Re-use your exact structure for loading/masking
        lat = pd.to_numeric(df[df.columns[1]], errors="coerce").values
        lon = pd.to_numeric(df[df.columns[2]], errors="coerce").values
        moisture = pd.to_numeric(df[df.columns[3]], errors="coerce").values
        dist_recorded = pd.to_numeric(df[df.columns[7]], errors="coerce").values
        mask = ~np.isnan(lat) & ~np.isnan(lon) & ~np.isnan(moisture)
        lat, lon, moisture, dist_recorded = lat[mask], lon[mask], moisture[mask], dist_recorded[mask]

        coeffs = np.polyfit(dist_recorded, moisture, 3)
        residuals = moisture - np.polyval(coeffs, dist_recorded)

        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32615", always_xy=True)
        x_m, y_m = transformer.transform(lon, lat)
        px, py = transformer.transform(input_lon, input_lat)

        # The Fix: Nearest sprinkler for the specific prediction point
        spr_coords_m = [transformer.transform(s['lon'], s['lat']) for s in sprinklers]
        input_dist_to_closest = min([np.sqrt((px - sx)**2 + (py - sy)**2) for sx, sy in spr_coords_m])

        OK = OrdinaryKriging(x_m, y_m, residuals, variogram_model='spherical')
        res_pred, _ = OK.execute("points", [px], [py])

        prediction = res_pred[0] + np.polyval(coeffs, input_dist_to_closest)
        return jsonify({"lat": input_lat, "lon": input_lon, "predicted_moisture": float(prediction)})
    except Exception as e:
        return jsonify({"error": str(e)})


def dist_points(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    l1, l2 = math.radians(lon1), math.radians(lon2)
    x = (l2 - l1) * math.cos((p1 + p2) / 2)
    y = (p2 - p1)
    return math.sqrt(x * x + y * y) * R

def read_gps_with_accuracy():
    if serGps:
        serGps.reset_input_buffer()
        time.sleep(0.1)

    lat, lon, hdop, vdop = None, None, None, None
    CEP, TWOD_MULTIPLIER = 1.0, 2.45
    timeout = time.time() + 1.0

    while time.time() < timeout:
        if serGps and serGps.in_waiting > 0:
            line = serGps.readline().decode('utf-8', errors='ignore').strip()

            if 'GSA' in line:
                msg = pynmea2.parse(line)
                hdop = float(msg.hdop)

            if 'GGA' in line:
                msg = pynmea2.parse(line)
                if msg.gps_qual > 0:
                    lat, lon = msg.latitude, msg.longitude

            if lat and hdop:
                h_err = (CEP * TWOD_MULTIPLIER) * hdop
                return lat, lon, h_err
@app.route("/")
def index():
    return render_template("index.html", initial_data=logged_data_list)

def too_close_to_existing_points(new_lat, new_lon, threshold):
    filename = "~/Drone/drone_app/data.csv"

    if not os.path.exists(filename):
        return False, None  # no file → no restriction

    try:
        with open(filename, 'r') as f:
            lines = f.readlines()[1:]  # skip header

        if not lines:
            return False, None  # empty file → no restriction

        for line in lines:
            parts = line.strip().split(",")

            try:
                lat = float(parts[1])
                lon = float(parts[2])
            except:
                continue

            d = dist_points(new_lat, new_lon, lat, lon)

            if d < threshold:
                return True, d  # too close

        return False, None  # all good

    except Exception as e:
        print("Distance check error:", e)
        return False, None

@app.route("/log")
def log_action():
    global sample_ID, last_lat, last_lon, current_moisture, current_latitude, current_longitude, logged_data_list
    force_log = request.args.get('override') == 'true'

    # 1. Trigger Actuator
    if serMoisture:
        serMoisture.write(b'l\n')
        time.sleep(0.5)
        if serMoisture.in_waiting:
            try:
                current_moisture = float(serMoisture.readline().decode().strip())
            except:
                current_moisture = "Error"

    # 2. Get GPS
    serGps.reset_input_buffer()
    new_lat, new_lon, h_err = read_gps_with_accuracy()

    if new_lat is None:
        return jsonify({"status": "error", "message": "No GPS Fix - Log Aborted"})

    # 3. Distance Logic
    distance_from_last = 0.0

# --- OPTIONAL: keep last-point distance ONLY for logging (not validation) ---
    if last_lat is not None:
        distance_from_last = dist_points(last_lat, last_lon, new_lat, new_lon)
    else:
        distance_from_last = h_err * 3 if h_err else 0


# --- TRUE VALIDATION: check against ALL points in CSV ---
    if not force_log and h_err:
        threshold = h_err * 3
        filename = "data.csv"

        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    lines = f.readlines()[1:]  # skip header

                for line in lines:
                    parts = line.strip().split(",")

                # skip malformed rows
                    if len(parts) < 3:
                        continue

                    try:
                        prev_lat = float(parts[1])
                        prev_lon = float(parts[2])
                    except:
                        continue

                    dist = dist_points(new_lat, new_lon, prev_lat, prev_lon)

                    if dist < threshold:
                        return jsonify({
                        "status": "warning",
                        "message": f"Log Skipped: Too close to existing point ({dist:.2f}m < {threshold:.2f}m)"
                        })

            except Exception as e:
                print("CSV distance check error:", e)

    # 4. Successful Log
    current_latitude, current_longitude = new_lat, new_lon
    last_lat, last_lon = new_lat, new_lon

    sprinklers = load_sprinklers()
    closest_dist = "N/A"
    closest_name = "None"

    if sprinklers and new_lat:
        distances = []
        for s in sprinklers:
            d = dist_points(new_lat, new_lon, s['lat'], s['lon'])
            distances.append((d, s['name']))

        min_entry = min(distances, key=lambda x: x[0])
        closest_dist = round(min_entry[0], 2)
        closest_name = min_entry[1]

    filename = "data.csv"

    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            f.write('Sample ID, Latitude, Longitude, Moisture,Elevation(m),  Distance from last point(m), Closest Sprinkler, Dist to Sprinkler(m)\n')

    url = f"https://epqs.nationalmap.gov/v1/json?x={current_longitude}&y={current_latitude}&units=Meters&wkid=4326"
    response = requests.get(url)
    elevation = response.json()['value']
    elevation = float(elevation)

    with open(filename, 'a') as f:
        f.write(f"{sample_ID},{current_latitude},{current_longitude},{current_moisture},{elevation}, {distance_from_last:.2f},{closest_name}, {closest_dist}\n")

    sample_ID += 1

    new_point = [
        sample_ID,
        current_latitude,
        current_longitude,
        current_moisture,
    ]

    logged_data_list.append(new_point)

    return jsonify({
        "full_list": logged_data_list,
        "new_point": new_point
    })


@app.route("/reset")
def reset_tracking():
    global sample_ID, last_lat, last_lon
    sample_ID = 0
    last_lat = last_lon = None
    return "Tracking and ID Reset."

@app.route("/check_landing")
def check_landing():
    # Directly read the GPIO pin instead of using the consumed flag
    pin_state = GPIO.input(LANDING_PIN) == GPIO.HIGH
    return jsonify({"landed": pin_state})


@app.route("/extend")
def extend():
    if serMoisture:
        serMoisture.write(b"e\n")
    return "SUCCESS: Actuator Extended"


@app.route("/retract")
def retract():
    if serMoisture:
        serMoisture.write(b"r\n")
    return "SUCCESS: Actuator Retracted"


@app.route("/collect")
def collect():
    global sample_ID, last_lat, last_lon, current_moisture, current_latitude, current_longitude

    lat, lon, h_err = read_gps_with_accuracy()

    url = f"https://epqs.nationalmap.gov/v1/json?x={lon}&y={lat}&units=Meters&wkid=4326"
    response = requests.get(url)
    elevation = response.json()['value']
    elevation = float(elevation)

    if serMoisture:
        serMoisture.write(b'l\n')
        time.sleep(0.5)
        if serMoisture.in_waiting:
            try:
                current_moisture = float(serMoisture.readline().decode().strip())
            except:
                current_moisture = "Error"

    closest_name = "None"
    closest_dist = "N/A"
    sprinklers = load_sprinklers()

    if sprinklers and lat:
        distances = []
        for s in sprinklers:
            d = dist_points(lat, lon, s['lat'], s['lon'])
            distances.append((d, s['name']))

        min_entry = min(distances, key=lambda x: x[0])
        closest_dist = round(min_entry[0], 2)
        closest_name = min_entry[1]

    return jsonify({
        "moisture": current_moisture,
        "lat": lat if lat else "No Fix",
        "lon": lon if lon else "No Fix",
        "elevation": elevation if elevation else "Couldn't get elevation data, check wifi",
        "h_err": round(h_err, 2) if h_err else "N/A",
        "closest_sprinkler": closest_name,
        "sprinkler_dist": closest_dist
    })


@app.route("/view_logs")
def view_logs():
    csv_path = os.path.expanduser("~/Drone/drone_app/data.csv")

    if not os.path.exists(csv_path):
        return "No logs available yet."

    return send_file(csv_path, mimetype='text/csv', as_attachment=False)


@app.route("/clear_logs")
def clear_logs():
    global logged_data_list, sample_ID, last_lat, last_lon

    csv_path = os.path.expanduser("~/Drone/drone_app/data.csv")

    if not os.path.exists(csv_path):
        return "No logs to clear."

    with open(csv_path, 'w') as f:
        f.write("Sample ID, Latitude, Longitude, Moisture, Elevation(m), Distance from last point(m),Closest Sprinkler, Distance to Sprinkler(m)\n")

    #  CLEAR MEMORY TOO
    logged_data_list = []
    sample_ID = 0
    last_lat = None
    last_lon = None

    return "All logs cleared successfully, memory + CSV reset."

@app.route("/get_latest_point")
def get_latest_point():
    if logged_data_list:
        return jsonify(logged_data_list[-1])
    return jsonify([])

@app.route("/loocv_rmse", methods=["POST"])
def loocv_rmse():
    try:
        import numpy as np
        import pandas as pd
        from pykrige.ok import OrdinaryKriging
        from pyproj import Transformer
        import os

        csv_path = os.path.expanduser("~/Drone/drone_app/data.csv")

        if not os.path.exists(csv_path):
            return jsonify({"error": "No data file found"})

        df = pd.read_csv(csv_path)

        # -----------------------------
        # READ FRONTEND CONFIG SAFELY
        # -----------------------------
        body = request.get_json(force=True, silent=True) or {}

        reg_type = body.get("regression", "cubic")
        var_type = body.get("variogram", "spherical")

        reg_map = {
            "linear": 1,
            "quadratic": 2,
            "cubic": 3
        }

        deg = reg_map.get(reg_type, 3)

        var_map = {
            "linear": "linear",
            "exponential": "exponential",
            "gaussian": "gaussian",
            "spherical": "spherical"
        }

        v_model = var_map.get(var_type, "spherical")

        # -----------------------------
        # LOAD DATA
        # -----------------------------
        lat = pd.to_numeric(df[df.columns[1]], errors="coerce").values
        lon = pd.to_numeric(df[df.columns[2]], errors="coerce").values
        moisture = pd.to_numeric(df[df.columns[3]], errors="coerce").values
        distance = pd.to_numeric(df[df.columns[7]], errors="coerce").values

        mask = (
            ~np.isnan(lat) &
            ~np.isnan(lon) &
            ~np.isnan(moisture) &
            ~np.isnan(distance)
        )

        lat = lat[mask]
        lon = lon[mask]
        moisture = moisture[mask]
        distance = distance[mask]

        if len(lat) < 6:
            return jsonify({"error": f"Not enough data for LOOCV: {len(lat)}"})

        transformer = Transformer.from_crs(
            "EPSG:4326",
            "EPSG:32615",
            always_xy=True
        )

        errors = []

        # -----------------------------
        # LOOCV LOOP
        # -----------------------------
        for i in range(len(lat)):

            try:
                train_idx = np.arange(len(lat)) != i

                lat_train = lat[train_idx]
                lon_train = lon[train_idx]
                moisture_train = moisture[train_idx]
                distance_train = distance[train_idx]

                lat_test = lat[i]
                lon_test = lon[i]
                true_val = moisture[i]

                # -------------------------
                # REGRESSION MODEL
                # -------------------------
                coeffs = np.polyfit(distance_train, moisture_train, deg)
                trend_train = np.polyval(coeffs, distance_train)
                residuals = moisture_train - trend_train

                # -------------------------
                # TRANSFORM
                # -------------------------
                x_train, y_train = transformer.transform(lon_train, lat_train)
                x_test, y_test = transformer.transform(lon_test, lat_test)

                # -------------------------
                # KRIGING
                # -------------------------
                OK = OrdinaryKriging(
                    x_train,
                    y_train,
                    residuals,
                    variogram_model=v_model,
                    nlags=6,
                    verbose=False,
                    enable_plotting=False
                )

                z_pred, _ = OK.execute("points", [x_test], [y_test])
                z_pred = float(z_pred[0])

                # -------------------------
                # TREND FOR TEST POINT
                # -------------------------
                dist_test = distance[i]
                trend_test = np.polyval(coeffs, dist_test)

                final_pred = trend_test + z_pred

                error = (final_pred - true_val) ** 2
                errors.append(error)

            except Exception as e:
                print(f"LOOCV iteration {i} failed:", e)
                continue

        if len(errors) == 0:
            return jsonify({"error": "All LOOCV iterations failed"})

        rmse = float(np.sqrt(np.mean(errors)))

        return jsonify({
            "rmse": rmse,
            "n_points_used": len(errors)
        })

    except Exception as e:
        print("LOOCV ERROR:", str(e))
        return jsonify({"error": str(e)})




@app.route("/simulate", methods=["POST"])
def simulate_action():
    global sample_ID, last_lat, last_lon, current_moisture, current_latitude, current_longitude, logged_data_list

    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "No JSON provided"})

    sim_lat = data.get("lat")
    sim_lon = data.get("lon")
    sim_moisture = data.get("moisture")

    if sim_lat is None or sim_lon is None or sim_moisture is None:
        return jsonify({"status": "error", "message": "Missing simulation inputs"})

    sim_lat = float(sim_lat)
    sim_lon = float(sim_lon)
    sim_moisture = float(sim_moisture)

    # ---- SAME VALIDATION LOGIC AS /log ----
    distance_from_last = 0.0

    if last_lat is not None:
        distance_from_last = dist_points(last_lat, last_lon, sim_lat, sim_lon)

    # irrigation / sprinkler logic preserved
    sprinklers = load_sprinklers()
    closest_dist = "N/A"
    closest_name = "None"

    if sprinklers:
        distances = []
        for s in sprinklers:
            d = dist_points(sim_lat, sim_lon, s['lat'], s['lon'])
            distances.append((d, s['name']))

        min_entry = min(distances, key=lambda x: x[0])
        closest_dist = round(min_entry[0], 2)
        closest_name = min_entry[1]

    # elevation (same API call as real system)
    url = f"https://epqs.nationalmap.gov/v1/json?x={sim_lon}&y={sim_lat}&units=Meters&wkid=4326"
    response = requests.get(url)

    try:
        elevation = float(response.json().get("value", 0))
    except:
        elevation = 0

    # ensure CSV exists
    filename = "data.csv"
    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            f.write('Sample ID, Latitude, Longitude, Moisture,Elevation(m), Distance from last point(m), Closest Sprinkler, Dist to Sprinkler(m)\n')

    # append simulated row
    with open(filename, 'a') as f:
        f.write(f"{sample_ID},{sim_lat},{sim_lon},{sim_moisture},{elevation},{distance_from_last:.2f},{closest_name},{closest_dist}\n")

    # update state (same as real log)
    current_latitude = sim_lat
    current_longitude = sim_lon
    current_moisture = sim_moisture
    last_lat = sim_lat
    last_lon = sim_lon

    sample_ID += 1

    new_point = [
        sample_ID,
        sim_lat,
        sim_lon,
        sim_moisture
    ]

    logged_data_list.append(new_point)

    return jsonify({
        "status": "success",
        "new_point": new_point,
        "mode": "simulation"
    })

# --- GPIO Setup for Pixhawk Landing Signal ---
LANDING_PIN = 37
GPIO.setmode(GPIO.BOARD)
GPIO.setup(LANDING_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)


def monitor_landing():
    """Background thread that waits for the Pixhawk Relay signal."""
    print("Auto-Log Thread: Active and listening on Pin 37...")

    while True:
        if GPIO.input(LANDING_PIN) == GPIO.HIGH: 
            global landing_event_flag
            landing_event_flag = True
            print("LANDING DETECTED via GPIO! Auto-logging point...")
            if serMoisture:
                serMoisture.write(b"e\n") 
                time.sleep(30)
            with app.test_client() as client:
                response = client.get('/log?override=true')
                print(f"Auto-Log Status: {response.status}")

            while GPIO.input(LANDING_PIN) == GPIO.HIGH:
                time.sleep(1)

            print("Signal reset. Waiting for next landing...")

        else: 
            landing_event_flag = False
            if serMoisture: 
                serMoisture.write(b"r\n")


threading.Thread(target=monitor_landing, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)