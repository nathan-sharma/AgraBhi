import numpy as np

def generate_field_points(corners):
    """
    Takes 4 GPS coordinates (lat, lon) in order: 
    [Bottom-Left, Bottom-Right, Top-Right, Top-Left]
    Returns 30 equally spaced points within the field boundary.
    """
    P0, P1, P2, P3 = [np.array(c) for c in corners]
    
    # Create 30 points arranged in a 5 rows x 6 columns grid
    u_vals = np.linspace(0, 1, 6) # Columns
    v_vals = np.linspace(0, 1, 5) # Rows
    
    points = []
    for v in v_vals:
        for u in u_vals:
            # Bilinear interpolation formula for quadrilateral mapping
            point = (
                (1 - u) * (1 - v) * P0 +
                u * (1 - v) * P1 +
                u * v * P2 +
                (1 - u) * v * P3
            )
            points.append(tuple(point))
            
    return points

# --- Example Usage ---
# Dummy GPS coordinates (Latitude, Longitude)
field_corners = [
    (30.4956, -97.13185),  # 0: Bottom-Left
    (30.49585, -97.12125),  # 1: Bottom-Right
    (30.49007, -97.12609),  # 2: Top-Right
    (30.49391, -97.11788)   # 3: Top-Left
]

grid_points = generate_field_points(field_corners)

print(f"Total points generated: {len(grid_points)}\n")
for i, pt in enumerate(grid_points, 1):
    print(f"Point {i}: Latitude {pt[0]:.4f}, Longitude {pt[1]:.4f}")
