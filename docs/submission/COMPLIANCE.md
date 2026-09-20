# ClauseCatcher — lablab.ai / AssemblyAI Voice Agent Hackathon compliance audit

Audited 2026-09-17 against HEAD `a629536`. Every rule below was read from the live
pages on 2026-09-17, not from memory or our own docs.

**Sources (all quoted verbatim below):**

| ID | Page | URL |
|---|---|---|
| EVT | Event page (About / Guidelines / Prizes / Judging / Schedule) | https://lablab.ai/ai-hackathons/assemblyai-voice-agent-hackathon |
| SUB | Submission Guidelines | https://lablab.ai/delivering-your-hackathon-solution |
| RB | lablab.ai Hackathon Rule Book | https://lablab.ai/hackathon-rules |
| TOU | Terms of Use (§3 Eligibility, §4 Content, §11 Warranties, §16 Participation Terms, §17 Payout) | https://lablab.ai/terms-of-use |
| GUI | Hackathon Guidelines FAQ | https://lablab.ai/guide |

**Deadline (verified, EVT):** header reads `Submission deadline Sep 30, 3:00 PM CUT`;
schedule line reads ` Sep 30 3:00 PM Coordinated Universal Time End of Submissions!`
→ **2026-09-30 15:00 UTC = 11:00 AM EDT**. Matches what our docs claim. RB adds:
"Manual submission is available for 6 hours post-hackathon for those with valid reasons
and prior approval from organizers or mentors." — that is a discretionary escape hatch
requiring **prior** approval, not a grace period. Do not plan around it.

---

## Findings, ordered by risk of disqualification

### Tier 1 — will cost the entry (missing required field / cannot be judged)

| # | Rule (quoted) | Source | Status | Evidence | Action |
|---|---|---|---|---|---|
| 1 | "**Application URL:** Provide a link that allows interaction with your prototype." / RB: "**Application URL**: Required for interactive evaluation." Scoring floor: "1 - Poor Application \| ... Demo link is not available." | SUB §3, RB §3 | **FAIL** | `docs/submission/LABLAB_SUBMISSION.md` still contains the literal placeholder `[APP_URL]`. `docs/submission/CHECKLIST.md:28` marks item 12 `pending`. No deployment exists. | Deploy per `docs/DEPLOY.md` (Render Docker from `render.yaml`), set `ASSEMBLYAI_API_KEY` + `GEMINI_API_KEY` in Render env, drive one real alert, paste the URL. **Highest-value single action.** |
| 2 | "**Video Presentation:** A maximum 5-minute video in MP4 format." RB: "**Video and Slide Presentation**: MP4 and PDF formats are mandatory." Scoring floor: "Demo video is not available in video presentation." | SUB §2, RB §2, RB judging §3 | **FAIL (link), PASS (file)** | File exists and is valid: `docs/submission/demo.mp4`, ffprobe → h264 + aac, 1920x1080, 30 fps, **174.40 s (2:54)**, 22.4 MB. But `LABLAB_SUBMISSION.md` still has `[VIMEO_URL]`; `CHECKLIST.md:24` item 8 `pending`. | Upload to Vimeo (privacy "Anyone"), paste clean `vimeo.com/<id>`. See also finding #9 — the runtime is a scoring problem. |
| 3 | "The hackathon takes place online on the lablab.ai platform and the lablab.ai Discord server. **Please register for both in order to participate.** To join, click the Enroll button..." | EVT, Guidelines | **UNKNOWN** | Nothing in this repo proves enrollment or Discord registration. Cannot be verified from the filesystem. | Confirm: (a) Enrolled on the event page, (b) joined discord.gg/lablabai, (c) Discord account linked in the lablab profile. GUI: "Participants must ensure their Discord account is connected to their lablab.ai profile." |
| 4 | "Do I need to create or join a team to participate? **Yes.** In order to participate you need to be a member of a team on lablab.ai. **This applies for solo participants as well**." / "Do all team members have to register... **Yes.** All members of each team will need to register independently via lablab.ai. This applies for solo participants as well." | GUI | **UNKNOWN** | Solo entry. A lablab *team object* must exist even for one person; submissions on the event page are namespaced `/<team-slug>/<project-slug>`. | Create the team on the event page ("Create or join a team" → "Create a team") before the deadline. A solo builder who never made a team has nowhere to attach the submission. |

### Tier 2 — scoring damage, not automatic DQ

| # | Rule (quoted) | Source | Status | Evidence | Action |
|---|---|---|---|---|---|
| 5 | "**Demo Application Platform:** Opt for Streamlit (for Python web apps), Replit (for online code execution), or Vercel (to host web apps)." RB states it harder: "**Demo Application Platform**: Use Streamlit, Replit, or Vercel." | SUB §3, RB §3 | **PARTIAL** | We plan Render (FastAPI + WebSocket + built React from one Docker image; `render.yaml`, `Dockerfile`). Neither page makes the list exclusive ("Opt for"), and the event's own published submissions list platforms outside it. But RB's imperative wording is a judge-visible mismatch. | Keep Render — Vercel cannot host a long-lived WebSocket + PCM stream. If the form is a fixed dropdown, choose "Other"; never claim a platform we are not on. Add one line to the long description explaining *why* Render (WebSocket audio), so a judge reads it as a technical choice, not a rule miss. |
| 6 | "**⚠️ Public GitHub Repository & IBM Bob Report:** ... Include any code or files where IBM Bob assisted in the development, and **be sure to include the exported IBM Bob report** of all relevant tasks/sessions used for your project." | SUB §3 (live text, 2026-09-17) | **UNKNOWN** | This is on the exact page EVT links as the submission guide, but the AssemblyAI event's own "What to submit" block lists only: Public GitHub repository / Demo application platform / Application URL. No IBM Bob anywhere on EVT, and AssemblyAI is the sole sponsor. Reads as stale boilerplate from an IBM-sponsored event. | Ask in Discord (question drafted below). Cheap insurance; do not build an IBM Bob report on speculation. |
| 7 | "Everything below is either re-implemented from a scouted reference's visual pattern (no code copied...)" — our own claim, against TOU: "All submissions by participants must be **original work, open source, and compliant with the MIT License** unless specified otherwise." | TOU §16, EVT Prizes ("Submissions must be original and MIT-compliant") | **PASS with caveat** | MIT `LICENSE` at repo root (`Copyright (c) 2026 Vishal Patel`); GitHub API confirms `license: MIT`, `private: false`, `pushed 2026-09-17T23:39:44Z`, remote HEAD == local HEAD `a629536`. Three `THIRD_PARTY.md` files state re-implementation, not copying, for Aceternity / Magic UI / Kokonut / React Bits patterns. | **Visual patterns are not copyrightable the way code is, and we copied no code** — the posture is right. Caveat: `THIRD_PARTY.md` asserts licenses for Aceternity ("Free, open Code tab, no paywall") and Kokonut ("MIT/open") that are **not SPDX identifiers we verified from a LICENSE file**. Magic UI (MIT) and React Bits (MIT) are named correctly. Low risk; if challenged, the defense is the re-implementation claim, not the license claim. |
| 8 | OFL-1.1 requires the copyright notice and license accompany redistributed font files. | @fontsource package metadata | **PARTIAL** | `node_modules/@fontsource-variable/inter`, `@fontsource/manrope`, `@fontsource/jetbrains-mono` all declare `"license": "OFL-1.1"` and ship a `LICENSE` file. Vite copies the `.woff2` binaries into `dist/` but **not** those LICENSE files. | Add a root `NOTICE` or `THIRD_PARTY.md` listing Inter / Manrope / JetBrains Mono (SIL OFL 1.1) and lucide-react (ISC). ~10 minutes, closes the only real license gap in the build. |
| 9 | RB judging, Presentation axis: "**2 - Limited** \| ... **Presentation video is less than 3 min.**" vs "**3 - Adequate** \| Effectively communicates the problem, solution, and value proposition **in less than 5 min**." | RB §3 judging table | **AT RISK** | `demo.mp4` is **174.40 s = 2:54** — six seconds under the 3:00 line that the rubric explicitly names as the marker for a *2 out of 5*. | Re-export at **3:30–4:30**. This is the single cheapest scoring gain available: the rubric puts a hard numeric floor at 3:00 and we are sitting under it by 6 seconds. |
| 10 | RB Presentation axis, 4–5 scores require: "Explain market analysis and marketing revenue. Explain future goals & plans." / "shows project's strengths and uniqueness through **competitive analysis**." SUB Pro Tips: "Include Total Addressable Market (TAM) and Serviceable Addressable Market (SAM)." | RB §3, SUB §4 | **PARTIAL** | `LABLAB_SUBMISSION.md` long description has a competitor line ("Most call-review tools analyze recordings after the call ends...") and a pricing hypothesis, but **no TAM/SAM figures**. `ClauseCatcher.pdf` is 11 pages — not audited for TAM/SAM here. | Verify the deck has a market-size slide. The rubric's top two Presentation bands both name market analysis explicitly. |

### Tier 3 — verified compliant, no action

| # | Rule (quoted) | Source | Status | Evidence |
|---|---|---|---|---|
| 11 | "Dates: Sep 1–30, 2026" / "Online Tuesday, September 1 2026 - 3:00 PM Coordinated Universal Time" | EVT | **PASS** | `git log --reverse --date=iso`: first commit `8442189` **2026-09-14 18:54:12 -0400** (= 2026-09-14 22:54 UTC), last `a629536` 2026-09-17 19:39:38 -0400. All 11 commits fall inside Sep 1–30. **No spike history predates the window** — `spikes/` was committed Sep 16, inside the window. |
| 11b | *No explicit "must be built during the hackathon" rule exists.* | RB, TOU, SUB, EVT, GUI all searched | **N/A** | The closest statements are descriptive, not restrictive: "you have the whole window to take an idea from an empty repo to a working voice agent" and "You can join at any point — registration stays open for the whole build window, so you can start on day one or pick the project up halfway through and still submit." Since our first commit is inside the window anyway, this is moot either way. |
| 12 | "Teams consist of **1-6 people**." (EVT overrides RB's "maximum of five participants" for this event.) | EVT Guidelines | **PASS** | Solo entry = 1. |
| 13 | "**A. Eligibility:** To access or use our Services, you must be **18 years or older** and have the requisite power and authority to enter into these Terms." | TOU §3.A | **PASS (assumed)** | No age evidence in the repo; participant is an adult. No students-only tag anywhere on EVT — the page says "Everyone is welcome to participate, regardless of previous AI or coding experience." |
| 14 | "you are not organized under the laws of, operating from, or otherwise located or resident in a country or territory that is subject to US economic or trade sanctions (i.e. an embargo, including North Korea, Iran, Cuba, Russia...)" | TOU §11 | **PASS** | US-based. EVT: "🌍 Fully online hackathon. Join and build from anywhere in the world." No region restriction. |
| 15 | "teams with our own members of staff will be excluded from the judging & award process" / "Organizers are welcome to participate but are not eligible for prizes." | GUI, RB | **PASS** | Not lablab/AssemblyAI/NativelyAI staff, not a listed mentor or judge. |
| 16 | *AI-assisted development.* No rule restricting or requiring disclosure of AI coding tools exists on any of the five pages. | RB, TOU, SUB, EVT, GUI | **PASS** | Searched all five for any restriction: none. The only adjacent clause is RB Ethical Conduct — "cheating, tampering with systems, **using unauthorized automation**, engaging in fraudulent behaviour" — which is scoped to gaming the event (RB names "plagiarism or gaming the voting system"), not code generation. **Positive evidence:** the event's own published submission list tags competing entries with `Claude Code`, `Codex` and `Anthropic Claude` as technologies. Claude Code use is allowed and is even a taggable technology here. |
| 17 | "**Cover Image:** ... **Format:** PNG or JPG. **Aspect Ratio:** Recommended 16:9." | SUB §2 | **PASS** | `cover.png` — PNG, **1920 x 1080**, ratio 1.7778 (exactly 16:9), 568 KB. |
| 18 | "**Slide Presentation:** Summarize your project in a PDF format slide presentation." | SUB §2 | **PASS** | `ClauseCatcher.pdf` — `%PDF-1.7`, 11 pages, 513 KB. |
| 19 | "**Short Description:** A concise summary (up to 255 characters)" | SUB §1 | **PASS** | 235 characters (counted in `LABLAB_SUBMISSION.md`). |
| 20 | "**Long Description:** Detailed write-up (at least 100 words)" | SUB §1 | **PASS** | ~760 words. |
| 21 | "**Technology & Category Tags:** Select tags that best categorize your project" | SUB §1 | **PASS (pending picker)** | Priority-ordered tag list in `LABLAB_SUBMISSION.md`, with the correct instruction not to invent tags absent from lablab's picker. |
| 22 | "**Public GitHub Repository**: Mandatory for storing your code." / "If you submit a private repository, judges won't be able to fully review your work, which may lower your overall score." | RB §3, SUB §3 | **PASS** | GitHub API: `private: false`, HTTP 200 unauthenticated. 172 tracked files. `git ls-files` shows **no `.env`, key or secret file tracked** — only `.env.example`. History scan for `sk-*` / `AIza*` / 32-hex patterns across all refs returned nothing. |
| 23 | "Every participant builds on AssemblyAI." / "Build a voice agent using AssemblyAI's real-time voice AI technology." | EVT About + Challenge | **PASS** | AssemblyAI is load-bearing in two places, not decorative: `server/stt.py` (Streaming STT v3) and `server/voice.py` (Voice Agent API), wired through `server/main.py`. Architecture rationale in `docs/adr/0001-voice-architecture.md`. |
| 24 | "Unethical behavior, such as **plagiarism** or gaming the voting system, will lead to immediate disqualification." | RB Ethical Conduct | **PASS** | Three `THIRD_PARTY.md` files pre-disclose every design influence with source URL and what was re-implemented. That disclosure is itself the defense against a plagiarism claim. |

### Tier 4 — data privacy, consent, third-party contract data

| # | Requirement | Source | Status | Evidence | Action |
|---|---|---|---|---|---|
| 25 | "you hereby irrevocably grant us world-wide, perpetual, non-[exclusive]... [license to] use, copy, publicly perform and display, reproduce, distribute, modify... Your Content" | TOU §4.C | **PASS** | Everything we submit becomes lablab-licensable. Our demo artifacts contain no real customer data: `docs/screenshots/setup-contract.png` shows `demo-contract.pdf` with four synthetic clauses (§3.1 Pricing & Seat Cap, §4.2 Renewal, §5.3 Data Retention, §6.1 Support SLA) naming no real company. | Before submitting, confirm `demo.mp4` uses the same synthetic contract and scripted lines — **never** upload a real signed contract or a real customer's voice into an artifact lablab gets a perpetual license to. |
| 26 | "(ii) violates any third-party right, including any copyright, trademark, patent, trade secret, **moral right, privacy right, right of publicity**..." | TOU §4.B | **PASS** | App enforces recording disclosure server-side before any audio flows: `server/main.py:280` `POST /api/consent`, and `server/main.py:288-289` raises `409 "contract and consent are required before starting a session"`. UI gate: `frontend/src/components/setup/ConsentCard.tsx` — "Everyone on the call has been told it's monitored / Disclosed consent is what keeps a monitored call compliant." Start is disabled until checked. | None required. This is a genuine differentiator — say it out loud in the video. Two-party-consent states (CA, FL, IL, PA, WA) make it a business-value point, not just hygiene. |
| 27 | *No rule on either page requires a privacy policy or data-retention statement.* | — | **PASS (gap noted)** | The app streams live speech to AssemblyAI and clause text to Google Gemini, and ingests third-party contract PDFs. Neither README nor the submission doc states retention. | Optional, ~5 min: one line in README stating that audio is streamed and not persisted, and that clause text goes to Gemini. Judges on the "Business Value" axis at a compliance product will look for it. |
| 28 | "Prizes are awarded **only to individuals**, not to teams or legal entities." + Form W-9/W-8BEN + government photo ID + bank verification within **90 calendar days** or "**permanently forfeited**. **No exceptions**." | TOU §17 | **N/A until win** | Post-award only. | If we win: US recipient path (W-9, no withholding, 1099-MISC over $600). Note the 90-day forfeiture clock starts at the notification email. |

---

## UNKNOWNs — exact questions to ask in Discord

Ask all four in one message in `#ineedhelp`, tagging `@Mentor`. None of these can be
resolved from any public page.

1. **IBM Bob report.** "The Submission Guidelines page (https://lablab.ai/delivering-your-hackathon-solution, section 3) says to include 'the exported IBM Bob report of all relevant tasks/sessions used for your project'. The AssemblyAI Voice Agent Hackathon event page's 'What to submit' section doesn't mention it. Is the IBM Bob report required for this hackathon, or is that line specific to IBM-sponsored events?"

2. **Demo platform.** "Submission Guidelines say to 'Opt for Streamlit, Replit, or Vercel' and the Rule Book says 'Use Streamlit, Replit, or Vercel'. Our app is a FastAPI + WebSocket server that streams PCM audio, so it's deployed on Render as a Docker web service instead. Is a working Application URL on another host accepted, or is the list mandatory?"

3. **Solo team object.** "For a solo participant — do I still need to create a team on the event page before I can submit, or does enrolling alone let me submit?"

4. **Deadline mechanics.** "Submission closes Sep 30 at 3:00 PM UTC. Does the submission have to be marked *final/submitted* by then, or is a saved draft created before the cutoff still judged? And does the 6-hour manual-submission window in the Rule Book need approval requested *before* the deadline?"

Secondary, only if the first four come back fast:

5. **AI-assisted development disclosure.** "Several published submissions in this hackathon are tagged with `Claude Code` and `Codex`. Confirming there's no restriction on AI coding assistants and no separate disclosure required beyond the technology tags?" *(Expected answer: allowed. Asking only to have it on the record — a past hackathon banned it.)*

---

## Top 5 actions, in order

1. **Deploy and paste the Application URL.** Without it, finding #1 caps the "Application of Technology" axis at *1 - Poor* by the rubric's own wording. Everything else is polish next to this.
2. **Upload `demo.mp4` to Vimeo and paste the link** — but re-export at 3:30–4:30 first. Shipping 2:54 walks into the rubric's named *2 - Limited* band for a six-second saving.
3. **Confirm the three platform prerequisites:** enrolled on the event page, joined + linked Discord, and a team object created (required even solo).
4. **Ask the four Discord questions above**, especially IBM Bob and the demo-platform list. Both are cheap to satisfy if the answer is "yes, required" and expensive to discover on Sep 30.
5. **Add a root `NOTICE`/`THIRD_PARTY.md`** for the OFL-1.1 fonts and ISC icons, and verify the deck has a TAM/SAM slide. Together ~20 minutes, and they close the only two substantive gaps left (license redistribution, Presentation rubric bands 4–5).

---

## What could not be verified

- **Platform-side state.** Enrollment, Discord linkage, team creation, and whether the lablab form's tag picker contains `AssemblyAI`, `Voice AI`, etc. — all live behind a login this audit does not touch.
- **Age eligibility (TOU §3.A, 18+).** Assumed satisfied; no repo evidence either way.
- **Deck contents.** `ClauseCatcher.pdf` verified only as a valid 11-page PDF — the slides were not read, so the TAM/SAM and competitive-analysis rubric items in finding #10 are unconfirmed.
- **Video contents.** `demo.mp4` verified only by container/codec/duration. Not watched, so finding #25 (no real contract or real third-party voice in the footage) is asserted from our own docs, not observed.
- **Aceternity UI and Kokonut UI license terms.** `THIRD_PARTY.md` asserts them; no LICENSE file was fetched from either project to confirm an SPDX identifier. Immaterial while the re-implementation claim holds.
- **The deployed app.** Does not exist yet, so nothing about it was tested. Render's free tier sleeps — once deployed, wake it before judging.
