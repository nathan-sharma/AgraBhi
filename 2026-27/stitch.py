#pi 5: /home/sharma007/stitch.py
import datetime
import glob
import os
import cv2

RAW_DIR = "/media/sharma007/myssd/panorama_raw/"
OUTPUT_DIR = "/media/sharma007/myssd/"

def stitch_images():
  image_paths = sorted(glob.glob(os.path.join(RAW_DIR, "*.jpg")))

  if not image_paths:
    print("No images found!")
    return

  images = []
  for path in image_paths:
    img = cv2.imread(path)
    if img is not None:
      images.append(img)

  print(f"Stitching {len(images)} images together...")
  stitcher = cv2.Stitcher_create()
  status, pano = stitcher.stitch(images)

  if status == cv2.Stitcher_OK:
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"panorama_{timestamp}.jpg"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    cv2.imwrite(output_path, pano)
    print(f"Panorama successfully saved to {output_path}")
  else:
    print(f"Stitching failed with error code: {status}")


if __name__ == "__main__":
  stitch_images()