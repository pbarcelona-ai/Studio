"""Prompt library for the Studio's Library tab: ready-made prompts to copy into Single Prompts.

Each entry: id, title, category, kind ("video" or "image"), prompt. The Studio shows a sample picture or clip next to a template when one of your
own regression or Single Prompts results was made from exactly the same prompt text. To add a template, add a line here.
"""

TEMPLATES = [
    # ---- Cinematic
    {"id": "city_chase", "category": "Cinematic", "kind": "video", "title": "Street chase",
     "prompt": "a young woman running towards the camera, zombies are chasing her down a city street. not blurry, no cartoon."},
    {"id": "rain_noir", "category": "Cinematic", "kind": "video", "title": "Rainy noir street",
     "prompt": "a detective in a long coat walks slowly down a rain-soaked neon street at night, reflections on wet asphalt, slow dolly shot, cinematic film noir, shallow depth of field"},
    {"id": "hero_walk", "category": "Cinematic", "kind": "video", "title": "Hero walk-away",
     "prompt": "a lone warrior walks away from the camera across a burning battlefield at sunset, embers drifting, wide anamorphic lens, epic cinematic lighting"},
    {"id": "car_chase", "category": "Cinematic", "kind": "video", "title": "Desert car chase",
     "prompt": "a vintage muscle car speeds along a desert highway at golden hour, dust trailing behind, low tracking shot, motion blur, film grain"},
    # ---- Epic and biblical
    {"id": "eden", "category": "Epic and biblical", "kind": "video", "title": "Garden of Eden",
     "prompt": "Adam and eve in the garden of eden. tree of knowledge in background. they are walking slowly enjoying the serene beauty of the garden, which is lush and vibrant with floral. there is a faint image of a dark angel following them as they walk. hyper-realistic, cinematic live action video, filmic lighting, depth of field, natural movements, Hollywood quality production"},
    {"id": "red_sea", "category": "Epic and biblical", "kind": "video", "title": "Parting of the sea",
     "prompt": "a bearded prophet raises his staff as a vast sea parts into two towering walls of water, a huge crowd of people crossing the dry seabed, dramatic storm clouds, epic cinematic live action, filmic lighting"},
    {"id": "desert_prophet", "category": "Epic and biblical", "kind": "image", "title": "Prophet in the desert",
     "prompt": "an old prophet in rough robes standing on a rocky ridge at dawn, wind in his cloak, golden light across a vast desert, photorealistic epic period film still, natural faces"},
    {"id": "temple", "category": "Epic and biblical", "kind": "image", "title": "Ancient temple interior",
     "prompt": "interior of a vast ancient temple, shafts of golden light through high windows, carved stone columns, priests in white linen, photorealistic cinematic period film still"},
    # ---- Fantasy and sci-fi
    {"id": "dragon", "category": "Fantasy and sci-fi", "kind": "video", "title": "Dragon over a castle",
     "prompt": "a huge dragon circles above a mountain castle at dusk, breathing a plume of fire, villagers looking up from the walls, sweeping aerial camera, cinematic fantasy"},
    {"id": "space_station", "category": "Fantasy and sci-fi", "kind": "video", "title": "Space station window",
     "prompt": "an astronaut floats slowly past a large window of a space station, a blue planet turning below, soft light, quiet and awe-inspiring, cinematic sci-fi"},
    {"id": "cyber_alley", "category": "Fantasy and sci-fi", "kind": "image", "title": "Cyberpunk alley",
     "prompt": "a narrow cyberpunk alley at night, glowing signs in several languages, steam rising, a lone figure with an umbrella, rain, volumetric light, photorealistic, highly detailed"},
    {"id": "elf_forest", "category": "Fantasy and sci-fi", "kind": "image", "title": "Elf in a glowing forest",
     "prompt": "an elf archer in a glowing enchanted forest, bioluminescent plants, mist between giant trees, intricate leather armor, cinematic fantasy illustration, sharp focus"},
    # ---- Nature
    {"id": "waterfall", "category": "Nature", "kind": "video", "title": "Misty waterfall",
     "prompt": "a tall waterfall in a lush green valley at sunrise, mist rising, birds flying across the frame, slow aerial push-in, ultra detailed, natural colors"},
    {"id": "ocean_storm", "category": "Nature", "kind": "video", "title": "Storm at sea",
     "prompt": "huge waves crash against a lighthouse during a storm at night, lightning flashes, spray flying, dramatic cinematic camera, realistic"},
    {"id": "wild_horses", "category": "Nature", "kind": "video", "title": "Wild horses running",
     "prompt": "a herd of wild horses gallops across a grassy plain at golden hour, dust and manes flying, low tracking shot, slow motion, cinematic wildlife film"},
    {"id": "macro_flower", "category": "Nature", "kind": "image", "title": "Macro flower with dew",
     "prompt": "macro photograph of a blooming flower covered in morning dew, soft golden backlight, creamy bokeh, extremely detailed petals"},
    # ---- Portraits
    {"id": "portrait_studio", "category": "Portraits", "kind": "image", "title": "Studio portrait",
     "prompt": "studio portrait of a woman in her thirties, soft key light, subtle rim light, natural skin texture, 85mm lens, shallow depth of field, photorealistic"},
    {"id": "old_sailor", "category": "Portraits", "kind": "image", "title": "Weathered sailor",
     "prompt": "close-up portrait of an old sailor with a white beard and deep wrinkles, stormy sea behind him, dramatic side lighting, photorealistic, highly detailed"},
    {"id": "child_laugh", "category": "Portraits", "kind": "video", "title": "Child laughing in a field",
     "prompt": "a small child laughs and spins in a field of tall grass at sunset, warm backlight, handheld camera, natural movement, cinematic"},
    # ---- Horror and mood
    {"id": "haunted_hall", "category": "Horror and mood", "kind": "video", "title": "Haunted hallway",
     "prompt": "a dim hallway in an abandoned house, a door slowly creaks open at the far end, a faint pale figure just visible in the dark, flickering light, slow push-in, cinematic horror"},
    {"id": "fog_graveyard", "category": "Horror and mood", "kind": "image", "title": "Foggy graveyard",
     "prompt": "an old graveyard at night in thick fog, a crooked tree and weathered tombstones, a faint lantern glow in the distance, moody cinematic still, photorealistic"},
    # ---- Anime and illustration
    {"id": "anime_city", "category": "Anime and illustration", "kind": "image", "title": "Anime rooftop",
     "prompt": "an anime girl standing on a rooftop at dusk, city lights beginning to glow, wind in her hair, detailed background, soft cinematic lighting, high quality illustration"},
    {"id": "storybook", "category": "Anime and illustration", "kind": "image", "title": "Storybook scene",
     "prompt": "a children's storybook illustration of a little fox crossing a wooden bridge over a stream, warm watercolor style, soft colors, gentle light"},
    # ---- Products and places
    {"id": "product_watch", "category": "Products and places", "kind": "image", "title": "Product shot",
     "prompt": "luxury wristwatch on dark stone, dramatic rim lighting, tiny water droplets, ultra sharp macro product photography, high-end advertising style"},
    {"id": "mountain_cabin", "category": "Products and places", "kind": "video", "title": "Mountain cabin at dawn",
     "prompt": "a small wooden cabin by a lake in the mountains at dawn, smoke rising from the chimney, mist over the water, slow aerial drift, peaceful, ultra detailed"},
]
