#!/usr/bin/env python3
"""Character token management for consistent character generation across book series.

Directory structure:
  projects/characters/
    <series>/
      <character>.json          # character token file
      character_index.json      # index of all characters in series
      references/<character>/   # reference images
    char_<name>/                # image sets generated on the Characters tab (not a series)
    _schema.json                # validation schema

Each character token:
{
  "name": "Adam",
  "series": "main",
  "visual_token": "adam_visual_token_here",
  "trigger_words": ["adam", "first man", "biblical figure"],
  "physical_traits": {
    "age": "30s",
    "hair": "dark, shoulder-length",
    "eyes": "brown",
    "build": "athletic",
    "skin": "olive",
    "distinguishing_features": ["strong jaw", "kind eyes"]
  },
  "clothing": "simple tunic, earth tones",
  "voice": "bm_george",
  "lora": {
    "repo": "username/adam-lora",
    "trigger_word": "adam_token",
    "base_model": "LTX-Video",
    "trained": false
  },
  "reference_images": [
    "projects/characters/main/references/adam/ref_01.png",
    "projects/characters/main/references/adam/ref_02.png"
  ],
  "consistency_notes": "Always depict as the first man, noble but human",
  "created": "2026-01-15",
  "updated": "2026-01-15"
}
"""
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Set, Union
from dataclasses import dataclass, asdict, field
from enum import Enum

# Import bookkit for project structure
try:
    from bookkit import ROOT, PROJECTS, SLUG_RE, slugify
except ImportError:
    ROOT = Path(__file__).resolve().parent.parent
    PROJECTS = ROOT / "projects"

CHARACTERS_ROOT = PROJECTS / "characters"      # shared between books: <series>/<character>.json and <series>/references/<character>/

# ===== COMPREHENSIVE TRAIT SYSTEM =====

class CharacterArchetype(str, Enum):
    """Character archetypes: plain human and the "any book" kinds, plus those for biblical and epic stories."""
    HUMAN = "human"                    # Mortal humans
    HUMAN_PRE_FALL = "human_pre_fall"  # Pre-Fall humans (Eden state)
    HUMAN_PROPHET = "human_prophet"    # Prophetic figures
    HUMAN_PATRIARCH = "human_patriarch" # Patriarchs (Abraham, Isaac, Jacob)
    HUMAN_WARRIOR = "human_warrior"    # Warriors/kings (David, Joshua)
    ANGEL_MESSENGER = "angel_messenger"    # Messenger angels (Gabriel)
    ANGEL_WARRIOR = "angel_warrior"        # Warrior angels (Michael)
    ANGEL_GUARDIAN = "angel_guardian"      # Guardian angels (Cherubim)
    ANGEL_SERAPHIM = "angel_seraphim"      # Highest order (Seraphim)
    ANGEL_LIVING_CREATURE = "angel_living_creature"  # Living Creatures
    DIVINE_PRESENCE = "divine_presence"    # God/theophany
    CHILD = "child"                        # Any book: a child
    CREATURE = "creature"                  # Any book: an animal, monster or fantasy being
    ROBOT = "robot"                        # Any book: a robot or machine
    SUPERNATURAL = "supernatural"          # Any book: a ghost, spirit, god or magical being
    FALLEN_ANGEL = "fallen_angel"          # Satan/demons
    FALLEN_DISGUISED = "fallen_disguised"  # Satan in disguise


# Archetype field requirements
ARCHETYPE_CONFIG = {
    CharacterArchetype.CHILD: {
        "required_physical": ["age", "hair", "eyes"],
        "optional_physical": ["height", "build", "skin", "expression", "distinguishing_features"],
        "required_fields": ["clothing"],
        "optional_fields": ["voice", "accessories", "posture", "gait"],
    },
    CharacterArchetype.CREATURE: {
        "required_physical": [],
        "optional_physical": ["height", "build", "skin", "eyes", "expression", "distinguishing_features", "scars"],
        "required_fields": [],
        "optional_fields": ["voice", "clothing", "accessories", "posture", "gait"],
    },
    CharacterArchetype.ROBOT: {
        "required_physical": [],
        "optional_physical": ["height", "build", "eyes", "expression", "distinguishing_features"],
        "required_fields": [],
        "optional_fields": ["voice", "clothing", "accessories", "weapons", "armor", "posture", "gait"],
    },
    CharacterArchetype.SUPERNATURAL: {
        "required_physical": [],
        "optional_physical": ["age", "height", "build", "skin", "hair", "eyes", "expression", "distinguishing_features", "luminosity"],
        "required_fields": [],
        "optional_fields": ["voice", "clothing", "accessories", "posture", "gait", "aura"],
    },
    CharacterArchetype.HUMAN: {
        "required_physical": ["age", "height", "build", "skin", "hair", "eyes"],
        "optional_physical": ["facial_hair", "expression", "distinguishing_features", "scars", "tattoos"],
        "required_fields": ["clothing", "voice"],
        "optional_fields": ["accessories", "weapons", "posture", "gait"],
    },
    CharacterArchetype.HUMAN_PRE_FALL: {
        "required_physical": ["age", "height", "build", "skin", "hair", "eyes", "expression"],
        "optional_physical": ["facial_hair", "distinguishing_features"],
        "required_fields": ["clothing"],  # "unclothed" is valid
        "optional_fields": ["voice", "posture", "gait"],
    },
    CharacterArchetype.HUMAN_PROPHET: {
        "required_physical": ["age", "height", "build", "skin", "hair", "eyes", "expression"],
        "optional_physical": ["facial_hair", "distinguishing_features", "scars"],
        "required_fields": ["clothing", "voice"],
        "optional_fields": ["accessories", "posture", "gait", "aura"],
    },
    CharacterArchetype.HUMAN_PATRIARCH: {
        "required_physical": ["age", "height", "build", "skin", "hair", "eyes", "facial_hair"],
        "optional_physical": ["expression", "distinguishing_features", "scars"],
        "required_fields": ["clothing", "voice"],
        "optional_fields": ["accessories", "weapons", "posture", "gait", "authority_markers"],
    },
    CharacterArchetype.HUMAN_WARRIOR: {
        "required_physical": ["age", "height", "build", "skin", "hair", "eyes"],
        "optional_physical": ["facial_hair", "expression", "distinguishing_features", "scars", "musculature"],
        "required_fields": ["clothing", "voice"],
        "optional_fields": ["weapons", "armor", "accessories", "posture", "gait", "battle_worn"],
    },
    CharacterArchetype.ANGEL_MESSENGER: {
        "required_physical": ["height", "build", "eyes", "wings"],
        "optional_physical": ["hair", "skin", "expression", "face_covering", "luminosity"],
        "required_fields": ["clothing", "voice"],
        "optional_fields": ["accessories", "posture", "light_color", "aura"],
    },
    CharacterArchetype.ANGEL_WARRIOR: {
        "required_physical": ["height", "build", "eyes", "wings"],
        "optional_physical": ["hair", "skin", "expression", "face_covering", "luminosity", "musculature", "scars"],
        "required_fields": ["clothing", "voice"],
        "optional_fields": ["armor", "accessories", "posture", "light_color", "aura", "weapons"],
    },
    CharacterArchetype.ANGEL_GUARDIAN: {
        "required_physical": ["height", "build", "eyes", "wings", "faces"],
        "optional_physical": ["hair", "skin", "expression", "luminosity"],
        "required_fields": ["clothing"],
        "optional_fields": ["voice", "accessories", "posture", "light_color", "aura"],
    },
    CharacterArchetype.ANGEL_SERAPHIM: {
        "required_physical": ["height", "wings"],
        "optional_physical": ["build", "eyes", "expression", "luminosity", "faces"],
        "required_fields": [],
        "optional_fields": ["voice", "clothing", "posture", "light_color", "fire_effects", "aura"],
    },
    CharacterArchetype.ANGEL_LIVING_CREATURE: {
        "required_physical": ["faces", "wings"],
        "optional_physical": ["eyes_covered_in_wings", "form", "luminosity", "expression"],
        "required_fields": [],
        "optional_fields": ["voice", "posture", "light_color", "aura"],
    },
    CharacterArchetype.DIVINE_PRESENCE: {
        "required_physical": [],
        "optional_physical": ["luminosity", "formlessness", "manifestation", "eyes", "voice_quality"],
        "required_fields": [],
        "optional_fields": ["clothing", "light_color", "accompanying_phenomena", "aura"],
    },
    CharacterArchetype.FALLEN_ANGEL: {
        "required_physical": ["height", "build", "skin", "eyes", "wings"],
        "optional_physical": ["hair", "expression", "scars", "chains", "corruption"],
        "required_fields": ["clothing", "voice"],
        "optional_fields": ["weapons", "accessories", "posture", "light_color", "fire_effects", "aura"],
    },
    CharacterArchetype.FALLEN_DISGUISED: {
        "required_physical": ["height", "build", "skin", "eyes", "expression"],
        "optional_physical": ["hair", "shifting_features", "unsettling_quality", "perfection"],
        "required_fields": ["clothing", "voice"],
        "optional_fields": ["accessories", "posture", "light_color", "aura"],
    },
}

# Valid value sets for dropdowns/validation
VALID_VALUES = {
    "age": ["infant", "child", "adolescent", "young_adult", "adult", "middle_aged", "old", "ancient", "timeless",
            "30", "25", "26", "35", "40", "50", "60", "100", "600", "900"],
    "height": ["very_short", "short", "average", "tall", "very_tall", "towering", "colossal",
               "tall lean", "short", "massive", "towering"],
    "build": ["frail", "slender", "lean", "average", "athletic", "muscular", "powerful", "massive", "colossal",
              "lean", "shepherd's frame", "farmer's build", "powerful", "weathered"],
    "skin": ["pale", "fair", "light", "olive", "brown", "dark_brown", "bronze", "copper", "ebony", "luminous", "translucent", "charred", "obsidian", "golden", "pearl", "iridescent",
             "olive-brown", "golden-brown", "warm golden-brown", "warm golden", "weathered bronze", "bronze"],
    "hair": ["none", "bald", "very_short", "short", "medium", "long", "very_long", "flowing", "curly", "wavy", "straight", "braided", "loc'd", "silver", "white", "golden", "dark", "black", "brown", "red", "auburn", "flaming", "luminous",
             "long dark brown", "very long dark wavy", "long dark brown hair", "short dark", "white", "silver-white", "long white", "dark", "dark wavy"],
    "hair_color": ["silver", "white", "golden", "blonde", "light_brown", "brown", "dark_brown", "black", "red", "auburn", "flaming", "luminous", "iridescent"],
    "eyes": ["blue", "green", "hazel", "brown", "dark_brown", "black", "amber", "gray", "violet", "golden", "burning", "luminous", "all_seeing", "multifaceted", "covered",
             "deep brown", "gentle brown", "large dark", "tear-shaped", "silver-white", "burning coal", "emerald-green", "deep amber", "like burning coals", "full of eyes"],
    "facial_hair": ["none", "clean_shaven", "stubble", "short_beard", "full_beard", "long_beard", "braided_beard", "mustache", "goatee",
                    "short dark beard", "long white beard", "short beard", "dark beard"],
    "expression": ["neutral", "serene", "joyful", "sorrowful", "grief_worn", "determined", "fierce", "compassionate", "stern", "peaceful", "innocent", "unashamed", "wise", "authoritative", "terrifying", "gentle", "radiant", "burning",
                   "grief-worn", "innocent unashamed", "unashamed peaceful", "peaceful", "kind", "intense", "stern radiant"],
    "distinguishing_features": ["strong_jaw", "high_cheekbones", "prominent_nose", "deep_set_eyes", "broad_forehead", "scar", "birthmark", "tattoo", "piercing", "none",
                                "strong jaw", "kind eyes", "distinctive jawline", "calloused hands", "massive frame", "weathered"],
    "scars": ["none", "battle_scars", "surgical", "ritual", "miraculous_healed", "brands"],
    "tattoos": ["none", "tribal", "ritual", "covenantal", "prophetic", "ownership"],
    "clothing": ["unclothed", "loincloth", "tunic", "robe", "mantle", "priestly_garments", "royal_robes", "armor", "warrior_garb", "simple_garments", "ravels", "light_itself", "shadow_draped",
                 "simple tunic", "earth tones", "rough woven fabric", "simple linen tunic", "white robes", "gleaming silver armor", "flowing golden hair", "robes of deep blue", "deep blue robes",
                 "naked", "unclothed naked", "unashamed in paradise", "naked unashamed"],
    "voice": ["bm_george", "bm_daniel", "bm_lewis", "af_bella", "af_sarah", "af_nicole", "am_michael", "am_adam", "divine_resonance", "thunderous", "gentle_whisper", "many_waters", "melodic", "terrifying", "silken"],
    "accessories": ["none", "staff", "crown", "diadem", "signet_ring", "phylacteries", "prayer_shawl", "sash", "belt", "pouch", "scroll", "tablet", "lamp", "incense"],
    "weapons": ["none", "sword", "spear", "bow", "sling", "staff_weapon", "divine_sword", "flaming_sword", "trumpet", "seal"],
    "armor": ["none", "leather", "scale", "chainmail", "plate", "divine_armor", "light_armor", "ceremonial"],
    "posture": ["standing", "kneeling", "prostrate", "seated", "enthroned", "walking", "floating", "hovering", "combat_stance", "blessing_pose"],
    "gait": ["slow", "measured", "purposeful", "swift", "limping", "gliding", "floating", "heavy"],
    "luminosity": ["none", "faint", "soft", "radiant", "blinding", "pulsing", "steady", "divine_glory", "luminous", "glowing", "brilliant"],
    "wings": ["none", "two", "four", "six", "many", "covering_face", "covering_feet", "folded", "spread", "flaming", "luminous", "feathered", "energy",
              "vast", "four-faced", "six-winged",
              "each unique", "white-gold", "silver-white", "shimmering verdant light", "burning fire", "charred", "six wings - face", "four each", "covering face", "covering feet", "covering face and feet", "veiled",
              "spread wide", "gold-red", "broken", "feet", "covered in eyes", "six each", "spanning wide", "flight", "full of eyes"],
    "faces": ["one", "four", "six", "many", "lion_ox_eagle_human", "covered_by_wings", "lion", "ox", "eagle", "human", "lion ox eagle human", "man", "woman", "child"],
    "light_color": ["white", "gold", "amber", "blue", "violet", "rainbow", "fire", "blood_red", "emerald", "sapphire"],
    "aura": ["none", "peaceful", "holy", "terrifying", "authoritative", "compassionate", "judgment", "mercy", "power", "glory",
             "holy", "terrifying", "authoritative", "compassionate", "judgment", "mercy"],
    "corruption": ["none", "charred", "cracked", "shadowed", "twisted", "burning_inside", "fallen_glory"],
    "perfection": ["impossible", "uncanny", "shifting", "flawless_beauty", "deceptive"],
    "shifting_features": ["subtle", "obvious", "constant", "emotion_triggered"],
    "unsettling_quality": ["mild", "strong", "overwhelming", "hypnotic"],
    "fire_effects": ["none", "eyes", "hair", "wings", "surrounding", "internal", "sword"],
    "manifestation": ["light", "cloud", "fire", "voice", "human_form", "throne", "chariot", "overwhelming light", "overwhelming", "divine light", "radiance"],
    "voice_quality": ["thunder", "many_waters", "gentle_whisper", "trumpet", "silence"],
    "accompanying_phenomena": ["earthquake", "storm", "silence", "light", "smoke", "angels", "music"],
    "authority_markers": ["staff", "crown", "signet", "mantle", "tablets", "scroll", "divine_seal"],
    "battle_worn": ["fresh", "scarred", "weary", "bloodied", "victorious"],
    "musculature": ["lean", "defined", "massive", "supernatural", "none"],
    "face_covering": ["none", "wings", "light", "veil", "helmet"],
    "eyes_covered_in_wings": ["all", "some", "none"],
    "form": ["beast", "human", "hybrid", "wheel", "throne", "formless divine presence", "formless"],
    "formlessness": ["total", "humanoid_suggestion", "enthroned", "riding_chariot"],
}


def validate_trait(field: str, value: str, archetype: Optional[CharacterArchetype] = None) -> tuple[bool, str]:
    """Validate a trait value against allowed values.
    Returns (is_valid, error_message).

    This is lenient - it accepts any value but provides suggestions for dropdowns.
    Strict validation only applies to fields that MUST be from a controlled vocabulary.
    """
    # Fields that should be validated strictly (controlled vocabulary)
    STRICT_FIELDS = {
        "archetype",
        "luminosity", "wings", "faces", "light_color", "aura",
        "corruption", "perfection", "shifting_features", "unsettling_quality",
        "fire_effects", "manifestation", "voice_quality", "accompanying_phenomena",
        "authority_markers", "battle_worn", "musculature", "face_covering",
        "eyes_covered_in_wings", "form", "formlessness",
    }

    if field not in VALID_VALUES:
        return True, ""  # Unknown field, allow it

    # For non-strict fields, accept any value (they're free-text descriptions)
    if field not in STRICT_FIELDS:
        return True, ""

    # Strict validation for controlled vocabulary fields
    valid = VALID_VALUES[field]
    values = [v.strip() for v in value.split(",")]
    for v in values:
        if v and v not in valid:
            return False, f"Invalid {field}: '{v}'. Valid options: {', '.join(valid)}"
    return True, ""


def validate_character(character: Dict, archetype: Optional[CharacterArchetype] = None) -> List[str]:
    """Validate a character token against its archetype requirements.
    Returns list of error messages (empty if valid)."""
    errors = []

    # Determine archetype if not provided
    if archetype is None:
        archetype_str = character.get("archetype", "human")
        try:
            archetype = CharacterArchetype(archetype_str)
        except ValueError:
            errors.append(f"Unknown archetype: {archetype_str}")
            archetype = CharacterArchetype.HUMAN

    config = ARCHETYPE_CONFIG.get(archetype, ARCHETYPE_CONFIG[CharacterArchetype.HUMAN])

    # Check required physical traits
    physical = character.get("physical_traits", {})
    for req in config.get("required_physical", []):
        if req not in physical or not physical[req]:
            errors.append(f"Missing required physical trait for {archetype.value}: {req}")

    # Check optional physical traits (warn but don't error)
    for opt in config.get("optional_physical", []):
        if opt not in physical:
            pass  # Optional

    # Validate physical trait values
    for key, value in physical.items():
        is_valid, msg = validate_trait(key, value, archetype)
        if not is_valid:
            errors.append(msg)

    # Check required fields
    for req in config.get("required_fields", []):
        if req not in character or not character[req]:
            errors.append(f"Missing required field for {archetype.value}: {req}")

    # Validate field values
    for key in config.get("required_fields", []) + config.get("optional_fields", []):
        if key in character and character[key]:
            is_valid, msg = validate_trait(key, character[key], archetype)
            if not is_valid:
                errors.append(msg)

    return errors


def get_archetype_fields(archetype: CharacterArchetype) -> Dict[str, List[str]]:
    """Get the field configuration for an archetype."""
    return ARCHETYPE_CONFIG.get(archetype, ARCHETYPE_CONFIG[CharacterArchetype.HUMAN])


def get_valid_values(field: str) -> List[str]:
    """Get valid values for a field (for dropdowns)."""
    return VALID_VALUES.get(field, [])


def create_character_template(archetype: CharacterArchetype, name: str, series: str) -> Dict:
    """Create a character template with default values for an archetype."""
    config = ARCHETYPE_CONFIG.get(archetype, ARCHETYPE_CONFIG[CharacterArchetype.HUMAN])

    physical_traits = {}
    for req in config.get("required_physical", []):
        physical_traits[req] = ""
    for opt in config.get("optional_physical", []):
        physical_traits[opt] = ""

    template = {
        "name": name,
        "series": series,
        "archetype": archetype.value,
        "visual_token": "",
        "trigger_words": [name.lower()],
        "physical_traits": physical_traits,
    }

    for req in config.get("required_fields", []):
        template[req] = ""
    for opt in config.get("optional_fields", []):
        template[opt] = ""

    template.update({
        "lora": {"repo": "", "trigger_word": "", "base_model": "", "trained": False},
        "reference_images": [],
        "consistency_notes": "",
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat(),
    })

    return template


SCHEMA = {
    "type": "object",
    "required": ["name", "series", "visual_token", "physical_traits", "archetype"],
    "properties": {
        "name": {"type": "string"},
        "series": {"type": "string"},
        "archetype": {"type": "string", "enum": [a.value for a in CharacterArchetype]},
        "visual_token": {"type": "string"},
        "trigger_words": {"type": "array", "items": {"type": "string"}},
        "physical_traits": {"type": "object"},
        "clothing": {"type": "string"},
        "voice": {"type": "string"},
        "accessories": {"type": "string"},
        "weapons": {"type": "string"},
        "armor": {"type": "string"},
        "posture": {"type": "string"},
        "gait": {"type": "string"},
        "luminosity": {"type": "string"},
        "wings": {"type": "string"},
        "faces": {"type": "string"},
        "light_color": {"type": "string"},
        "aura": {"type": "string"},
        "corruption": {"type": "string"},
        "perfection": {"type": "string"},
        "shifting_features": {"type": "string"},
        "unsettling_quality": {"type": "string"},
        "fire_effects": {"type": "string"},
        "manifestation": {"type": "string"},
        "voice_quality": {"type": "string"},
        "accompanying_phenomena": {"type": "string"},
        "authority_markers": {"type": "string"},
        "battle_worn": {"type": "string"},
        "musculature": {"type": "string"},
        "face_covering": {"type": "string"},
        "eyes_covered_in_wings": {"type": "string"},
        "form": {"type": "string"},
        "formlessness": {"type": "string"},
        "lora": {"type": "object"},
        "stages": {"type": "array"},
        "reference_images": {"type": "array", "items": {"type": "string"}},
        "consistency_notes": {"type": "string"},
        "created": {"type": "string"},
        "updated": {"type": "string"},
    }
}


def ensure_characters_dir():
    """Ensure the characters root directory exists."""
    CHARACTERS_ROOT.mkdir(parents=True, exist_ok=True)


def get_series_dir(series: str) -> Path:
    """Get the directory for a book series."""
    safe_series = slugify(series)
    return CHARACTERS_ROOT / safe_series


def get_character_path(series: str, character_name: str) -> Path:
    """Get the path to a character token file."""
    safe_name = slugify(character_name)
    return get_series_dir(series) / f"{safe_name}.json"


def get_index_path(series: str) -> Path:
    """Get the path to the character index file."""
    return get_series_dir(series) / "character_index.json"


def load_character(series: str, character_name: str) -> Optional[Dict]:
    """Load a character token from file."""
    path = get_character_path(series, character_name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def save_character(character: Dict) -> Path:
    """Save a character token to file."""
    ensure_characters_dir()
    series = character.get("series", "unknown")
    name = character.get("name", "unnamed")

    series_dir = get_series_dir(series)
    series_dir.mkdir(parents=True, exist_ok=True)

    path = series_dir / f"{slugify(name)}.json"

    # Update timestamp
    character["updated"] = datetime.now().isoformat()
    if "created" not in character:
        character["created"] = character["updated"]

    path.write_text(json.dumps(character, indent=2))
    update_index(series)
    return path


def update_index(series: str):
    """Update the character index for a series."""
    series_dir = get_series_dir(series)
    if not series_dir.exists():
        return

    index = {"series": series, "characters": []}
    for path in sorted(series_dir.glob("*.json")):
        if path.name == "character_index.json":
            continue
        try:
            char = json.loads(path.read_text())
            index["characters"].append({
                "name": char.get("name"),
                "file": path.name,
                "visual_token": char.get("visual_token", "")[:100],
                "has_lora": char.get("lora", {}).get("trained", False),
                "updated": char.get("updated", "")
            })
        except Exception:
            pass

    (series_dir / "character_index.json").write_text(json.dumps(index, indent=2))


def list_characters(series: str) -> List[Dict]:
    """List all characters in a series."""
    index_path = get_index_path(series)
    if not index_path.exists():
        return []
    try:
        return json.loads(index_path.read_text()).get("characters", [])
    except Exception:
        return []


def list_series() -> List[str]:
    """List all book series with character tokens."""
    if not CHARACTERS_ROOT.exists():
        return []
    # a folder with promptset.json is a generated character IMAGE set (char_adam, ...), not a series of character tokens
    return sorted(d.name for d in CHARACTERS_ROOT.iterdir() if d.is_dir() and d.name != "_schema" and not (d / "promptset.json").exists())


def get_character_tokens_for_prompt(series: str, characters: List[str]) -> str:
    """Generate a character token string for inclusion in prompts."""
    tokens = []
    for char_name in characters:
        char = load_character(series, char_name)
        if char:
            token_parts = [char.get("visual_token", "")]
            if char.get("physical_traits"):
                traits = char["physical_traits"]
                desc = ", ".join(f"{k}: {v}" for k, v in traits.items() if v)
                if desc:
                    token_parts.append(desc)
            if char.get("clothing"):
                token_parts.append(f"wearing {char['clothing']}")
            if char.get("consistency_notes"):
                token_parts.append(char["consistency_notes"])
            tokens.append(" | ".join(token_parts))
    return "\n\nCHARACTER TOKENS:\n" + "\n".join(tokens) if tokens else ""


# <book>.json "voice" words (see bookkit.VOICE_MAP) -> Kokoro voice ids, which is what a character token stores
BOOK_VOICES = {"narrator": "bm_george", "male": "am_michael", "female": "af_bella", "elder": "bm_lewis",
                "deity": "bm_lewis", "child": "af_sky", "villain": "am_adam"}


def _character_from_book_entry(name: str, data: Dict) -> Dict:
    """One <book>.json character -> a character token. Handles both shapes:
       list form written by book_continuity.py : {"name", "token", "voice": "male"}
       older dict form                    : {"visual_token", "physical_traits", "clothing", "voice", "aliases", "notes"}"""
    voice = data.get("voice", "")
    return {
        "name": name,
        "series": "",  # set by the caller
        "visual_token": data.get("visual_token") or data.get("token", ""),
        "trigger_words": [name.lower()] + list(data.get("aliases", [])),
        "physical_traits": data.get("physical_traits", {}),
        "clothing": data.get("clothing", ""),
        "voice": BOOK_VOICES.get(voice, voice),
        "lora": {"repo": "", "trigger_word": "", "base_model": "", "trained": False},
        "reference_images": [],
        "consistency_notes": data.get("notes", ""),
        "stages": data.get("stages") or [],
    }


def extract_characters_from_book(book_path: Path) -> List[Dict]:
    """Extract character definitions from a <book>.json file."""
    if not book_path.exists():
        return []

    try:
        continuity = json.loads(book_path.read_text())
    except Exception:
        return []

    chars = continuity.get("characters", [])
    characters = []
    if isinstance(chars, dict):                       # older shape: {name: {...}}
        for name, data in chars.items():
            if isinstance(data, dict):
                characters.append(_character_from_book_entry(name, data))
    elif isinstance(chars, list):                     # shape written by book_continuity.py: [{name, token, voice}, ...]
        for data in chars:
            if isinstance(data, dict) and data.get("name"):
                characters.append(_character_from_book_entry(str(data["name"]), data))
    return characters


# The fields a continuity book can supply. On overwrite only these are replaced, and only when the book has a value for them.
BOOK_FIELDS = ("visual_token", "physical_traits", "clothing", "voice", "consistency_notes", "stages")


def sync_from_book(project_slug: str, series: Optional[str] = None, overwrite: bool = False, dry_run: bool = False) -> Dict:
    """Copy a project's <book>.json characters into a series.
    overwrite=False : characters already in the series are left alone (they may have been edited by hand).
    overwrite=True  : an existing character gets the continuity book's visual token, voice, clothing, traits and notes (each only if the continuity book
                      has a value), plus any new trigger words. Reference images, LoRA info, created date, other fields and trigger
                      words you added are kept.
    dry_run=True    : count what would happen, write nothing.
    Returns {"series", "continuity" (was there a <book>.json), "total", "added", "updated", "skipped", "dry_run"}."""
    book_path = PROJECTS / "books" / project_slug / f"{project_slug}.json"
    series = series or project_slug
    report = {"series": series, "continuity": book_path.exists(), "total": 0, "added": 0, "updated": 0, "skipped": 0, "dry_run": dry_run}
    if not report["continuity"]:
        return report
    for char in extract_characters_from_book(book_path):
        report["total"] += 1
        char["series"] = series
        current = load_character(series, char["name"]) if get_character_path(series, char["name"]).exists() else None
        if current is not None and not overwrite:
            report["skipped"] += 1
            continue
        if current is not None:                       # overwrite: merge, do not replace the whole file
            merged = dict(current)
            merged["series"] = series
            for key in BOOK_FIELDS:
                if char.get(key):
                    merged[key] = char[key]
            words = list(current.get("trigger_words", []))
            words += [w for w in char.get("trigger_words", []) if w not in words]
            merged["trigger_words"] = words
            char = merged
        if not dry_run:
            save_character(char)
        report["updated" if current is not None else "added"] += 1
    return report


VOICE_WORD_OF = {}           # Kokoro voice id -> the book's voice word; the first word listed for an id wins
for _w, _v in BOOK_VOICES.items():
    VOICE_WORD_OF.setdefault(_v, _w)


def send_to_book(project_slug: str, series: str, names: List[str], dry_run: bool = False) -> Dict:
    """The other direction of sync_from_book: copy the chosen series characters INTO the book's continuity book (<book>.json).
    A character already in the book gets the series' visual token (and its voice, when the series voice maps to one of the book's voice
    words); a character the book does not have is added. Other fields in the book's file are kept. Chapters that are already written
    keep the old wording; only chapters written (or rebuilt) afterwards use the new tokens.
    Returns {"book", "found" (is there a <book>.json), "updated", "added", "unchanged", "missing" (names not in the series), "dry_run"}."""
    path = PROJECTS / "books" / project_slug / f"{project_slug}.json"
    report = {"book": project_slug, "found": path.exists(), "updated": 0, "added": 0, "unchanged": 0, "missing": [], "dry_run": dry_run}
    if not report["found"]:
        return report
    continuity = json.loads(path.read_text())
    chars = continuity.get("characters")
    if not isinstance(chars, list):
        raise ValueError(f"{project_slug}.json keeps its characters in an older layout that cannot be updated from here")
    by_name = {str(c.get("name", "")).lower(): c for c in chars if isinstance(c, dict)}
    for name in names:
        src = load_character(series, name) if get_character_path(series, name).exists() else None
        if not src or not str(src.get("visual_token", "")).strip():
            report["missing"].append(name)
            continue
        token = str(src["visual_token"]).strip()
        word = VOICE_WORD_OF.get(str(src.get("voice", "")).strip())
        cur = by_name.get(name.lower())
        if cur is None:
            new = {"name": name, "token": token, "voice": word or "male", **({"stages": src["stages"]} if src.get("stages") else {})}
            if not dry_run:
                chars.append(new)
            report["added"] += 1
            continue
        changed = False
        if str(cur.get("token", "")).strip() != token:
            changed = True
            if not dry_run:
                cur["token"] = token
        if word and cur.get("voice") != word and BOOK_VOICES.get(cur.get("voice")) != src.get("voice"):
            changed = True
            if not dry_run:
                cur["voice"] = word
        stages = src.get("stages") or []
        if stages != (cur.get("stages") or []):      # life stages travel with the token (book_write.py picks one by chapter)
            changed = True
            if not dry_run:
                cur["stages"] = stages
        report["updated" if changed else "unchanged"] += 1
    if not dry_run and (report["updated"] or report["added"]):
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(continuity, indent=1, ensure_ascii=False))
        tmp.replace(path)
    return report


def sync_characters_from_project(project_slug: str) -> int:
    """Add the characters from a project's <book>.json to its series (mapped below, else the project slug).
    Never overwrites an existing character. Returns the number of characters added.
    (studio.py calls this each time it lists projects, so it must be safe to repeat.)"""
    series_map = {
        "adam_eve": "main",
        "enoch": "main",
        # Add more mappings as needed
    }
    series = series_map.get(project_slug, project_slug)
    return sync_from_book(project_slug, series, overwrite=False)["added"]


def create_character_from_description(series: str, name: str, description: str,
                                       visual_token: str = "") -> Dict:
    """Create a character token from a natural language description.
    Uses AI to parse the description into structured fields."""
    # This would call an LLM to parse the description
    # For now, return a template
    return {
        "name": name,
        "series": series,
        "visual_token": visual_token or f"{slugify(name)}_token",
        "trigger_words": [name.lower()],
        "physical_traits": {},
        "clothing": "",
        "voice": "",
        "lora": {"repo": "", "trigger_word": "", "base_model": "", "trained": False},
        "reference_images": [],
        "consistency_notes": description,
    }


# Global prompt constants for consistency
PHOTOREAL_TAIL = (
    "photorealistic epic biblical period film, primeval world, "
    "2.39:1 widescreen, cinematic natural lighting, "
    "realistic faces and anatomy, tactile natural materials, "
    "shot on ARRI Alexa 65, anamorphic lenses, "
    "no cartoon, no animated, no illustration, no 3d render, "
    "no cgi look, no anime, no stylized, no painting, no drawing, "
    "no modern objects, no text, no subtitles, no logos, no watermark"
)

NEGATIVE_PROMPT = (
    "cartoon, animated, illustration, 3d render, cgi, anime, "
    "stylized, painting, drawing, sketch, artificial, plastic, "
    "smooth skin, doll-like, toy, figurine, low quality, blurry, "
    "deformed, ugly, bad anatomy, extra limbs, watermark, text"
)


def get_prompt_suffix() -> str:
    """Get the photorealistic prompt suffix for all generations."""
    return PHOTOREAL_TAIL


def get_negative_prompt() -> str:
    """Get the negative prompt for all generations."""
    return NEGATIVE_PROMPT


def build_character_prompt(character: Dict, action: str = "") -> str:
    """Build a complete prompt for a character including visual token, traits, and constants."""
    parts = []

    if character.get("visual_token"):
        parts.append(character["visual_token"])

    if character.get("physical_traits"):
        traits = character["physical_traits"]
        desc = ", ".join(f"{k}: {v}" for k, v in traits.items() if v)
        if desc:
            parts.append(desc)

    if character.get("clothing"):
        parts.append(f"wearing {character['clothing']}")

    if action:
        parts.append(action)

    if character.get("consistency_notes"):
        parts.append(character["consistency_notes"])

    # Add the photorealistic tail
    parts.append(PHOTOREAL_TAIL)

    return ", ".join(parts)


def get_reference_dir(series: str, character_name: str) -> Path:
    """Get the reference images directory for a character."""
    return get_series_dir(series) / "references" / slugify(character_name)      # references belong to the character, not to one book


def ensure_reference_dir(series: str, character_name: str) -> Path:
    """Ensure the reference images directory exists."""
    ref_dir = get_reference_dir(series, character_name)
    ref_dir.mkdir(parents=True, exist_ok=True)
    return ref_dir


def get_all_character_tokens(series: str) -> str:
    """Get all character tokens for a series formatted for prompts."""
    chars = list_characters(series)
    if not chars:
        return ""

    tokens = []
    for c in chars:
        full = load_character(series, c["name"])
        if full:
            token_parts = [full.get("visual_token", "")]
            if full.get("physical_traits"):
                traits = full["physical_traits"]
                desc = ", ".join(f"{k}: {v}" for k, v in traits.items() if v)
                if desc:
                    token_parts.append(desc)
            if full.get("clothing"):
                token_parts.append(f"wearing {full['clothing']}")
            if full.get("consistency_notes"):
                token_parts.append(full["consistency_notes"])
            tokens.append(f"### {full['name']}\n" + " | ".join(token_parts))

    return "\n\nCHARACTER TOKENS FOR " + series.upper() + ":\n" + "\n\n".join(tokens)


PICTURE_TYPES = (".png", ".jpg", ".jpeg", ".webp")


def _listed_path(path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def first_reference(series: str, character_name: str, stage: str = "") -> Optional[Path]:
    """The picture that stands for this character: for a life stage, the first in its references/<stage>/ folder; else the first file in the
    saved list that exists, else the first picture in the character's references/ folder. None if there is none."""
    folder = get_reference_dir(series, character_name)
    if stage:
        sub = folder / slugify(str(stage))
        pics = sorted(x for x in sub.iterdir() if x.suffix.lower() in PICTURE_TYPES) if sub.is_dir() else []
        if pics:
            return pics[0]
    char = load_character(series, character_name) or {}
    for r in char.get("reference_images") or []:
        p = _listed_path(r)
        if p.is_file() and p.suffix.lower() in PICTURE_TYPES:
            return p
    pics = sorted(x for x in folder.iterdir() if x.suffix.lower() in PICTURE_TYPES) if folder.is_dir() else []
    return pics[0] if pics else None


def reference_pictures(series: str, character_name: str) -> List[Dict]:
    """Every picture of a character for the page: the list's files in order, then the folder's other files. {"path" (from the repository root),
    "name", "listed", "exists", "used" (this is the one that stands for the character), "file" (<series folder>/<path inside it>, for /thumb and /file)}."""
    used, base, out, seen = first_reference(series, character_name), get_series_dir(series).resolve(), [], set()
    folder = get_reference_dir(series, character_name)
    char = load_character(series, character_name) or {}
    candidates = [(_listed_path(r), True) for r in char.get("reference_images") or []]
    candidates += [(x, False) for x in (sorted(folder.iterdir()) if folder.is_dir() else []) if x.suffix.lower() in PICTURE_TYPES]
    for p, listed in candidates:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        inside = base in rp.parents
        out.append({"path": rp.relative_to(ROOT.resolve()).as_posix() if ROOT.resolve() in rp.parents else str(p), "name": p.name, "listed": listed, "exists": p.is_file(),
                    "used": bool(used) and rp == used.resolve(), "file": f"{base.name}/{rp.relative_to(base).as_posix()}" if inside and p.is_file() else ""})
    return out


def use_reference(series: str, character_name: str, path: str) -> bool:
    """Make this picture the one that stands for the character: the first in its list (added if it was only in the folder). It must be one of the character's pictures."""
    char = load_character(series, character_name)
    if not char:
        return False
    match = next((r for r in reference_pictures(series, character_name) if r["path"] == path and r["exists"]), None)
    if match is None:
        return False
    keep = [r for r in (char.get("reference_images") or []) if _listed_path(r).resolve() != _listed_path(path).resolve()]
    char["reference_images"] = [path] + keep
    save_character(char)
    return True


def add_reference_image(series: str, character_name: str, image_path: str) -> bool:
    """Add a reference image path to a character."""
    char = load_character(series, character_name)
    if not char:
        return False

    if "reference_images" not in char:
        char["reference_images"] = []

    if image_path not in char["reference_images"]:
        char["reference_images"].append(image_path)
        save_character(char)

    return True


def update_lora_info(series: str, character_name: str, lora_repo: str,
                      trigger_word: str, base_model: str) -> bool:
    """Update LoRA information for a character."""
    char = load_character(series, character_name)
    if not char:
        return False

    char["lora"] = {
        "repo": lora_repo,
        "trigger_word": trigger_word,
        "base_model": base_model,
        "trained": True
    }
    save_character(char)
    return True


def delete_character(series: str, character_name: str) -> bool:
    """Delete a character token file."""
    path = get_character_path(series, character_name)
    if path.exists():
        path.unlink()
        update_index(series)
        return True
    return False


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python character_tokens.py <command> [args]")
        print("Commands:")
        print("  list-series")
        print("  list <series>")
        print("  get <series> <character>")
        print("  delete <series> <character>")
        print("  sync <project_slug>")
        print("  tokens <series>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list-series":
        print(json.dumps(list_series(), indent=2))
    elif cmd == "list":
        series = sys.argv[2] if len(sys.argv) > 2 else "main"
        print(json.dumps(list_characters(series), indent=2))
    elif cmd == "get":
        series = sys.argv[2] if len(sys.argv) > 2 else "main"
        name = sys.argv[3] if len(sys.argv) > 3 else ""
        print(json.dumps(load_character(series, name), indent=2))
    elif cmd == "delete":
        series = sys.argv[2] if len(sys.argv) > 2 else "main"
        name = sys.argv[3] if len(sys.argv) > 3 else ""
        ok = delete_character(series, name)
        print(f"Deleted: {ok}")
    elif cmd == "sync":
        project = sys.argv[2] if len(sys.argv) > 2 else "adam_eve"
        count = sync_characters_from_project(project)
        print(f"Synced {count} characters from {project}")
    elif cmd == "tokens":
        series = sys.argv[2] if len(sys.argv) > 2 else "main"
        print(get_all_character_tokens(series))
    else:
        print(f"Unknown command: {cmd}")