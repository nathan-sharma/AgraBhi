# Coded by Nathan
import serial
import pynmea2
import time
import csv
import psutil as ps
import os

current_latitude = "N/A"
current_longitude = "N/A"
current_moisture = "N/A"
sample_ID = 0

serMoisture = None
serGps = None

def communicate_to_actuator(command):
    global serMoisture
    cmd_char = command[0]
    encode_to_bytes = (cmd_char+ '\n').encode('utf-8')
    try:
        serMoisture.write(encode_to_bytes)
        if cmd_char == "e":
            print("Actuator extended.")
        elif cmd_char == "r":
            print("Actuator retracted.")
        elif cmd_char == 'l':
            print("Sensor triggered.")
    except serial.SerialException as e:
        print(f"Error sending command to Arduino: {e}")
    except Exception as e:
        print(f"Error: {e}")




def initialize_log_file(filename="data.csv"):
    if not os.path.exists(filename):
        with open(filename, 'w') as file:
            file.write('Sample ID, Latitude, Longitude, Moisture\n')




def update_moisture_reading():
    time.sleep(1.5)
    global current_moisture
    if serMoisture.in_waiting > 0:
        try:
            line1 = serMoisture.readline().decode('utf-8').replace('\r', '').strip()
            data = float(line1)
            current_moisture = data
        except Exception as e:
            print(f"Moisture read error: {e}")
            current_moisture = "Read Error"
   
def update_gps_reading():
    global current_latitude, current_longitude
    if serGps.in_waiting > 0:
        try:
            line2 = serGps.readline().decode('utf-8').rstrip()


            if line2.startswith('$'):
                gps_reading = pynmea2.parse(line2)


                if hasattr(gps_reading, 'latitude') and hasattr(gps_reading, 'longitude'):
                    current_latitude = str(gps_reading.latitude)
                    current_longitude = str(gps_reading.longitude)


        except pynmea2.ParseError as e:
            print(f"GPS Parsing error on line: {line2} Error: {e}")
        except Exception as e:
            print(f"GPS read error: {e}")


def read_sensor():
    return current_moisture
def read_latitude():
    return current_latitude
def read_longitude():
    return current_longitude
def log_data():
    filename = "data.csv"

    moisture = read_sensor()
    latitude = read_latitude()
    longitude = read_longitude()

    if latitude != "N/A" and moisture != "N/A" and type(moisture) is float:
        with open(filename, 'a') as file:
            file.write('{},{},{},{}\n'.format(
                sample_ID,
                latitude,
                longitude,
                moisture
            ))
        print(f"Logged data. Sample ID = {sample_ID}.")
    else:
        print("Waiting for valid sensor data...")




if __name__ == '__main__':
    try:
        serMoisture = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
        serGps = serial.Serial('/dev/ttyS0', 9600, timeout=1)
    except serial.SerialException as e:
        print(f"FATAL ERROR: Could not open one or more serial ports. Check connections and permissions: {e}")
        exit()


    serMoisture.flush()
    serGps.flush()
    initialize_log_file()
    print("Starting the program. Press Ctrl+C to stop.")


    while True:
        command = input("Enter a command: ")
        if command == "e":
            communicate_to_actuator(command)
        elif command == "r":
            communicate_to_actuator(command)
        elif command == "l":
            communicate_to_actuator(command)
            global sample_ID
            sample_ID +=1;
            update_moisture_reading()
            update_gps_reading()
            log_data()
        elif command == "re":
            sample_ID = 0
        else:
            print("Exiting...")
            break

