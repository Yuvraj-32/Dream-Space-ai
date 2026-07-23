import os
"""
Debug visualization: draw detected walls on top of the floor plan image.
Saves output to debug_walls.png for visual inspection.
"""
import sys, cv2, numpy as np
sys.path.insert(0, '.')
from detector import detect_floor_plan

img_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "67ca2328a5aebddb6989e0c8_30x40 3 Bedroom Floor Plan.webp")
img = cv2.imread(img_path)
r = detect_floor_plan(img_path)

overlay = img.copy()
W, H = r['image_size']['width'], r['image_size']['height']

# Draw ALL detected walls
for w in r['walls']:
    if w['wall_type'] == 'main_wall':
        color = (0, 0, 255)   # RED = main
        thick = 4
    else:
        color = (0, 255, 0)   # GREEN = partition
        thick = 2
    cv2.line(overlay, (w['x1'], w['y1']), (w['x2'], w['y2']), color, thick)
    # Label
    mx, my = (w['x1']+w['x2'])//2, (w['y1']+w['y2'])//2
    cv2.putText(overlay, w['id'].replace('wall_','W'), (mx-10, my-5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

# Draw openings
for o in r['openings']:
    cx, cy = int(o.get('x', 0)), int(o.get('y', 0))
    if o['type'] == 'door':
        cv2.circle(overlay, (cx, cy), 12, (255, 0, 0), 2)  # BLUE = door
    else:
        cv2.rectangle(overlay, (cx-10, cy-10), (cx+10, cy+10), (255, 255, 0), 2)  # CYAN = window

# Draw rooms
for rm in r['rooms']:
    b = rm['bbox']
    cv2.rectangle(overlay, (b['x'], b['y']), (b['x']+b['w'], b['y']+b['h']),
                  (255, 0, 255), 2)  # MAGENTA = room bbox
    cv2.putText(overlay, rm['id'], (b['x']+5, b['y']+20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1)

# Also create a side-by-side with structural extraction
from detector import _preprocess, _extract_structural
gray, blurred, thresh, scale = _preprocess(img)
ph, pw = thresh.shape[:2]
structural, dist_transform = _extract_structural(thresh, pw, ph)

# Upscale structural to original size
structural_full = cv2.resize(structural, (W, H), interpolation=cv2.INTER_NEAREST)
struct_color = cv2.cvtColor(structural_full, cv2.COLOR_GRAY2BGR)

# Save both
cv2.imwrite('debug_walls.png', overlay)
cv2.imwrite('debug_structural.png', struct_color)

print(f'Saved debug_walls.png ({W}x{H})')
print(f'Saved debug_structural.png')
print(f'Walls: {len(r["walls"])}  Rooms: {len(r["rooms"])}  Openings: {len(r["openings"])}')
print()

# Count walls by type
horiz = [w for w in r['walls'] if w['angle'] < 5 or w['angle'] > 175]
vert  = [w for w in r['walls'] if abs(w['angle'] - 90) < 5]
other = [w for w in r['walls'] if w not in horiz and w not in vert]
print(f'Horizontal walls: {len(horiz)}')
print(f'Vertical walls:   {len(vert)}')
print(f'Other angle:      {len(other)}')

# Expected from visual inspection of the floor plan:
print()
print('=== EXPECTED vs DETECTED ===')
print('Expected ~9 rooms: Bedroom#2, Bedroom#3, Master Bedroom,')
print('  Family Room, Dining Area, Kitchen, Closet, Washroom, Hallway')
print(f'Detected: {len(r["rooms"])} rooms')
print()
print('Expected ~11 doors + 4 windows = 15 openings')
print(f'Detected: {len(r["openings"])} openings')
