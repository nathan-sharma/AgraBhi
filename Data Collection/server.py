#Path: /Drone/drone_app/server.py

import serial, pynmea2, time, os, math
from flask import Flask, render_template, jsonify
logged_data_list = []

app = Flask(__name__)


current_latitude = "N/A"
current_longitude = "N/A"
current_moisture = "N/A"
sample_ID = 0
last_lat = None
last_lon = None
points = [] 

try:
    serMoisture = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
    serGps = serial.Serial('/dev/ttyAMA0', 115200, timeout=1)
except Exception as e:
    print(f"Serial Error: {e}")
    serMoisture = serGps = None

def dist_points(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    l1, l2 = math.radians(lon1), math.radians(lon2)
    x = (l2 - l1) * math.cos((p1 + p2) / 2)
    y = (p2 - p1)
    return math.sqrt(x*x + y*y) * R

def read_gps_with_accuracy():
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
    return None, None, None

@app.route("/")
def index():
    return render_template("index.html", initial_data=logged_data_list)

@app.route("/log")
def log_action():
    global sample_ID, last_lat, last_lon, current_moisture, current_latitude, current_longitude>
    
    # Actuator
    if serMoisture:
        serMoisture.write(b'l\n')
        time.sleep(0.5)
        if serMoisture.in_waiting:
            try:
                current_moisture = float(serMoisture.readline().decode().strip())
            except: current_moisture = "Error"

    # GPS
    serGps.reset_input_buffer()
    new_lat, new_lon, h_err = read_gps_with_accuracy()
    
    if new_lat is None:
        return jsonify({"status": "error", "message": "No GPS Fix - Log Aborted"})

    distance_from_last = 0.0
    if last_lat is not None:
        distance_from_last = dist_points(last_lat, last_lon, new_lat, new_lon)
      # Min distance for accurate logging
        if h_err and distance_from_last < (h_err * 3):
            return jsonify({
                "status": "warning", 
                "message": f"Log Skipped: Points too close ({distance_from_last:.2f}m < {h_err*>
            })

    current_latitude, current_longitude = new_lat, new_lon
    last_lat, last_lon = new_lat, new_lon
    
    filename = "data.csv"
    if not os.path.exists(filename):
        with open(filename, 'w') as f: f.write('Sample ID, Latitude, Longitude, Moisture, Dista>
    
    with open(filename, 'a') as f:
        f.write(f"{sample_ID},{current_latitude},{current_longitude},{current_moisture},{distan>
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
        "new_point":  new_point
}) 
@app.route("/reset")
def reset_tracking():
    global sample_ID, last_lat, last_lon
    sample_ID = 0
   last_lat = last_lon = None
    return "Tracking and ID Reset."

@app.route("/extend")
def extend():
    if serMoisture: serMoisture.write(b"e\n")
    return "SUCCESS: Actuator Extended"

@app.route("/retract")
def retract():
    if serMoisture: serMoisture.write(b"r\n")
    return "SUCCESS: Actuator Retracted"

@app.route("/collect") 
def collect(): 
    global sample_ID, last_lat, last_lon, current_moisture, current_latitude, current_longitude
    # Get GPS Data
    lat, lon, h_err = read_gps_with_accuracy()
   
    if serMoisture:
        serMoisture.write(b'l\n')
        time.sleep(0.5)
        if serMoisture.in_waiting:
            try:
                current_moisture = float(serMoisture.readline().decode().strip())
            except: current_moisture = "Error"



    # Return everything as a single JSON object
    return jsonify({
        "moisture": current_moisture,
        "lat": lat if lat else "No Fix",
        "lon": lon if lon else "No Fix",
        "h_err": round(h_err, 2) if h_err else "N/A"
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
