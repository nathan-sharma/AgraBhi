#prereq to run: pip install shapely 
import random
from shapely.geometry import Polygon, Point

def generate_field_points(boundaries, num_points=50):
    """
    Generates random GPS coordinates inside a 4-corner farm field.
    :param boundaries: List of 4 tuples in (latitude, longitude) format.
    :param num_points: Number of random points to generate (default is 30).
    :return: List of (latitude, longitude) tuples.
    """
    # Shapely expects (longitude, latitude) or (x, y) coordinates
    # We swap the input (lat, lon) to (lon, lat) for proper spatial calculation
    formatted_boundaries = [(lon, lat) for lat, lon in boundaries]
    field_polygon = Polygon(formatted_boundaries)
    
    # Get the bounding box of the field (min_lon, min_lat, max_lon, max_lat)
    min_lon, min_lat, max_lon, max_lat = field_polygon.bounds
    
    valid_points = []
    
    while len(valid_points) < num_points:
        # Generate random coordinates within the bounding box
        rand_lon = random.uniform(min_lon, max_lon)
        rand_lat = random.uniform(min_lat, max_lat)
        
        point = Point(rand_lon, rand_lat)
        
        # Check if the point is actually inside the field polygon
        if field_polygon.contains(point):
            # Store back as (latitude, longitude)
            valid_points.append((rand_lat, rand_lon))
            
    return valid_points

# --- Example Usage ---
# Enter your 4 field corners as (Latitude, Longitude)
# Order them sequentially (clockwise or counter-clockwise) around the field
farm_boundaries = [
    (29.7350, -95.8230),  # Corner 1: Top left
    (29.7350, -95.8210),  # Corner 2: Top right
    (29.7330, -95.8210),  # Corner 3: Bottom right
    (29.7330, -95.8230)   # Corner 4: Bottom left
]

random_samples = generate_field_points(farm_boundaries, num_points=50)

print(f"Generated {len(random_samples)} random GPS coordinates:")
for i, coord in enumerate(random_samples, 1):
    print(f"Point {i}: Lat {coord[0]:.6f}, Lon {coord[1]:.6f}")
