# drive.py
# Sends track speeds to the ESP32 that runs the motors, and reads back what the ESP32 sends
# (IMU data + measured track speeds; imu.py turns the IMU data into roll / pitch). On boards
# whose feedback has no raw IMU data, it also asks for that data 20 times a second.
#   Test on its own:  python drive.py 0.1 0.1 1     (left m/s, right m/s, seconds)
#   THE ROVER WILL MOVE when you run that test.

import json
import sys
import threading
import time

import serial

import roverconfig as cfg
from imu import Imu


def clamp(v):
    return max(-cfg.MAX_SPEED, min(cfg.MAX_SPEED, v))


class Drive:
    def __init__(self, port=cfg.ESP_PORT, baud=cfg.ESP_BAUD):
        self.esp = serial.Serial(port, baud, timeout=0.05)
        self.write_lock = threading.Lock()    # the main loop and the reader thread both write
        self.last_cmd = (0.0, 0.0)            # last track speeds sent (logged by stabilitylog.py)
        self._moving_time = float("-inf")     # last time a non-zero speed was sent
        self.imu = Imu()
        self._last_config = float("-inf")
        threading.Thread(target=self._reader, daemon=True).start()

    def _send(self, cmd):
        with self.write_lock:
            self.esp.write((json.dumps(cmd) + "\n").encode())

    def set(self, left, right):
        """Left / right track speed in m/s (clamped to MAX_SPEED)."""
        left, right = round(clamp(left), 3), round(clamp(right), 3)
        self.last_cmd = (left, right)
        if left or right:
            self._moving_time = time.monotonic()
        self._send({"T": 1, "L": left, "R": right})

    def stop(self):
        self.set(0, 0)

    def parked(self):
        """True once the rover hasn't been told to move for 2 s (it has stopped rolling)."""
        return time.monotonic() - self._moving_time > 2.0

    def _configure_feedback(self):
        """Make sure the ESP32 is streaming its feedback (it is by default after power-on)."""
        self._last_config = time.monotonic()
        try:
            self._send({"T": 143, "cmd": 0})                    # don't echo our commands back
            self._send({"T": 142, "cmd": cfg.ESP_FEEDBACK_MS})  # time between feedback lines, ms
            self._send({"T": 131, "cmd": 1})                    # continuous feedback on
        except (serial.SerialException, OSError):
            pass

    def _reader(self):
        buffer = b""
        last_feedback = last_request = float("-inf")
        while self.esp.is_open:
            try:
                buffer += self.esp.read(max(1, self.esp.in_waiting))
            except (serial.SerialException, OSError, TypeError):
                if not self.esp.is_open:
                    return                  # close() was called
                time.sleep(0.5)
                continue
            *lines, buffer = buffer.split(b"\n")
            for line in lines:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue                # half a line, boot text, etc.
                if isinstance(msg, dict) and msg.get("T") in (1001, 1002):
                    self.imu.handle(msg, still=self.parked())
                    if msg["T"] == 1001:
                        last_feedback = time.monotonic()
            if len(buffer) > 4096:
                buffer = b""                # no newline in 4 kB: not our JSON, throw it away
            now = time.monotonic()
            # General Driver board: its feedback has no raw IMU data, so ask for it.
            # (Only motion commands keep the ESP32's own 3 s motor watchdog alive, not this.)
            if self.imu.needs_raw_request and now - last_request >= cfg.ESP_FEEDBACK_MS / 1000.0:
                last_request = now
                try:
                    self._send({"T": 126})
                except (serial.SerialException, OSError):
                    pass
            # No feedback (just started, or the ESP32 rebooted): ask for it again every 2 s.
            if now - last_feedback > 2.0 and now - self._last_config > 2.0:
                self._configure_feedback()

    def close(self):
        try:
            self.stop()
        except Exception:
            pass
        self.esp.close()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("usage: python drive.py LEFT RIGHT SECONDS    e.g.  python drive.py 0.1 0.1 1")
    left, right, seconds = (float(a) for a in sys.argv[1:])
    d = Drive()
    try:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            d.set(left, right)
            time.sleep(1.0 / cfg.LOOP_HZ)
    finally:
        d.close()
