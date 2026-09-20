# ClauseCatcher demo video script

Target length: 2:30-3:00. Written for a single screen-recorded take with voiceover, no live presenter on camera. Host on Vimeo (unlisted, "Anyone" can view). Do not use YouTube.

## Recording tips

- Record at 1920×1080, 30fps, in OBS. Use a dedicated "Display Capture" or windowed browser source sized to exactly 1920×1080 so nothing gets scaled at export.
- Close every other app, silence notifications (Windows Focus Assist on), and hide the taskbar before rolling.
- Record screen and voiceover as separate takes if that's easier to get clean: capture the app interaction silently first, then narrate over it in a second pass. Keep them in sync by talking through the actions out loud once, off-mic, before the real narration take, so the pacing matches.
- Do at least two full run-throughs of the cockpit section before recording. The alert timing (about five seconds from sentence to card, 4 to 6.5 s across the logged runs) needs to feel natural in narration, not rushed or padded.
- Zoom the browser to 100% (not 125%+) so the three-pane cockpit layout doesn't crop at 1080p.
- Export at a bitrate high enough that the mono voice-orb animation and the underline sweep on the transcript don't compress into mush: 8 Mbps or higher.

## Shot list with timestamps

| Time | Screen | Voiceover | Notes |
|---|---|---|---|
| 0:00-0:12 | Landing page, hero headline | "Sales reps go off-script. Contracts don't. ClauseCatcher listens to a live call and speaks the exact clause back the moment a rep contradicts it." | Let the headline sit on screen for the first 3 seconds before talking. |
| 0:12-0:20 | Scroll to "how it works" strip | "It's built on AssemblyAI, start to finish: Streaming transcription, a contradiction check against the contract, and a spoken correction in the rep's own call." | One slow scroll, no clicking yet. |
| 0:20-0:22 | Click "Try the live demo" | (silent, just the click and page transition) | Quick cut. |
| 0:22-0:32 | Setup screen: click "Use demo contract" | "We load a sample sales contract. No manual typing." | Clause cards stagger in as they load. |
| 0:32-0:42 | Setup screen: clause cards visible, scroll past two or three | "Each clause is pulled straight from the PDF: section number, title, the literal text. Nothing here is generated." | Pause on one card long enough to read it. |
| 0:42-0:50 | Consent card, check the box, click "Start the call" | "One more step before we listen: consent." | Quick, matter-of-fact. |
| 0:50-0:58 | Cockpit loads, top bar shows "STT · connected" / "Voice · connected", transcript starts filling with a consistent rep line | "The call is live. AssemblyAI is transcribing in real time, and nothing has fired yet, because nothing's wrong yet." | Let one clean line finish and settle. |
| 0:58-1:05 | Simulate/rep line lands: "We can also do a 10 percent automatic discount for a client like this." Transcript renders it, underline sweep hits "10 percent automatic discount." | "Now the rep offers a discount the contract doesn't allow." | This is the setup for the wow moment. Hold half a beat after the underline before continuing. |
| 1:05-1:15 | Alert card slides in: "Contradicts §3.1," literal clause quote, "Rep said" line | "Seconds later, it flags the line and cites the section." | Let the card fully settle before talking over it. |
| 1:15-1:28 | Voice orb switches to speaking state, "ClauseCatcher speaking…" label, waveform-reactive orb | (let 2-3 seconds of actual agent audio play so the judge hears it) "...and says the clause back, word for word, straight from the contract." | This is the single most important few seconds in the video. Don't talk over the agent's own audio. |
| 1:28-1:35 | "Spoken verbatim ✓" badge fades in under the quote | "Verified against the contract text after it's spoken, not just assumed." | Zoom or hold on this badge for a beat. |
| 1:35-1:45 | Second rep line lands clean (no alert), then a false "24/7 on Standard" line triggers a second alert on §6.1 | "This isn't one canned trigger. A second, unrelated false claim gets caught the same way." | Compresses two beats. Cut if time is tight; this is the first thing to shorten. |
| 1:45-1:55 | Click command bar, select clause §4.2 | "A manager on the call can ask about any clause directly." | Type or select quickly. |
| 1:55-2:05 | Risk-meter dot for §4.2 lights up, voice orb speaks again | "Same mechanism, same check: the answer is the contract's own words, spoken aloud." | |
| 2:05-2:12 | Click "End call" | (silent transition) | |
| 2:12-2:28 | Report screen: score ring counts up, contradiction timeline, facts row (cost, calls, errors, transcript count) | "At the end of the call, a report: what was said, what was caught, and what the API time actually cost." | Let the ring animation finish before cutting. |
| 2:28-2:40 | Cut back to landing page or a static ClauseCatcher wordmark | "ClauseCatcher: the correction the rep actually hears, in the rep's own words back at them, straight from the contract." | Closing line, no call to action needed beyond the product itself. |

Total: about 2:40, inside the 2:30-3:00 window. Cut the 1:35-1:45 second-alert beat first if the edit runs long. Keep everything from 0:50-1:35 (the first alert and spoken correction) no matter what; that's the demo's entire reason for existing.

## What's on screen, in order

1. Landing (marketing, static)
2. Setup: demo contract load → clause reveal → consent
3. Cockpit: live call, first alert + spoken correction (the wow moment)
4. Cockpit: second alert (optional, cut first if short on time)
5. Cockpit: ask a clause by number, spoken answer
6. Report: score, timeline, facts, clause citations

## Fallbacks if a live take doesn't cooperate

- If the Voice Agent connection is slow or drops mid-recording, cut and re-take that segment rather than narrating over dead air. The spoken correction has to be heard clearly.
- If the browser mic path isn't reliable on recording day, use the cockpit's "Simulate rep line" input instead. It drives the exact same pipeline (transcript → claim-check → alert → speech) and is labeled in the UI as a demo aid, so it isn't a misrepresentation of what's running under it.
