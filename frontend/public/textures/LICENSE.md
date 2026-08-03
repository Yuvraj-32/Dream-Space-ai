# Texture assets — sources and licence

Every map in this directory is a published PBR **scan** from
[ambientCG](https://ambientcg.com), released under
[CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/)
(public domain — no attribution required, though it is given here anyway).

None of these files are AI-generated or derived by filtering a colour image.
The normal and roughness maps are the real measured maps that ship with each
scan, which is why they are trustworthy as PBR inputs.

The `.jpg` maps are **git-ignored** (see the repo `.gitignore`) — this file is
the tracked manifest. Fetch or repair the binaries with:

```bash
cd frontend
npm run textures                          # fetch anything missing
node scripts/fetch-textures.mjs --force   # re-fetch everything
```

## Installed materials

"Real-world size" is the physical area the texture covers, as published by
ambientCG. It is mirrored in `src/materials/registry.js` as `tile`, and is what
keeps a brick the same size on a 1 m wall and a 9 m wall. Where ambientCG
publishes no dimensions, a sensible value is assumed (marked ~).

| Folder | ambientCG asset | Real-world size | Material |
|---|---|---|---|
| `plaster_matte/` | [Plaster001](https://ambientcg.com/view?id=Plaster001) | ~2.00 × 2.00 m | Matte Plaster |
| `wood_polished/` | [WoodFloor043](https://ambientcg.com/view?id=WoodFloor043) | 1.30 × 0.65 m | Polished Wood |
| `tile_glossy/` | [Tiles074](https://ambientcg.com/view?id=Tiles074) | 2.10 × 2.10 m | Glossy Tile |
| `concrete_raw/` | [Concrete034](https://ambientcg.com/view?id=Concrete034) | 1.10 × 0.55 m | Raw Concrete |
| `brick_exposed/` | [Bricks086](https://ambientcg.com/view?id=Bricks086) | 2.60 × 1.30 m | Exposed Brick |
| `limewash/` | [PaintedPlaster017](https://ambientcg.com/view?id=PaintedPlaster017) | ~2.00 × 2.00 m | Limewash |
| `venetian_plaster/` | [Plaster006](https://ambientcg.com/view?id=Plaster006) | ~2.00 × 2.00 m | Venetian Plaster |
| `stucco/` | [Plaster002](https://ambientcg.com/view?id=Plaster002) | ~2.00 × 2.00 m | Stucco |
| `microcement/` | [Concrete016](https://ambientcg.com/view?id=Concrete016) | ~2.00 × 2.00 m | Microcement |
| `wood_light_oak/` | [WoodFloor062](https://ambientcg.com/view?id=WoodFloor062) | ~1.20 × 1.20 m | Light Oak |
| `wood_walnut/` | [Wood027](https://ambientcg.com/view?id=Wood027) | ~1.00 × 1.00 m | Walnut |
| `wood_dark_walnut/` | [Wood051](https://ambientcg.com/view?id=Wood051) | 0.80 × 0.80 m | Dark Walnut |
| `travertine_beige/` | [Travertine009](https://ambientcg.com/view?id=Travertine009) | 1.20 × 1.20 m | Travertine Beige |
| `sandstone/` | [Bricks099](https://ambientcg.com/view?id=Bricks099) | ~2.00 × 1.00 m | Sandstone |
| `marble_white/` | [Marble012](https://ambientcg.com/view?id=Marble012) | ~1.50 × 1.50 m | White Marble |
| `marble_black/` | [Marble016](https://ambientcg.com/view?id=Marble016) | ~1.50 × 1.50 m | Black Marble |
| `brick_whitewashed/` | [PaintedBricks004](https://ambientcg.com/view?id=PaintedBricks004) | 1.55 × 1.55 m | Whitewashed Brick |
| `brick_grey/` | [Bricks061](https://ambientcg.com/view?id=Bricks061) | 1.05 × 1.05 m | Grey Brick |
| `wallpaper_linen/` | [Fabric036](https://ambientcg.com/view?id=Fabric036) | ~0.25 × 0.25 m | Linen |
| `wallpaper_grasscloth/` | [Fabric061](https://ambientcg.com/view?id=Fabric061) | 0.40 × 0.40 m | Grasscloth |
| `clay_plaster/` | [Plaster003](https://ambientcg.com/view?id=Plaster003) | ~2.00 × 2.00 m | Clay Plaster |
| `tadelakt/` | [Concrete048](https://ambientcg.com/view?id=Concrete048) | ~2.00 × 2.00 m | Tadelakt |
| `wood_charred/` | [Wood062](https://ambientcg.com/view?id=Wood062) | ~1.00 × 1.00 m | Charred Wood |
| `bamboo/` | [Bamboo002B](https://ambientcg.com/view?id=Bamboo002B) | 2.60 × 2.60 m | Bamboo |
| `wood_painted_panel/` | [PaintedWood009C](https://ambientcg.com/view?id=PaintedWood009C) | ~1.50 × 1.50 m | Painted Panel |
| `terrazzo/` | [Terrazzo013](https://ambientcg.com/view?id=Terrazzo013) | ~1.50 × 1.50 m | Terrazzo |
| `tile_subway/` | [Tiles010](https://ambientcg.com/view?id=Tiles010) | ~1.20 × 1.20 m | Subway Tile |
| `granite/` | [Granite002A](https://ambientcg.com/view?id=Granite002A) | ~1.50 × 1.50 m | Granite |
| `limestone/` | [Tiles143](https://ambientcg.com/view?id=Tiles143) | 2.00 × 2.00 m | Limestone |
| `onyx_polished/` | [Onyx015](https://ambientcg.com/view?id=Onyx015) | ~1.80 × 1.80 m | Polished Onyx |
| `brick_rustic_red/` | [Bricks026](https://ambientcg.com/view?id=Bricks026) | ~2.00 × 1.00 m | Rustic Red Brick |
| `brick_charcoal/` | [Bricks056](https://ambientcg.com/view?id=Bricks056) | 1.05 × 1.05 m | Charcoal Brick |
| `cork/` | [Cork004](https://ambientcg.com/view?id=Cork004) | ~0.90 × 0.90 m | Cork |
| `rattan/` | [Wicker010A](https://ambientcg.com/view?id=Wicker010A) | ~0.70 × 0.70 m | Rattan |

## Required files

Each folder must contain exactly these three files, all `1K-JPG` variants:

```
<folder>/
  color.jpg        ← <Asset>_1K-JPG_Color.jpg        (sRGB albedo)
  normal.jpg       ← <Asset>_1K-JPG_NormalGL.jpg     (OpenGL convention — NOT NormalDX)
  roughness.jpg    ← <Asset>_1K-JPG_Roughness.jpg    (linear)
```

The material picker reuses `color.jpg` as its preview swatch (scaled down by
the browser), so there is no separate thumbnail file to keep in sync.

Displacement and ambient-occlusion maps are deliberately **not** used. `NormalDX`
(DirectX convention, green channel inverted) must not be substituted for
`NormalGL` — it inverts every surface's lighting.

## Awaiting assets

Two wallpapers are registered but **hidden from the picker** because no genuine
CC0 PBR scan of them exists — a printed pattern is artwork, not a scanned
surface, and fabricating normal/roughness maps for one would be precisely the
fake-PBR shortcut this project avoids.

| Folder | Material | Needs |
|---|---|---|
| `wallpaper_botanical/` | Botanical | `color.jpg`, `normal.jpg`, `roughness.jpg` |
| `wallpaper_geometric/` | Geometric | `color.jpg`, `normal.jpg`, `roughness.jpg` |

To enable one: drop a licensed set into its folder using the filenames above,
set the material's `tile` to the artwork's real-world repeat size in metres,
and remove `assetPending: true` from its entry in `src/materials/registry.js`.
A tiling albedo alone is enough to start — omit `normal`/`roughness` from that
entry's `maps` and the scalar values are used instead of a fabricated map.

## Behaviour when a map is missing

Non-fatal by design. The material falls back to its scalar `roughness` /
`metalness` from the registry and logs one console warning, so a fresh clone
without textures still runs.
