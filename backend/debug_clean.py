import os
"""
Side-by-side comparison: structural extraction + wall overlay.
Shows exactly what's being extracted vs what's being detected.
"""
import sys, cv2, numpy as np
sys.path.insert(0, '.')
from detector import detect_floor_plan, _preprocess, _extract_structural

img_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "67ca2328a5aebddb6989e0c8_30x40 3 Bedroom Floor Plan.webp")
img = cv2.imread(img_path)
r = detect_floor_plan(img_path)
H, W = img.shape[:2]

# Create a clean wall-only visualization (no image background)
canvas = np.ones((H, W, 3), dtype=np.uint8) * 255  # white background

# Draw walls on white canvas
for w in r['walls']:
    if w['wall_type'] == 'main_wall':
        color = (0, 0, 200)    # dark red = main wall
        thick = max(6, int(w['thickness'] * 0.5))
    else:
        color = (100, 100, 100) # gray = partition
        thick = max(2, int(w['thickness'] * 0.3))
    cv2.line(canvas, (w['x1'], w['y1']), (w['x2'], w['y2']), color, thick)

# Draw openings as blue gaps
for o in r['openings']:
    cx, cy = int(o.get('center_x', 0)), int(o.get('center_y', 0))
    if o['type'] == 'door':
        cv2.circle(canvas, (cx, cy), 8, (255, 100, 0), -1)  # blue filled circle
    else:
        cv2.rectangle(canvas, (cx-8, cy-4), (cx+8, cy+4), (0, 180, 255), -1)  # yellow rect

# Draw room boundaries
for rm in r['rooms']:
    pts = np.array(rm['polygon'], dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(canvas, [pts], True, (200, 0, 200), 2)
    cx, cy = rm['centroid']['x'], rm['centroid']['y']
    cv2.putText(canvas, rm['id'], (cx-30, cy),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 0, 200), 1)

cv2.imwrite('debug_clean_walls.png', canvas)
print('Saved debug_clean_walls.png')

# Count and analyze wall coverage
all_walls = r['walls']
horiz = [w for w in all_walls if w['angle'] < 5 or w['angle'] > 175]
vert = [w for w in all_walls if abs(w['angle'] - 90) < 5]
diag = [w for w in all_walls if w not in horiz and w not in vert]

print(f'\nWall summary:')
print(f'  Total: {len(all_walls)}')
print(f'  Horizontal: {len(horiz)}')
print(f'  Vertical: {len(vert)}')
print(f'  Diagonal (noise): {len(diag)}')
for d in diag:
    print(f'    {d["id"]}: angle={d["angle"]:.1f} thick={d["thickness"]:.1f} len={d["length"]:.0f}')

# What SHOULD exist (from visual inspection):
print('\n=== EXPECTED WALLS (from floor plan) ===')
expected = [
    'Top exterior (full width ~1632px)',
    'Bottom exterior (full width ~1632px)',
    'Left exterior (full height ~1250px)',
    'Right exterior (full height ~1250px)',
    'Hallway horizontal (separates bedrooms from living area)',
    'Bedroom #2 left wall (vertical)',
    'Bedroom #2 / #3 divider (vertical)',
    'Bedroom #3 / Master divider (vertical)',
    'Master bedroom right inner wall',
    'Kitchen / Dining divider (vertical)',
    'Kitchen / Closet divider (horizontal)',
    'Closet walls (3-4 segments)',
    'Washroom walls (3-4 segments)',
    'Bathroom walls in bedrooms (small partitions)',
    'Porch/entry area walls',
]
for e in expected:
    print(f'  Expected: {e}')

print(f'\nRooms: {len(r["rooms"])}')
print(f'Openings: {len(r["openings"])}')
