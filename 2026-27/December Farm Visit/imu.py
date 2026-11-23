# imu.py
# Turns the IMU data that the ESP32 sends back into roll / pitch / yaw.
#
# Waveshare's UGV robots come with one of two ESP32 boards, and their firmware reports the IMU
# differently. This file handles both:
#   - "General Driver for Robots" board (QMI8658 IMU). Its feedback line, about every 50 ms, is
#         {"T":1001,"L":0.2,"R":0.2,"r":1.40,"p":3.19,"y":-12.3,"temp":45.1,"v":11.9}
#     with its own roll / pitch in DEGREES. Those angles come from a filter that corrects so
#     fast that bumps show up as fake tilt, so drive.py also asks for the raw sensor data
#     ({"T":126} -> {"T":1002, ..., "ax": mg, ..., "gx": deg/s, ...}) 20 times a second and
#     the tilt is worked out here from that instead.
#   - "ROS Driver for Robots" board (ICM-20948 IMU, current firmware): the feedback line itself
#     carries RAW accelerometer / gyro counts: {"T":1001,"L":..,"R":..,"ax":..,"gx":..,...}.
# Either way the tilt is worked out the same way:
#   - gravity (the accelerometer) says which way is down, so it gives the true tilt, but every
#     bump and speed change disturbs it;
#   - the gyro follows quick rocking smoothly, but drifts.
# A complementary filter blends the two: gyro for fast changes, gravity for slow ones
# (IMU_FILTER_TAU_S in roverconfig.py sets the crossover). While the rover is parked and
# truly still, the gyro's zero offset is measured and removed so it can't creep into the tilt.
# If no raw data arrives at all, the ESP32's own angles are used as a fallback.
#
# drive.py owns the ESP32 serial port and hands every message to Imu.handle().
# To see live readings:  python stabilitylog.py

import math
import threading
import time
from collections import deque

import roverconfig as cfg

RAW_KEYS = ("ax", "ay", "az", "gx", "gy", "gz")
ACCEL_COUNTS_PER_G = 8192.0     # ROS Driver board raw counts (the scale factors Waveshare's
GYRO_COUNTS_PER_DPS = 16.4      # own ROS driver uses)
BIAS_TAU_S = 5.0                # gyro zero offset: averaged over about this long while parked
BIAS_MAX_DPS = 8.0              # faster than this while parked = someone moving it, not an offset
STILL_WINDOW_S = 1.0            # parked AND gravity's direction steady over this long = truly still
STILL_MAX_CHANGE_DEG = 0.5      # (tilt change between the two halves of that window)


class Imu:
    def __init__(self):
        self.lock = threading.Lock()
        self.reading = None             # latest reading (dict, see _publish()), or None
        self.reading_time = 0.0
        self.count = 0                  # readings so far
        self.needs_raw_request = False  # True: feedback has no raw data, so drive.py asks for it
        self.last_feedback = None       # latest feedback line (dict), for the test printout
        self._tracks = (None, None)     # measured track speeds, m/s
        self._roll = self._pitch = None     # filter state (board axes, degrees)
        self._yaw = 0.0
        self._bias = [0.0, 0.0, 0.0]    # gyro zero offset, deg/s
        self._bias_samples = 0
        self._recent = deque()          # (time, gravity roll, gravity pitch) over the last second
        self._last_raw_t = None
        self._raw_time = float("-inf")  # when raw data last arrived

    def handle(self, msg, now=None, still=False):
        """One message (already parsed from JSON) from the ESP32. still=True: the rover hasn't
        been told to move for a while, so the gyro should be reading zero."""
        now = time.monotonic() if now is None else now
        kind = msg.get("T")
        has_raw = all(isinstance(msg.get(k), (int, float)) for k in RAW_KEYS)
        if kind == 1001:
            self.last_feedback = msg
            self._tracks = (msg.get("L"), msg.get("R"))
            if has_raw:                                     # ROS Driver board: raw counts
                self.needs_raw_request = False
                accel = [msg[k] / ACCEL_COUNTS_PER_G for k in RAW_KEYS[:3]]
                gyro = [msg[k] / GYRO_COUNTS_PER_DPS for k in RAW_KEYS[3:]]
                self._raw(accel, gyro, now, still, "raw IMU data in the feedback, filtered on the Pi")
            else:
                self.needs_raw_request = True
                if "r" in msg and "p" in msg and now - self._raw_time > cfg.IMU_MAX_AGE_S:
                    self._esp_angles(msg, now)
        elif kind == 1002 and has_raw:                      # General Driver board's reply to {"T":126}
            accel = [msg[k] / 1000.0 for k in RAW_KEYS[:3]]     # mg -> g
            gyro = [float(msg[k]) for k in RAW_KEYS[3:]]        # already deg/s
            self._raw(accel, gyro, now, still, "raw IMU data asked for with T:126, filtered on the Pi")

    def _raw(self, accel, gyro, now, still, source):
        dt = 0.0 if self._last_raw_t is None else min(max(now - self._last_raw_t, 0.0), 0.2)
        self._last_raw_t = self._raw_time = now
        ax, ay, az = accel
        roll_g = math.degrees(math.atan2(ay, az))                   # tilt from gravity alone
        pitch_g = math.degrees(math.atan2(-ax, math.hypot(ay, az)))

        steady = still and self._tilt_steady(now, roll_g, pitch_g)
        if steady and max(abs(g) for g in gyro) < BIAS_MAX_DPS:
            # Not driving, and gravity says the tilt isn't changing (so nobody is tipping it by
            # hand and the soil probe isn't levering it up): whatever the gyro reads now is its
            # zero offset. Plain average at first, then a slow running average (the offset
            # changes a little as the board warms up).
            self._bias_samples += 1
            k = max(1.0 / self._bias_samples, dt / (BIAS_TAU_S + dt))
            self._bias = [b + k * (g - b) for b, g in zip(self._bias, gyro)]
        elif not still:
            self._recent.clear()
        gx, gy, gz = (g - b for g, b in zip(gyro, self._bias))
        if self._roll is None:
            self._roll, self._pitch = roll_g, pitch_g
        else:
            k = cfg.IMU_FILTER_TAU_S / (cfg.IMU_FILTER_TAU_S + dt)
            self._roll = k * (self._roll + gx * dt) + (1 - k) * roll_g
            self._pitch = k * (self._pitch + gy * dt) + (1 - k) * pitch_g
        self._yaw += gz * dt
        self._publish(self._roll, self._pitch, self._yaw, (*accel, *gyro), now, source)

    def _tilt_steady(self, now, roll_g, pitch_g):
        """True if gravity's direction hasn't moved over the last second: the average tilt in
        the first and second half of that second differ by under STILL_MAX_CHANGE_DEG.
        (Averages, because single readings jitter.)"""
        self._recent.append((now, roll_g, pitch_g))
        while now - self._recent[0][0] > STILL_WINDOW_S:
            self._recent.popleft()
        n = len(self._recent)
        if n < 8 or now - self._recent[0][0] < 0.8 * STILL_WINDOW_S:
            return False                # not a full second of readings yet
        first, second = list(self._recent)[:n // 2], list(self._recent)[n // 2:]
        for i in (1, 2):
            change = sum(r[i] for r in second) / len(second) - sum(r[i] for r in first) / len(first)
            if abs(change) > STILL_MAX_CHANGE_DEG:
                return False
        return True

    def _esp_angles(self, msg, now):
        # The ESP32's own angles. Degrees on the General Driver board (and the first ROS Driver
        # firmware); radians on the May-2024 ROS Driver firmwares, which also send "odl" / "q0".
        scale = math.degrees(1.0) if ("odl" in msg or "q0" in msg) else 1.0
        self._publish(msg["r"] * scale, msg["p"] * scale, msg.get("y", 0.0) * scale, None, now,
                      "the ESP32's own angles (no raw IMU data received)")

    def _publish(self, roll, pitch, yaw, raw, now, source):
        if cfg.IMU_SWAP_ROLL_PITCH:
            roll, pitch = pitch, roll
        reading = {
            "roll": roll - cfg.IMU_ROLL_OFFSET_DEG,
            "pitch": pitch - cfg.IMU_PITCH_OFFSET_DEG,
            "roll_uncal": roll,           # before the level offsets (used by the level calibration)
            "pitch_uncal": pitch,
            "yaw": yaw,                   # heading, degrees; only changes in it mean anything
            "raw": raw,                   # (ax, ay, az in g, gx, gy, gz in deg/s as measured), or None
            "tracks": self._tracks,       # measured track speeds, m/s
            "source": source,
            "gyro_offset": tuple(self._bias),
        }
        with self.lock:
            self.reading, self.reading_time = reading, now
            self.count += 1

    def latest(self):
        """(reading, count): the newest reading, or None if nothing fresh, plus how many
        readings have arrived so far (it goes up by one with each new reading)."""
        with self.lock:
            if self.reading and time.monotonic() - self.reading_time <= cfg.IMU_MAX_AGE_S:
                return self.reading, self.count
            return None, self.count
