import serial
import pynmea2
import time
import os
import pandas as pd
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from acquisitionfunc import calculate_optimal_target

app = Flask(__name__)
CORS(app)

CSV_PATH = os.path.expanduser("~/Drone/drone_app/data.csv")
try:
    serArduino = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
    serGps = serial.Serial('/dev/ttyAMA0', 115200, timeout=1)
except Exception as e:
    print(f"Can't connect properly to the arduino {e}")
    serArduino = serGps = None

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


@app.route("/optimal_point", methods=["GET"])
def get_optimal_point():
    try:
        optimal_results = calculate_optimal_target()
        

        if optimal_results is None:
            return jsonify({
                "status": "error",
                "message": "You don't have enough data."
            }), 400
            
        return jsonify({
            "status": "success",
            "optimal_point": optimal_results
        })
    except Exception as e:
        print(f"Failed while calculating best pt {e}")
        return jsonify({
            "status": "error",
            "message": f"Failed: {str(e)}"
        }), 500

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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)