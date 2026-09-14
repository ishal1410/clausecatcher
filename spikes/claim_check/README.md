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
Optional flags: `--limit N` (first N claims only), `--sleep-ms 4500`, `--model gemini-2.5-flash`.

Without a key and without `--fake`, the script exits 2 immediately with no network call.

## Status

Real Gemini accuracy is **UNMEASURED** — no key was configured on this machine when
this spike was built. `--fake` only proves the plumbing (prompt building, schema
validation, clause_id checking, confidence clamping, metrics math) runs end-to-end.
Run the real eval command above once a key exists to get actual numbers.

## Files

- `claim_check.py` — `check_claim(sentence, clauses, *, client=None, model=None)`
- `labeled_claims.json` — 32 labeled sentences against `spikes/harness/fake_contract.json`
- `eval_claim_check.py` — runs the eval, prints a table, writes `out/eval_<timestamp>.json`
- `test_claim_check.py` — offline unittest suite (`python -m unittest test_claim_check`)
