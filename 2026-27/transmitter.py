import socket
import time
import serial

PYGPS_HOST = '127.0.0.1' 
PYGPS_PORT = 50012        
LORA_PORT = '/dev/ttyACM0'
LORA_BAUD = 9600

def parse_nmea_gga(nmea_str):
    parts = nmea_str.split(',')
    if len(parts) < 10:
        return None

    raw_lat, lat_dir = parts[2], parts[3]
    raw_lon, lon_dir = parts[4], parts[5]
    alt = parts[9]

    if not raw_lat or not raw_lon:
        return None
#convert to decimal
    lat_deg = float(raw_lat[:2]) + float(raw_lat[2:]) / 60.0
    if lat_dir == 'S':
        lat_deg = -lat_deg

    lon_deg = float(raw_lon[:3]) + float(raw_lon[3:]) / 60.0
    if lon_dir == 'W':
        lon_deg = -lon_deg

    return f"{lat_deg:.7f},{lon_deg:.7f},{alt}"

def run_transmitter():
    lora = serial.Serial(LORA_PORT, LORA_BAUD, timeout=1)

    print("Connecting to PyGPSClient socket server...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((PYGPS_HOST, PYGPS_PORT))
    print("Connected! Transmitting RTK GPS data over LoRa...\n")

    buffer = ""
    try:
        while True:
            data = s.recv(1024).decode('utf-8', errors='ignore')
            buffer += data
            lines = buffer.split('\r\n')
            buffer = lines.pop()  # Keep partial line in buffer

            for line in lines:
                if '$GNGGA' in line or '$GPGGA' in line:
                    parsed = parse_nmea_gga(line)
                    if parsed:
                        payload = f"{parsed}\n"
                        lora.write(payload.encode('utf-8'))
                        print(f"Sent RTK Data: {payload.strip()}")
                        time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping transmitter.")
    finally:
        s.close()
        lora.close()

if __name__ == "__main__":
    run_transmitter()
