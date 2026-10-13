#!/usr/bin/env python3
"""Race Radar: deterministic half of the daily job.

The research agent edits data/radar.json (and config/sources.json). This script
does everything that shouldn't depend on judgment:

  validate                 check data + config against the schema
  finalize --prev FILE     after the agent runs: drop past races, bump
                           lastChecked, write a change summary (with clash
                           notes for the owner's notification)
  build [--out DIR]        render site/index.html with the data inlined

Standard library only (Python 3.9+).
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RADAR = ROOT / "data" / "radar.json"
SOURCES = ROOT / "config" / "sources.json"
PROFILE = ROOT / "config" / "profile.json"
TEMPLATE = ROOT / "site" / "index.html"

STATUSES = ("act", "open", "announced", "closed")
STATUS_LABEL = {"act": "Act now", "open": "Open", "announced": "Announced", "closed": "Closed"}
DISTANCES = ("mile", "3k", "5k", "10k", "half")
SOURCE_GROUPS = ("organiser", "course", "listing")
SOURCE_STATUSES = ("listing", "quiet", "new", "suggested")
RACE_FIELDS = ("id", "name", "date", "venue", "distances", "status", "statusText",
               "url", "why", "firstSeen", "updated")
OPTIONAL_RACE_FIELDS = ("waitlistEmail",)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def parse_date(s):
    return dt.date.fromisoformat(s)


def is_date(s):
    if not isinstance(s, str) or not DATE_RE.match(s):
        return False
    try:
        parse_date(s)
        return True
    except ValueError:
        return False


# ---------- validation ----------

def validate_radar(data):
    errs = []
    if not isinstance(data, dict):
        return ["radar.json must be an object"]
    if not isinstance(data.get("lastChecked"), str):
        errs.append("lastChecked must be an ISO timestamp string")
    races = data.get("races")
    if not isinstance(races, list):
        return errs + ["races must be a list"]
    seen = set()
    for i, r in enumerate(races):
        where = "races[%d] (%s)" % (i, r.get("id", "?") if isinstance(r, dict) else "?")
        if not isinstance(r, dict):
            errs.append(where + ": must be an object")
            continue
        for k in RACE_FIELDS:
            if k not in r:
                errs.append("%s: missing %s" % (where, k))
        extra = set(r) - set(RACE_FIELDS) - set(OPTIONAL_RACE_FIELDS)
        if extra:
            errs.append("%s: unknown fields %s" % (where, sorted(extra)))
        rid = r.get("id")
        if not isinstance(rid, str) or not ID_RE.match(rid):
            errs.append(where + ": id must be a lowercase slug")
        elif rid in seen:
            errs.append(where + ": duplicate id")
        seen.add(rid)
        for k in ("date", "firstSeen", "updated"):
            if k in r and not is_date(r[k]):
                errs.append("%s: %s must be YYYY-MM-DD" % (where, k))
        if r.get("status") not in STATUSES:
            errs.append("%s: status must be one of %s" % (where, STATUSES))
        ds = r.get("distances")
        if not isinstance(ds, list) or not ds or any(d not in DISTANCES for d in ds):
            errs.append("%s: distances must be a non-empty subset of %s" % (where, DISTANCES))
        if not str(r.get("url", "")).startswith(("https://", "http://")):
            errs.append(where + ": url must be http(s)")
        for k in ("name", "venue", "statusText", "why"):
            if k in r and (not isinstance(r[k], str) or not r[k].strip()):
                errs.append("%s: %s must be a non-empty string" % (where, k))
        if "waitlistEmail" in r and not (isinstance(r["waitlistEmail"], str) and EMAIL_RE.match(r["waitlistEmail"])):
            errs.append(where + ": waitlistEmail must be an email address")
    return errs


def validate_sources(cfg):
    errs = []
    if not isinstance(cfg.get("suggestFormUrl", ""), str):
        errs.append("suggestFormUrl must be a string")
    keys = [g.get("key") for g in cfg.get("groups", [])]
    if sorted(keys) != sorted(SOURCE_GROUPS):
        errs.append("groups must define exactly %s" % (SOURCE_GROUPS,))
    seen = set()
    for i, s in enumerate(cfg.get("sources", [])):
        where = "sources[%d] (%s)" % (i, s.get("id", "?"))
        sid = s.get("id")
        if not isinstance(sid, str) or not ID_RE.match(sid):
            errs.append(where + ": id must be a lowercase slug")
        elif sid in seen:
            errs.append(where + ": duplicate id")
        seen.add(sid)
        if not s.get("name"):
            errs.append(where + ": missing name")
        if s.get("group") not in SOURCE_GROUPS:
            errs.append("%s: group must be one of %s" % (where, SOURCE_GROUPS))
        if s.get("status") not in SOURCE_STATUSES:
            errs.append("%s: status must be one of %s" % (where, SOURCE_STATUSES))
        if not str(s.get("url", "")).startswith(("https://", "http://")):
            errs.append(where + ": url must be http(s)")
    return errs


def validate_profile(profile):
    errs = []
    for i, c in enumerate(profile.get("commitments", [])):
        if not is_date(c.get("date")) or not c.get("label"):
            errs.append("commitments[%d]: needs a YYYY-MM-DD date and a label" % i)
    if not isinstance(profile.get("clashWindowDays", 7), int):
        errs.append("clashWindowDays must be an integer")
    return errs


# ---------- mechanical rules ----------

def short_date(d):
    return "%d %s" % (d.day, MONTHS[d.month - 1])


def clash_text(race_date, commitments, window):
    """Describe every commitment within `window` days of the race, e.g.
    '7 days after Malaga HM (8 Nov)' or 'Same day as target 5K (29 Nov)'."""
    rd = parse_date(race_date)
    parts = []
    for c in sorted(commitments, key=lambda c: c["date"]):
        cd = parse_date(c["date"])
        delta = (rd - cd).days
        if abs(delta) > window:
            continue
        when = "%s (%s)" % (c["label"], short_date(cd))
        if delta == 0:
            parts.append("Same day as " + when)
        else:
            n = abs(delta)
            unit = "day" if n == 1 else "days"
            parts.append("%d %s %s %s" % (n, unit, "after" if delta > 0 else "before", when))
    return "; ".join(parts)


def finalize(new, prev, profile, today, now_iso):
    """Apply the deterministic update rules. Returns (data, changes)."""
    today_s = today.isoformat()
    prev_by_id = {r["id"]: r for r in prev.get("races", [])}

    races = []
    for r in new.get("races", []):
        if r["date"] < today_s:
            continue
        r = dict(r)
        r.pop("clash", None)
        old = prev_by_id.get(r["id"])
        if old is None:
            r["firstSeen"] = today_s
            r["updated"] = today_s
        else:
            r["firstSeen"] = old["firstSeen"]
            changed = (old["status"], old["statusText"]) != (r["status"], r["statusText"])
            r["updated"] = today_s if changed else old["updated"]
        races.append(r)
    races.sort(key=lambda r: (r["date"], r["id"]))

    out = dict(new)
    out["lastChecked"] = now_iso
    out["races"] = races
    return out, diff(prev, out, today_s, profile)


def diff(prev, new, today_s, profile=None):
    """Human summary: 'Race – date – new status' lines. Clashes with the owner's
    commitments are noted here only: they matter to the owner, not to site visitors."""
    profile = profile or {}
    commitments = profile.get("commitments", [])
    window = profile.get("clashWindowDays", 7)
    prev_by_id = {r["id"]: r for r in prev.get("races", [])}
    new_ids = {r["id"] for r in new.get("races", [])}
    lines = []

    def fmt(r, label):
        line = "%s – %s – %s" % (r["name"], short_date(parse_date(r["date"])), label)
        clash = clash_text(r["date"], commitments, window) if label != "Removed" else ""
        return line + (" ⚠ " + clash if clash else "")

    for r in new.get("races", []):
        old = prev_by_id.get(r["id"])
        if old is None:
            lines.append(fmt(r, "New: %s (%s)" % (STATUS_LABEL[r["status"]], r["statusText"])))
        elif (old["status"], old["statusText"]) != (r["status"], r["statusText"]):
            lines.append(fmt(r, "%s (%s)" % (STATUS_LABEL[r["status"]], r["statusText"])))
    for rid, r in prev_by_id.items():
        if rid not in new_ids and r["date"] >= today_s:
            lines.append(fmt(r, "Removed"))
    return lines


# ---------- build ----------

def embed_json(data):
    # Safe inside <script type="application/json">: no '</' can close the tag.
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def build(out_dir):
    radar, sources = load(RADAR), load(SOURCES)
    public_sources = dict(sources)
    # howToCheck is agent guidance; the page only needs the public fields.
    public_sources["sources"] = [
        {k: v for k, v in s.items() if k != "howToCheck"} for s in sources["sources"]
    ]
    html = TEMPLATE.read_text(encoding="utf-8")
    for token in ("{{RADAR_JSON}}", "{{SOURCES_JSON}}"):
        if token not in html:
            raise SystemExit("template is missing " + token)
    html = html.replace("{{RADAR_JSON}}", embed_json(radar))
    html = html.replace("{{SOURCES_JSON}}", embed_json(public_sources))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "radar.json").write_text(json.dumps(radar, indent=2, ensure_ascii=False), encoding="utf-8")
    return out / "index.html"


# ---------- CLI ----------

def all_errors():
    return (["radar.json: " + e for e in validate_radar(load(RADAR))]
            + ["sources.json: " + e for e in validate_sources(load(SOURCES))]
            + ["profile.json: " + e for e in validate_profile(load(PROFILE))])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    f = sub.add_parser("finalize")
    f.add_argument("--prev", required=True, help="radar.json as it was before the agent ran")
    f.add_argument("--changes", help="write the change summary to this file")
    f.add_argument("--today", help="override today's date (YYYY-MM-DD)")
    b = sub.add_parser("build")
    b.add_argument("--out", default=str(ROOT / "dist"))
    args = p.parse_args(argv)

    if args.cmd == "validate":
        errs = all_errors()
        for e in errs:
            print("✗ " + e, file=sys.stderr)
        if errs:
            return 1
        print("✓ data and config are valid")
        return 0

    if args.cmd == "finalize":
        new, prev = load(RADAR), load(args.prev)
        errs = validate_radar(new)
        if errs:
            for e in errs:
                print("✗ " + e, file=sys.stderr)
            print("Agent output is invalid; restoring previous radar.json.", file=sys.stderr)
            dump(RADAR, prev)
            return 1
        now = dt.datetime.now(dt.timezone.utc)
        today = parse_date(args.today) if args.today else now.date()
        data, changes = finalize(new, prev, load(PROFILE), today, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        dump(RADAR, data)
        summary = "\n".join(changes) if changes else "No changes today."
        if args.changes:
            Path(args.changes).write_text(summary + "\n", encoding="utf-8")
        print(summary)
        return 0

    if args.cmd == "build":
        errs = all_errors()
        if errs:
            for e in errs:
                print("✗ " + e, file=sys.stderr)
            return 1
        print("Built " + str(build(args.out)))
        return 0


if __name__ == "__main__":
    sys.exit(main())
