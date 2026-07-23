"""
Hand-counted ground truth for the regression harness.

Floor-plan detection has no single "correct" answer — open-plan spaces,
rendered vs. CAD styles, and ambiguous door/window marks all make exact
counts unrealistic. So each fixture records a *sane range* per metric
(hand-counted from the source image, with slack), not an exact number.

The pytest suite asserts detector output falls inside these ranges AND
snapshots the full output so any pipeline change is visible in a diff,
even when it stays inside the range.

Counts were established by visual inspection on 2026-07-18.
"""

GROUND_TRUTH = {
    # ── Clean CAD line drawing, 3-bedroom, 2732x1908 ──────────────────
    # Labeled rooms: Bedroom #2, Bedroom #3, Master Bedroom, Family Room,
    # Dining Area, Kitchen, Closet, Washroom + an unlabeled bathroom
    # (toilet/tub). Family/Dining/Kitchen are open-plan (flow together
    # with no dividing walls), so the number of *enclosed* regions is
    # fewer than the number of named spaces: ~6-9 enclosed rooms.
    # Doors: ~7-9 swing arcs. Windows: ~4-6 on exterior walls.
    "3br_cad.jpg": {
        "notes": "Clean CAD line drawing. Furniture (beds, sofas, tub) "
                 "is drawn in outline and is the main source of false walls.",
        "rooms":    (6, 11),   # enclosed regions
        "walls":    (20, 60),  # after all cleanup
        "openings": (8, 22),   # doors + windows
        "doors":    (4, 16),
        "windows":  (2, 12),
    },

    # ── Rendered/colored plan, 2nd floor, 1640x1093 ───────────────────
    # This is a realistic render (tan floor fill, textures) NOT a line
    # drawing. Interior rooms: Bathroom, Master Bedroom, and an open
    # attic void (X-hatched). The Deck is exterior. Hard case — the
    # colored floor fill defeats white-region room detection.
    # This fixture documents a KNOWN-WEAK case; ranges are wide.
    "truoba_render.jpg": {
        "notes": "Rendered plan with colored floor fill, not CAD lines. "
                 "Known-weak case for the classical pipeline.",
        "rooms":    (1, 6),
        "walls":    (8, 40),
        "openings": (0, 12),
        "doors":    (0, 10),
        "windows":  (0, 8),
    },
}
