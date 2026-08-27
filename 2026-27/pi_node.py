#command to run this: python pi_node.py --id [either PI1 or PI2] --port /dev/ttyACM0 --baud 115200

import argparse
import random
import threading
import time
import serial

TRANSMIT_SECONDS = 8
TRANSMIT_INTERVAL = 1.5  

REACHED_TARGET = False
_lock = threading.Lock()


def input_thread():
    global REACHED_TARGET
    while True:
        cmd = input().strip().lower()
        if cmd in ("go", "1", "true", "t"):
            with _lock:
                REACHED_TARGET = True
            print("[input] REACHED_TARGET -> True")
        elif cmd in ("stop", "0", "false", "f"):
            with _lock:
                REACHED_TARGET = False
            print("[input] REACHED_TARGET -> False")


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


def fake_reading(base_lat, base_lon):
#RANDOM VALUE!!!
    lat = base_lat + random.uniform(-0.0002, 0.0002)
    lon = base_lon + random.uniform(-0.0002, 0.0002)
    moisture = random.uniform(5, 20)
    return lat, lon, moisture


def run(my_id, port, baud, base_lat, base_lon):
    global REACHED_TARGET

    ser = serial.Serial(port, baud, timeout=1)
    reader = LineReader(ser)
    threading.Thread(target=input_thread, daemon=True).start()

    print(f"[{my_id}] Booted. Mode: RECEIVING. Type 'go' to simulate arrival.")

    try:
        while True:
            for line in reader.read_lines():
                pkt = parse_packet(line)
                if pkt is None:
                    continue
                pkt_id, pkt_type, payload = pkt

                if pkt_type == "ASSIGN" and pkt_id == my_id:
                    target_lat, target_lon = map(float, payload.split(","))
                    print(f"[{my_id}] Got my assignment: drive to ({target_lat:.6f}, {target_lon:.6f})")
                else:
                    print(f"[{my_id}] Ignoring packet not addressed to me: {line}")

            with _lock:
                reached = REACHED_TARGET

            if reached:
                print(f"[{my_id}] SWITCHED MODE TO TRANSMITTING")
                lat, lon, moisture = fake_reading(base_lat, base_lon)
                payload = f"{lat:.6f},{lon:.6f},{moisture:.2f}"
                packet = f"{my_id}|DATA|{payload}\n"

                deadline = time.time() + TRANSMIT_SECONDS
                while time.time() < deadline:
                    ser.write(packet.encode("utf-8"))
                    print(f"[{my_id}] Sent DATA: {payload}")
                    time.sleep(TRANSMIT_INTERVAL)

                with _lock:
                    REACHED_TARGET = False
                print(f"[{my_id}] SWITCHED MODE TO RECEIVING")

            time.sleep(0.05)

    except KeyboardInterrupt:
        print(f"\n[{my_id}] Stopping.")
    finally:
        ser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="e.g. PI1 or PI2")
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--base-lat", type=float, default=27.5960)
    parser.add_argument("--base-lon", type=float, default=-97.8930)
    args = parser.parse_args()

    run(args.id.upper(), args.port, args.baud, args.base_lat, args.base_lon)