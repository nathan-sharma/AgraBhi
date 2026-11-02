#!/usr/bin/env python3
"""
  python3 waypoint_nav.py --gyro-test               # check gyro sign/units FIRST
  python3 waypoint_nav.py LAT LON [LAT LON ...]     # drive through waypoints in order
"""
import argparse, json, math, os, sys, threading, time

import serial
from pygnssutils import GNSSNTRIPClient

GPS_PORT, GPS_BAUD = '/dev/ttyAMA2', 460800
ESP_PORT, ESP_BAUD = '/dev/ttyACM0', 115200

NTRIP_SERVER, NTRIP_PORT, NTRIP_MOUNTPOINT = 'truertk.pointonenav.com', 2101, 'AUTO'
NTRIP_USER = 'redacted'
NTRIP_PASSWORD = 'redacted'
NTRIP_GGA_INTERVAL = 10

MIN_FIX_QUALITY = 4        
GPS_TIMEOUT = 1.0          
LOOP_HZ = 20
MAX_RUN_TIME = 600         # s safety timeout for the whole run
IMU_POLL_HZ = 40
GYRO_KEY = 'gz'            
GYRO_SCALE = 0.061           # multiply raw value to get deg/s
GYRO_SIGN = 1.0           # want: clockwise rotation should be positive. Flip if test shows the opposite.
BIAS_CAL_SECONDS = 2.0     #rover needs to be still
GYRO_STALE = 0.5          
COURSE_BASELINE = 0.30     # m of straight travel per GPS heading sample
MAX_TURN_IN_WINDOW = 15.0  # deg: ignore the sample if we turned more than this meanwhile
HEADING_GAIN = 0.3         # how hard each GPS sample pulls the heading (0..1)
BIAS_GAIN = 0.1            # how fast the gyro bias is re-learned (0..1)
MAX_BIAS_DRIFT = 3.0       # deg/s the bias may move away from the startup value
INIT_DRIVE_DIST = 1.0      # m driven straight at startup to find the initial heading
INIT_SPEED = 0.2           # m/s

CRUISE_SPEED = 0.3
SLOW_SPEED = 0.15
SLOW_RADIUS = 1.5          # m from waypoint where we slow down
MAX_TRACK_SPEED = 0.5      # hard clamp on any track command


KP_STEER = 0.006           # m/s of track-speed difference per degree of error  (TUNE)
MAX_CORRECTION = 0.20      # m/s max added/subtracted per track
PIVOT_ENTER = 45.0         # deg: error above this -> stop and pivot
PIVOT_EXIT = 10.0          # deg: pivot until error is below this
PIVOT_SPEED = 0.25         # m/s per track while pivoting (raise on grass)  (TUNE)
PIVOT_MIN = 0.12           # m/s, slowest pivot (must still overcome friction)
PIVOT_KP = 0.01            # m/s per degree, eases off the pivot as error shrinks
LOOKAHEAD = 1.0            # m, pure pursuit carrot distance

ARRIVE_RADIUS = 0.5        # m
CROSS_MAX_DIST = 3.0       # m: "crossed the finish line" only counts within this range

EARTH_R = 6371000.0

def wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


def wrap360(a):
    return a % 360.0


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class Frame:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.coslat = math.cos(math.radians(lat0))

    def xy(self, lat, lon):
        return (EARTH_R * math.radians(lon - self.lon0) * self.coslat,
                EARTH_R * math.radians(lat - self.lat0))


class HeadingEstimator:
    def __init__(self):
        self.lock = threading.Lock()
        self.heading = None
        self.bias = 0.0
        self.bias0 = 0.0
        self.last_t = None
        self.cal = None          # list while calibrating bias
        self.anchor = None       # (x, y, t, heading) start of current GPS course window
        self.total_turn = 0.0    # unwrapped integrated gyro angle (for --gyro-test)

    def start_bias_cal(self):
        with self.lock:
            self.cal = []

    def finish_bias_cal(self):
        with self.lock:
            if self.cal:
                self.bias = sum(self.cal) / len(self.cal)
            self.bias0 = self.bias
            n = len(self.cal or [])
            self.cal = None
            return self.bias, n

    def gyro(self, rate, t):
        """rate in deg/s, clockwise positive."""
        with self.lock:
            if self.cal is not None:
                self.cal.append(rate)
            dt = None if self.last_t is None else t - self.last_t
            self.last_t = t
            if dt is None or not (0 < dt < 0.5):
                return
            d = (rate - self.bias) * dt
            self.total_turn += d
            if self.heading is not None:
                self.heading = wrap360(self.heading + d)

    def set_heading(self, h):
        with self.lock:
            self.heading = wrap360(h)
            self.anchor = None

    def get(self):
        with self.lock:
            return self.heading

    def gps_update(self, x, y, t, straight):
        """Feed every new RTK position. `straight` = rover is driving forward
        (not pivoting), so course-over-ground is meaningful."""
        with self.lock:
            if not straight or self.heading is None:
                self.anchor = None
                return
            if self.anchor is None:
                self.anchor = (x, y, t, self.heading)
                return
            ax, ay, at, ah = self.anchor
            turned = wrap180(self.heading - ah)
            if abs(turned) > MAX_TURN_IN_WINDOW:
                self.anchor = (x, y, t, self.heading)
                return
            if math.hypot(x - ax, y - ay) < COURSE_BASELINE:
                return
            course = wrap360(math.degrees(math.atan2(x - ax, y - ay)))
            # GPS course is the average direction over the window, so compare it
            # with the gyro heading halfway through the window.
            ref = ah + turned / 2.0
            err = wrap180(course - ref)
            self.heading = wrap360(self.heading + HEADING_GAIN * err)
            T = max(t - at, 0.1)
            # Estimate was too low (err>0) -> we subtracted too much bias.
            self.bias = clamp(self.bias - BIAS_GAIN * err / T,
                              self.bias0 - MAX_BIAS_DRIFT, self.bias0 + MAX_BIAS_DRIFT)
            self.anchor = (x, y, t, self.heading)

class Navigator:
    def __init__(self):
        self.pivoting = False

    def step(self, x, y, heading, a, b):
        """a, b = (x, y) of segment start/end. Returns dict with track commands."""
        dx, dy = b[0] - a[0], b[1] - a[1]
        seg_len = max(math.hypot(dx, dy), 1e-6)
        ux, uy = dx / seg_len, dy / seg_len
        s = (x - a[0]) * ux + (y - a[1]) * uy              # along-track progress
        cross = -(x - a[0]) * uy + (y - a[1]) * ux          # cross-track (+ = right of path)
        dist = math.hypot(b[0] - x, b[1] - y)

        out = dict(s=s, seg_len=seg_len, cross=cross, dist=dist,
                   arrived=False, mode='drive', err=0.0, l=0.0, r=0.0)

        if dist <= ARRIVE_RADIUS or (s >= seg_len and dist <= CROSS_MAX_DIST):
            out['arrived'] = True
            out['mode'] = 'arrived'
            return out

        # pure pursuit carrot on the line
        sc = min(max(s, 0.0) + LOOKAHEAD, seg_len)
        cx, cy = a[0] + ux * sc, a[1] + uy * sc
        bearing = math.degrees(math.atan2(cx - x, cy - y))
        err = wrap180(bearing - heading)                    # + = target is to the right
        out['err'] = err

        if not self.pivoting and abs(err) > PIVOT_ENTER:
            self.pivoting = True
        elif self.pivoting and abs(err) < PIVOT_EXIT:
            self.pivoting = False

        if self.pivoting:
            p = clamp(PIVOT_KP * abs(err), PIVOT_MIN, PIVOT_SPEED)
            sgn = 1.0 if err > 0 else -1.0                  # right turn: left track fwd, right back
            out.update(mode='pivot', l=sgn * p, r=-sgn * p)
            return out

        v = SLOW_SPEED if dist < SLOW_RADIUS else CRUISE_SPEED
        corr = clamp(KP_STEER * err, -MAX_CORRECTION, MAX_CORRECTION)
        out.update(mode='drive',
                   l=clamp(v + corr, 0.0, MAX_TRACK_SPEED),
                   r=clamp(v - corr, 0.0, MAX_TRACK_SPEED))
        return out

class Esp:
    def __init__(self, port, baud):
        self.ser = serial.Serial(port, baud, timeout=0.05)
        self.wlock = threading.Lock()
        self.on_rate = None
        self.last_rate_t = 0.0
        self.show_raw = 0
        self._stop = threading.Event()

    def write(self, obj):
        with self.wlock:
            self.ser.write((json.dumps(obj) + "\n").encode())

    def drive(self, l, r):
        l = clamp(l, -MAX_TRACK_SPEED, MAX_TRACK_SPEED)
        r = clamp(r, -MAX_TRACK_SPEED, MAX_TRACK_SPEED)
        self.write({"T": 1, "L": round(l, 3), "R": round(r, 3)})

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def close(self):
        self._stop.set()
        time.sleep(0.1)
        self.ser.close()

    def _loop(self):
        period = 1.0 / IMU_POLL_HZ
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self.write({"T": 126})              # request IMU data
                time.sleep(0.01)
                while self.ser.in_waiting:
                    self._handle(self.ser.readline().decode('utf-8', errors='ignore').strip())
            except Exception as e:
                print(f"[ESP] {e}")
                time.sleep(0.2)
            time.sleep(max(0.0, period - (time.time() - t0)))

    def _handle(self, line):
        if not line.startswith('{'):
            return
        try:
            d = json.loads(line)
        except ValueError:
            return
        if self.show_raw > 0:
            print("[ESP raw]", line)
            self.show_raw -= 1
        if GYRO_KEY in d:
            t = time.time()
            self.last_rate_t = t
            if self.on_rate:
                self.on_rate(float(d[GYRO_KEY]) * GYRO_SCALE * GYRO_SIGN, t)

lock = threading.Lock()
latest = None            # (timestamp, lat, lon, fix_quality)
gps_serial = None


def parse_gga(s):
    p = s.split(',')
    if len(p) < 7 or not p[2] or not p[4]:
        return None
    lat = float(p[2][:2]) + float(p[2][2:]) / 60.0
    lon = float(p[4][:3]) + float(p[4][3:]) / 60.0
    if p[3] == 'S': lat = -lat
    if p[5] == 'W': lon = -lon
    return lat, lon, int(p[6] or 0)


def gps_reader():
    global latest
    while True:
        try:
            raw = gps_serial.readline().decode('utf-8', errors='ignore').strip()
            if raw.startswith(('$GNGGA', '$GPGGA')):
                g = parse_gga(raw)
                if g:
                    with lock:
                        latest = (time.time(), *g)
        except Exception as e:
            print(f"[GPS] {e}")
            time.sleep(0.5)


def ntrip_thread(client, lat, lon):
    try:
        client.run(server=NTRIP_SERVER, port=NTRIP_PORT, mountpoint=NTRIP_MOUNTPOINT,
                   ntripuser=NTRIP_USER, ntrippassword=NTRIP_PASSWORD,
                   ggainterval=NTRIP_GGA_INTERVAL, ggamode=0,
                   reflat=lat, reflon=lon, refalt=0.0, refsep=0.0, output=gps_serial)
    except Exception:
        import traceback; traceback.print_exc()


def get_fix():
    with lock:
        f = latest
    if f is None or time.time() - f[0] > GPS_TIMEOUT or f[3] < MIN_FIX_QUALITY:
        return None
    return f

def gyro_test(esp, est):
    print("Gyro test. Keep the rover still for the bias calibration...")
    esp.show_raw = 5
    est.start_bias_cal()
    time.sleep(BIAS_CAL_SECONDS)
    bias, n = est.finish_bias_cal()
    if n == 0:
        sys.exit("No gyro samples received. Check the raw [ESP raw] lines above and set GYRO_KEY.")
    print(f"Bias = {bias:.3f} deg/s from {n} samples.")
    est.set_heading(0.0)
    est.total_turn = 0.0
    print("Now rotate the rover 90 deg CLOCKWISE by hand. Ctrl-C when done.")
    try:
        while True:
            print(f"heading = {est.get():7.1f} deg   (integrated total {est.total_turn:7.1f})")
            time.sleep(0.25)
    except KeyboardInterrupt:
        tot = est.total_turn
        print(f"\nIntegrated: {tot:.1f} deg.")
        if abs(tot) < 5:
            print("Barely moved: wrong GYRO_KEY, or the rover wasn't rotated.")
        else:
            print("If you rotated exactly 90 deg clockwise:")
            if tot < 0:
                print("  -> sign is wrong: flip GYRO_SIGN.")
            print(f"  -> multiply GYRO_SCALE by {90.0 / abs(tot):.3f}")


def init_heading(esp, est, frame):
    print(f"Finding initial heading: driving straight {INIT_DRIVE_DIST} m. Clear the path ahead!")
    period = 1.0 / LOOP_HZ
    fix = get_fix()
    x0, y0 = frame.xy(fix[1], fix[2])
    t_start = time.time()
    while True:
        t_loop = time.time()
        fix = get_fix()
        if fix is None or t_loop - t_start > 20:
            esp.drive(0, 0)
            sys.exit("Lost RTK fix (or timeout) during heading init.")
        x, y = frame.xy(fix[1], fix[2])
        if math.hypot(x - x0, y - y0) >= INIT_DRIVE_DIST:
            break
        esp.drive(INIT_SPEED, INIT_SPEED)
        time.sleep(max(0, period - (time.time() - t_loop)))
    esp.drive(0, 0)
    h = math.degrees(math.atan2(x - x0, y - y0))
    est.set_heading(h)
    print(f"Initial heading = {wrap360(h):.1f} deg")
    return (x, y)


def navigate(esp, est, frame, waypoints, start_xy):
    nav = Navigator()
    period = 1.0 / LOOP_HZ
    run_start = time.time()
    prev = start_xy
    last_fix_t = None
    last_print = 0.0

    for i, wp in enumerate(waypoints, 1):
        print(f"--- Waypoint {i}/{len(waypoints)} ---")
        mode, l_cmd, r_cmd = 'pivot', 0.0, 0.0
        while True:
            t_loop = time.time()
            if t_loop - run_start > MAX_RUN_TIME:
                esp.drive(0, 0); print("Run timeout - stopped."); return False

            fix = get_fix()
            if fix is None:
                esp.drive(0, 0)
                print("No valid RTK fix - stopped, waiting...")
                time.sleep(period); continue
            if t_loop - esp.last_rate_t > GYRO_STALE:
                esp.drive(0, 0)
                print("Gyro data stale - stopped, waiting...")
                time.sleep(period); continue

            x, y = frame.xy(fix[1], fix[2])
            if fix[0] != last_fix_t:
                last_fix_t = fix[0]
                straight = (mode == 'drive' and (l_cmd + r_cmd) / 2.0 > 0.08)
                est.gps_update(x, y, fix[0], straight)

            heading = est.get()
            res = nav.step(x, y, heading, prev, wp)
            if res['arrived']:
                esp.drive(0, 0)
                print(f"Arrived at waypoint {i}: {res['dist']:.2f} m away.")
                break

            mode, l_cmd, r_cmd = res['mode'], res['l'], res['r']
            esp.drive(l_cmd, r_cmd)

            if t_loop - last_print > 0.5:
                last_print = t_loop
                print(f"{mode:5s} dist={res['dist']:5.2f} xtrack={res['cross']:+5.2f} "
                      f"hdg={heading:5.1f} err={res['err']:+6.1f} L={l_cmd:+.2f} R={r_cmd:+.2f}")
            time.sleep(max(0, period - (time.time() - t_loop)))
        prev = wp
    print("All waypoints reached.")
    return True


def main():
    global gps_serial
    ap = argparse.ArgumentParser()
    ap.add_argument('--gyro-test', action='store_true')
    ap.add_argument('coords', nargs='*', type=float, help='LAT LON [LAT LON ...]')
    args = ap.parse_args()

    if not args.gyro_test:
        if len(args.coords) < 2 or len(args.coords) % 2:
            sys.exit("Give waypoints as LAT LON [LAT LON ...]  (or use --gyro-test)")
        if not NTRIP_USER:
            sys.exit("Set NTRIP_USER and NTRIP_PASSWORD environment variables.")

    est = HeadingEstimator()
    esp = Esp(ESP_PORT, ESP_BAUD)
    esp.on_rate = est.gyro
    time.sleep(2)
    esp.start()

    try:
        if args.gyro_test:
            gyro_test(esp, est)
            return

        gps_serial = serial.Serial(GPS_PORT, GPS_BAUD, timeout=1)
        threading.Thread(target=gps_reader, daemon=True).start()

        print("Waiting for initial fix...")
        while True:
            with lock:
                f = latest
            if f:
                break
            time.sleep(0.5)

        client = GNSSNTRIPClient(None, verbosity=1)
        threading.Thread(target=ntrip_thread, args=(client,), daemon=True).start()

        print(f"Waiting for RTK fix quality >= {MIN_FIX_QUALITY}...")
        while get_fix() is None:
            time.sleep(0.5)

        # gyro bias: rover is stationary right now
        time.sleep(0.5)
        if time.time() - esp.last_rate_t > GYRO_STALE:
            sys.exit("No gyro data. Run --gyro-test and check GYRO_KEY.")
        print("Calibrating gyro bias - keep the rover still...")
        est.start_bias_cal()
        time.sleep(BIAS_CAL_SECONDS)
        bias, n = est.finish_bias_cal()
        print(f"Gyro bias {bias:.3f} deg/s ({n} samples)")

        fix = get_fix()
        frame = Frame(fix[1], fix[2])
        pts = [frame.xy(args.coords[i], args.coords[i + 1]) for i in range(0, len(args.coords), 2)]

        start_xy = init_heading(esp, est, frame)
        navigate(esp, est, frame, pts, start_xy)
    except KeyboardInterrupt:
        print("\nAborted.")
    finally:
        try:
            esp.drive(0, 0)
        except Exception:
            pass
        esp.close()
        if gps_serial:
            gps_serial.close()


if __name__ == "__main__":
    main()
