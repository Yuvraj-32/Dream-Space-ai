# DreamSpace AI (Web) — Floor Plan to 3D Walkthrough
### Dev Plan v1 — No furniture, walls/floors/ceilings only

---

## Overview

User uploads a 2D floor plan image → AI detects walls/rooms/openings → user confirms/corrects in a 2D editor → app generates a 3D model → user walks through it FPP-style → user selects walls/floors and changes textures/colors live → final clean walkthrough mode.

Furniture is explicitly out of scope for v1. Walls, floors, ceilings, doors, windows only.

---

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| Frontend framework | **React** (Vite) | Fast dev loop, huge ecosystem |
| 3D rendering | **Three.js** via **react-three-fiber** + **drei** | Industry standard for web 3D, good React integration |
| FPP controls | **@react-three/drei PointerLockControls** + custom character controller | Mouse-look + WASD movement |
| Physics/collision | **cannon-es** or **@react-three/rapier** | Wall collision so player can't clip through walls |
| 2D floor plan editor | **Konva.js** or **fabric.js** (canvas-based) | Drag corners, snap walls, mark doors/windows on top of the uploaded image |
| Wall/room detection (CV) | **OpenCV** (Python) for line/edge detection + a **segmentation model** (start with classical Hough Transform + contour detection; upgrade to a fine-tuned model on **CubiCasa5k** dataset later) | Auto-detect walls from the uploaded image |
| Backend/API | **FastAPI** (Python) | Needed for CV/ML processing; clean integration with OpenCV/PyTorch |
| Image processing pipeline | **Python + OpenCV + NumPy** | Preprocessing (denoise, threshold, line detection) |
| 3D geometry generation | **Custom logic** — convert 2D wall polylines + thickness into extruded 3D meshes (server-side or client-side with Three.js `ExtrudeGeometry`) | Turns confirmed 2D plan into 3D walls/floor/ceiling |
| Texture assets | **Poly Haven** (free PBR textures) or **ambientCG** | Wall/floor material swatches for the texture editor |
| File storage | **Cloudflare R2** or **AWS S3** | Store uploaded plans + generated models |
| Auth (if needed later) | **Clerk** or **Supabase Auth** | Skip for MVP if it's single-session/no-login |
| Hosting | **Vercel** (frontend) + **Render/Railway** (FastAPI backend) | Matches your existing Render experience from Vehikill |

---

## Phase 0 — Setup & Skeleton (Week 1)
- Set up React + Vite frontend, FastAPI backend, repo structure.
- Basic file upload UI → sends image to backend, backend just echoes it back (no processing yet).
- Empty Three.js scene rendering a placeholder box, confirm react-three-fiber pipeline works end-to-end.

**Goal:** upload → empty 3D canvas renders. Plumbing proven.

---

## Phase 1 — Floor Plan Detection (Weeks 2–4)
- OpenCV preprocessing: grayscale, denoise, adaptive threshold.
- Hough Line Transform to detect straight wall lines.
- Contour detection to identify closed room polygons.
- Basic door/window gap detection (breaks in wall lines with standard-width gaps).
- Output: a JSON structure of walls (start point, end point, thickness) and room polygons.

**Goal:** given a clean floor plan image, backend returns a rough vector wall layout as JSON.

⚠️ Expect this to be imperfect on messy/hand-drawn plans — that's what Phase 2 fixes.

---

## Phase 2 — 2D Confirmation Editor (Weeks 4–6)
- Render the detected walls (from Phase 1 JSON) as an editable overlay on top of the original image using Konva.js/fabric.js.
- User can: drag wall endpoints, add/delete walls, mark/adjust door and window openings, snap-to-grid or snap-to-existing-corner.
- "Confirm Layout" button locks in the final 2D vector plan.

**Goal:** user always ends up with an accurate wall layout, regardless of how good Phase 1's auto-detection is. This is the reliability layer.

---

## Phase 3 — 3D Model Generation (Weeks 6–8)
- Take confirmed 2D wall polylines + thickness → extrude into 3D wall meshes (standard height, e.g. 9–10 ft) using Three.js `ExtrudeGeometry` or manual mesh construction.
- Generate floor plane per room polygon, ceiling plane per room polygon.
- Cut door/window openings as actual gaps in wall geometry (not just textures).
- Assign default materials (plain white walls, grey floor) as placeholder.

**Goal:** confirmed 2D plan → real 3D model with walls, floor, ceiling, correctly sized openings.

---

## Phase 4 — FPP Walkthrough (Weeks 8–10)
- Add first-person camera controller (PointerLockControls: mouse-look + WASD movement).
- Add collision detection (cannon-es or rapier) so the player can't walk through walls.
- Add basic room-scale navigation: player spawn point, ground collision (can't fall through floor), reasonable eye height.
- Basic lighting (ambient + directional) so the space is visible.

**Goal:** user can walk through their generated model like a simple FPS game character.

---

## Phase 5 — Material/Texture Editor (Weeks 10–12)
- Raycasting on click: detect which wall/floor mesh was clicked.
- Sidebar UI: color picker + texture swatch gallery (wood, tile, paint, brick, etc. from Poly Haven/ambientCG).
- On selection, swap the material on the clicked mesh in real time.
- Allow undo/reset per surface.

**Goal:** user can personalize every wall and floor with their own color/texture choices, live, no reload.

---

## Phase 6 — Final Showcase Walkthrough (Week 12–13)
- Same FPP controller, but edit UI hidden — a clean "presentation mode."
- Optional: add a toggle to switch between "Edit Mode" and "Showcase Mode."
- Optional: simple orbit/flythrough camera path as an alternative to manual walking, for demo/sharing purposes.

**Goal:** the finished, shareable "walk through your own design" experience — this is the deliverable that mirrors the DreamSpace AI pitch deck.

---

## Nice-to-haves (post-MVP, not in initial build)
- Furniture placement (drag-and-drop models, snapping to floor).
- Multi-floor support.
- Shareable link (like your DreamSpace AI deck promises) so a client can open the walkthrough without login.
- Mobile/touch controls for the FPP walkthrough.
- Export to video/GIF of a walkthrough path.
- AI-suggested color/material palettes.

---

## Key risks to flag early
1. **CV accuracy on arbitrary floor plans** — Phase 2's editor is the mitigation, not a nice-to-have. Don't skip it to save time.
2. **Collision detection on generated geometry** — walls generated from messy vector data can have gaps/overlaps that break collision. Validate geometry (closed loops, no self-intersections) before extrusion.
3. **Performance** — texture swapping and collision on larger multi-room layouts can get heavy in-browser; keep an eye on draw calls and collider count as room count grows.
