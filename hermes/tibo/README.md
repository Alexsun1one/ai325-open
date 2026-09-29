# Tibo public activity + intent observer

The website is `site/public/tibo`, with a homepage/arsenal `PlaygroundSpotlight`.
`GET /api/tibo/status` projects the public snapshot plus validated semantic analysis.

The existing Hermes job `aitibo-x-observer` runs every 30 minutes, delivers locally,
and works under `/data/aitibo`. No social posting, notifications, or account writes.
It collects public @thsottiaux posts, then reasons over context using observer-prompt.txt.
Public search is partial. A statement that a reset completed never confirms a visitor's quota.

## Source and runtime mapping

- `tibo_monitor.py` → `/data/aitibo/monitor/tibo_monitor.py`
- `test_tibo_monitor.py` → same monitor directory
- `../../app/tibo_intent.py` → `/data/aitibo/monitor/tibo_intent.py` (pure stdlib)
- `../../app/tibo_prediction.py` → `/data/aitibo/monitor/tibo_prediction.py`
- `observer-prompt.txt` → `/data/aitibo/ops/hermes-observer-prompt.txt`
- Public data: `/data/aitibo/shared/status.json` + `intent.json`
- ai325 Compose binds that directory read-only at `/tibo-data`.

`scripts/ops/upgrade_tibo_intent.py --staging DIR [--no-trigger]` upgrades only the
existing observer after checking its identity/schedule and a SHA256 manifest.
Stage the five files using runtime basenames (prompt basename
`hermes-observer-prompt.txt`), and `manifest.json` mapping those basenames to SHA256.
It backs up existing owned files, runs monitor tests, edits only this named job's
prompt, and optionally triggers an immediate run. It does not deploy ai325 code.

Analysis must bind to the same successful fetched_at, include the latest post,
use exact excerpts from retained posts, provide all seven locales, and be no older
than 24 hours. Missing, mismatched or invalid analysis is hidden; public facts and
machine interpretation are separate. Interpretation confidence is not a probability
of a future reset. No next-reset countdown is fabricated.

The observer also produces `enrichment.json`: seven-language translations for
the ten displayed posts (cached by exact original text) and a next-reset signal
index. The API adds `post_translations` and `prediction`. The 0–95/100 index is
an editorial evidence score, not a calibrated probability. Weights are explicit
in `app/tibo_prediction.py`; repeated signal categories cannot accumulate points.
Past completions and banked credits cannot count as new reset promises. Weekdays
are resolved against original post dates in Pacific time, not collection time.
Missing/expired analysis has no score. Unchanged translations can survive a new
collection timestamp; changed original wording always invalidates its translation.

Monitor migration only reclassifies formerly AMBIGUOUS_RESET_MENTION records.
Quoted/link/negation categories remain protected because historical snapshots may
no longer retain their raw quote metadata.

Validation:

    python3 -m unittest discover -s hermes/tibo -q
    python3 -m unittest app.test_tibo_status app.test_tibo_intent -q
    node --test site/tests/tibo-live-state.test.cjs site/tests/tibo-intent.test.cjs
    cd site && npm run build

Website deployment must follow committed main → app rebuild/compose → static export
→ preserve prior hashed chunks → two-stage static rsync. Back up the account DB,
image and previous static output first. Never copy individual files into live app/static.

The next-reset index also accepts incident_context (+20) for a verified incident within three days. A later completed reset closes this signal; upcoming model/product launches share launch_context (+15). These are editorial weights, not historical success rates. Public replies and their parent context are checked for vague next-week hints.
