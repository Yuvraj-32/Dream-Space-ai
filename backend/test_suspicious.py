import os
import sys
sys.path.insert(0, '.')
from detector import detect_floor_plan

img = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "67ca2328a5aebddb6989e0c8_30x40 3 Bedroom Floor Plan.webp")
r = detect_floor_plan(img)

W = r['image_size']['width']
H = r['image_size']['height']

print('=== SUSPICIOUS WALLS ===')
print()

# Off-angle
print('Off-angle (not 0 or 90):')
for w in r['walls']:
    a = w['angle']
    if not (a < 5 or a > 175 or abs(a - 90) < 5):
        print('  %s: (%d,%d)->(%d,%d) angle=%.1f thick=%.1f len=%.0f' %
              (w['id'], w['x1'], w['y1'], w['x2'], w['y2'], a, w['thickness'], w['length']))

# Near edges (dimension lines)
print()
print('Near image edges (y<180 or x<120):')
for w in r['walls']:
    ymin = min(w['y1'], w['y2'])
    xmin = min(w['x1'], w['x2'])
    if ymin < 180 or xmin < 120:
        print('  %s: (%d,%d)->(%d,%d) thick=%.1f len=%.0f' %
              (w['id'], w['x1'], w['y1'], w['x2'], w['y2'], w['thickness'], w['length']))

# Thin
print()
print('Very thin (< 3px):')
for w in r['walls']:
    if w['thickness'] < 3.0:
        print('  %s: (%d,%d)->(%d,%d) thick=%.1f len=%.0f' %
              (w['id'], w['x1'], w['y1'], w['x2'], w['y2'], w['thickness'], w['length']))
