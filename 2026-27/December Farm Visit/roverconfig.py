# roverconfig.py
# Settings for everything that runs on the Pi. All the other Pi files import this,
# so ports and tuning numbers only need changing here.

import os

ROVER_ID = "PI1"          # must match ROVER_ID in laptopnode.py
LAPTOP_ID = "LAPTOP"      # must match LAPTOP_ID in laptopnode.py

# ---- Serial ports ----
# The radio and the Arduino are both /dev/ttyACM*, and which one gets ACM0 can change
# with plug order. If rovernode.py says the Arduino didn't answer, swap these two.
# (Run   ls -l /dev/serial/by-id/   and use those paths here to stop them ever swapping.)
RADIO_PORT = "/dev/ttyACM0"
RADIO_BAUD = 115200
ARDUINO_PORT = "/dev/ttyACM1"
ARDUINO_BAUD = 9600
ESP_PORT = "/dev/ttyUSB0"
ESP_BAUD = 115200
GPS_PORT = "/dev/ttyAMA2"
GPS_BAUD = 460800

# ---- Driving ----
MAX_SPEED = 0.4           # m/s, hard clamp on any track command
CMD_TIMEOUT = 0.8         # s without a DRIVE packet -> stop (dead-man)
LOOP_HZ = 20

# ---- Soil probe actuator ----
BLOCK_DRIVE_WHEN_PROBE_DOWN = True   # refuse to drive while the probe is in the ground
ACTUATOR_TRAVEL_S = 5.0              # s the actuator needs to fully retract; driving stays
                                     # blocked this long after a retract (and after startup)

# ---- Data logging ----
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soil_samples.csv")
MAX_READING_AGE_S = 3.0   # a GPS fix or soil reading older than this counts as missing

# ---- Stability logging (P on the laptop starts / stops it; see stabilitylog.py) ----
STABILITY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stability_logs")
STABILITY_LOG_HZ = 20     # rows per second written while logging. Must be at least the GPS
                          # rate (the LG290P sends 10 fixes/s by default) so no fix is skipped.
ESP_FEEDBACK_MS = 50      # the ESP32 sends IMU + track-speed feedback this often (50 ms = 20 Hz)
IMU_MAX_AGE_S = 0.5       # an IMU reading older than this counts as missing
IMU_FILTER_TAU_S = 1.0    # roll/pitch filter: tilt changes faster than ~1 s come from the gyro,
                          # slower ones from gravity (so bumps don't show up as fake tilt)
# Level calibration: park on flat ground, run   python stabilitylog.py level   and copy the
# two numbers it prints here.
IMU_ROLL_OFFSET_DEG = 0.07
IMU_PITCH_OFFSET_DEG = -0.93
IMU_SWAP_ROLL_PITCH = False  # set True if lifting the rover's nose changes ROLL instead of PITCH

# ---- RTK corrections (Point One) ----
USE_NTRIP = True
NTRIP_SERVER = "truertk.pointonenav.com"
NTRIP_PORT = 2101
NTRIP_MOUNTPOINT = "AUTO"
NTRIP_USER = "redacted"
NTRIP_PASSWORD = "redacted"
NTRIP_GGA_INTERVAL = 10
