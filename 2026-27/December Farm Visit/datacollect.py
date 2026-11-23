# datacollect.py
# Reads the GPS (with RTK corrections from Point One) and the soil sensor, and logs
# samples to a CSV file on the Pi.
#   Test on its own:  python datacollect.py     (prints live readings; logs nothing)

import csv
import os
import threading
import time
import traceback
from datetime import datetime

import serial
from pygnssutils import GNSSNTRIPClient

import roverconfig as cfg

CSV_HEADER = ["sample_id", "timestamp", "latitude", "longitude", "altitude_m",
              "fix_quality", "moisture", "temperature"]


def parse_nmea_gga(line):
    """Turn a $GNGGA / $GPGGA sentence into (lat, lon, alt_msl, geoid_sep, fix_quality).
    Returns None if the sentence is damaged or has no position fix."""
    start, star = line.find("$"), line.rfind("*")
    if start < 0 or star < start:
        return None
    body = line[start + 1:star]
    try:
        checksum = 0
        for ch in body:
            checksum ^= ord(ch)
        if checksum != int(line[star + 1:star + 3], 16):
            return None
        parts = body.split(",")
        if parts[0] not in ("GNGGA", "GPGGA") or len(parts) < 12:
            return None
        raw_lat, lat_dir, raw_lon, lon_dir, fix_quality = parts[2:7]
        if not raw_lat or not raw_lon or not parts[9] or fix_quality in ("", "0"):
            return None
        lat = float(raw_lat[:2]) + float(raw_lat[2:]) / 60.0
        if lat_dir == "S":
            lat = -lat
        lon = float(raw_lon[:3]) + float(raw_lon[3:]) / 60.0
        if lon_dir == "W":
            lon = -lon
        alt_msl = float(parts[9])
        geoid_sep = float(parts[11]) if parts[11] else 0.0
        return lat, lon, alt_msl, geoid_sep, fix_quality
    except (ValueError, IndexError):
        return None


class DataCollector:
    def __init__(self, link):
        self.link = link              # ArduinoLink: the soil readings come through it
        self.lock = threading.Lock()
        self.fix = None               # latest (lat, lon, alt_msl, geoid_sep, fix_quality)
        self.fix_time = 0.0
        self.next_id = self._next_sample_id()
        self.gps_serial = serial.Serial(cfg.GPS_PORT, cfg.GPS_BAUD, timeout=1)
        threading.Thread(target=self._gps_reader, daemon=True).start()
        if cfg.USE_NTRIP:
            threading.Thread(target=self._ntrip_runner, daemon=True).start()

    # ---- GPS ----
    def _gps_reader(self):
        while True:
            try:
                raw = self.gps_serial.readline().decode("utf-8", errors="ignore")
            except Exception as e:
                print(f"[GPS] read error: {e}")
                time.sleep(1)
                continue
            if "GGA" in raw:
                parsed = parse_nmea_gga(raw.strip())
                if parsed:
                    with self.lock:
                        self.fix = parsed
                        self.fix_time = time.monotonic()

    def latest_fix(self):
        """Latest (lat, lon, alt_msl, geoid_sep, fix_quality), or None if there's no fresh fix."""
        with self.lock:
            if self.fix and time.monotonic() - self.fix_time <= cfg.MAX_READING_AGE_S:
                return self.fix
        return None

    def latest_fix_with_time(self):
        """(fix, time it arrived), or (None, None) if there's no fresh fix. The arrival time tells
        a new fix from the same one read twice (used by stabilitylog.py)."""
        with self.lock:
            if self.fix and time.monotonic() - self.fix_time <= cfg.MAX_READING_AGE_S:
                return self.fix, self.fix_time
        return None, None

    def _ntrip_runner(self):
        # Same approach as datacollecter.py: the first GPS fix is used as the reference position.
        print("[NTRIP] Waiting for a first GPS fix to use as the reference position...")
        fix = None
        while fix is None:
            time.sleep(0.5)
            fix = self.latest_fix()
        lat, lon, alt, sep, _ = fix
        print(f"[NTRIP] Reference position lat={lat:.7f}, lon={lon:.7f}. Starting corrections.")
        try:
            ntrip = GNSSNTRIPClient(None)
            while True:
                # The client gives up after a few failed retries (e.g. the internet drops),
                # so start it again whenever it has stopped.
                if not ntrip.connected:
                    ntrip.run(
                        server=cfg.NTRIP_SERVER,
                        port=cfg.NTRIP_PORT,
                        mountpoint=cfg.NTRIP_MOUNTPOINT,
                        ntripuser=cfg.NTRIP_USER,
                        ntrippassword=cfg.NTRIP_PASSWORD,
                        ggainterval=cfg.NTRIP_GGA_INTERVAL,
                        ggamode=1,              # fixed reference position
                        reflat=lat,
                        reflon=lon,
                        refalt=alt,
                        refsep=sep,
                        output=self.gps_serial,
                    )
                time.sleep(15)
        except Exception:
            print("[NTRIP] CRASHED (GPS keeps working, but without RTK corrections):")
            traceback.print_exc()

    # ---- CSV logging ----
    def _next_sample_id(self):
        """Carry on numbering from the last sample already in the CSV."""
        last = 0
        if os.path.exists(cfg.CSV_PATH):
            with open(cfg.CSV_PATH, newline="") as f:
                for row in csv.reader(f):
                    if row and row[0].isdigit():
                        last = max(last, int(row[0]))
        return last + 1

    def take_sample(self):
        """Append one row to the CSV and return it. Anything missing is left blank."""
        fix = self.latest_fix()
        soil = self.link.latest_soil()
        lat = lon = alt = fix_quality = moisture = temperature = ""
        if fix:
            lat, lon, alt, fix_quality = f"{fix[0]:.7f}", f"{fix[1]:.7f}", fix[2], fix[4]
        if soil:
            moisture, temperature = soil
        row = [self.next_id, datetime.now().isoformat(timespec="seconds"),
               lat, lon, alt, fix_quality, moisture, temperature]
        new_file = not os.path.exists(cfg.CSV_PATH)
        with open(cfg.CSV_PATH, "a", newline="") as f:
            writer = csv.writer(f)
            if new_file:
                writer.writerow(CSV_HEADER)
            writer.writerow(row)
            f.flush()
            os.fsync(f.fileno())    # make sure it's on the SD card even if power is cut
        self.next_id += 1
        return row


if __name__ == "__main__":
    from arduinolink import ArduinoLink
    dc = DataCollector(ArduinoLink())
    print("Live readings (nothing is logged). Ctrl+C to quit.")
    try:
        while True:
            fix, soil = dc.latest_fix(), dc.link.latest_soil()
            print("GPS:", f"{fix[0]:.7f}, {fix[1]:.7f}  alt {fix[2]} m  fix quality {fix[4]}" if fix else "no fix",
                  "| soil (moisture, temp):", soil if soil else "no reading")
            time.sleep(1)
    except KeyboardInterrupt:
        pass
