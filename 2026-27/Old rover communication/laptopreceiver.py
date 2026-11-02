import serial
import time
LORA_PORT = 'COM3'  
LORA_BAUD = 115200
def run_receiver():
    try:
        lora = serial.Serial(LORA_PORT, LORA_BAUD, timeout=1)
        print(f"Listening on {LORA_PORT}, {LORA_BAUD} baud...\n")

        while True:
            if lora.in_waiting > 0:
                raw_data = lora.read(lora.in_waiting)
                text = raw_data.decode('utf-8', errors='ignore')
                print(f"Raw received: {repr(text)}")
                
            time.sleep(0.05)
    except serial.SerialException as e:
        print(f"Serial Error: {e}")
    except KeyboardInterrupt:
        print("\nStopping receiver.")
    finally:
        if 'lora' in locals() and lora.is_open:
            lora.close()
if __name__ == "__main__":
    run_receiver()