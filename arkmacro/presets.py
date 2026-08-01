"""
Ready-made drop templates, grouped by what you are farming.

ARK's inventory filter is a case-insensitive "contains" match on the item's
display name, and Drop All acts on whatever the filter left on screen. A short
keyword therefore also catches tools, structures and armor that share the word
— so every preset carries a risk flag the UI surfaces.

risk:
    "ok"   -> matches the resource only
    "high" -> also matches gear you are probably carrying
"""
from __future__ import annotations

# The shortest keyword worth typing. The filter is a "contains" match, so a
# one-letter keyword is not a filter at all: "o" lists Stone, Wood, Obsidian,
# Cooked Meat, Hide Boots and most of a bag, and Drop All takes every one of
# them. Three is the floor for anything that names a real resource — "sap" is
# the shortest that does.
MIN_KEYWORD = 3


def too_short(keyword: str) -> bool:
    """Whether a keyword is below the floor. Empty is handled by the caller."""
    return 0 < len(str(keyword).strip()) < MIN_KEYWORD

# (category, [(name, keyword, risk, note)])
PRESETS: list[tuple[str, list[tuple[str, str, str, str]]]] = [
    ("Wood & trees", [
        ("Thatch", "thatch", "ok",
         "Comes with every tree hit and fills your weight fast."),
        ("Wood", "wood", "high",
         "Also matches Wooden Club and any wooden structure in your bag."),
        ("Sap", "sap", "ok", "Resource only."),
    ]),
    ("Stone & metal", [
        ("Stone", "stone", "high",
         "Also matches Stone Pick and Stone Hatchet. Switch to metal tools "
         "before arming this one."),
        ("Metal", "metal", "high",
         "Every metal tool, armor piece and structure carries the word, and "
         "Metal Ingot does too. There is no substring that catches the ore "
         "alone — empty your bag of metal gear before arming this one."),
        ("Flint", "flint", "ok", "Safe — no tool is named Flint."),
        ("Obsidian", "obsidian", "ok", "Resource only."),
        ("Crystal", "crystal", "ok", "Resource only."),
    ]),
    ("Plants & berries", [
        ("Fiber", "fiber", "ok", "Safe."),
        ("Amarberry", "amarberry", "ok", "Yellow berry, dye only."),
        ("Azulberry", "azulberry", "ok", "Blue berry, dye only."),
        ("Tintoberry", "tintoberry", "ok", "Red berry, dye only."),
        ("Every berry", "berry", "high",
         "Also drops Mejoberry (kibble) and Narcoberry (narcotics). Prefer the "
         "three dye berries individually."),
    ]),
    ("Meat & hunting", [
        ("Raw meat", "raw meat", "ok",
         "Does not match Raw Prime Meat — that name has no 'raw meat' run."),
        ("Spoiled meat", "spoiled", "ok", "Safe."),
        ("Hide", "hide", "high",
         "Also matches Hide armor pieces (Hide Shirt, Hide Pants...)."),
        ("Keratin", "keratin", "ok", "Safe."),
        ("Chitin", "chitin", "ok", "Safe."),
        ("Pelt", "pelt", "ok", "Safe."),
    ]),
]


def flat() -> list[tuple[str, str, str, str, str]]:
    """(category, name, keyword, risk, note) for every preset."""
    return [(category, *item) for category, items in PRESETS for item in items]


def default_templates() -> list[dict]:
    """Starting set — only the safe ones ship enabled."""
    return [
        {"name": "Thatch", "keyword": "thatch", "enabled": True},
        {"name": "Fiber", "keyword": "fiber", "enabled": True},
        {"name": "Flint", "keyword": "flint", "enabled": False},
        {"name": "Stone", "keyword": "stone", "enabled": False},
    ]


def risk_of(keyword: str) -> tuple[str, str]:
    """(risk, note) for the preset with this keyword, if there is one."""
    for _category, _name, preset_keyword, risk, note in flat():
        if preset_keyword.lower() == (keyword or "").strip().lower():
            return risk, note
    return "", ""
