#this is the code for the pi we'll walk around with 
#it reads the sensor data from arduino and gets RTK GPS data from pointonenav
#then it sends it to the laptop over the usb radio

import serial
import threading
import time
import logging
from pygnssutils import GNSSNTRIPClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
GPS_PORT = '/dev/ttyAMA2'
GPS_BAUD = 460800
NTRIP_SERVER = 'truertk.pointonenav.com'
NTRIP_PORT = 2101
NTRIP_MOUNTPOINT = 'AUTO'
NTRIP_USER = 'redacted'
NTRIP_PASSWORD = 'redacted'
NTRIP_GGA_INTERVAL = 10 
USE_FIXED_REF = True
LORA_PORT = '/dev/ttyACM0'
LORA_BAUD = 115200
ARDUINO_PORT = '/dev/ttyACM1'
ARDUINO_BAUD = 9600

latest_gps = None
latest_gps_raw = None
latest_moisture = None
lock = threading.Lock()

gps_serial = None


def parse_nmea_gga(nmea_str):
    parts = nmea_str.split(',')
    if len(parts) < 12:
        return None
    raw_lat, lat_dir = parts[2], parts[3]
    raw_lon, lon_dir = parts[4], parts[5]
    fix_quality = parts[6]
    alt_msl_str = parts[9]
    geoid_sep_str = parts[11]
    if not raw_lat or not raw_lon or not alt_msl_str:
        return None
    lat_deg = float(raw_lat[:2]) + float(raw_lat[2:]) / 60.0
    if lat_dir == 'S':
        lat_deg = -lat_deg
    lon_deg = float(raw_lon[:3]) + float(raw_lon[3:]) / 60.0
    if lon_dir == 'W':
        lon_deg = -lon_deg
    alt_msl = float(alt_msl_str)
    geoid_sep = float(geoid_sep_str) if geoid_sep_str else 0.0
    display = f"{lat_deg:.7f},{lon_deg:.7f},{alt_msl},{fix_quality}"
    return display, lat_deg, lon_deg, alt_msl, geoid_sep, fix_quality


def gps_reader():
    global latest_gps, latest_gps_raw
    while True:
        try:
            raw = gps_serial.readline().decode('utf-8', errors='ignore')
            if not raw:
                continue
            if '$GNGGA' in raw or '$GPGGA' in raw:
                parsed = parse_nmea_gga(raw.strip())
                if parsed:
                    display, lat, lon, alt, sep, fix_q = parsed
                    with lock:
                        latest_gps = display
                        latest_gps_raw = (lat, lon, alt, sep, fix_q)
        except Exception as e:
            print(f"[GPS thread] error: {e}")
            time.sleep(1)


def wait_for_initial_fix(timeout=None):
    print("Waiting for an initial GPS fix to use as the reference position...")
    start = time.time()
    while True:
        with lock:
            raw = latest_gps_raw
        if raw is not None:
            lat, lon, alt, sep, fix_q = raw
            print(f"Captured reference position: lat={lat:.7f}, lon={lon:.7f}, "
                  f"alt(MSL)={alt} m, geoid_sep={sep} m (fix quality={fix_q})")
            return lat, lon, alt, sep
        if timeout is not None and (time.time() - start) > timeout:
            raise TimeoutError("No GPS fix received within timeout; check antenna/sky view.")
        time.sleep(0.5)


def start_ntrip_client(ntrip, ref_lat=0.0, ref_lon=0.0, ref_alt=0.0, ref_sep=0.0):
    try:
        print("Starting NTRIP client...")
        result = ntrip.run(
            server=NTRIP_SERVER,
            port=NTRIP_PORT,
            mountpoint=NTRIP_MOUNTPOINT,
            ntripuser=NTRIP_USER,
            ntrippassword=NTRIP_PASSWORD,
            ggainterval=NTRIP_GGA_INTERVAL,
            ggamode=1 if USE_FIXED_REF else 0, 
            reflat=ref_lat,
            reflon=ref_lon,
            refalt=ref_alt,
            refsep=ref_sep,
            output=gps_serial,
        )
        print(f"NTRIP client run() returned: {result}")
    except Exception:
        import traceback
        print("[NTRIP thread] CRASHED:")
        traceback.print_exc()


def moisture_reader():
    global latest_moisture
    ard = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=1)
    print("Connected to Arduino.")
    try:
        while True:
            line = ard.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith("DATA,"):
                parts = line.split(',')
                if len(parts) == 3:
                    moisture, temperature = parts[1], parts[2]
                    with lock:
                        latest_moisture = f"{moisture},{temperature}"
    except Exception as e:
        print(f"[Moisture thread] error: {e}")
    finally:
        ard.close()


def run_transmitter():
    global gps_serial
    lora = serial.Serial(LORA_PORT, LORA_BAUD, timeout=1)

    gps_serial = serial.Serial(GPS_PORT, GPS_BAUD, timeout=1)
    print("Opened GPS receiver serial port.")

    t_gps = threading.Thread(target=gps_reader, daemon=True)
    t_gps.start()

    if USE_FIXED_REF:
        ref_lat, ref_lon, ref_alt, ref_sep = wait_for_initial_fix(timeout=120)
    else:
        ref_lat = ref_lon = ref_alt = ref_sep = 0.0
    ntrip = GNSSNTRIPClient(None, verbosity=3)

    t_ntrip = threading.Thread(
        target=start_ntrip_client, args=(ntrip, ref_lat, ref_lon, ref_alt, ref_sep), daemon=True
    )
    t_moisture = threading.Thread(target=moisture_reader, daemon=True)
    t_ntrip.start()
    t_moisture.start()

    print("Transmitting combined GPS + moisture data over LoRa...\n")
    try:
        while True:
            with lock:
                gps = latest_gps
                moisture = latest_moisture

            if gps is not None:
                moisture_field = moisture if moisture is not None else "NA,NA"
                payload = f"{gps},{moisture_field}\n"
                lora.write(payload.encode('utf-8'))
                print(f"Sent: {payload.strip()}")
            else:
                print("Waiting for GPS fix...")

            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping transmitter.")
    finally:
        lora.close()
        gps_serial.close()


if __name__ == "__main__":
    run_transmitter()