# ClauseCatcher: lablab.ai submission checklist

Deadline: **Wed Sep 30 2026, 11:00 AM EDT** (15:00 UTC). Aim to submit by Sep 29 so there's time to fix upload problems.

Sources (read 2026-09-17):
- Event page ("What to submit", judging criteria, rules): https://lablab.ai/ai-hackathons/assemblyai-voice-agent-hackathon
- Field limits and formats: https://lablab.ai/delivering-your-hackathon-solution

Worth knowing from the event page: "5 winners · $1,000 cash + $1,000 in API credits each". No prize is ranked above the others, so the target is a top-5 finish. Judging criteria: Application of Technology, Presentation, Business Value, Originality. Rules: "Submissions must be original and MIT-compliant."

Form text for every field: `docs/submission/LABLAB_SUBMISSION.md`.

## Requirements

| # | Requirement (official wording) | Status | What you do |
|---|---|---|---|
| 1 | Enroll on lablab.ai and join the lablab.ai Discord ("Please register for both in order to participate") | needs user login | On the event page, click **Enroll** at the bottom. Join https://discord.gg/lablabai. |
| 2 | Team of 1-6 people | needs user login | A solo team is fine. After enrolling, create the team from the event dashboard. Only a logged-in account can see the exact button name. |
| 3 | Project title | done | Paste `ClauseCatcher`. |
| 4 | Short description, "up to 255 characters" | done (235 chars) | Paste it from LABLAB_SUBMISSION.md. |
| 5 | Long description, "at least 100 words" | done (~760 words) | Paste the whole code block. If the editor supports headings, turn the CAPS headings into headings. |
| 6 | Technology & category tags | needs user login | Pick from the tag picker, in the priority order in LABLAB_SUBMISSION.md. Only use tags the picker actually offers. |
| 7 | Cover image: "PNG or JPG", "Recommended 16:9" | done | Upload `docs/submission/cover.png` (1920x1080 PNG). |
| 8 | Video presentation: "A maximum 5-minute video in MP4 format" | pending | Record from `DEMO_SCRIPT.md` and export an MP4 of 5:00 or less. Upload it to Vimeo (privacy "Anyone"). Replace `[VIMEO_URL]` with the plain vimeo.com/<id> link. If the form asks for a file, upload the MP4 itself. |
| 9 | Slide presentation, "PDF format" | done (upload pending) | Upload `docs/submission/ClauseCatcher.pdf` (10 pages). Its slide 9 already says 136 tests. The older outline `SLIDES.md` still says 81, which is harmless but stale. |
| 10 | Public GitHub repository | done, but local work isn't pushed | https://github.com/ishal1410/clausecatcher is public (HTTP 200). Several local files aren't pushed yet: `docs/screenshots/`, `cover.png`, `cover.html`, `ClauseCatcher.pdf`, `CHECKLIST.md`, the README and LABLAB_SUBMISSION.md edits, `tools/`, and uncommitted changes in `server/main.py`, `server/tests/test_session_flow.py` and `frontend/src/hooks/useSession.ts`. Review, commit and push them. The README screenshots don't show on GitHub until you do. |
| 11 | Demo application platform | done (text) | Type or pick `Render`. If the picker only offers Streamlit, Replit or Vercel, choose "Other" if it exists. |
| 12 | Application URL ("a link that allows interaction with your prototype") | pending | Deploy using `docs/DEPLOY.md`: Render dashboard, then **New +**, then **Web Service**, connect the GitHub repo, and use Docker from `render.yaml`. Set `ASSEMBLYAI_API_KEY` and `GEMINI_API_KEY` in Render's Environment tab. Open the URL and drive a real alert. Then replace `[APP_URL]`. |
| 13 | "MIT-compliant" submission | **done** | MIT `LICENSE` added at repo root; README License section updated. |
| 14 | Browser-mic live path verified end to end | pending | Not verified yet. Every submission text says so. If you verify it before the deadline, add one measured line to LABLAB_SUBMISSION.md and the README. |
| 15 | Submit | needs user login | On the event dashboard, open your team's project submission form. Paste the fields, upload the cover, video and PDF, and submit. Afterwards, open the public project page and check that every field shows up. |

## Final order of work (with time estimates)

1. Decide on the license and add the MIT LICENSE (#13): 5 min
2. Commit and push the pending work (#10): 10 min
3. Deploy to Render and smoke-test a live alert (#12): 45 min
4. Record, export and upload the video (#8): 2-3 h
5. Skim the slide PDF once before uploading (#9): 5 min
6. Fill in the form and submit (#3-7, #11, #15): 20 min
7. Wake the Render app right before judging: 1 min
