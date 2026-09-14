# ClauseCatcher

Catches a sales rep promising something the contract forbids — live, on the call — and speaks the actual clause back before the deal closes.

**Status: work in progress.** Built for the lablab.ai AssemblyAI Voice Agent Hackathon (deadline Sep 30 2026).

## The problem

Sales reps improvise. What they promise verbally and what the contract actually says can diverge, and nobody's listening for the gap in real time. By the time legal or a customer notices, the call is over and the damage (a broken promise, a compliance exposure) is already made.

## How it works

1. **Listen** — the browser mic streams the rep's audio to the server over a websocket, which forwards it to AssemblyAI Streaming STT v3 (24 kHz) for a live transcript.
2. **Check** — each finished sentence goes to Gemini (free tier) for a claim-check against the uploaded contract's clauses: does this sentence contradict something the contract says?
3. **Alert** — on a contradiction, a separate AssemblyAI Voice Agent session speaks an alert. The clause text in that alert is always quoted verbatim from the contract — never generated or paraphrased by the LLM. A monitor can also ask the agent questions about the contract mid-call ("what does clause 4.2 say") via a `lookup_clause` tool call. At the end of the call, a compliance report lists every clause referenced and every contradiction caught.

## AssemblyAI products used

- **Streaming STT v3** with keyterms, for the always-on rep transcript.
- **Voice Agent API** — `conversation.message` (role `user`) + `reply.create` to trigger a spoken alert on demand, and client-side tool calling (`lookup_clause`) for monitor Q&A.

Gemini (free tier) does the claim-check judgment call; it never writes the words that get spoken back — those come straight from the contract text.

## Local run

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in ASSEMBLYAI_API_KEY and GEMINI_API_KEY
uvicorn server.main:app --reload
```

## Project layout

```
server/     FastAPI backend — websocket audio pipe, claim-check, alert/report routes
web/        browser client (mic capture, live transcript, alert UI)
spikes/     throwaway API experiments that informed the architecture (not part of the app)
docs/adr/   architecture decision records
```

See `docs/adr/0001-voice-architecture.md` for why the design uses two separate connections (transcription vs. voice agent) instead of one.
