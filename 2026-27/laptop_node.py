import argparse
import csv
import os
import time
import numpy as np
import serial

import rover_optimizer as opt

TRANSMIT_SECONDS = 8
TRANSMIT_INTERVAL = 1.5

PI_IDS = ["PI1", "PI2"]  # extend this list (and nothing else) to add more rovers

DATA_LOG_PATH = "collected_data.csv"  # every real rover reading ever received, persisted to disk


def load_collected_data():
    if not os.path.exists(DATA_LOG_PATH):
        return np.empty((0, 3))
    rows = []
    with open(DATA_LOG_PATH, "r", newline="") as f:
        reader = csv.reader(f)
        next(reader, None) 
        for row in reader:
            if len(row) >= 3:
                lat, lon, moisture = row[0], row[1], row[2]  # ignore extra columns like pi_id/timestamp
                rows.append([float(lat), float(lon), float(moisture)])
    return np.array(rows) if rows else np.empty((0, 3))


def append_collected_data(pid, lat, lon, moisture):
    file_exists = os.path.exists(DATA_LOG_PATH)
    with open(DATA_LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["lat", "lon", "moisture", "pi_id", "timestamp"])
        writer.writerow([lat, lon, moisture, pid, time.strftime("%Y-%m-%d %H:%M:%S")])


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
    parts = line.split("|")
    if len(parts) != 3:
        return None
    pkt_id, pkt_type, payload = parts
    return pkt_id, pkt_type, payload


def run(port, baud):
    ser = serial.Serial(port, baud, timeout=1)
    ser.reset_input_buffer()  # discard any stale bytes left over from before this script started
    reader = LineReader(ser)

    previously_collected = load_collected_data()
    augmented_data = np.vstack([opt.data, previously_collected]) if len(previously_collected) else opt.data.copy()
    real_sample_count = len(opt.data) + len(previously_collected)
    print(f"[MOM] Booted. Loaded {len(previously_collected)} previously-collected point(s) from {DATA_LOG_PATH}.")
    print(f"[MOM] Starting real sample count: {real_sample_count}")
    print("[MOM] Mode: RECEIVING. Waiting for data from:", PI_IDS)

    try:
        round_num = 1
        while True:
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
                        print(f"[MOM] Already have data from {pkt_id} this round, ignoring repeat")
                        continue

                    lat, lon, moisture = map(float, payload.split(","))
                    received[pkt_id] = (lat, lon, moisture)
                    append_collected_data(pkt_id, lat, lon, moisture)
                    print(f"[MOM] Got data from {pkt_id}: ({lat:.6f}, {lon:.6f}), moisture={moisture:.2f}"
                          f"  [{len(received)}/{len(PI_IDS)}]")

                time.sleep(0.05)

            print(f"[MOM] Have data from all rovers. Running calculations for round {round_num}...")

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
                print(f"[MOM] Assignment: {pid} -> ({b_lat:.6f}, {b_lon:.6f})  ({dist:.1f} m)")

            for pid in PI_IDS:
                b_lat, b_lon, _ = assignment_by_id[pid]
                packet = f"{pid}|ASSIGN|{b_lat:.6f},{b_lon:.6f}\n"

                print(f"[MOM] SWITCHED MODE TO TRANSMITTING (sending {pid}'s assignment)")
                deadline = time.time() + TRANSMIT_SECONDS
                while time.time() < deadline:
                    ser.write(packet.encode("utf-8"))
                    time.sleep(TRANSMIT_INTERVAL)
                print(f"[MOM] SWITCHED MODE TO RECEIVING")

            ser.reset_input_buffer()  # discard any stray/duplicate bytes left over from this round
            round_num += 1

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