#once we get the next point to go to from laptop.py, we need a way to check our precise location as we walk through the field 
#this code takes the Pi's super precise rtk data and calculates the distance between its precise location and the next optimal point laptop.py calculated continously 
#it gets the optimal point from current_target.csv 

import argparse
import csv
import math
import os
import sys
import time
import serial

TARGET_LOG_PATH = "current_target.csv"  # written by laptop_node.py
ARRIVAL_THRESHOLD_METERS = 0.5        
STATUS_PRINT_INTERVAL_SECONDS = 1.0    

EARTH_RADIUS_M = 6371000.0


def haversine_distance_m(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def load_current_target(path=TARGET_LOG_PATH):
    if not os.path.exists(path):
        return None
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip the header
        rows = list(reader)
    if not rows:
        return None
    pid, lat, lon, _timestamp = rows[-1]
    return pid, float(lat), float(lon)


def alert_arrived(pid, lat, lon, distance):
    banner = f"*** {pid} HAS ARRIVED AT TARGET ({lat:.6f}, {lon:.6f}) - {distance:.1f} m away ***"
    print("\n" + "=" * len(banner))
    print(banner)
    print("=" * len(banner) + "\n")
    try:
        import winsound
        for _ in range(3):
            winsound.Beep(1000, 400)
    except ImportError:
        sys.stdout.write("\a\a\a")
        sys.stdout.flush()


class LineReader:
    def __init__(self, ser):
        self.ser = ser
        self.buffer = ""

    def read_lines(self):
        lines = []
        if self.ser.in_waiting > 0:
            self.buffer += self.ser.read(self.ser.in_waiting).decode("utf-8", errors="ignore")
            while "\n" in self.buffer:
                line, self.buffer = self.buffer.split("\n", 1)
                line = line.strip()
                if line:
                    lines.append(line)
        return lines


def parse_position(line):
    parts = line.split(",")
    if len(parts) != 6:
        return None
    lat, lon, _alt, _fix_quality, _moisture, _temp = parts
    try:
        return float(lat), float(lon)
    except ValueError:
        return None


def run(port, baud, threshold_m):
    ser = serial.Serial(port, baud, timeout=1)
    ser.reset_input_buffer()
    reader = LineReader(ser)

    print(f"[CHECK] Listening on {port} for rover position updates...")
    print(f"[CHECK] Arrival threshold: {threshold_m} m")

    arrived = False
    last_status_time = 0.0
    warned_no_target = False

    try:
        while True:
            target = load_current_target()
            if target is None:
                if not warned_no_target:
                    print("[CHECK] No target found yet - waiting for laptop_node.py to write one...")
                    warned_no_target = True
                time.sleep(STATUS_PRINT_INTERVAL_SECONDS)
                continue
            warned_no_target = False

            pid, target_lat, target_lon = target

            for line in reader.read_lines():
                pos = parse_position(line)
                if pos is None:
                    continue
                lat, lon = pos
                distance = haversine_distance_m(lat, lon, target_lat, target_lon)

                now = time.time()
                if now - last_status_time >= STATUS_PRINT_INTERVAL_SECONDS:
                    print(f"[CHECK] {pid} at ({lat:.6f}, {lon:.6f}) - {distance:.1f} m from target")
                    last_status_time = now

                if distance <= threshold_m:
                    if not arrived:
                        alert_arrived(pid, target_lat, target_lon, distance)
                        arrived = True
                else:
                    arrived = False  # reset so leaving and re-entering the zone re-alerts

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n[CHECK] Stopping.")
    finally:
        ser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--threshold", type=float, default=ARRIVAL_THRESHOLD_METERS,
                         help="Arrival threshold in meters")
    args = parser.parse_args()

    run(args.port, args.baud, args.threshold)