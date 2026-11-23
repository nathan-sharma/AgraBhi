# arduinolink.py
# The one shared serial connection to the Arduino.
# The actuator and the soil sensor are both on the same Arduino, and only one thing can
# hold its serial port, so actuator.py and datacollect.py both go through this file.

import threading
import time
from collections import deque

import serial

import roverconfig as cfg


class ArduinoLink:
    def __init__(self, port=cfg.ARDUINO_PORT, baud=cfg.ARDUINO_BAUD):
        self.port = port
        self.ser = serial.Serial(port, baud, timeout=1)
        self.lock = threading.Lock()
        self.soil = None                  # latest (moisture, temperature), kept as text
        self.soil_time = 0.0
        self.replies = deque(maxlen=20)   # recent non-DATA lines, e.g. "actuator extended."
        threading.Thread(target=self._reader, daemon=True).start()
        time.sleep(2)                     # opening the port resets most Arduinos; let it boot

    def _reader(self):
        while True:
            try:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
            except Exception as e:
                print(f"[Arduino] read error: {e}")
                time.sleep(1)
                continue
            if line.startswith("DATA,"):
                parts = line.split(",")
                if len(parts) == 3:
                    with self.lock:
                        self.soil = (parts[1].strip(), parts[2].strip())
                        self.soil_time = time.monotonic()
            elif line:
                print(f"[Arduino] {line}")
                with self.lock:
                    self.replies.append(line.lower())

    def latest_soil(self):
        """Latest (moisture, temperature) from the soil sensor, or None if nothing fresh."""
        with self.lock:
            if self.soil and time.monotonic() - self.soil_time <= cfg.MAX_READING_AGE_S:
                return self.soil
        return None

    def command(self, char, expect, timeout=1.0):
        """Send a one-letter command; True if the Arduino answers with a line containing `expect`."""
        with self.lock:
            self.replies.clear()
        self.ser.write(char.encode())
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if any(expect in line for line in self.replies):
                    return True
            time.sleep(0.01)
        return False
