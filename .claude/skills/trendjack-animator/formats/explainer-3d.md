# Format: 3D "how it works" explainer (spoken, 15-30 s)

A curious question, then one smooth camera journey that shows how the product works from the inside, on a clean
studio stage, told by a calm, matter-of-fact narrator. Works best for products with a visible mechanism (a filter,
a pump, a layered fabric, a hidden compartment). Audio mode: `"audio": "voice"` + an instrumental `music` bed.
Template: `templates/narrated.example.json`.

## Beats (one shot each, 4-8 shots)

1. **The question** (hook): "Why do houseplants die while you're away?" The everyday object on the stage, close.
2. **The surprise**: the real reason, in one plain sentence.
3. **Into the object**: the camera pushes into a cutaway or cross-section of the product.
4. **The mechanism**: the part that does the work, animated simply (water rising, layers compressing, air flowing).
5. **Back out**: the result in the real world.
6. **The product**: name + offer, product as the hero on the stage.

## Stage and look

- One seamless studio stage for the whole ad: a curved solid backdrop (cyclorama) in one colour (blue, light grey
  or the brand colour), soft studio light, everything standing on the stage floor. Describe it the same way in
  every still prompt, or generate one empty stage image and add it under `references` as `"stage"`.
- Look: the 3D film look or a cleaner "glossy 3D product render" look (see looks.md).
- Cutaways are clean and simple: no labels or text in the image (captions carry the words).

## Voice and music

- Calm, matter-of-fact, slightly dry narrator; short sentences, no hype words. One sentence per line.
- Voice comes from ElevenLabs through `scripts/elevenlabs_tts.py` (one continuous take), never from Starpop.
- Music: playful, light instrumental (plucked bass or pizzicato strings with a soft ticking pulse, about 95 bpm,
  curious mood, no vocals), made on suno.com, low under the voice.
- Don't imitate a specific creator's voice, music or branding; make the format your own.

## Camera

Every shot moves, and the moves connect: push-in, push through the surface, glide along the mechanism,
pull back out. Keep the screen direction the same from shot to shot so it feels like one journey.
