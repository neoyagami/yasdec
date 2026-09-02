from __future__ import annotations

from typing import TypedDict


class DeckModel(TypedDict):
    name: str
    rows: int
    columns: int
    key_count: int
    key_pixels: tuple[int, int]
    aliases: tuple[str, ...]
    spectrum_fps: int


# Models represented by a button grid. Dials and pedals are deliberately
# excluded; Neo's auxiliary info strip is ignored by this button editor.
BUTTON_DECK_MODELS: dict[str, DeckModel] = {
    "mini": {
        "name": "Stream Deck Mini",
        "rows": 2,
        "columns": 3,
        "key_count": 6,
        "key_pixels": (80, 80),
        "aliases": ("stream deck mini", "mini", "6 key"),
        "spectrum_fps": 12,
    },
    "original": {
        "name": "Stream Deck Original",
        "rows": 3,
        "columns": 5,
        "key_count": 15,
        "key_pixels": (72, 72),
        "aliases": ("stream deck original", "stream deck (original)", "original"),
        "spectrum_fps": 8,
    },
    "mk2": {
        "name": "Stream Deck MK.2",
        "rows": 3,
        "columns": 5,
        "key_count": 15,
        "key_pixels": (72, 72),
        "aliases": ("stream deck mk.2", "stream deck mk2", "mk.2", "mk2", "stream deck"),
        "spectrum_fps": 8,
    },
    "neo": {
        "name": "Stream Deck Neo (keys)",
        "rows": 2,
        "columns": 4,
        "key_count": 8,
        "key_pixels": (96, 96),
        "aliases": ("stream deck neo", "neo"),
        "spectrum_fps": 10,
    },
    "xl": {
        "name": "Stream Deck XL",
        "rows": 4,
        "columns": 8,
        "key_count": 32,
        "key_pixels": (96, 96),
        "aliases": ("stream deck xl", "xl", "32 key"),
        "spectrum_fps": 4,
    },
}


def match_deck_model(deck_type: str, key_count: int, layout: tuple[int, int]) -> str | None:
    normalized = deck_type.casefold().strip()
    matches: list[tuple[int, str]] = []
    for model_id, model in BUTTON_DECK_MODELS.items():
        for alias in model["aliases"]:
            candidate = alias.casefold()
            if candidate == normalized:
                matches.append((100 + len(candidate), model_id))
            elif candidate in normalized:
                matches.append((len(candidate), model_id))
    if matches:
        return max(matches)[1]

    rows, columns = layout
    dimensional = [
        model_id
        for model_id, model in BUTTON_DECK_MODELS.items()
        if model["key_count"] == key_count and model["rows"] == rows and model["columns"] == columns
    ]
    return dimensional[0] if len(dimensional) == 1 else None
