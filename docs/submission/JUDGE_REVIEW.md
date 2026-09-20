# ClauseCatcher — adversarial judge review

**Reviewed:** 2026-09-17, against repo HEAD `a629536` (clean, fully pushed to `origin/main`).
**Event:** lablab.ai AssemblyAI Voice Agent Hackathon, Sep 1–30 2026. 5 equal winners
($1,000 cash + $1,000 AAI credits each). **Goal is top 5, not first.**
**Criteria judged against:** Application of Technology, Presentation, Business Value, Originality.

> **Sourcing note on the criteria.** The four criteria names come from `CHECKLIST.md`, which
> records them as read off the event page on 2026-09-17. Three independent WebFetch attempts on
> `lablab.ai/ai-hackathons/assemblyai-voice-agent-hackathon`, `/rules`, and
> `/delivering-your-hackathon-solution` returned only the hero block (dates, "$10,000 Prize Pool
> ($5k cash + $5k in AAI credits)") — lablab renders the criteria and "What to submit" sections
> client-side, so they are not fetchable. **The per-criterion weights and official one-line
> definitions were NOT verifiable and are not quoted here.** This review treats the four criteria
> as equally weighted. If lablab publishes weights, re-check §1 — the ranking of fixes does not
> change, but the arithmetic does.

**What was actually inspected:** the public repo as a stranger sees it, `README.md`,
`docs/adr/0001-voice-architecture.md`, `LABLAB_SUBMISSION.md`, `SLIDES.md`, `DEMO_NOTES.md`,
`DEMO_SCRIPT.md`, `CHECKLIST.md`, all 10 rendered pages of `ClauseCatcher.pdf`, `cover.png`,
16 extracted frames of `demo.mp4`, a per-second RMS sweep of its audio track, `server/*.py`
line counts and test counts, `spikes/claim_check/`, and the GitHub repo metadata via `gh`.

---

## 1. Predicted scores

**Scale: 1–5 per criterion, half-points allowed, 4 criteria, 20 points total.**
(1 = missing, 2 = weak, 3 = competent/median entry, 4 = clearly above the field,
5 = the entry other teams get compared to.) A top-5 finish in a month-long lablab event with
an AssemblyAI-specific field realistically needs **~16/20**, because the field will contain
several polished, hosted, phone-callable voice agents.

### BEFORE fixes — **15.0 / 20 (75%)** · verdict: *bubble. Top 8, not safely top 5.*

| Criterion | Score | The reasoning a judge would actually give |
|---|---|---|
| **Application of Technology** | **4.5 / 5** | "This is the most technically honest entry I've read. Two AssemblyAI products, both load-bearing, and the split between them isn't decoration — ADR-0001 documents that a single Voice Agent session was live-tested and auto-started 4 replies over the rep despite an explicit silence prompt, and that the docs expose no off-switch. That's an architecture decision earned from a failed experiment, not picked from a blog post. `reply.create` + 'say exactly' with a post-hoc similarity grader (`_grade_match`, `literal_spoken`) is a real engineering answer to hallucinated legal text. 2,072 lines of server, 136 server + 21 frontend tests, a per-session cost meter, origin-locked WebSockets, budget and kill-switch env vars, a 54–84 MB Docker image. **What stops it being a 5:** the core discriminator — the Gemini contradiction check — has no measured accuracy. There is a 32-example labeled set sitting in `spikes/claim_check/labeled_claims.json` and a runner, and `spikes/claim_check/README.md` says in bold that real accuracy is *UNMEASURED*. And it has never run anywhere but the builder's laptop." |
| **Presentation** | **3.5 / 5** | "The craft is there — the deck and the cockpit UI are better-looking than most funded products, the video is a clean 2:54 at 1080p30 with steady narration (RMS −17 to −22 dBFS throughout, no clipping, no level drift). Then I hit the problem: **the cover image says `~2 s sentence to alert` and the video shows five seconds of dead air before the alert lands.** Slide 4 says `§3.1 flagged in ~2 s`; slide 9's hero stat is `~2 s`. The app's own landing page, visible on screen at 0:20 of the same video, says `~5 s`. The submission contradicts itself inside sixty seconds and the honest number is the one that loses. Also: the wow moment — the first alert and the spoken clause — doesn't arrive until **1:09**, 40% of the way in, after 42 seconds of landing page and contract upload. And the README a judge lands on says *Status: in development*, *Demo video: TODO*, *Live app: TODO*." |
| **Business Value** | **3.0 / 5** | "Buyer is named specifically (sales-ops / revenue-compliance at B2B companies whose reps quote pricing and SLA terms live), the pain is legible, and the unit economics are actually measured — $0.0755 for 55 s, $0.1535 for 1:52 — which almost nobody does. But **nobody has said they would pay.** No discovery calls, no quotes from a sales-ops person, no market sizing, no design partner, no pilot. The submission itself labels the business model 'hypothesis (not yet validated with buyers)'. That honesty is admirable and it is also a self-assessed 3. On top of that, the deployment gap is a business-value problem, not just a presentation one: a compliance tool that has never run outside one laptop has no deployability story to a buyer." |
| **Originality** | **4.0 / 5** | "In a field that will be thick with AI receptionists, appointment-bookers and inbound-call agents, 'the contract interrupts the rep, in its own words, mid-call' is a framing I haven't seen. The deliberate refusal to let the LLM author spoken text is the genuinely novel bit and it's the right instinct for the domain. **What caps it at 4:** the mechanism underneath is the standard STT → LLM-classify → TTS chain, and the Voice Agent is used as a speech endpoint, not as an agent — no tool-calling, no turn-taking, no conversation. In a hackathon named after the Voice Agent API, a judge will notice that the agent never agents. The ADR defends that choice well, but defending a choice is not the same as being original in the axis being scored." |

### AFTER the recommended fixes — **17.5 / 20 (88%)** · verdict: *safely top 5, plausibly top 2.*

| Criterion | Before | After | What moved it |
|---|---|---|---|
| Application of Technology | 4.5 | **5.0** | Run the existing 32-claim eval against real Gemini and publish the confusion matrix. A measured precision/recall on the contradiction check closes the only real technical hole. A live hosted URL closes the second. |
| Presentation | 3.5 | **4.5** | Kill the `~2 s` / `~$0.12` contradiction everywhere. Recut so the first alert lands by ~0:45. Turn the latency waits into a narrated credibility beat instead of dead air. Fix the README's three "TODO"s. (Not a 5 — the recut is a cut, not a reshoot, so pacing stays merely good.) |
| Business Value | 3.0 | **3.5** | Three to five real conversations with sales-ops people, quoted verbatim in the deck, plus one pricing anchor priced against a named alternative. This is the hardest point in the list to earn and the only one that needs other humans. |
| Originality | 4.0 | **4.0** | Unmoved, and correctly so. Don't spend hours here; you cannot retrofit novelty into the mechanism, and the framing is already the strongest thing you have. |

---

## 2. What a strong rival shows, and exactly where we lose to it

The archetype to beat in a sponsor-run voice hackathon is not a better idea. It is **an entry a
judge can *use* in ninety seconds.**

| What the strong rival shows | What we show | Cost to us |
|---|---|---|
| **A URL, and often a phone number.** Judge clicks, talks, it answers. Zero setup. The single most reliable way to convert a skeptical judge into a believer. | `Application URL: [APP_URL]` — still a placeholder. README: *Live app: TODO*. Judge's only path is `pip install`, two API keys of their own, `npm run build`, `uvicorn`. **Nobody does that.** | **Largest single loss.** Against an equal entry that is clickable, we lose. Some judges score an unhosted entry as unfinished regardless of the repo. |
| **Sub-second conversational turn latency**, usually barge-in, because that's the whole point of a voice agent and the sponsor's own marketing. | 4.0–5.6 s from sentence end to alert. The video honestly contains ~14 s of dead air across three latency waits (measured silence windows: 64–68 s, 107–110 s, 124–128 s). | Real, and **partly unfixable inside the deadline** — the Gemini claim check is the slow leg. Beatable only by *reframing*: we are not a conversational agent, we are a guardrail, and 5 seconds inside a 30-minute call is in time to correct. Say that out loud, in the video, during the wait. |
| **Several scenarios, ideally an unscripted one**, or a judge-supplied input. | One demo contract, four clauses, two scripted contradictions (§3.1, §6.1), one scripted question (§4.2). Every measured number in every document comes from **N=1 runs**, and the docs say so. | Moderate. "Does it work on *my* contract?" has no answer today. The fix — upload one different contract on camera — is cheap. |
| **Some human signal**: a design partner, a waitlist, three quotes, a pilot, even 20 survey responses. | None. Business model explicitly a stated hypothesis. | Moderate on Business Value; it is the one axis where a weekend of hustle beats a weekend of code. |
| **Visible use of the sponsor's headline product as an *agent*** — tool calls, multi-turn, interruption handling. | Voice Agent used as a "say exactly" speech endpoint. Well-justified (ADR-0001), but the agent surface a judge sees is narrow. | Small-to-moderate under Application of Technology, and it is a *deliberate* trade. Don't reverse it — Option A is a proven live failure. Pre-empt it in the video instead (see Q3, §4). |

**Where we beat the archetype, and must therefore lead with it:** almost nobody in a hackathon
ships a *falsifiable* engineering claim. We have one — the spoken output is verified word-for-word
against the source text after it is spoken, with a similarity number on screen. The typical rival
demos an agent that says plausible things. We demo an agent that says *provably the right things*.
That, plus the on-camera honesty about 5 seconds, is the differentiation. Lead both.

---

## 3. Ranked fix list — what moves points, what is decoration

### Tier 1 — do these or don't submit

**F1. Kill the `~2 s` / `~$0.12` contradiction. ~45 min. Moves Presentation, and protects every other score.**
This is not a cosmetic inconsistency; it is the one thing in the submission that makes a judge
stop trusting the rest of it, and the *entire* pitch is built on "measured, not projected."
Occurrences and corrected wording are in §5. `cover.html` is plain HTML — edit three `<div class="stat">`
values and re-screenshot (10 min). The PDF needs `ClauseCatcher.pptx` edited and re-exported;
**there is no deck build tooling in the repo** (`tools/` holds only `demo_video`, `deploy`, `e2e_mic`),
so budget 30 min of manual PowerPoint work for slides 4, 9 and 10.

**F2. Deploy and put a real URL in every field. 45–90 min. Moves Application of Technology and Business Value.**
`render.yaml`, `Dockerfile` and `docs/DEPLOY.md` already exist and `CHECKLIST.md` has a verified
60-second pre-judging warmup runbook including the WebSocket-101 probe. This is execution, not
design. Then replace `[APP_URL]`, and replace the README's `Live app: TODO`.
**Caveat a judge will find:** Render free tier sleeps after 15 idle minutes. Run the warmup
runbook before judging, and add one line to the submission text: *"Hosted on Render's free tier;
first request after idle takes ~60 s to wake."* An unexplained 60-second white screen reads as broken.

**F3. Run the eval you already built. ~30 min, $0. Moves Application of Technology to 5, and defuses the single hardest judge question.**
`spikes/claim_check/labeled_claims.json` holds 32 labeled sentences; `eval_claim_check.py` runs
them at 4500 ms spacing (≈2.5 min of wall time) on the Gemini free tier. `spikes/claim_check/README.md`
currently says, in bold, **"Real Gemini accuracy is UNMEASURED."** That sentence is in a public repo
and a judge who opens it has found your weakest point for you. Run it, publish the confusion matrix
in the README and as a bullet on slide 9. **Even a mediocre number beats no number** — and the
system's design bias (errors → "unclear", never "contradiction") means a low false-positive rate is
the likely result, which is exactly the number that matters for this product. If the result is bad,
you have learned something worth more than a slide.

**F4. Fix the README's three "TODO"s. ~5 min. Moves Presentation.**
`Status: in development.` → shipped status. `Demo video: TODO (Vimeo)` → the Vimeo URL.
`Live app: TODO` → the Render URL. A stranger's first 10 seconds on the repo currently say
"unfinished." The repo is not unfinished; the README is lying downward.

### Tier 2 — real points, do if time allows

**F5. Recut the video so the first alert lands by ~0:45, and narrate the wait. 60–90 min. Moves Presentation.**
Current beat map (from `DEMO_NOTES.md`, confirmed against extracted frames): title 0:00, landing
0:03, how-it-works 0:09, setup 0:21, contract loaded 0:24, call starts 0:38, first alert **1:09**.
The wow is 40% in. Compress 0:03–0:38 to about 18 seconds — the landing page and the clause-card
reveal are lovely and they are *not* the product. Target: first alert by 0:45.

On the dead air: **keep the latency, kill the silence.** Do not cut the waits — `DEMO_NOTES.md` is
right that cutting them misrepresents the system, and a judge who later sees the ~5 s number will
respect that you left it in. But 5 seconds of digital silence reads as a broken recording, not as
honesty. Fill each wait with narration that *names the number*:

> "That pause is real. About five seconds — the contradiction check is the slow leg, and we left it
> in rather than cut it. On a thirty-minute call, five seconds is still in time to correct."

That converts the worst 14 seconds of the video into the most credible 14 seconds of the video.

**F6. Say "this is a real microphone" out loud. ~10 min (one narration line + re-mux). Moves Presentation.**
Every cockpit frame shows a **"SIMULATE REP LINE — Demo aid: sent as if the rep said it"** input box
in the right rail. `DEMO_NOTES.md` states the shipped take used real mic audio through AssemblyAI
Streaming STT — but a judge reading that on-screen label has no way to know which path ran, and will
assume the cheaper one. One sentence over the cockpit ("this is real microphone audio through
AssemblyAI Streaming STT; the simulate box is there for noisy rooms and isn't what's running")
protects the whole demo. Cheapest credibility point in the list.

**F7. Three to five real conversations with sales-ops people. 3–4 h, needs other humans. Moves Business Value.**
LinkedIn or a Slack community; ask two questions: *"has a rep on your team ever promised something
the contract didn't allow?"* and *"who found out, and when?"* Quote two answers verbatim on slide 10.
This is the only Business Value point that can actually be earned before the deadline, and the only
fix here that money and code cannot substitute for.

**F8. Upload a second, different contract on camera. ~20 min. Moves Application of Technology.**
Ten seconds of the video, or one extra slide with a screenshot: a different PDF, different clause
numbering, clauses extracted correctly. Answers "does this work on anything but your fixture?"
without a single word of argument.

### Tier 3 — decoration. Do only if everything above is done.

- GitHub repo topics and homepage URL (repo metadata currently has `repositoryTopics: null`,
  `homepageUrl: ""`). Two minutes, near-zero judge impact.
- Burned-in subtitles on the video. Real for accessibility, but lablab judges watch with sound —
  this is a voice hackathon.
- A README architecture-diagram polish pass. The Mermaid diagram already renders and reads fine.
- More tests. 136 + 21 is already above what any judge will check. Adding a 157th moves nothing.
- Reconciling `SLIDES.md` (9 slides, stale numbers) with the shipped 10-page PDF. `SLIDES.md` is
  an internal outline; **do not spend deck-fix time here until `cover.png` and the PDF are corrected.**
  (Correct it eventually for consistency — it currently carries the same `~2 s` error.)

### Blunt note on "generic AI-built slop"

There is very little, and it is worth saying so because the instinct to over-hedge is the real risk
here. The ADR argues *against* the author's own first choice with logged evidence, quotes its own
cost arithmetic, and flags an unverified assumption about judging criteria. `DEMO_NOTES.md` records
that two copy claims were **corrected downward to match the measurements rather than the other way
round.** That is not what generated documentation looks like.

Three things do read as machine-shaped and are worth ten minutes each:

1. **The long description's ALL-CAPS section headers** (`IN ONE LINE`, `THE PROBLEM`, `WHAT
   CLAUSECATCHER DOES`, `WHY IT CAN BE TRUSTED`, `MEASURED, NOT PROJECTED`) — nine shouted headings
   in 760 words is a format tell. The content is fine; the packaging looks auto-generated. If
   lablab's editor supports headings, convert them. If not, cut to four.
2. **Repeated triads.** "Listen. Check. Speak." / "what was said, what was caught, what it cost" /
   "section number, title, the literal text." Individually good lines; at this density it becomes
   a rhythm a judge has read five hundred times this month. Break two of them.
3. **Over-hedging.** "Every figure here comes from a single run, not an average" appears in the
   README, the long description, and the slides' speaker notes. Say it **once**, precisely, in the
   place that carries the numbers (slide 9). Saying it three times converts honesty into apology
   and invites the judge to wonder what else is shaky.

---

## 4. The 10 hardest questions, honest answers, and where each answer must live

**Q1. "Your cover image says two seconds. Your video shows five. Which is it?"**
*(Certain to be asked if not pre-fixed. This is the credibility-killer.)*
**Honest answer:** Five. Measured live 2026-09-17: 4.6 s, 5.6 s, 4.0 s. The `~2 s` figures on the
cover and slides 4/9 are stale from an earlier estimate and are wrong. The app's own landing page
already says `~5 s`.
**Where it lives:** Nowhere — *fix it before submission* (F1). If a live Q&A happens anyway, answer
in exactly those words, with no softening. A judge forgives a corrected number instantly and never
forgives a defended one.

**Q2. "How often does it accuse a rep who said nothing wrong?"**
*(The question that decides whether this is a product or a demo.)*
**Honest answer today:** Unmeasured against a labeled set. What is known: in the shipped take, 5
claim checks produced 2 correct contradictions and 0 errors, and consistent lines raised nothing
(§4.2 and §5.3 were checked and held). Architecturally, errors, timeouts and unparseable responses
all resolve to "unclear," never to "contradiction," so the failure mode is biased toward misses over
accusations — deliberately, because a false accusation on a live sales call is worse than a miss.
**Where it lives:** README "Measured results", slide 9, and the long description — **after running
F3**, as a real precision/recall on the 32-example set. This question is the single strongest
argument for spending the 30 minutes.

**Q3. "It's a Voice *Agent* hackathon. Your agent doesn't agent — it's a TTS endpoint."**
**Honest answer:** Correct, and deliberate. A single Voice Agent session doing both jobs was
live-tested and auto-started 4 replies over the rep despite an explicit silence prompt, and the
turn-detection docs expose no reply-suppression control — only sensitivity and timing knobs. We
also tried injecting the alert as a conversation message; the agent ignored the injected content
entirely. Only a direct "say this exactly" instruction produces a verbatim spoken match. On a sales
call, a paraphrased contract clause is a new promise, so the agent's LLM must not choose the words.
We used the Voice Agent for the job it verifiably does well and Streaming STT for the job it
verifiably does well.
**Where it lives:** Already in ADR-0001, README "Why AssemblyAI", and slide 7 — which is good work.
**It is not yet in the video.** Add one narration line over the architecture beat; a judge who
watches only the video never reaches the ADR.

**Q4. "Why is there no link I can click?"**
**Honest answer today:** There isn't one yet; the Docker image, `render.yaml` and deploy runbook
exist but the deploy hasn't been executed. **Fix this (F2) rather than answering it.** If it is
genuinely impossible: say plainly that the hosted instance is unverified and that no claim in the
submission is made for one — which the current materials already do, correctly.
**Where it lives:** The submission's Application URL field, the README Links block, and the end card.

**Q5. "What stops the Voice Agent from paraphrasing the clause and inventing a legal term?"**
**Honest answer:** Two things, and one of them is a check rather than a guarantee. The instruction
is a direct "say this exactly, word for word," and the text handed to it is extracted from the PDF
at upload time and never passes through an LLM. Then the app grades the agent's own transcript
against the source and reports `literal_spoken` plus a similarity score on screen. In the shipped
take that read 2/2 verbatim at similarity 1.0. **It is verification after the fact, not prevention** —
if the agent ever paraphrased, the app would flag it, but the words would already have been spoken.
**Where it lives:** README "Safety rules" (reword the phrase "verbatim guarantee" — see §5), slide 8,
and one spoken line in the video when the "Spoken verbatim" badge appears.

**Q6. "Who has told you they'd pay for this?"**
**Honest answer:** Nobody yet. The buyer hypothesis is sales-ops and revenue-compliance owners at
B2B companies whose reps quote pricing, renewal, retention or SLA terms on live calls. The pricing
hypothesis is a per-rep monthly subscription; measured API cost is $0.08–$0.15 per call, so unit
economics are not the constraint. Neither has been validated with a buyer.
**Where it lives:** The long description already labels it a hypothesis, which is the right call.
Upgrade it with F7 — two verbatim quotes from real sales-ops people on slide 10 is worth more than
any amount of TAM arithmetic.

**Q7. "Five seconds — the customer has already heard the promise. Isn't the damage done?"**
**Honest answer:** The promise is out, yes. What ClauseCatcher changes is whether the rep can
correct it *on the same call* instead of the company discovering it weeks later in a dispute. On a
30-minute call, a 5-second correction lands inside the same exchange. The unacceptable latency is
not 5 seconds, it's 5 weeks.
**Where it lives:** This is the reframe that neutralizes the biggest technical weakness, and it
appears **nowhere in the current materials.** It belongs spoken in the video over the first wait
(F5), and as one line on slide 4 or 9.

**Q8. "Everything in this submission is one run. Is any of it repeatable?"**
**Honest answer:** Two independent takes were measured: 6.2 s / 4.3 s / $0.1466 and 5.6 s / 4.0 s /
$0.1535 — same shape, which is why the honest headline is "about 4–6 seconds" and "about 15 cents."
A separate automated browser-mic run on 2026-09-17 passed 17/17 checks with alert → first voice
audio at 375 ms. Every document says the figures are single runs rather than averages.
**Where it lives:** README (already correct) and slide 9. **Add the second take's numbers** — right
now `DEMO_NOTES.md` is the only place the N=2 consistency is visible, and no judge reads that file.
Two consistent runs is a materially different claim from one run.

**Q9. "There's a 'Simulate rep line' box on screen the whole demo. Is any of this real?"**
**Honest answer:** The shipped take is one continuous live session against real upstreams — real
AssemblyAI Streaming STT of audio played into the browser's microphone, real Gemini verdicts, real
Voice Agent audio captured off the session WebSocket. The simulate box is a labeled demo aid for
noisy recording environments and was not the input path in this take.
**Where it lives:** `DEMO_NOTES.md` says this clearly; a judge will never open it. Put it in the
video narration (F6) and in one README line under Measured results.

**Q10. "What breaks first when a real sales team turns this on tomorrow?"**
**Honest answer:** Three things, in order. (1) Contract parsing — `pdfplumber` on a real 40-page
MSA with tables and nested numbering, against a 4-clause fixture today. (2) Claim-check precision
on ambiguous sales language, which is unmeasured (Q2). (3) Audio capture — it listens to the
browser tab's mic, not to the calling platform, so a rep on Zoom needs the audio routed; no
platform integration exists.
**Where it lives:** Slide 10 "What's next" names two of these. **Add the contract-parsing limit** —
naming the thing that breaks first is the answer that makes a judge believe the rest of the deck,
and hiding it is the answer that makes them go looking.

---

## 5. Overclaims and unsupported statements — quoted, with corrections

Ordered by how much damage each does.

### 5.1 `~2 s` — wrong, and contradicted by our own video and our own app. **[CRITICAL]**

Measured reality: **4.0 s, 4.6 s, 5.6 s** (2026-09-17, live browser). Every `~2 s` in the
submission is stale.

| Location | Current text | Corrected text |
|---|---|---|
| `docs/submission/cover.png` (and its source `cover.html:64`) | `~2 s` / `sentence to alert` | `~5 s` / `sentence to alert` |
| `ClauseCatcher.pdf` slide 4 | "§3.1 flagged in ~2 s" | "§3.1 flagged in ~5 s" |
| `ClauseCatcher.pdf` slide 9 (hero stat) | `~2 s` / `sentence end to alert` | `~5 s` / `sentence end to alert (4.0–5.6 s measured)` |
| `docs/submission/SLIDES.md`, slide 8 | "Alerts ~2 seconds after the sentence" | "Alerts about 4 to 6 seconds after the sentence" |

`frontend/src/components/landing/Landing.tsx:670` already says `~5 s` and is correct — which is
precisely why the cover and deck are dangerous: **the judge sees both numbers in the same minute.**

### 5.2 `~$0.12` — not a measured value. **[HIGH]**

Measured: **$0.0755** (55 s call) and **$0.1535** (1:52 call); an earlier take read $0.1466. `~$0.12`
matches none of them and understates the call the video actually shows.

| Location | Current text | Corrected text |
|---|---|---|
| `ClauseCatcher.pdf` slide 9 | `~$0.12` / `API usage, full demo call` | `~$0.15` / `API usage, the call in this demo` |
| `ClauseCatcher.pdf` slide 10 | "~$0.12 API usage per demo call" | "$0.08–$0.15 of API usage per call, by the app's own meter" |

`Landing.tsx:672` already says `~$0.15`. Same contradiction as 5.1.

### 5.3 `~78 ms` — true, but it is not the number the video demonstrates. **[MEDIUM]**

Slide 9 and `cover.png` show **`~78 ms` / "speak request to first audio"**, from the 2026-09-15 run.
The 2026-09-17 browser run measured **375 ms** from alert to first voice audio — a different
boundary, so both can be true. But `78 ms` next to a video containing 5-second waits reads as
cherry-picking the one flattering number.
**Corrected wording:** `~375 ms` / `alert to first spoken word (browser, 2026-09-17)`. It is still
an excellent number, it is the one the viewer actually experiences, and using it removes the
appearance of stat-shopping. If you keep 78 ms, label it `speak request → first audio frame` and
put 375 ms beside it.

### 5.4 "the verbatim guarantee" — it is a verified check, not a guarantee. **[MEDIUM]**

> `README.md:57` — "That 'say exactly' instruction is the trick that makes **the verbatim guarantee**
> real"
> `SLIDES.md:62` — "**The verbatim guarantee** only works because of that instruction"
> `DEMO_SCRIPT.md:31` — "Same mechanism, **same guarantee**"

The implementation (`server/voice.py:_grade_match` → `literal_spoken`, `similarity`) grades the
agent's transcript **after** it speaks. A paraphrase would be detected and flagged, not prevented.
**Corrected wording:** "the verbatim *check*" / "every spoken alert is graded against the contract
text and flagged if it doesn't match, word for word." Keep "similarity 1.0, 2/2 verbatim" — that
part is measured and it is the strongest sentence in the submission.

### 5.5 Slide 10's "NEXT" list understates what is already done. **[MEDIUM — underclaim]**

> Slide 10, `NEXT`: "Browser-mic path, hardened end to end"

The browser-mic path **was verified on 2026-09-17**: an automated run drove real
`getUserMedia` → AudioWorklet → 16 kHz PCM16 through the full pipeline and passed **17/17** checks.
Listing it as future work throws away a point you already earned and makes the entry look less
finished than it is.
**Corrected wording:** move it to slide 9 as "Browser-mic path verified end to end — 17/17 automated
checks, 2026-09-17." Leave "A hosted, deployed instance" under NEXT **only if F2 isn't done.**

### 5.6 README "Status: in development" and two TODO links. **[MEDIUM]**

> `README.md` — "**Status: in development.**" … "Demo video: TODO (Vimeo)" … "Live app: TODO"

`demo.mp4` is committed and shipped. The status line and the video TODO are simply out of date, and
they are the first and last things a stranger reads on the repo.
**Corrected wording:** "Status: submitted to the AssemblyAI Voice Agent Hackathon (Sep 2026)." Fill
both links.

### 5.7 `spikes/claim_check/README.md` — accurate, and it hands a judge your weakest point. **[INFORMATIONAL]**

> "Real Gemini accuracy is **UNMEASURED** — no key was configured on this machine when this spike
> was built."

This is not an overclaim; it is exemplary honesty in a public repo. It is also a labeled 32-example
set and a working runner, sitting unrun, with a bold "UNMEASURED" next to it. **Don't edit this
sentence — delete the condition that makes it true (F3).**

### 5.8 Nothing else overclaims, and that is worth stating.

No superlatives survived a targeted sweep for `guarantee|100%|never miss|always|accuracy|zero false|
enterprise-grade|production-ready|SOC 2|GDPR|HIPAA` across the README, all submission docs, the
cover source and the landing page copy — only the "guarantee" instances in 5.4. Cost figures,
latency figures and test counts (136 server / 21 frontend, both verified against the test files)
all match the code. The N=1 caveat is stated everywhere it applies. **The materials' problem is not
that they exaggerate; it is that two stale numbers survived a downward correction pass that
everything else went through.**

---

## 6. One-page summary

**Before: 15.0/20. After: 17.5/20.** The gap between those is about **four hours of work**, none of
it code, and three of the four top fixes are execution of things that already exist in the repo
(a deploy config, an eval harness, a video edit).

**Top 5 point-movers, in order:**

1. **Fix `~2 s` → `~5 s` and `~$0.12` → `~$0.15` on `cover.png` and PDF slides 4/9/10.** ~45 min.
   Protects everything else; the submission currently contradicts itself on camera.
2. **Deploy to Render, fill `[APP_URL]`, run the warmup runbook before judging.** 45–90 min.
   "No link to click" is the most reliable way to lose to an equal rival.
3. **Run `eval_claim_check.py` on the 32 labeled claims; publish the confusion matrix.** ~30 min, $0.
   Converts the hardest judge question into a slide bullet.
4. **Recut so the first alert lands by ~0:45, and narrate the 5-second waits instead of leaving
   silence.** 60–90 min. The wow currently arrives at 1:09 and the video contains ~14 s of dead air.
5. **Fix the README's three TODOs, and say "this is a real microphone" out loud in the video.**
   ~15 min combined. The cheapest credibility points available.

**Do not spend time on:** more tests, repo topics, subtitles, README diagram polish, or reconciling
`SLIDES.md` before the shipped PDF is corrected.
