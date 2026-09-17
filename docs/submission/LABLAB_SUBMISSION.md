# lablab.ai submission: ClauseCatcher

Copy-paste content for the lablab.ai submission form, field by field, in the order the event page lists them.

- Event: AssemblyAI - Voice Agent Hackathon, https://lablab.ai/ai-hackathons/assemblyai-voice-agent-hackathon
- Deadline: **Wed Sep 30 2026, 11:00 AM EDT** (event data `endAt: 2026-09-30T15:00:00.000Z`)
- Field list: event page, "What to submit". Field limits: https://lablab.ai/delivering-your-hackathon-solution
- Only two placeholders remain: `[VIMEO_URL]` and `[APP_URL]`. Fill both before submitting.

---

## 1. Basic information

### Project title

```
ClauseCatcher
```

### Short description (limit: 255 characters)

```
A voice agent for live sales calls. When a rep promises something the signed contract doesn't allow, it reads the exact clause back out loud within about 2 seconds. It quotes the contract word for word and never makes up legal wording.
```

(235 characters.)

### Long description (minimum: 100 words)

```
IN ONE LINE
When a sales rep promises something the contract doesn't allow, ClauseCatcher reads the rep the actual clause out loud, word for word, about 2 seconds later.

THE PROBLEM
Sales reps improvise on live calls. One sentence ("we can do a verbal discount on the extra seats") can promise something the signed contract forbids. Nobody catches it while the call is happening, so it turns up weeks later as a customer dispute instead of a one-sentence correction. Today, compliance and sales-ops teams catch this, if they catch it at all, by spot-checking recordings after the fact.

WHAT CLAUSECATCHER DOES
ClauseCatcher runs in a browser tab next to the call. Upload the contract PDF and it pulls out every clause once, word for word. During the call:
1. Listen: the rep's microphone audio streams to AssemblyAI Streaming STT v3. The session is seeded with keyterms taken from the contract, so contract-specific terms transcribe cleanly.
2. Check: each finished sentence goes to Gemini (free tier) with the clauses attached. Gemini returns only a verdict and a clause ID. It never writes any text that gets shown or spoken.
3. Alert: when a sentence contradicts a clause, an alert card appears with the offending phrase underlined. The AssemblyAI Voice Agent API then speaks the literal clause, using a direct "say this exactly, word for word" instruction. The audio plays in the ClauseCatcher tab, through the rep's own headset or speakers. ClauseCatcher doesn't connect to the calling platform, so it doesn't inject anything into the call itself.
4. Answer: a manager on the call can ask about any clause by number and hears it read back the same verbatim way.
5. Report: when the call ends, the report lists every clause referenced and every contradiction caught.

WHY IT CAN BE TRUSTED
- Clause text is quoted, never generated. The LLM only picks a clause ID.
- If a check fails, times out or can't be parsed, the sentence is marked "unclear", never "contradiction". Falsely accusing a rep is worse than missing a line, so errors stay silent.
- Every alert cites one specific clause, and each clause can fire at most once every 20 seconds.

HOW IT USES ASSEMBLYAI
It opens two AssemblyAI connections, and each has one job. Streaming STT v3 transcribes the whole call and has no reply behavior. The Voice Agent API is opened only when there is something to say. We started with a single Voice Agent session that both listened and spoke. Tested live, it started replying over the rep on its own, even with an explicit instruction to stay silent. Splitting the roles removes that failure by design (see docs/adr/0001-voice-architecture.md). We also tried injecting the alert as a conversation message. The agent ignored it. Only the direct "say exactly" instruction gave a word-for-word spoken match. We use the Voice Agent as a speaker on purpose: its own LLM never picks the words, because on a sales call a paraphrased contract is a new promise.

MEASURED, NOT PROJECTED
One live end-to-end run on 2026-09-15, with real AssemblyAI and Gemini connections and scripted rep lines fed into the pipeline:
- Two false claims caught: a fake automatic discount (contract §3.1) and a fake 24/7 support promise (§6.1). Consistent lines raised no alerts.
- Alert about 2 s after the sentence ended. Spoken clause matched the contract text exactly (similarity 1.0). First voice audio about 78 ms after the speak request.
- A spoken question about clause §4.2 was answered correctly.
- About $0.12 of API usage for the whole call.
- 136 backend tests pass (pytest server/).
Not yet verified end to end: the live browser-microphone path, and the hosted deployment. We don't claim results for either.

WHO IT'S FOR
Sales-ops and revenue-compliance teams at B2B companies whose reps quote pricing, renewal, data-retention or SLA terms on live calls. The first buyer is whoever owns contract risk today and learns about a bad promise only after the customer brings it up.

Most call-review tools analyze recordings after the call ends. ClauseCatcher differs in two ways: it acts during the call, and it checks the rep against this customer's signed contract, not a generic sales script. Business-model hypothesis (not yet validated with buyers): a per-rep monthly subscription sold to sales-ops. API cost is small next to that; the measured demo call used about $0.12.

WHAT'S NEXT
A hardened browser-mic path, CRM and meeting-platform integration (for example Zoom or Google Meet audio), multi-contract accounts, and a per-seat pricing pilot with a sales team.
```

Word count: about 760. Keep the section headings in caps; lablab's editor may strip Markdown.

### Technology & category tags

Pick from lablab's tag picker. If a tag doesn't exist there, skip it. Don't invent tags. In priority order:

- Technology: `AssemblyAI`, `Gemini`, `FastAPI`, `Python`, `React`, `TypeScript`
- Category: `Voice AI` / `Voice Agents`, `Speech-to-Text`, `Sales`, `Compliance`, `Legal`, `Productivity`

---

## 2. Cover image and presentation

### Cover image

Upload `docs/submission/cover.png`: 1920 x 1080 PNG (16:9), about 0.6 MB. Source: `docs/submission/cover.html`. The official guide says "PNG or JPG" and "Recommended 16:9". It gives no pixel size.

### Video presentation

```
[VIMEO_URL]
```

Rules from the guide: "A maximum 5-minute video in MP4 format. Begin with an introduction, discuss your PDF presentation, then showcase your project's functionalities." Keep the MP4 export at or under 5:00. Script: `docs/submission/DEMO_SCRIPT.md`. If the form wants an upload instead of a link, upload the same MP4.

### Slide presentation

Upload `docs/submission/ClauseCatcher.pdf` (the guide asks for PDF). Outline and speaker notes: `docs/submission/SLIDES.md`. The PDF already says 136 tests (slide 9).

---

## 3. App hosting and repository

### Public GitHub repository

```
https://github.com/ishal1410/clausecatcher
```

### Demo application platform

```
Render
```

(The guide suggests Streamlit, Replit or Vercel. It doesn't require them. The app is a FastAPI + WebSocket server serving the built React UI from one Docker image, so it runs on Render's free Docker web service. See `docs/DEPLOY.md`. If the form only offers those three, pick "Other" if it's there. Don't pick a platform the app isn't actually hosted on.)

### Application URL

```
[APP_URL]
```

Render's free tier sleeps when idle. Open the URL about 1 minute before submitting, and again during judging, so the first judge doesn't hit a cold start.
