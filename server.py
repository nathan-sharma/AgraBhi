#this code works (server.py) 
#a lot of stuff here is useless from older version of the code, will be cleaned up soon
import serial
import pynmea2
import time
import os 
import math
import pandas as pd
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS 
from acquisitionfunc import calculate_optimal_target, predict_moisture_at_location, calculate_swarm_targets

rover_battery = 100.0 
acquisition_alpha = 0.8
active_variogram_model = "gaussian"

swarm_rovers = {
    "Rover_1": {"lat": 27.59613, "lon": -97.89477, "battery": 90},
    "Rover_2": {"lat": 27.59641 , "lon": -97.89375, "battery": 90},
    "Rover_3": {"lat": 27.59675, "lon": -97.89415, "battery": 90},
    "Rover_4": {"lat": 27.59693, "lon": -97.8932, "battery": 90},
    "Rover_5": {"lat": 27.59702, "lon": -97.89211, "battery": 90}
}

app = Flask(__name__)
CORS(app)

CSV_PATH = os.path.expanduser("~/Drone/drone_app/data.csv")
try:
    serArduino = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
    serGps = serial.Serial('/dev/ttyAMA0', 115200, timeout=1)
except Exception as e:
    print(f"Can't connect properly to the arduino {e}")
    serArduino = serGps = None

def _calculate_haversine_decay(current_lat, current_lon, target_lat, target_lon):
    R = 6371000 
    phi1 = math.radians(current_lat)
    phi2 = math.radians(target_lat)
    delta_phi = math.radians(target_lat - current_lat)
    delta_lambda = math.radians(target_lon - current_lon)
    
    a = (math.sin(delta_phi / 2) ** 2 + 
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance_meters = R * c 
    
    battery_lost = 100*distance_meters/4590
    return distance_meters, battery_lost

def read_gps_with_accuracy():
    if not serGps:
        return None, None
    try:
        serGps.flushInput()
        for _ in range(30):
            line = serGps.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith('$GNGGA') or line.startswith('$GPGGA'):
                msg = pynmea2.parse(line)
                if msg.latitude and msg.longitude:
                    return msg.latitude, msg.longitude
    except Exception as e:
        print(f"GPS won't work {e}")
    return None, None

def read_arduino_sensors():
    default_vals = (0.0, 0.0)
    if not serArduino:
        return default_vals
    try:
        serArduino.flushInput()
        serArduino.flushOutput()
        serArduino.write(b"l\n")
        time.sleep(0.1)
        raw_line = serArduino.readline().decode('utf-8', errors='ignore').strip()
        if raw_line and "," in raw_line:
            parts = raw_line.split(",")
            return float(parts[0]), float(parts[1])
    except Exception as e:
        print(f"Arduino won't work {e}")
    return default_vals

@app.route("/get_latest_point", methods=["GET"])
def get_latest_point():
    return jsonify({"status": "ready"}), 200

@app.route("/collect", methods=["GET"])
def collect():
    lat, lon = read_gps_with_accuracy()
    moisture, temperature = read_arduino_sensors()
    return jsonify({
        "lat": lat if lat is not None else "N/A",
        "lon": lon if lon is not None else "N/A",
        "moisture": moisture,
        "temperature": temperature
    })


@app.route("/log", methods=["GET"])
def log_data():
    lat, lon = read_gps_with_accuracy()
    moisture, temperature = read_arduino_sensors()
    depth_cm = request.args.get("depth", default="0")

    if lat is None or lon is None:
        if request.args.get("override") != "true":
            return jsonify({
                "status": "warning", 
                "message": "GPS doesn't have a lock, might be something wrong with its connection to the pi."
            })
        lat, lon = 0.0, 0.0

    next_id = 1
    if os.path.exists(CSV_PATH) and os.path.getsize(CSV_PATH) > 0:
        try:
            existing_df = pd.read_csv(CSV_PATH)
            next_id = len(existing_df) + 1
        except Exception:
            pass

    new_row = {
        "Sample_ID": next_id,
        "Latitude": lat,
        "Longitude": lon,
        "Depth_cm": float(depth_cm),
        "Moisture": moisture,
        "Temperature": temperature,
        "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    df_new = pd.DataFrame([new_row])
    if not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0:
        df_new.to_csv(CSV_PATH, index=False)
    else:
        df_new.to_csv(CSV_PATH, mode='a', header=False, index=False)

    return jsonify({
        "status": "success",
        "new_point": [next_id, lat, lon, depth_cm, moisture, temperature]
    })



@app.route("/update_swarm_positions", methods=["POST"])
def update_swarm_positions():
    global swarm_rovers
    try:
        data = request.json
        if not data or "swarm_data" not in data:
            return jsonify({"status": "error", "message": "Missing swarm data configuration blueprint."}), 400
        
        incoming_swarm = data["swarm_data"]
        
        # Overwrite internal memory dictionary with manually submitted frontend coordinates
        for rover_id in swarm_rovers.keys():
            if rover_id in incoming_swarm:
                swarm_rovers[rover_id]["lat"] = float(str(incoming_swarm[rover_id]["lat"]).strip())
                swarm_rovers[rover_id]["lon"] = float(str(incoming_swarm[rover_id]["lon"]).strip())
                swarm_rovers[rover_id]["battery"] = float(str(incoming_swarm[rover_id]["battery"]).strip())
                
        return jsonify({
            "status": "success",
            "message": "Global swarm state tracker synchronized successfully!",
            "current_state": swarm_rovers
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Sync processing failure: {str(e)}"}), 500
@app.route("/update_battery", methods=["POST"])

def update_battery():
    global rover_battery
    data = request.json
    try:
        new_lat = float(data.get("lat"))
        new_lon = float(data.get("lon"))
        current_lat = 27.59413
        current_lon = -97.89429
        
        distance_meters, battery_lost = _calculate_haversine_decay(current_lat, current_lon, new_lat, new_lon)
        rover_battery = max(0.0, rover_battery - battery_lost)
        
        return jsonify({
            "status": "success",
            "distance_moved_m": round(distance_meters, 2),
            "battery_lost_pct": round(battery_lost, 2),
            "current_battery": round(rover_battery, 2)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Battery processing failure: {str(e)}"}), 400

@app.route("/optimal_point", methods=["GET"])
def get_optimal_point():
    try:
        optimal_results = calculate_optimal_target(battery_pct=rover_battery, a=acquisition_alpha, model=active_variogram_model)
        if optimal_results is None:
            return jsonify({
                "status": "error",
                "message": "Not enough data. Make sure you have at least 3 points with GPS locks."
            }), 400
            
        return jsonify({
            "status": "success",
            "optimal_point": optimal_results
        })
    except Exception as e:
        print(f"Failed while calculating best pt {e}")
        return jsonify({"status": "error", "message": f"Failed: {str(e)}"}), 500

@app.route("/swarm_optimal_point", methods=["GET"])
def get_swarm_optimal_point():
    global swarm_rovers
    try:
        swarm_output = calculate_swarm_targets(swarm_rovers, a=acquisition_alpha, model=active_variogram_model)
        
        if swarm_output is None:
            return jsonify({
                "status": "error",
                "message": "Insufficient baseline data. Log your 15 randomly scattered field points first."
            }), 400
        pure_lags = swarm_output["Rover_1"].get("variogram_lags", [])
        pure_variances = swarm_output["Rover_1"].get("variogram_values", [])
        for r_id, results in swarm_output.items():
            current_lat = swarm_rovers[r_id]["lat"]
            current_lon = swarm_rovers[r_id]["lon"]
            target_lat = results["target_lat"]
            target_lon = results["target_lon"]

            dist, drain = _calculate_haversine_decay(current_lat, current_lon, target_lat, target_lon)

            swarm_rovers[r_id]["battery"] = max(0.0, swarm_rovers[r_id]["battery"] - drain)
            swarm_rovers[r_id]["lat"] = target_lat
            swarm_rovers[r_id]["lon"] = target_lon
            
            swarm_output[r_id]["distance_m"] = round(dist, 2)
            swarm_output[r_id]["drain_pct"] = round(drain, 2)
            swarm_output[r_id]["remaining_battery"] = round(swarm_rovers[r_id]["battery"], 2)

        return jsonify({
            "status": "success",
            "swarm_assignments": swarm_output, 
           "mean_kriging_variance": swarm_output["Rover_1"]["mean_kriging_variance"],
          "variogram": {
                "lags": pure_lags,
                "values": pure_variances
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Swarm compute failure: {str(e)}"}), 500

@app.route("/view_logs", methods=["GET"])
def view_logs():
    if os.path.exists(CSV_PATH):
        return send_file(CSV_PATH, as_attachment=True, download_name="data.csv")
    return "No logging index initialized yet.", 404

@app.route("/clear_logs", methods=["GET"])
def clear_logs():
    try:
        if os.path.exists(CSV_PATH):
            os.remove(CSV_PATH)
        return "SUCCESS. Everything has been erased.", 200
    except Exception as e:
        return f"Couldn't erase: {e}", 500

@app.route("/predict_point", methods=["POST"])
def handle_predict_point():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "Missing JSON payload"}), 400
        target_lat = float(data.get("lat"))
        target_lon = float(data.get("lon"))
        predicted_moisture = predict_moisture_at_location(target_lat, target_lon, variogram_model=active_variogram_model)
        if predicted_moisture is None:
            return jsonify({"status": "error", "message": "Prediction failed. Verify data.csv exists."}), 400
            
        return jsonify({
            "status": "success",
            "lat": target_lat,
            "lon": target_lon,
            "predicted_moisture_pct": round(predicted_moisture, 2) 
        })
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid latitude or longitude format formatting values."}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Server processing error: {str(e)}"}), 500

@app.route("/get_system_specs", methods=["GET"])
def get_system_specs():

    home_lat = 27.59496
    home_lon = -97.89311
    field_diagonal_meters = 275
    
    return jsonify({
        "status": "success",
        "specs": {
            "home": {
                "lat": home_lat,
                "lon": home_lon
            },
            "field_diagonal_meters": field_diagonal_meters,
            "swarm_fleet_status": swarm_rovers
        }
    }), 200

@app.route("/update_alpha", methods=["POST"])
def update_alpha():
    global acquisition_alpha
    try:
        data = request.json
        if not data or "alpha" not in data:
            return jsonify({"status": "error", "message": "Missing alpha??"}), 400
        
        new_alpha = float(data["alpha"])
        
        # Keep alpha safe between 0.0 and 1.0
        if not (0.0 <= new_alpha <= 1.0):
            return jsonify({"status": "error", "message": "Alpha must be between 0.0 and 1.0"}), 400
            
        acquisition_alpha = new_alpha
        print(f"alpha was updated to: {acquisition_alpha}")
        
        return jsonify({
            "status": "success", 
            "message": "Alpha updated successfully!",
            "current_alpha": acquisition_alpha
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/update_variogram", methods=["POST"])
def update_variogram():
    global active_variogram_model
    try:
        data = request.json
        if not data or "model" not in data:
            return jsonify({"status": "error", "message": "Missing model target selection."}), 400
        
        chosen_model = str(data["model"]).lower().strip()
        
        valid_models = ["gaussian", "exponential", "spherical", "linear"]
        if chosen_model not in valid_models:
            return jsonify({"status": "error", "message": f"Invalid model. Must be one of {valid_models}"}), 400
            
        active_variogram_model = chosen_model
        print(f"Variogram changed to: {active_variogram_model}")
        
        return jsonify({
            "status": "success", 
            "message": "Variogram model updated successfully!",
            "current_model": active_variogram_model
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
