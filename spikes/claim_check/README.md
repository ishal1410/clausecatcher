# claim_check spike (Option B)

Given one finalized rep sentence + the contract clauses, decide if it contradicts a
clause. Clause text shown to users always comes from `fake_contract.json` by
`clause_id` — the LLM never gets to author clause wording, only pick a verdict.

## Get a free Gemini API key (no card required)

1. Go to https://aistudio.google.com/apikey
2. Sign in with a Google account, click "Create API key" — free tier, no billing setup.
3. Set it as a user env var (same pattern as `ASSEMBLYAI_API_KEY`), e.g. PowerShell:
   ```powershell
   setx GEMINI_API_KEY "your-key-here"
   ```
   then open a new shell. `GOOGLE_API_KEY` also works.

## Run the eval

Offline plumbing check (no key, no network):
```
python eval_claim_check.py --fake
```

Real eval once a key is set (defaults to 4500ms between calls to stay well under
free-tier rate limits — see comment in `eval_claim_check.py`):
```
python eval_claim_check.py
```
Optional flags: `--limit N` (first N claims only), `--sleep-ms 4500`, `--model <model-id>`.
A full 32-claim run takes about 4 minutes, almost all of it the pacing sleep.

Without a key and without `--fake`, the script exits 2 immediately with no network call.

## Status

**Measured 2026-09-18 on `gemini-3.5-flash-lite`** (the model the server ships with),
all 32 labeled claims, free tier: 14/14 contradictions caught with the correct clause
ID, 0 false alarms on the 18 non-contradictions, 0 errors, latency p50 3461 ms / p95
3995 ms. Full run: `docs/evidence/claim_check_eval_20260918.json`; confusion matrix and
caveats: `docs/evidence/README.md`.

The caveat that matters: all 32 sentences were written by the same author against the
same four-clause demo contract, so a perfect score here is the checker passing on its
own fixture. It says nothing about an unseen contract.

Before that run, two constants here were stale against the live API and were corrected
to match `server/claim_check.py`: the model default (`gemini-2.5-flash` now 404s as "no
longer available to new users") and `TIMEOUT_MS` (8000 ms, below Gemini's 10 s minimum
deadline). `--fake` still runs offline and only proves the plumbing.

## Files

- `claim_check.py` — `check_claim(sentence, clauses, *, client=None, model=None)`
- `labeled_claims.json` — 32 labeled sentences against `spikes/harness/fake_contract.json`
- `eval_claim_check.py` — runs the eval, prints a table, writes `out/eval_<timestamp>.json`
- `test_claim_check.py` — offline unittest suite (`python -m unittest test_claim_check`)
