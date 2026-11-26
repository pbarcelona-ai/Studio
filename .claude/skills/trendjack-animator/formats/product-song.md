# Format: product song / music video (sung, 15-45 s)

A short, catchy original song about the moment the product fixes, cut like a music video: one quick shot per phrase,
on the beat. Less story than the drama song, more rhythm and repetition. Audio mode: `"audio": "song"`.
Start from `templates/song.example.json` and change the lyrics and shots.

## Song shape

| Part         | Length              | Job                                                                                                |
| ------------ | ------------------- | -------------------------------------------------------------------------------------------------- |
| Hook line    | first 2 s           | The problem or a vivid picture, sung from the first word: `Cold feet at midnight, again`           |
| Verse        | 2-4 lines           | The everyday moment, specific and visual (what, where, when)                                       |
| Chorus       | 2 lines, sung twice | The promise or the reframe, simple enough to remember: `It was never you / it was your old pillow` |
| Feature line | 1 line              | The one thing that makes it work, said plainly (one feature, not a list)                           |
| Offer        | 1 line              | Product name + offer                                                                               |

- 3-7 words per line. Repetition is the point: the chorus comes back word for word.
- A rhyme is fine here if it's natural; never force one.
- One feature line at most; the rest of the specs go in the ad text.

## Genre by buyer

| Buyer                              | Genre (bpm)                                          |
| ---------------------------------- | ---------------------------------------------------- |
| Broad, 25-45                       | upbeat pop, 110-120                                  |
| 45+, home and family               | warm country-pop or acoustic pop, 100-115            |
| Calm categories (sleep, wellbeing) | warm acoustic pop, 100-110, still with a steady beat |
| Young, playful                     | bright pop with handclaps, 115-125                   |

Avoid genres where words get buried (dance, house, EDM, K-pop). Never slow or sad.
The song is made on suno.com in the browser, never inside Starpop (Stage 3 of SKILL.md).

## Shots

Median shot 1.5-2.5 s, a new picture on every phrase, cuts on the first word of a phrase. Each chorus pass gets
different shots (never reuse a shot inside one ad). Characters act the words. Give the hero 1-2 lip-sync shots on the
chorus (close-up, face clearly visible, `"lipsync": true`); everything else is acted B-roll.
