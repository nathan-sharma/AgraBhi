# stabilitylog.py
# Stability logging: GPS position + IMU tilt, many times a second, for the path-tracking and
# tilt measurements. Press P on the laptop to start a run, P again to stop it.
#
# Every run goes in its own CSV file on the Pi, numbered in order:
#     stability_logs/run_0007_20261123_140512.csv
# Pausing and resuming gives two runs (e.g. run 7 and run 8). The laptop shows a short
# summary when a run stops (GPS rate, % of time RTK fixed, worst roll / pitch).
#
# One row every 1/STABILITY_LOG_HZ s (20 per second). Columns:
#   timestamp       Pi clock (same clock as the timestamps in soil_samples.csv)
#   t_s             seconds since this run started
#   gps_new         1 = a GPS fix that no earlier row had. FOR PATH TRACKING USE ONLY THESE ROWS
#                   (one row per GPS fix). 0 = position repeated from the previous fix.
#   latitude, longitude, altitude_m
#   fix_quality     4 = RTK fixed, 5 = RTK float, 2 = DGPS, 1 = GPS only
#   roll_deg, pitch_deg   tilt from the ESP32's IMU, with the level offsets removed
#   yaw_deg         gyro heading change since the run started (relative only; drifts slowly)
#   ax_g, ay_g, az_g, gx_dps, gy_dps, gz_dps   raw IMU readings (board axes; gyro as measured,
#                   before its zero offset is removed), kept so the tilt can be re-worked later
#   cmd_left, cmd_right       track speeds the Pi commanded, m/s
#   track_left, track_right   track speeds the ESP32 measured, m/s
#   event           e.g. "sample 12" on the row where soil sample 12 was logged
# A blank cell means that reading was missing at that moment.
#
#   Test on its own (stop rovernode.py first; only one program can hold the ports):
#     python stabilitylog.py          live tilt + GPS readout (logs nothing)
#     python stabilitylog.py level    level calibration: rover parked still on flat ground

import csv
import os
import re
import sys
import threading
import time
from datetime import datetime

import roverconfig as cfg

RTK_FRESH_S = 1.0     # for "% of time RTK fixed": a row counts as fixed only if an RTK-fixed
                      # position arrived within this long (so GPS outages count against it)

HEADER = ["timestamp", "t_s", "gps_new", "latitude", "longitude", "altitude_m", "fix_quality",
          "roll_deg", "pitch_deg", "yaw_deg", "ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps",
          "cmd_left", "cmd_right", "track_left", "track_right", "event"]


def blank_if_none(v):
    return "" if v is None else v


class StabilityLogger:
    def __init__(self, drive, data):
        self.drive = drive            # Drive: commanded speeds, and drive.imu for the tilt
        self.data = data              # DataCollector: GPS fixes
        self.lock = threading.Lock()
        self.thread = None
        self.file = None
        self.running = False
        self.last_result = None       # summary of the last finished run (for the laptop)
        os.makedirs(cfg.STABILITY_DIR, exist_ok=True)
        self.run_id = self._last_run_id()

    def _last_run_id(self):
        """Carry on numbering from the runs already in the folder."""
        last = 0
        for name in os.listdir(cfg.STABILITY_DIR):
            m = re.match(r"run_(\d+)_", name)
            if m:
                last = max(last, int(m.group(1)))
        return last

    # ---- start / stop (called from rovernode.py) ----
    def start(self):
        """Start a new run. Does nothing if one is already running. Raises OSError if the
        file can't be created."""
        with self.lock:
            if self.running:
                return
            run_id = self.run_id + 1
            path = os.path.join(cfg.STABILITY_DIR, f"run_{run_id:04d}_{datetime.now():%Y%m%d_%H%M%S}.csv")
            self.file = open(path, "w", newline="")
            self.writer = csv.writer(self.file)
            self.writer.writerow(HEADER)
            self.run_id, self.path = run_id, path
            self.t0 = time.monotonic()
            self.rows = self.gps_fixes = self.fixed_rows = 0
            self.max_roll = self.max_pitch = None
            self.last_fix_time = None
            self.yaw0 = None
            self.events = []
            self.error = None
            self.running = True
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
        print(f"[LOG] Run {self.run_id} started -> {self.path}")

    def stop(self):
        """Finish the current run and close its file. Does nothing if nothing is running."""
        with self.lock:
            self.running = False
            thread = self.thread
        if thread:
            thread.join(timeout=2)
        with self.lock:
            if self.file:
                self._finish()

    def mark(self, text):
        """Note an event (e.g. a soil sample) on the next row, if a run is going."""
        with self.lock:
            if self.running:
                self.events.append(text)

    def status(self):
        """Short text for the laptop:
             ON,run,imu,fix                              while logging
             OFF,run,seconds,gps_hz,rtk_fixed_%,max_roll,max_pitch[,error]   after a run
             OFF                                         nothing logged since startup"""
        with self.lock:
            if self.running:
                imu, _ = self.drive.imu.latest()
                fix = self.data.latest_fix()
                return f"ON,{self.run_id},{'OK' if imu else 'NONE'},{fix[4] if fix else 0}"
            return self.last_result or "OFF"

    # ---- the logging itself ----
    def _loop(self):
        period = 1.0 / cfg.STABILITY_LOG_HZ
        next_row = last_sync = time.monotonic()
        while True:
            with self.lock:
                if not self.running:
                    return
                try:
                    self._write_row()
                    if time.monotonic() - last_sync >= 1.0:
                        self._sync()        # at most ~1 s of data lost if the power is cut
                        last_sync = time.monotonic()
                except OSError as e:        # e.g. SD card full: end the run, say why
                    print(f"[LOG] Write failed, run {self.run_id} stopped: {e}")
                    self.error = "WRITE ERROR"
                    self.running = False
                    self._finish()
                    return
            next_row += period
            delay = next_row - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_row = time.monotonic()     # fell behind (slow SD card): don't try to catch up

    def _write_row(self):
        now = time.monotonic()
        fix, fix_time = self.data.latest_fix_with_time()
        imu, _ = self.drive.imu.latest()

        gps_new, gps = 0, ["", "", "", ""]
        if fix:
            gps = [f"{fix[0]:.9f}", f"{fix[1]:.9f}", fix[2], fix[4]]
            if fix_time != self.last_fix_time:
                gps_new = 1
                self.last_fix_time = fix_time
                self.gps_fixes += 1
        if fix and fix[4] == "4" and now - fix_time <= RTK_FRESH_S:
            self.fixed_rows += 1        # this moment (1/STABILITY_LOG_HZ s) had RTK fixed

        tilt, raw, tracks = ["", "", ""], [""] * 6, ["", ""]
        if imu:
            if self.yaw0 is None:
                self.yaw0 = imu["yaw"]
            roll, pitch = imu["roll"], imu["pitch"]
            tilt = [round(roll, 2), round(pitch, 2), round(imu["yaw"] - self.yaw0, 2)]
            self.max_roll = max(abs(roll), self.max_roll or 0.0)
            self.max_pitch = max(abs(pitch), self.max_pitch or 0.0)
            if imu["raw"]:
                raw = [round(v, 4) for v in imu["raw"][:3]] + [round(v, 2) for v in imu["raw"][3:]]
            tracks = [blank_if_none(v) for v in imu["tracks"]]

        event = "; ".join(self.events)
        self.events = []
        self.writer.writerow([datetime.now().isoformat(timespec="milliseconds"), f"{now - self.t0:.3f}",
                              gps_new, *gps, *tilt, *raw, *self.drive.last_cmd, *tracks, event])
        self.rows += 1

    def _sync(self):
        self.file.flush()
        os.fsync(self.file.fileno())

    def _finish(self):
        """Close the file and make the summary. Called with the lock held."""
        try:
            self._sync()
        except (OSError, ValueError):
            pass
        self.file.close()
        self.file = None
        seconds = time.monotonic() - self.t0
        gps_hz = self.gps_fixes / seconds if seconds > 0 else 0.0
        fixed_pct = 100.0 * self.fixed_rows / self.rows if self.rows else 0.0     # % of the run's time
        roll = "" if self.max_roll is None else f"{self.max_roll:.1f}"
        pitch = "" if self.max_pitch is None else f"{self.max_pitch:.1f}"
        self.last_result = f"OFF,{self.run_id},{seconds:.0f},{gps_hz:.1f},{fixed_pct:.0f},{roll},{pitch}"
        if self.error:
            self.last_result += f",{self.error}"
        print(f"[LOG] Run {self.run_id} stopped: {self.rows} rows in {seconds:.0f} s, "
              f"GPS {gps_hz:.1f} fixes/s, RTK fixed {fixed_pct:.0f}% of the time, "
              f"max |roll| {roll or '-'} deg, max |pitch| {pitch or '-'} deg  -> {self.path}")


# ---- Stand-alone checks ----
def live_readout(drive, data):
    print("Live readings (nothing is logged). Ctrl+C to quit.\n"
          "Checks:  lift the rover's nose -> PITCH should change (not roll; if it's roll, set\n"
          "         IMU_SWAP_ROLL_PITCH = True).  Tip it sideways -> ROLL should change.\n"
          "         Turn it one full circle -> yaw should change by about 360.\n"
          "         GPS should show about 10 fixes/s (5 is the least for path tracking).\n")
    last_count, last_fix_time, fixes = 0, None, 0
    shown_feedback, last_source = False, None
    next_print = time.monotonic() + 1.0
    while True:
        if not shown_feedback and drive.imu.last_feedback:
            shown_feedback = True
            print(f"The ESP32's feedback looks like this:\n  {drive.imu.last_feedback}\n")
        fix, fix_time = data.latest_fix_with_time()
        if fix and fix_time != last_fix_time:
            last_fix_time = fix_time
            fixes += 1
        if time.monotonic() >= next_print:
            next_print += 1.0
            imu, count = drive.imu.latest()
            if imu and imu["source"] != last_source:
                last_source = imu["source"]
                print(f"Tilt from: {last_source}")
            if imu:
                accel = ""
                if imu["raw"]:
                    ax, ay, az = imu["raw"][:3]
                    accel = f"  |accel| {(ax * ax + ay * ay + az * az) ** 0.5:.2f} g"
                tilt = (f"roll {imu['roll']:+6.1f}  pitch {imu['pitch']:+6.1f}  yaw {imu['yaw']:+7.1f}"
                        f"{accel}  ({count - last_count} readings/s)")
            else:
                tilt = "NO IMU DATA from the ESP32"
            gps = f"GPS {fixes} fixes/s, fix quality {fix[4]}" if fix else "GPS: no fix"
            print(f"{tilt} | {gps}")
            last_count, fixes = count, 0
        time.sleep(0.01)


def level_calibration(drive, seconds=10):
    print("Level calibration: park the rover on flat, level ground and don't touch it.")
    time.sleep(5)       # lets the gyro's zero offset settle first
    print(f"Measuring for {seconds} s...")
    rolls, pitches, z = [], [], []
    last_count = 0
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        imu, count = drive.imu.latest()
        if imu and count != last_count:
            last_count = count
            rolls.append(imu["roll_uncal"])
            pitches.append(imu["pitch_uncal"])
            if imu["raw"]:
                z.append(imu["raw"][2])
        time.sleep(0.01)
    if len(rolls) < 10:
        sys.exit("Not enough IMU readings from the ESP32. Is ESP_PORT right, and is the rover powered on?")
    if z and sum(z) / len(z) < 0.8:
        print("WARNING: the IMU's z axis isn't pointing up, so its mounting differs from what this "
              "code assumes. The roll / pitch numbers may be wrong.")
    roll, pitch = sum(rolls) / len(rolls), sum(pitches) / len(pitches)
    print(f"\nPut these two lines in roverconfig.py (replacing the old ones):\n"
          f"IMU_ROLL_OFFSET_DEG = {roll:.2f}\n"
          f"IMU_PITCH_OFFSET_DEG = {pitch:.2f}\n\n"
          "If the ground might not be perfectly level: run this again with the rover turned 180 deg\n"
          "on the same spot, and use the average of the two runs' numbers.")


if __name__ == "__main__":
    from drive import Drive
    d = Drive()
    try:
        if sys.argv[1:] == ["level"]:
            level_calibration(d)
        else:
            from datacollect import DataCollector
            live_readout(d, DataCollector(None))    # None: no Arduino needed just to read the GPS
    except KeyboardInterrupt:
        pass
    finally:
        d.close()
