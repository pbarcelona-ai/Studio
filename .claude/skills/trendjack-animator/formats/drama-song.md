# Format: drama song ad (sung, 15-20 s)

A tiny sales story, sung in the first person. Someone close says something that stings, the narrator says why it
happens, a trusted person brings the product, and the same people at the same place see the change.
Audio mode: `"audio": "song"`. Template: `templates/song.example.json`.

## The 7 lines

| #   | Beat       | What the line does                                   | Example                                  |
| --- | ---------- | ---------------------------------------------------- | ---------------------------------------- |
| 1   | The sting  | Someone close says something that stings, as a quote | `"Grandpa skipped a page!" she laughed.` |
| 2   | The cause  | Why it happens, plain and specific                   | `The words were just a blur.`            |
| 3   | The mentor | A close, trusted person brings the product           | `My son came with a lamp.`               |
| 4   | The truth  | One line about how it works, with a key word         | `"It's bright. That's the point."`       |
| 5   | The rise   | The change, said simply and honestly                 | `Now I read every word.`                 |
| 6   | The win    | Same place, same witness, the opposite of line 1     | `"Read it again!" she begs.`             |
| 7   | The offer  | Product name + offer                                 | `Try Acme for thirty nights.`            |

- The win only lands if line 6 happens where line 1 did, in front of the same person.
- The key word (here "bright") carries how the product works, ideally with a second meaning.
- The hero looks like the buyer (age, gender, world). The witness is someone the buyer loves: grandchildren,
  a partner, a friend, a colleague.
- Pitch three arcs on one card (lines in the option preview); recommend the one whose hero is most like the buyer.

## Lyric rules

- 7 lines, about 30 words for 15 s (plan on roughly 2 sung words per second).
- 3-7 words per line, one idea per line, no rhymes, no metaphors, everyday speech in the target language.
- Other people's quotes carry the sting and the win; the narrator just reports.
- Lip-sync: the hero may sing 1-2 lines on camera (best: line 1 reacting to the sting, or line 5 the rise),
  close-up, `"lipsync": true`. The quoted lines of other people are acted, not lip-synced.
- Write the brand name as it should be **sung** and fix the spelling in captions with `caption_replace`
  (e.g. lyrics "Loo-mee", `{"LOO-MEE": "LUMEE"}`).

## Song

Style: warm uplifting pop, acoustic pop or country-pop at 105-120 bpm, the hero's vocal gender, "Sung in
<language>". Never slow or sad: a ballad kills a short ad. Keep the example's vocal-start sentence and negative tags.
Make the song on suno.com in the browser (never inside Starpop); see Stage 3 of SKILL.md.

## Shots

One shot per phrase; split a long first line into the quote and "she laughed". The product appears first in the
mentor shot. The last shot ends on the product.
