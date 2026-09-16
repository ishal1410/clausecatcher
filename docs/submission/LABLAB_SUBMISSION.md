# lablab.ai submission: ClauseCatcher

Reference copy of the submission form content. Deadline: Sep 30 2026, 11:00 AM EDT.

## Title options

1. **ClauseCatcher**
2. **ClauseCatcher: Live Contract Compliance for Sales Calls**
3. **ClauseCatcher: Catch the Promise Before the Contract Doesn't**

## Short description (≤255 characters)

> ClauseCatcher listens to live sales calls and speaks the exact contract clause the moment a rep contradicts it: verbatim, in real time, no LLM-generated legal language.

(184 characters)

## Long description

Sales reps improvise. What they say on a call and what the signed contract actually permits can drift apart in a single sentence, and by the time anyone notices, the call is over and the promise is already made. ClauseCatcher is a live compliance guardian that sits on the call and catches that drift while it's still happening.

It listens to the rep's audio continuously through AssemblyAI Streaming STT v3, seeded with keyterms pulled from the uploaded contract so section-specific language transcribes cleanly. Every finished sentence is checked against the contract's clauses by Gemini running on the free tier, which returns only a verdict and a clause ID, never generated text. The moment a sentence contradicts a clause, the AssemblyAI Voice Agent API speaks that clause out loud, using a direct "say this exactly, word for word" instruction rather than feeding it through the agent's own language generation. That distinction is the whole point: the correction a rep hears is the actual contract text, not an LLM's summary of it.

A manager sitting in on the call can ask about any clause by number and get the same verbatim spoken answer. At the end of the call, ClauseCatcher produces a short report listing every clause referenced and every contradiction caught, so the record of the call matches what was actually said.

Two design choices matter for trust. First, clause text is never generated: it's extracted once from the contract PDF and quoted, not paraphrased, every time. Second, when the claim-check step fails or times out, the sentence is marked "unclear," never treated as a contradiction. A tool that falsely accuses a rep is worse than one that occasionally misses something, so ClauseCatcher is built to fail toward silence.

A live end-to-end run on 2026-09-15, with real AssemblyAI connections and a real Gemini claim-check, caught two scripted false claims (a fake automatic discount and a fake 24/7 availability promise), raised no alerts on consistent lines, spoke both corrections back with an exact word-for-word match to the contract, and answered a spoken clause question correctly, all for about $0.12 of API usage.

## Tech / tags

`AssemblyAI` · `Voice Agent API` · `Streaming STT` · `Gemini` · `FastAPI` · `Python` · `React` · `TypeScript` · `Vite` · `Sales Tech` · `Compliance` · `Real-time Audio`

## Judging criteria answers

### Application of Technology

ClauseCatcher uses both halves of the AssemblyAI Voice Agent Hackathon's namesake API for two different, deliberately separated jobs: Streaming STT v3 carries the rep's audio for the whole call with no reply behavior to manage, and the Voice Agent API is opened reactively, only when there's something to say, and instructed to speak a fixed string exactly rather than generate a response. That two-connection split came out of a documented architecture decision (`docs/adr/0001-voice-architecture.md`): a single Voice Agent session handling both listening and speaking was tested live first, and it started unprompted replies over the rep's speech despite an explicit silence instruction. Splitting the two roles across two connections removed that failure mode structurally instead of trying to prompt around it.

### Presentation

The product's single visual and audio payoff, an alert card appearing with the offending phrase underlined in the transcript while the Voice Agent speaks the literal clause back, is designed to be the one thing a judge remembers. The cockpit UI (see `docs/UI_SCREENS_SPEC.md`) keeps that moment uncluttered: a three-pane live-call view with the transcript, the alert stack, and a voice orb that visibly reacts to the agent's own audio.

### Business Value

Sales compliance failures are expensive precisely because nobody catches them until after the call: a rep's verbal promise becomes a customer expectation, and reconciling that against the signed contract after the fact is a support or legal problem instead of a one-sentence correction. ClauseCatcher moves that catch to the moment it happens, live, audibly, with a record attached. It's aimed at compliance and sales-ops teams who currently rely on spot-checking recorded calls after the fact.

### Originality

The mechanism that makes this work, using a direct "say this text exactly" instruction to the Voice Agent instead of injecting content as a fake conversation turn, was found through failed attempts, not assumed. An earlier version tried injecting the alert as a conversation message and the agent ignored it and asked for the alert content again; the literal-instruction approach was what actually produced a verbatim spoken match. The product's core constraint, that an AI-adjacent tool speaking on a live sales call must never say anything the contract doesn't literally say, shaped every part of the pipeline around quoting instead of generating.
