#this runs on the computer and simply logs data from the pi over radio and calculates the next best point with our acquisition function 
#the data is logged on a file called collected_data.csv 
#the most optimal point is logged on a file called current_target.csv
#location checker uses current_target.csv to continously check the calculated optimal location the pi should go to v.s. where we are now as we walk through the field 

import argparse
import csv
import os
import time
import numpy as np
import serial

import rover_optimizer as opt

PI_IDS = ["PI1"] 

DATA_LOG_PATH = "collected_data.csv" 
TARGET_LOG_PATH = "current_target.csv" 


def load_collected_data():
    if not os.path.exists(DATA_LOG_PATH):
        return np.empty((0, 3))
    rows = []
    with open(DATA_LOG_PATH, "r", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 3:
                lat, lon, moisture = row[0], row[1], row[2] 
                rows.append([float(lat), float(lon), float(moisture)])
    return np.array(rows) if rows else np.empty((0, 3))


def append_collected_data(pid, lat, lon, moisture):
    file_exists = os.path.exists(DATA_LOG_PATH)
    with open(DATA_LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["lat", "lon", "moisture", "pi_id", "timestamp"])
        writer.writerow([lat, lon, moisture, pid, time.strftime("%Y-%m-%d %H:%M:%S")])


def write_current_target(pid, lat, lon):
    file_exists = os.path.exists(TARGET_LOG_PATH)
    with open(TARGET_LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["pi_id", "lat", "lon", "timestamp"])
        writer.writerow([pid, lat, lon, time.strftime("%Y-%m-%d %H:%M:%S")])


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


def parse_packet(line):
    parts = line.split(",")
    if len(parts) != 6:
        return None
    lat, lon, alt, fix_quality, moisture, temp = parts
    if moisture == "NA" or temp == "NA":
        return None
    payload = f"{lat},{lon},{moisture}"
    return PI_IDS[0], "DATA", payload


def run(port, baud):
    ser = serial.Serial(port, baud, timeout=1)
    ser.reset_input_buffer() 
    reader = LineReader(ser)

    previously_collected = load_collected_data()
    augmented_data = np.vstack([opt.data, previously_collected]) if len(previously_collected) else opt.data.copy()
    real_sample_count = len(opt.data) + len(previously_collected)
    print(f"[MOM] Booted. Loaded {len(previously_collected)} previously-collected point(s) from {DATA_LOG_PATH}.")
    print(f"[MOM] Starting real sample count: {real_sample_count}")
    print("[MOM] Mode: RECEIVING. Waiting for data from:", PI_IDS)

    try:
        received = {}
        while len(received) < len(PI_IDS):
            for line in reader.read_lines():
                pkt = parse_packet(line)
                if pkt is None:
                    continue
                pkt_id, pkt_type, payload = pkt

                if pkt_type != "DATA" or pkt_id not in PI_IDS:
                    continue

                if pkt_id in received:
                    print(f"[MOM] Already have data from {pkt_id}, ignoring repeat")
                    continue

                lat, lon, moisture = map(float, payload.split(","))
                received[pkt_id] = (lat, lon, moisture)
                append_collected_data(pkt_id, lat, lon, moisture)
                print(f"[MOM] Got data from {pkt_id}: ({lat:.6f}, {lon:.6f}), moisture={moisture:.2f}"
                      f"  [{len(received)}/{len(PI_IDS)}]")

            time.sleep(0.05)

        print("[MOM] Have data from all rovers. Running calculations...")

        new_rows = np.array([[lat, lon, moisture] for (lat, lon, moisture) in received.values()])
        augmented_data = np.vstack([augmented_data, new_rows])
        real_sample_count += len(new_rows)

        current_alpha = 1 - real_sample_count / 50
        print(f"[MOM] real samples so far: {real_sample_count}, alpha: {current_alpha:.3f}")

        results, augmented_data = opt.hallucinate_dataset(augmented_data, iterations=len(PI_IDS), a=current_alpha)
        best_points = [(f"best_{i+1}", r["best_lat"], r["best_lon"]) for i, r in enumerate(results)]
        print("[MOM] Candidate points:", [(n, f"{la:.6f}", f"{lo:.6f}") for n, la, lo in best_points])
        pi_positions = [(received[pid][0], received[pid][1]) for pid in PI_IDS]
        assignment, total_distance = opt.assign_points(pi_positions, best_points)
        assignment_by_id = {PI_IDS[input_idx]: (b_lat, b_lon, dist)
                             for input_idx, _, b_lat, b_lon, dist in assignment}

        for pid in PI_IDS:
            b_lat, b_lon, dist = assignment_by_id[pid]
            print(f"[MOM] Optimal next point for {pid}: ({b_lat:.6f}, {b_lon:.6f})  ({dist:.1f} m away)")
            write_current_target(pid, b_lat, b_lon)

    except KeyboardInterrupt:
        print("\n[MOM] Stopping.")
    finally:
        ser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    run(args.port, args.baud)