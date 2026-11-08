#!/usr/bin/env python3
"""Initialize the example character tokens with the provided examples."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from character_tokens import (
    save_character, get_reference_dir, ensure_reference_dir,
    PHOTOREAL_TAIL, NEGATIVE_PROMPT
)
from pathlib import Path

# Adam character token
adam = {
    "name": "Adam",
    "series": "main",
    "visual_token": "ADAM: first man, about 30, tall lean olive-brown skin, long dark brown hair, short dark beard, deep brown eyes, grief-worn face",
    "trigger_words": ["adam", "first man", "biblical figure", "adam_token"],
    "physical_traits": {
        "age": "30",
        "height": "tall",
        "build": "lean",
        "skin": "olive-brown",
        "hair": "long dark brown",
        "facial_hair": "short dark beard",
        "eyes": "deep brown",
        "expression": "grief-worn"
    },
    "clothing": "simple tunic, earth tones, rough woven fabric",
    "voice": "bm_george",
    "lora": {
        "repo": "",
        "trigger_word": "adam_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/adam/ref_01.png",
        "projects/characters/main/references/adam/ref_02.png",
        "projects/characters/main/references/adam/ref_03.png"
    ],
    "consistency_notes": "Always depict as the first man, noble but human, burdened by knowledge of the fall",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Eve character token
eve = {
    "name": "Eve",
    "series": "main",
    "visual_token": "EVE: first woman, about 26, warm golden-brown skin, very long dark wavy hair, large dark eyes, tear-streaked remorseful face",
    "trigger_words": ["eve", "first woman", "biblical figure", "eve_token"],
    "physical_traits": {
        "age": "26",
        "height": "average",
        "build": "slender",
        "skin": "warm golden-brown",
        "hair": "very long dark wavy",
        "eyes": "large dark",
        "expression": "tear-streaked remorseful"
    },
    "clothing": "simple tunic, earth tones, rough woven fabric",
    "voice": "af_bella",
    "lora": {
        "repo": "",
        "trigger_word": "eve_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/eve/ref_01.png",
        "projects/characters/main/references/eve/ref_02.png",
        "projects/characters/main/references/eve/ref_03.png"
    ],
    "consistency_notes": "Always depict as the first woman, beautiful but bearing the weight of the fall, maternal grace mixed with sorrow",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Satan disguised
satan_disguised = {
    "name": "Satan_Disguised",
    "series": "main",
    "visual_token": "SATAN_DISGUISED: beautiful androgynous figure, impossible perfection, shifting features, eyes that hold ancient malice, radiant but wrong",
    "trigger_words": ["satan", "lucifer", "tempter", "disguised", "satan_disguised_token"],
    "physical_traits": {
        "age": "ageless",
        "height": "tall",
        "build": "impossibly perfect",
        "skin": "flawless, slightly luminescent",
        "hair": "shifts between styles",
        "eyes": "ancient malice behind beauty",
        "expression": "seductive, calculating"
    },
    "clothing": "robes that shift between light and shadow",
    "voice": "bm_lewis",
    "lora": {
        "repo": "",
        "trigger_word": "satan_disguised_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/satan_disguised/ref_01.png",
        "projects/characters/main/references/satan_disguised/ref_02.png"
    ],
    "consistency_notes": "Always beautiful but uncanny - the deception should be felt by the viewer. Features shift subtly. Never fully trustworthy.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Satan true form
satan_true = {
    "name": "Satan_True",
    "series": "main",
    "visual_token": "SATAN_TRUE: monstrous fallen angel, charred wings, cracked obsidian skin, burning eyes, towering, radiating corruption and ancient hatred",
    "trigger_words": ["satan", "devil", "fallen angel", "true form", "satan_true_token"],
    "physical_traits": {
        "age": "ancient",
        "height": "towering",
        "build": "monstrous, muscular",
        "skin": "cracked obsidian, charred",
        "wings": "charred, broken, spanning wide",
        "eyes": "burning, malevolent",
        "expression": "pure hatred, pride, corruption"
    },
    "clothing": "tattered remnants of angelic armor, fused to charred skin",
    "voice": "bm_lewis",
    "lora": {
        "repo": "",
        "trigger_word": "satan_true_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/satan_true/ref_01.png",
        "projects/characters/main/references/satan_true/ref_02.png"
    ],
    "consistency_notes": "Pure corruption made visible. The antithesis of creation. Charred, broken, but still terrifyingly powerful.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# God/The Lord
god = {
    "name": "God",
    "series": "main",
    "visual_token": "GOD: overwhelming presence of light, formless but felt, voice like many waters, righteousness visible as radiance, mercy and judgment intertwined",
    "trigger_words": ["god", "the lord", "creator", "almighty", "god_token"],
    "physical_traits": {
        "form": "formless divine presence",
        "manifestation": "overwhelming light, radiance",
        "eyes": "all-seeing, compassionate and judging",
        "presence": "voice like many waters"
    },
    "clothing": "light itself as garment",
    "voice": "bm_lewis",
    "lora": {
        "repo": "",
        "trigger_word": "god_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/god/ref_01.png"
    ],
    "consistency_notes": "Never fully shown - always a presence, light, voice. The camera cannot contain the divine. Use light, shadow, and reaction shots.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Adam (Garden/Unclothed) - pre-Fall state in Eden
adam_garden = {
    "name": "Adam_Garden",
    "series": "main",
    "visual_token": "ADAM_GARDEN: first man, about 30, tall lean olive-brown skin, long dark brown hair, short dark beard, deep brown eyes, innocent unashamed expression, unclothed",
    "trigger_words": ["adam", "first man", "biblical figure", "adam_token", "adam_garden", "eden", "pre-fall", "unclothed"],
    "physical_traits": {
        "age": "30",
        "height": "tall",
        "build": "lean",
        "skin": "olive-brown",
        "hair": "long dark brown",
        "facial_hair": "short dark beard",
        "eyes": "deep brown",
        "expression": "innocent, unashamed, peaceful"
    },
    "clothing": "unclothed, naked, unashamed in paradise",
    "voice": "bm_george",
    "lora": {
        "repo": "",
        "trigger_word": "adam_garden_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/adam_garden/ref_01.png",
        "projects/characters/main/references/adam_garden/ref_02.png",
        "projects/characters/main/references/adam_garden/ref_03.png"
    ],
    "consistency_notes": "Pre-Fall Adam in the Garden of Eden - innocent, unashamed of his nakedness, at peace with creation. No shame, no grief. Lit by dappled garden light. This version only for Garden scenes before the Fall.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Eve (Garden/Unclothed) - pre-Fall state in Eden
eve_garden = {
    "name": "Eve_Garden",
    "series": "main",
    "visual_token": "EVE_GARDEN: first woman, about 26, warm golden-brown skin, very long dark wavy hair, large dark eyes, innocent serene expression, unclothed",
    "trigger_words": ["eve", "first woman", "biblical figure", "eve_token", "eve_garden", "eden", "pre-fall", "unclothed"],
    "physical_traits": {
        "age": "26",
        "height": "average",
        "build": "slender",
        "skin": "warm golden-brown",
        "hair": "very long dark wavy",
        "eyes": "large dark",
        "expression": "innocent, serene, unashamed"
    },
    "clothing": "unclothed, naked, unashamed in paradise",
    "voice": "af_bella",
    "lora": {
        "repo": "",
        "trigger_word": "eve_garden_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/eve_garden/ref_01.png",
        "projects/characters/main/references/eve_garden/ref_02.png",
        "projects/characters/main/references/eve_garden/ref_03.png"
    ],
    "consistency_notes": "Pre-Fall Eve in the Garden of Eden - innocent, unashamed of her nakedness, at peace with creation. No shame, no sorrow. Lit by dappled garden light. This version only for Garden scenes before the Fall.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Gabriel - Archangel, messenger of God
gabriel = {
    "name": "Gabriel",
    "series": "main",
    "visual_token": "GABRIEL: archangel messenger, tall luminous figure, silver-white hair flowing, eyes like burning coals, radiant white robes with golden sash, vast wings folded, awe-inspiring yet gentle presence, holds a trumpet",
    "trigger_words": ["gabriel", "archangel", "messenger", "angel of revelation", "gabriel_token"],
    "physical_traits": {
        "age": "ageless",
        "height": "tall",
        "build": "ethereal, commanding",
        "skin": "luminous, porcelain",
        "hair": "silver-white, flowing",
        "eyes": "burning coals, piercing",
        "wings": "vast, white-gold, folded",
        "expression": "solemn, authoritative, compassionate"
    },
    "clothing": "radiant white robes with golden sash, trumpet at side",
    "voice": "bm_lewis",
    "lora": {
        "repo": "",
        "trigger_word": "gabriel_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/gabriel/ref_01.png",
        "projects/characters/main/references/gabriel/ref_02.png",
        "projects/characters/main/references/gabriel/ref_03.png"
    ],
    "consistency_notes": "The archangel who stands in God's presence. Messenger of revelation - announced births of John and Jesus. Always radiant, awe-inspiring but not terrifying. Trumpet signifies divine announcement. Wings folded unless in flight. Carries the weight of heaven's messages.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Michael - Archangel, warrior, leader of heavenly hosts
michael = {
    "name": "Michael",
    "series": "main",
    "visual_token": "MICHAEL: archangel warrior, towering figure in gleaming silver armor, flaming sword raised, vast wings spread, fierce noble face, eyes blazing with righteous fire, commander of heavenly armies",
    "trigger_words": ["michael", "archangel", "warrior", "captain of hosts", "dragon slayer", "michael_token"],
    "physical_traits": {
        "age": "ageless",
        "height": "towering",
        "build": "powerful, muscular",
        "skin": "radiant, bronze-gold",
        "hair": "golden, short, wind-blown",
        "eyes": "blazing blue fire",
        "wings": "vast, silver-white, spread wide",
        "expression": "fierce, resolute, righteous fury"
    },
    "clothing": "gleaming silver armor, flaming sword, commander's cloak",
    "voice": "bm_lewis",
    "lora": {
        "repo": "",
        "trigger_word": "michael_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/michael/ref_01.png",
        "projects/characters/main/references/michael/ref_02.png",
        "projects/characters/main/references/michael/ref_03.png"
    ],
    "consistency_notes": "Prince of the heavenly host, leader of God's armies. Cast Satan from heaven. The warrior archangel - not a messenger but a defender. Flaming sword, armor, commanding presence. 'Who is like God?' - his name is his battle cry. Always depicted in active combat or victorious stance.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Raphael - Archangel, healer
raphael = {
    "name": "Raphael",
    "series": "main",
    "visual_token": "RAPHAEL: archangel healer, gentle radiant figure, emerald-green eyes, flowing golden hair, white robes with green sash, staff entwined with healing serpent, wings shimmering with verdant light, compassionate smile",
    "trigger_words": ["raphael", "archangel", "healer", "medicine of God", "raphael_token"],
    "physical_traits": {
        "age": "ageless",
        "height": "tall",
        "build": "graceful, gentle",
        "skin": "warm, luminous",
        "hair": "golden, flowing",
        "eyes": "emerald-green, healing",
        "wings": "shimmering verdant light",
        "expression": "compassionate, serene, gentle"
    },
    "clothing": "white robes with green sash, healing staff with serpent",
    "voice": "bm_george",
    "lora": {
        "repo": "",
        "trigger_word": "raphael_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/raphael/ref_01.png",
        "projects/characters/main/references/raphael/ref_02.png",
        "projects/characters/main/references/raphael/ref_03.png"
    ],
    "consistency_notes": "Name means 'God heals' or 'Medicine of God'. Healed Tobit's blindness, bound Azazel. Gentle, compassionate, the physician of heaven. Green/emerald color palette. Carries the caduceus-like staff. Not a warrior - a restorer. His presence brings wholeness.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Uriel - Archangel, angel of wisdom/repentance
uriel = {
    "name": "Uriel",
    "series": "main",
    "visual_token": "URIEL: archangel of wisdom, stern radiant figure, deep amber eyes, silver-white beard, robes of deep crimson and gold, flaming scroll in hand, wings like burning fire, face illuminated by divine knowledge",
    "trigger_words": ["uriel", "archangel", "wisdom", "fire of God", "repentance", "uriel_token"],
    "physical_traits": {
        "age": "ageless",
        "height": "tall",
        "build": "stately, imposing",
        "skin": "radiant, weathered",
        "hair": "silver-white, long, beard",
        "eyes": "deep amber, all-seeing",
        "wings": "burning fire, gold-red",
        "expression": "stern, wise, penetrating"
    },
    "clothing": "deep crimson and gold robes, flaming scroll",
    "voice": "bm_lewis",
    "lora": {
        "repo": "",
        "trigger_word": "uriel_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/uriel/ref_01.png",
        "projects/characters/main/references/uriel/ref_02.png",
        "projects/characters/main/references/uriel/ref_03.png"
    ],
    "consistency_notes": "Name means 'Fire of God' or 'Light of God'. Angel of wisdom, repentance, and divine judgment. Guarded Eden's gate with flaming sword after the Fall. Holds the scroll of divine knowledge. Stern but not cruel - the truth that burns away falsehood. Fire and light motifs.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Cherubim - Highest order, guardians
cherubim = {
    "name": "Cherubim",
    "series": "main",
    "visual_token": "CHERUBIM: highest angelic order, four-faced guardians, each with four wings, faces of lion, ox, eagle, and man, eyes covering entire body, wheels within wheels burning with fire, throne bearers of God, terrifying majesty",
    "trigger_words": ["cherubim", "cherub", "guardians", "throne bearers", "four faces", "cherubim_token"],
    "physical_traits": {
        "age": "ageless",
        "height": "colossal",
        "build": "multi-formed, terrifying",
        "skin": "covered in eyes, burning",
        "faces": "lion, ox, eagle, man",
        "wings": "four each, covered in eyes",
        "eyes": "entire body covered in eyes",
        "expression": "terrifying majesty, unblinking vigilance"
    },
    "clothing": "wings as garment, fire and lightning",
    "voice": "bm_lewis",
    "lora": {
        "repo": "",
        "trigger_word": "cherubim_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/cherubim/ref_01.png",
        "projects/characters/main/references/cherubim/ref_02.png"
    ],
    "consistency_notes": "Highest order of angels (with Seraphim). Guardians of God's throne and Eden's gate. Four faces: lion (wild), ox (domestic), eagle (air), man (intelligence). Four wings, covered in eyes. Wheels within wheels (Ophanim). Not cute babies - terrifying living creatures. Bearers of God's throne chariot.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Seraphim - Highest order, burning ones
seraphim = {
    "name": "Seraphim",
    "series": "main",
    "visual_token": "SERAPHIM: highest angelic order, six-winged burning ones, two wings cover face, two cover feet, two for flight, blazing with divine fire, crying Holy Holy Holy, radiant serpentine forms, voices like thunder",
    "trigger_words": ["seraphim", "seraph", "burning ones", "six wings", "holy holy holy", "seraphim_token"],
    "physical_traits": {
        "age": "ageless",
        "height": "towering",
        "build": "serpentine, radiant",
        "skin": "living fire, copper-bronze",
        "wings": "six wings - face, feet, flight",
        "eyes": "veiled by wings",
        "expression": "consumed by worship, awe"
    },
    "clothing": "fire itself, wings as covering",
    "voice": "bm_lewis",
    "lora": {
        "repo": "",
        "trigger_word": "seraphim_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/seraphim/ref_01.png",
        "projects/characters/main/references/seraphim/ref_02.png"
    ],
    "consistency_notes": "Highest order with Cherubim. 'Burning ones' - consumed by God's holiness. Six wings: two cover face (humility), two cover feet (reverence), two for flight. Cry 'Holy, Holy, Holy' incessantly. Isaiah 6 vision. Not humanoid - serpentine, fiery, overwhelming. Purify with live coal from altar.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Living Creatures - Four from Ezekiel/Revelation
living_creatures = {
    "name": "Living_Creatures",
    "series": "main",
    "visual_token": "LIVING CREATURES: four living beings around the throne, each with six wings full of eyes, first like lion, second like ox, third face of man, fourth like flying eagle, ceaselessly crying Holy Holy Holy, lightning and thunder proceed from them",
    "trigger_words": ["living creatures", "four beasts", "ezekiel", "revelation", "throne guardians", "living_creatures_token"],
    "physical_traits": {
        "age": "ageless",
        "height": "colossal",
        "build": "four distinct forms united",
        "skin": "covered in eyes, gleaming",
        "faces": "lion, ox, man, eagle",
        "wings": "six each, full of eyes",
        "eyes": "wings and bodies full of eyes",
        "expression": "eternal worship, unceasing"
    },
    "clothing": "wings and light, crowns of gold",
    "voice": "bm_lewis",
    "lora": {
        "repo": "",
        "trigger_word": "living_creatures_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/living_creatures/ref_01.png",
        "projects/characters/main/references/living_creatures/ref_02.png"
    ],
    "consistency_notes": "The four living creatures (zoe) of Ezekiel 1 and Revelation 4. Distinct from cherubim/seraphim but related. Each has unique face: lion, ox, man, eagle. Six wings full of eyes. Never cease saying 'Holy, Holy, Holy'. Give glory to the One on the throne. Lightning, thunder, voices proceed from them. Harnessed to the throne-chariot.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Archangels - General group
archangels = {
    "name": "Archangels",
    "series": "main",
    "visual_token": "ARCHANGELS: seven chief princes, standing before God's throne, each distinct - Michael warrior, Gabriel messenger, Raphael healer, Uriel wisdom, Raguel justice, Remiel hope, Sariel guidance, radiant armor and robes, vast wings, divine authority",
    "trigger_words": ["archangels", "seven archangels", "chief princes", "heavenly host leaders", "archangels_token"],
    "physical_traits": {
        "age": "ageless",
        "height": "towering",
        "build": "varied, each distinct",
        "skin": "radiant, varied tones",
        "wings": "vast, each unique",
        "eyes": "piercing, all-seeing",
        "expression": "united purpose, divine authority"
    },
    "clothing": "radiant armor and robes, each distinct colors and symbols",
    "voice": "bm_lewis",
    "lora": {
        "repo": "",
        "trigger_word": "archangels_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/archangels/ref_01.png",
        "projects/characters/main/references/archangels/ref_02.png"
    ],
    "consistency_notes": "The seven chief princes who stand before God (Tobit 12:15, Revelation 8:2). Michael, Gabriel, Raphael, Uriel, Raguel, Remiel, Sariel. Each has distinct role and appearance. United in purpose, diverse in function. Group scenes should show seven distinct figures. Not interchangeable - each carries their office.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Enoch - Walked with God, taken up
enoch = {
    "name": "Enoch",
    "series": "main",
    "visual_token": "ENOCH: seventh from Adam, about 50, lean weathered frame, long white hair and beard, eyes that have seen eternity, simple linen robe, radiant glow growing, walking toward light, feet leaving ground, transcription of heavenly secrets in hand",
    "trigger_words": ["enoch", "seventh from adam", "walked with god", "taken up", "metatron", "enoch_token"],
    "physical_traits": {
        "age": "50 (365 years)",
        "height": "average",
        "build": "lean, weathered",
        "skin": "bronze, radiant",
        "hair": "long white, flowing",
        "beard": "long white",
        "eyes": "eternal, knowing",
        "expression": "rapturous, peaceful, ascending"
    },
    "clothing": "simple linen robe, scroll of heavenly secrets",
    "voice": "bm_george",
    "lora": {
        "repo": "",
        "trigger_word": "enoch_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/enoch/ref_01.png",
        "projects/characters/main/references/enoch/ref_02.png",
        "projects/characters/main/references/enoch/ref_03.png"
    ],
    "consistency_notes": "Seventh from Adam, walked with God 300 years, then 'was not, for God took him' (Gen 5:24). Only human besides Elijah taken bodily to heaven. Author of 1 Enoch. Later tradition identifies him as Metatron. Transition from mortal to glorified. Radiance increasing. Walking upward into light.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Noah - Righteous, built ark
noah = {
    "name": "Noah",
    "series": "main",
    "visual_token": "NOAH: righteous man, about 600, massive frame, long white beard, weathered bronze skin, calloused hands, simple rough tunic, standing before colossal ark under construction, hammer in hand, animals gathering, storm clouds gathering, faith amid mockery",
    "trigger_words": ["noah", "ark builder", "righteous", "preacher of righteousness", "noah_token"],
    "physical_traits": {
        "age": "600",
        "height": "tall",
        "build": "massive, powerful",
        "skin": "weathered bronze",
        "hair": "white, long",
        "beard": "long white, full",
        "eyes": "steady, faithful",
        "expression": "determined, sorrowful, obedient"
    },
    "clothing": "rough tunic, leather apron, work clothes",
    "voice": "bm_daniel",
    "lora": {
        "repo": "",
        "trigger_word": "noah_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/noah/ref_01.png",
        "projects/characters/main/references/noah/ref_02.png",
        "projects/characters/main/references/noah/ref_03.png"
    ],
    "consistency_notes": "Only righteous man in his generation. Built ark for 120 years while preaching. 'Preacher of righteousness' (2 Pet 2:5). Massive physical presence from centuries of labor. Weathered by elements. Animals trust him. Storm clouds always gathering in background. Not old and frail - powerful, obedient, burdened by coming judgment.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Cain - First murderer, marked
cain = {
    "name": "Cain",
    "series": "main",
    "visual_token": "CAIN: firstborn, about 30, powerful farmer's build, olive skin, dark hair, intense dark eyes, distinctive mark on forehead, blood-stained hands, tiller of ground, offerings of grain rejected, jealous rage, fugitive wanderer",
    "trigger_words": ["cain", "firstborn", "murderer", "marked", "tiller of ground", "cain_token"],
    "physical_traits": {
        "age": "30",
        "height": "tall",
        "build": "powerful, muscular",
        "skin": "olive, sun-bronzed",
        "hair": "dark, unkempt",
        "eyes": "dark, tormented",
        "mark": "divine mark on forehead",
        "expression": "jealous, tormented, defiant"
    },
    "clothing": "rough work tunic, stained with earth and blood",
    "voice": "bm_george",
    "lora": {
        "repo": "",
        "trigger_word": "cain_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/cain/ref_01.png",
        "projects/characters/main/references/cain/ref_02.png",
        "projects/characters/main/references/cain/ref_03.png"
    ],
    "consistency_notes": "First human born, first murderer. Farmer - tiller of ground. Offering rejected, killed Abel in jealousy. Marked by God for protection (not curse). 'My punishment is greater than I can bear.' Fugitive, builder of cities. Tormented but defiant. The mark is visible - protective, not shameful. Earth tones, blood stains.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

# Abel - Righteous shepherd, murdered
abel = {
    "name": "Abel",
    "series": "main",
    "visual_token": "ABEL: second son, about 25, slender shepherd's frame, warm golden skin, gentle brown eyes, flowing hair, simple shepherd's garment, staff in hand, lamb at feet, acceptable offering of firstlings, innocent trust, first martyr",
    "trigger_words": ["abel", "second son", "shepherd", "righteous", "martyr", "firstlings", "abel_token"],
    "physical_traits": {
        "age": "25",
        "height": "average",
        "build": "slender, gentle",
        "skin": "warm golden",
        "hair": "dark, flowing",
        "eyes": "gentle brown, trusting",
        "expression": "innocent, peaceful, accepting"
    },
    "clothing": "simple shepherd's garment, staff",
    "voice": "af_bella",
    "lora": {
        "repo": "",
        "trigger_word": "abel_token",
        "base_model": "LTX-Video",
        "trained": False
    },
    "reference_images": [
        "projects/characters/main/references/abel/ref_01.png",
        "projects/characters/main/references/abel/ref_02.png",
        "projects/characters/main/references/abel/ref_03.png"
    ],
    "consistency_notes": "Second son, shepherd - keeper of sheep. Offering of firstlings accepted. First martyr - killed by brother. 'By faith Abel offered a more excellent sacrifice' (Heb 11:4). Blood cries from ground. Innocent, trusting, peaceful. Gentle contrast to Cain. Lamb imagery. Shepherd's staff. Firstlings of flock.",
    "created": "2026-01-15",
    "updated": "2026-01-15"
}

if __name__ == "__main__":
    print("Initializing the example character tokens...")

    # Save all characters
    for char in [adam, eve, satan_disguised, satan_true, god, adam_garden, eve_garden,
                 gabriel, michael, raphael, uriel, cherubim, seraphim, living_creatures,
                 archangels, enoch, noah, cain, abel]:
        path = save_character(char)
        print(f"Saved {char['name']} to {path}")

        # Ensure reference directories exist
        ref_dir = ensure_reference_dir("main", char["name"])
        print(f"  Reference dir: {ref_dir}")

    print("\nDone! Character tokens initialized.")
    print("\nReference image directories created:")
    print("  projects/characters/main/references/adam/")
    print("  projects/characters/main/references/eve/")
    print("  projects/characters/main/references/satan_disguised/")
    print("  projects/characters/main/references/satan_true/")
    print("  projects/characters/main/references/god/")
    print("  projects/characters/main/references/adam_garden/")
    print("  projects/characters/main/references/eve_garden/")
    print("  projects/characters/main/references/gabriel/")
    print("  projects/characters/main/references/michael/")
    print("  projects/characters/main/references/raphael/")
    print("  projects/characters/main/references/uriel/")
    print("  projects/characters/main/references/cherubim/")
    print("  projects/characters/main/references/seraphim/")
    print("  projects/characters/main/references/living_creatures/")
    print("  projects/characters/main/references/archangels/")
    print("  projects/characters/main/references/enoch/")
    print("  projects/characters/main/references/noah/")
    print("  projects/characters/main/references/cain/")
    print("  projects/characters/main/references/abel/")
    print("\nPlace reference images in these directories:")
    print("  ref_01.png (neutral, front)")
    print("  ref_02.png (profile)")
    print("  ref_03.png (close-up eyes)")