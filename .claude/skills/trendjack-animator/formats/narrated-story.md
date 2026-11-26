# Format: narrated cartoon story (spoken, 20-45 s)

An animated short with a warm narrator: a relatable problem, a person the hero trusts, a short look at how the
product works, the payoff. Audio mode: `"audio": "voice"` + an optional instrumental `music` bed.
Template: `templates/narrated.example.json` (change the lines and shots).

## Beats

| Beat         | Share          | Job                                                                                         |
| ------------ | -------------- | ------------------------------------------------------------------------------------------- |
| Hook         | first 1-3 s    | Tension or curiosity in the first sentence, on a close shot. Never a calm establishing shot |
| Problem      | ~15 %          | Specific and sensory (3 a.m., the cold side of the bed, the stiff back at the desk)         |
| Self-blame   | 1 line         | "I thought it was just me." The emotional hinge                                             |
| Failed fixes | ~10 %          | A fast montage of 1-1.5 s inserts of what didn't work                                       |
| The person   | ~10 %          | Someone the hero trusts shows the answer (partner, parent, friend)                          |
| How it works | 1-2 lines      | One clear mechanism, shown while it's said (a cutaway or glowing close-up)                  |
| Payoff       | ~15 %          | The first good result, ideally a callback to the hook                                       |
| Twist        | 1 line         | Sweet or funny, never a reveal of wrongdoing or loss                                        |
| Offer        | last 2-3 lines | Product name, the offer, the next step                                                      |

## Voice

- One narrator, first person or warm third person. Short sentences, one per line in `voice.lines`.
- Generate ONE continuous voiceover of all lines together (never one clip per line: the voice drifts and the
  pacing breaks). Voice = ElevenLabs direct through `scripts/elevenlabs_tts.py make`, which also saves the word
  timings. Pick the voice id in the ElevenLabs voice library (browser) or with Starpop `search_voices` (free,
  read-only); never generate speech inside Starpop. Model `eleven_v4` handles most languages; set `language_code`.
- If the narrator is on screen, their talking shots are lip-sync shots (`"lipsync": true`).
- If the voice service fails, wait and retry later rather than switching to a sung voice.

## Music bed

`music.style`: an instrumental that fits the mood, steady and light (e.g. "warm acoustic guitar and soft piano,
gentle steady beat, hopeful, 100 bpm, no vocals"), made on suno.com by the user. `volume` 0.14-0.2 keeps it under
the voice. Founder or talking ads usually work better with no music bed at all; ask.

## Shots

One shot per line (split long lines). Inserts for the failed-fixes montage can be 1-1.5 s. Show the mechanism
literally while it's said.
