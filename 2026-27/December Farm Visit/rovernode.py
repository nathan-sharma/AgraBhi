#!/usr/bin/env python3
# rovernode.py
# THE ONE FILE YOU RUN ON THE PI:   python rovernode.py
# (ports and settings are in roverconfig.py)
#
# This file owns the radio. Every packet from the laptop arrives here and is handed
# to the sub file that does that job:
#     DRIVE / STOP  ->  drive.py         track speeds to the ESP32
#     ACT           ->  actuator.py      extend / retract / stop the soil probe (via the Arduino)
#     SAMPLE        ->  datacollect.py   sample ID + GPS + soil reading -> CSV row on the Pi
#     LOG           ->  stabilitylog.py  start / stop logging GPS + IMU tilt for the stability runs
#     STATUS        ->  short health report back to the laptop
#
# Packets (same format as before):  ID|TYPE|payload\n
#   laptop -> rover:  PI1|DRIVE|0.25,0.25    PI1|STOP|0
#                     PI1|ACT|E  (extend)    PI1|ACT|R  (retract)    PI1|ACT|Z  (stop where it is)
#                     PI1|SAMPLE|0           PI1|STATUS|0
#                     PI1|LOG|1  (start a stability run)    PI1|LOG|0  (stop it)
#   rover -> laptop:  LAPTOP|ACT|EXTENDED    LAPTOP|ACT|RETRACTED    LAPTOP|ACT|STOPPED
#                     LAPTOP|SAMPLE|id,lat,lon,alt,fix,moisture,temperature
#                     LAPTOP|LOG|ON,run,imu,fix     (while logging)
#                     LAPTOP|LOG|OFF,run,seconds,gps_hz,rtk_fixed_%,max_roll,max_pitch
#                     LAPTOP|STATUS|fix,probe,samples_logged,soil,imu,logging_run_or_OFF
#                     LAPTOP|INFO|any text
# Anything not addressed to this rover is ignored. If no DRIVE packet arrives for
# CMD_TIMEOUT seconds, the rover stops (dead-man).

import logging
import time

import serial

import roverconfig as cfg
from actuator import Actuator
from arduinolink import ArduinoLink
from datacollect import DataCollector
from drive import Drive
from stabilitylog import StabilityLogger

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


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


def run():
    me = cfg.ROVER_ID
    radio = serial.Serial(cfg.RADIO_PORT, cfg.RADIO_BAUD, timeout=0.05, write_timeout=0.5)
    drive = Drive()
    print(f"[{me}] Connecting to the Arduino (retracts the probe)...")
    link = ArduinoLink()
    actuator = Actuator(link)
    data = DataCollector(link)
    stability = StabilityLogger(drive, data)
    reader = LineReader(radio)

    def reply(ptype, payload):
        print(f"[{me}] -> laptop: {ptype} {payload}")
        try:
            radio.write(f"{cfg.LAPTOP_ID}|{ptype}|{payload}\n".encode())
        except serial.SerialTimeoutException:
            print(f"[{me}] Radio busy, reply not sent.")

    l = r = 0.0
    last_cmd = float("-inf")
    last_block_msg = float("-inf")
    radio.reset_input_buffer()      # drop anything that arrived while starting up
    print(f"[{me}] Rover node up. Next sample ID: {data.next_id}. Logging to {cfg.CSV_PATH}")
    reply("INFO", f"Rover node up. Next sample ID {data.next_id}")

    try:
        while True:
            for line in reader.read_lines():
                parts = line.split("|")
                if len(parts) != 3 or parts[0] != me:
                    continue
                _, pkt_type, payload = parts
                try:
                    if pkt_type == "DRIVE":
                        a, b = payload.split(",")
                        l, r = float(a), float(b)
                        last_cmd = time.monotonic()

                    elif pkt_type == "STOP":
                        l = r = 0.0

                    elif pkt_type == "ACT":
                        commands = {"E": actuator.extend, "R": actuator.retract, "Z": actuator.stop}
                        if payload not in commands:
                            raise ValueError
                        l = r = 0.0
                        drive.stop()        # never move the probe while the tracks are turning
                        if commands[payload]():
                            reply("ACT", actuator.state)
                        else:
                            reply("INFO", "Arduino did not answer the actuator command")

                    elif pkt_type == "SAMPLE":
                        try:
                            row = data.take_sample()
                        except OSError as e:
                            reply("INFO", f"Sample NOT logged: {e}")
                        else:
                            stability.mark(f"sample {row[0]}")
                            # id,lat,lon,alt,fix,moisture,temperature (timestamp stays in the CSV)
                            reply("SAMPLE", ",".join(str(v) for v in [row[0]] + row[2:]))

                    elif pkt_type == "LOG":
                        # "1" = start, "0" = stop. Sending the same one twice is harmless, so the
                        # laptop can just resend if the reply got lost.
                        if payload == "1":
                            try:
                                stability.start()
                            except OSError as e:
                                reply("INFO", f"Logging NOT started: {e}")
                                continue
                        elif payload == "0":
                            stability.stop()
                        else:
                            raise ValueError
                        reply("LOG", stability.status())

                    elif pkt_type == "STATUS":
                        fix = data.latest_fix()
                        soil = "OK" if link.latest_soil() else "NONE"
                        imu = "OK" if drive.imu.latest()[0] else "NONE"
                        logging_run = stability.run_id if stability.running else "OFF"
                        reply("STATUS", f"{fix[4] if fix else 0},{actuator.state},{data.next_id - 1},{soil},"
                                        f"{imu},{logging_run}")

                except ValueError:
                    print(f"[{me}] Garbled packet ignored: {line}")

            now = time.monotonic()
            if now - last_cmd > cfg.CMD_TIMEOUT:
                if l or r:
                    print(f"[{me}] No DRIVE packets - stopped (dead-man).")
                l = r = 0.0

            blocked = (l or r) and cfg.BLOCK_DRIVE_WHEN_PROBE_DOWN and actuator.probe_down()
            if blocked:
                l = r = 0.0
            drive.set(l, r)
            if blocked and now - last_block_msg > 2.0:
                last_block_msg = now
                reply("INFO", "Drive blocked: probe is not fully up. Press R, then wait a few seconds")

            time.sleep(1.0 / cfg.LOOP_HZ)

    except KeyboardInterrupt:
        print(f"\n[{me}] Stopping.")
    finally:
        stability.stop()
        drive.close()
        radio.close()


if __name__ == "__main__":
    run()
