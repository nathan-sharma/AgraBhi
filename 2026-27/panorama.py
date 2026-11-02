#pi 0: /home/sharma007/panorama.py
import os
import shutil
import subprocess

LOCAL_DIR = "/home/sharma007/panorama_raw"

REMOTE_USER = "sharma007"
REMOTE_HOST = "sharmaguy007.local"
REMOTE_SSD_RAW = "/media/sharma007/myssd/panorama_raw/"


def run_manual_workflow():
  if os.path.exists(LOCAL_DIR):
    shutil.rmtree(LOCAL_DIR)
  os.makedirs(LOCAL_DIR, exist_ok=True)

  print("=" * 50)
  print("t = take picture, s = send pictures to pi for stitching")

  photo_index = 0

  while True:
    user_input = (
        input(f"Command [Photo {photo_index + 1} - 't'/'s']: ").strip().lower()
    )

    if user_input == "t":
      filename = f"pano_{photo_index:03d}.jpg"
      local_path = os.path.join(LOCAL_DIR, filename)

      print(f"📸 Capturing photo {photo_index + 1}...")
      subprocess.run(
          ["rpicam-still", "-o", local_path, "-t", "200"], check=True
      )
      print(f"Saved {filename}\n")
      photo_index += 1

    elif user_input == "s":
      if photo_index == 0:
        print("No photos taken yet!")
        continue
      print("\n Stopping captures.")
      break

    else:
      print("Invalid input. Type 't' to take a photo or 's' to finish.")

  print("Clearing old raw images on Pi 5...")
  clear_cmd = ["ssh", f"{REMOTE_USER}@{REMOTE_HOST}", f"rm -rf {REMOTE_SSD_RAW}"]
  subprocess.run(clear_cmd, check=True)

  print("Transferring raw images to Pi 5...")
  transfer_cmd = [
      "rsync",
      "-avz",
      f"{LOCAL_DIR}/",
      f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_SSD_RAW}",
  ]
  subprocess.run(transfer_cmd, check=True)
  print("Done! Pictures transferred")

  print("Stitching...")
  stitch_cmd = [
      "ssh",
      f"{REMOTE_USER}@{REMOTE_HOST}",
      "python3 /home/sharma007/stitch.py",
  ]
  subprocess.run(stitch_cmd, check=True)
  print("Finished.")


if __name__ == "__main__":
  run_manual_workflow()