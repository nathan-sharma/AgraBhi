#!/usr/bin/env python3
# laptopnode.py
# Run on the laptop (the one with the radio):   python laptopnode.py     (set PORT below)
# Talks to rovernode.py on the Pi. Don't run anything else that uses the radio port
# at the same time.
#
# Click the window, then:
#   W/S forward/back     A/D pivot left/right     Space or release = stop
#   E = extend probe     R = retract probe        Z = stop the probe where it is
#   L = log a sample (sample ID + GPS + soil moisture/temperature -> CSV on the Pi)
#   G = ask the rover for its status (GPS fix, probe, samples logged, soil sensor)
#   Q = quit

import time
import tkinter as tk

import serial

PORT = "COM3"
BAUD = 115200
ROVER_ID = "PI1"        # must match roverconfig.py on the Pi
LAPTOP_ID = "LAPTOP"    # must match roverconfig.py on the Pi

SPEED = 0.25            # m/s forward/back
TURN = 0.20             # m/s per track while pivoting
SEND_MS = 200           # a DRIVE packet goes out this often while a drive key is held (5 Hz)
REPLY_TIMEOUT = 3.0     # s to wait for the rover to answer E / R / Z / L / G

# key -> (packet type, payload, description)
COMMANDS = {
    "e": ("ACT", "E", "extend probe"),
    "r": ("ACT", "R", "retract probe"),
    "z": ("ACT", "Z", "stop probe"),
    "l": ("SAMPLE", "0", "log sample"),
    "g": ("STATUS", "0", "status request"),
}
FIX_NAMES = {"0": "NO FIX", "1": "GPS only (no RTK)", "2": "DGPS", "4": "RTK FIXED", "5": "RTK float"}
PROBE_NAMES = {"EXTENDED": "DOWN (extended)", "RETRACTED": "up (retracted)", "STOPPED": "STOPPED part-way"}

ser = serial.Serial(PORT, BAUD, timeout=0.05)
keys = set()
last_sent = {}          # key -> time it was last sent (stops key auto-repeat re-sending)
rx_buffer = ""
stops_left = 0          # STOP packets still to send after the drive keys are released
waiting_since = None    # when we last sent a command that the rover should answer
ui = {"driving": "stopped", "probe": "unknown (press G)", "sample": "none yet",
      "status": "unknown (press G)", "msg": ""}

root = tk.Tk()
root.title("Rover control")
label = tk.Label(root, padx=30, pady=30, justify="left", anchor="w", width=86, font=("Courier New", 11))
label.pack()


def refresh_label():
    label.config(text=(
        f"Rover: {ROVER_ID}     (click this window first)\n\n"
        "W/S forward/back     A/D pivot     Space = stop\n"
        "E extend probe       R retract probe       Z stop probe\n"
        "L log a sample       G rover status       Q quit\n\n"
        f"Driving:       {ui['driving']}\n"
        f"Probe:         {ui['probe']}\n"
        f"Last sample:   {ui['sample']}\n"
        f"Rover status:  {ui['status']}\n"
        f"Message:       {ui['msg']}"))


def send(ptype, payload):
    ser.write(f"{ROVER_ID}|{ptype}|{payload}\n".encode())


def handle_reply(ptype, payload):
    """A packet from the rover addressed to the laptop."""
    global waiting_since
    waiting_since = None
    f = payload.split(",")
    if ptype == "ACT":
        ui["probe"] = PROBE_NAMES.get(payload, payload)
        ui["msg"] = f"Rover: probe {payload.lower()}"
    elif ptype == "SAMPLE" and len(f) == 7:
        sid, lat, lon, alt, fix, moisture, temperature = f
        gps = f"{lat}, {lon}  alt {alt} m  {FIX_NAMES.get(fix, 'fix ' + fix)}" if lat else "NO GPS FIX"
        soil = f"moisture {moisture}  temp {temperature}" if moisture else "NO SOIL READING"
        ui["sample"] = f"#{sid}  {gps}\n               {soil}"
        missing = [name for name, value in (("GPS", lat), ("soil reading", moisture)) if not value]
        ui["msg"] = f"Rover: sample {sid} logged" + (f"  ** MISSING: {' and '.join(missing)} **" if missing else "")
    elif ptype == "STATUS" and len(f) == 4:
        fix, probe, count, soil = f
        ui["probe"] = PROBE_NAMES.get(probe, probe)
        ui["status"] = (f"GPS {FIX_NAMES.get(fix, 'fix ' + fix)} | {count} samples logged | "
                        f"soil sensor {'OK' if soil == 'OK' else 'NO DATA'}")
        ui["msg"] = "Rover: status received"
    else:
        ui["msg"] = f"Rover: {payload}"


def read_radio():
    global rx_buffer
    if ser.in_waiting:
        rx_buffer += ser.read(ser.in_waiting).decode("utf-8", errors="ignore")
        while "\n" in rx_buffer:
            line, rx_buffer = rx_buffer.split("\n", 1)
            parts = line.strip().split("|")
            if len(parts) == 3 and parts[0] == LAPTOP_ID:
                handle_reply(parts[1], parts[2])


def on_press(e):
    global waiting_since
    k = e.keysym.lower()
    fresh = k not in keys       # holding a key down repeats the press event; only act on the first
    keys.add(k)
    now = time.monotonic()
    if k in COMMANDS and fresh and now - last_sent.get(k, -10) > 0.5:
        ptype, payload, description = COMMANDS[k]
        send(ptype, payload)
        last_sent[k] = now
        waiting_since = now
        ui["msg"] = f"Sent: {description}. Waiting for the rover..."
        refresh_label()


root.bind("<KeyPress>", on_press)
root.bind("<KeyRelease>", lambda e: keys.discard(e.keysym.lower()))
root.bind("<FocusOut>", lambda e: keys.clear())     # clicking away counts as releasing every key


def tick():
    global stops_left, waiting_since
    read_radio()
    if "q" in keys:
        send("STOP", "0")
        root.destroy()
        return

    l = r = 0.0
    if "space" not in keys:
        if "w" in keys: l += SPEED; r += SPEED
        if "s" in keys: l -= SPEED; r -= SPEED
        if "d" in keys: l += TURN; r -= TURN
        if "a" in keys: l -= TURN; r += TURN

    # DRIVE packets only go out while a drive key is held. On release, send a few STOPs and
    # then stay quiet, which leaves the radio free for the rover's replies. (If every STOP
    # were lost, the rover's dead-man timer would still stop it.)
    if l or r:
        send("DRIVE", f"{l:.2f},{r:.2f}")
        stops_left = 3
        ui["driving"] = f"left {l:+.2f}  right {r:+.2f} m/s"
    else:
        if stops_left > 0:
            send("STOP", "0")
            stops_left -= 1
        ui["driving"] = "stopped"

    if waiting_since is not None and time.monotonic() - waiting_since > REPLY_TIMEOUT:
        waiting_since = None
        ui["msg"] = "No reply from the rover. Press the key again."

    refresh_label()
    root.after(SEND_MS, tick)


refresh_label()
tick()
root.mainloop()
try:
    send("STOP", "0")
finally:
    ser.close()
