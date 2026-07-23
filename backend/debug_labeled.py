import os
"""
Label EVERY wall by ID on the floor plan image.
This lets us pinpoint exact noise walls vs real walls.
"""
import sys, cv2, numpy as np
sys.path.insert(0, '.')
from detector import detect_floor_plan

img_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "67ca2328a5aebddb6989e0c8_30x40 3 Bedroom Floor Plan.webp")
img = cv2.imread(img_path)
r = detect_floor_plan(img_path)
overlay = img.copy()

for w in r['walls']:
    x1, y1, x2, y2 = w['x1'], w['y1'], w['x2'], w['y2']
    is_main = w['wall_type'] == 'main_wall'
    t = w['thickness']

    # Color by type
    if is_main:
        color = (0, 0, 255)  # red
        lw = max(4, int(t * 0.3))
    elif t < 3:
        color = (0, 255, 255)  # yellow = suspicious thin
        lw = 3
    else:
        color = (0, 255, 0)  # green = partition
        lw = max(2, int(t * 0.2))

    cv2.line(overlay, (x1, y1), (x2, y2), color, lw)

    # Label with wall ID + thickness
    mx, my = (x1+x2)//2, (y1+y2)//2
    label = f"{w['id']} t={t:.1f} L={w['length']:.0f}"
    # Background rect for readability
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1)
    cv2.rectangle(overlay, (mx-2, my-th-2), (mx+tw+2, my+2), (0, 0, 0), -1)
    cv2.putText(overlay, label, (mx, my), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)

cv2.imwrite('debug_labeled.png', overlay)
print('Saved debug_labeled.png')

# Analysis: identify suspicious walls
print('\n=== NOISE CANDIDATES ===')
print('Walls with thickness < 3px (phantom edges, not real walls):')
for w in r['walls']:
    if w['thickness'] < 3:
        print(f"  {w['id']}: thick={w['thickness']:.1f} len={w['length']:.0f} ({w['x1']},{w['y1']})->({w['x2']},{w['y2']})")

print('\nWalls shorter than 100px (furniture fragments):')
for w in r['walls']:
    if w['length'] < 100:
        print(f"  {w['id']}: thick={w['thickness']:.1f} len={w['length']:.0f} ({w['x1']},{w['y1']})->({w['x2']},{w['y2']})")

print('\nWalls shorter than 150px AND thinner than 10px:')
for w in r['walls']:
    if w['length'] < 150 and w['thickness'] < 10:
        print(f"  {w['id']}: thick={w['thickness']:.1f} len={w['length']:.0f} ({w['x1']},{w['y1']})->({w['x2']},{w['y2']})")
