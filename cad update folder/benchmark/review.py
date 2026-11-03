"""Apply a reviewer's corrections to a draft label file and mark it reviewed.

    from review import edit
    edit("nitin_gf", note="...", remove=["d0", "win0"],
         doors=[[2.93, 7.43, 0.81]], walls=[[4.3, 12.43, 4.3, 13.36, 0.1]],
         rooms={"r3": {"dims_ft": None}})

Every call appends its note to the file's "notes", so the ground truth stays auditable.
"""
import json
import os

from bench_core import LABELS


def edit(slug, note, remove=(), walls=(), doors=(), windows=(), rooms=None, move=None, status="reviewed"):
    path = os.path.join(LABELS, f"{slug}.json")
    with open(path, encoding="utf-8") as f:
        lab = json.load(f)
    gone = set(remove)
    for key in ("walls", "doors", "windows", "rooms"):
        lab[key] = [x for x in lab[key] if x["id"] not in gone]

    def next_id(key, prefix):
        used = {x["id"] for x in lab[key]}
        i = 0
        while f"{prefix}{i}" in used:
            i += 1
        return f"{prefix}{i}"

    for w in walls:
        lab["walls"].append({"id": next_id("walls", "w"), "a": [w[0], w[1]], "b": [w[2], w[3]],
                             "t": w[4] if len(w) > 4 else 0.2})
    for key, prefix, items in (("doors", "d", doors), ("windows", "win", windows)):
        for o in items:
            lab[key].append({"id": next_id(key, prefix), "at": [o[0], o[1]], "w": o[2]})
    for rid, changes in (rooms or {}).items():
        room = next(r for r in lab["rooms"] if r["id"] == rid)
        room.update(changes)
    for oid, xy in (move or {}).items():       # move a wall end / opening / room anchor
        for key in ("doors", "windows", "rooms"):
            for x in lab[key]:
                if x["id"] == oid:
                    x["at"] = list(xy)
    lab["check"] = []
    lab["status"] = status
    lab["notes"].append(note)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(lab, f, indent=1, ensure_ascii=False)
    return {k: len(lab[k]) for k in ("walls", "doors", "windows", "rooms")}
