# Race Radar

A daily-updated page of fast, PB-focused mile to 10K races in London, the South East and the UK's quickest courses. It includes a public **Sources** section where collaborators can see everything the radar checks and suggest additions.

## How it works

```
GitHub Action, 06:00 UTC daily
  1. claude -p prompts/daily.md      research; edits data/radar.json + config/sources.json
  2. scripts/radar.py finalize       validate, drop past races, clash flags, timestamps, diff
  3. tests + commit
  4. scripts/radar.py build          site/index.html + data → dist/ → GitHub Pages
  5. ntfy push with the change list  (optional)
```

Pushing to `main` (for example, after editing sources by hand) only rebuilds and deploys. The agent doesn't run.

| Path | What it is |
|---|---|
| `data/radar.json` | Races on the board. The source of truth. |
| `config/sources.json` | Criteria, suggestion-form link, and every source checked, shown publicly on the page. `howToCheck` is guidance for the agent only and isn't published. |
| `config/profile.json` | Runner PBs and commitments used for clash flags. |
| `prompts/daily.md` | The research agent's instructions. |
| `scripts/radar.py` | `validate`, `finalize`, `build`. Standard library only, Python 3.9+. |
| `site/index.html` | Page template. The data is inlined at build time. |
| `legacy/` | The original Artifact page and the one-off 13 Oct script, kept for reference. |

## Local use

```bash
python3 scripts/radar.py validate
python3 -m unittest discover -s tests
python3 scripts/radar.py build && open dist/index.html
```

## Handling suggestions

1. Collaborators click **Suggest a source** on the page, which opens a Google Form.
2. To show a suggestion publicly while you review it, add it to `config/sources.json` with `"status": "suggested"` (and optionally `"suggestedBy": "Name"`). It appears under "Suggested, under review", and the agent skips it.
3. To approve it, set `group` and change `status` to `"new"`. The next run checks it.

## One-time setup

1. Create a **public** GitHub repo and push this folder to `main`.
2. Go to **Settings → Pages → Source** and choose **GitHub Actions**.
3. Go to **Settings → Secrets and variables → Actions** and add:
   - `ANTHROPIC_API_KEY` (secret, required)
   - `NTFY_TOPIC` (secret, optional): a hard-to-guess topic name. Subscribe to it in the ntfy app for phone pushes.
   - `RADAR_MODEL` (variable, optional): overrides the default `claude-sonnet-5-5`.
4. Create the Google Form and put its link in `suggestFormUrl` in `config/sources.json`. The button stays hidden until you do.
5. Run the workflow once by hand (**Actions → Race Radar → Run workflow**).
6. **Turn off the Cowork scheduled task** so two jobs aren't writing at once, then send club mates the new URL.
