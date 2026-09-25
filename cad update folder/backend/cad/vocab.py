"""Room-name vocabulary shared by cluster ranking (Phase 1) and room typing (Phase 2).

Keys are the app's room types (what SceneCanvas/MaterialSelector display);
values are lowercase words/prefixes seen in CAD labels, including the Spanish
and Indian-English terms found in the Phase 0 samples.
"""
ROOM_WORDS = {
    "bedroom": ["bed", "bedroom", "master", "guest room", "dormitorio", "recamara", "habitacion"],
    "living_room": ["living", "drawing room", "family", "lounge", "hall", "sala", "estar", "sit out", "sit-out"],
    "kitchen": ["kitchen", "kit.", "cocina", "pantry"],
    "dining": ["dining", "comedor"],
    "bath": ["bath", "toilet", "wc", "w.c", "wash", "shower", "powder", "bano", "baño", "aseo", "sanitario"],
    "closet": ["closet", "wardrobe", "dress", "vestidor"],
    "storage": ["store", "storage", "utility", "laundry", "lavanderia", "deposito", "bodega"],
    "office": ["study", "office", "estudio", "library"],
    "garage": ["garage", "parking", "car porch", "cochera", "garaje"],
    "outdoor": ["balcony", "terrace", "porch", "verandah", "veranda", "deck", "patio", "terraza", "balcon", "gazebo", "bbq"],
    "entry": ["entrance", "entry", "foyer", "lobby", "passage", "corridor", "vestibule", "pasillo", "recibidor"],
    "pooja": ["pooja", "puja", "prayer", "mandir"],
}

def room_type_for(text):
    """Map a CAD label ('BED ROOM - 3 12'-3\"X14'-0\"', 'SALA FAMILIAR') to an
    app room type, or None if it doesn't look like a room name."""
    t = " " + " ".join(text.lower().replace("_", " ").split()) + " "
    t = t.replace("bed room", "bedroom").replace("living room", "living").replace("dining room", "dining")
    for room_type, words in ROOM_WORDS.items():
        for w in words:
            if f" {w}" in t:
                return room_type
    return None


def looks_like_room_label(text):
    return len(text) <= 60 and room_type_for(text) is not None
