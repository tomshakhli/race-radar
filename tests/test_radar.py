import copy
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import radar  # noqa: E402

PROFILE = {
    "clashWindowDays": 7,
    "commitments": [
        {"date": "2026-11-08", "label": "Malaga HM"},
        {"date": "2026-11-29", "label": "target 5K"},
    ],
}


def race(**kw):
    r = {
        "id": "test-5k-2026", "name": "Test 5K", "date": "2026-12-20", "venue": "Somewhere",
        "distances": ["5k"], "status": "open", "statusText": "Entries open",
        "url": "https://example.com", "why": "Fast.",
        "firstSeen": "2026-10-01", "updated": "2026-10-01",
    }
    r.update(kw)
    return r


class RepoData(unittest.TestCase):
    def test_committed_data_and_config_are_valid(self):
        self.assertEqual(radar.all_errors(), [])


class Validate(unittest.TestCase):
    def test_good_race_passes(self):
        self.assertEqual(radar.validate_radar({"lastChecked": "x", "races": [race()]}), [])

    def test_catches_bad_fields(self):
        bad = race(status="maybe", distances=["marathon"], date="1 Dec", url="ftp://x")
        errs = " ".join(radar.validate_radar({"lastChecked": "x", "races": [bad]}))
        for word in ("status", "distances", "date", "url"):
            self.assertIn(word, errs)

    def test_catches_duplicates_and_missing_fields(self):
        r = race()
        del r["why"]
        errs = radar.validate_radar({"lastChecked": "x", "races": [r, race()]})
        self.assertTrue(any("missing why" in e for e in errs))
        self.assertTrue(any("duplicate id" in e for e in errs))

    def test_half_marathon_and_contact_email(self):
        ok = race(distances=["half"], contactEmail="entries@example.com", contactLabel="Waitlist")
        self.assertEqual(radar.validate_radar({"lastChecked": "x", "races": [ok]}), [])
        bad = race(contactEmail="not-an-email")
        errs = radar.validate_radar({"lastChecked": "x", "races": [bad]})
        self.assertTrue(any("contactEmail" in e for e in errs))
        orphan = race(contactLabel="Waitlist")
        errs = radar.validate_radar({"lastChecked": "x", "races": [orphan]})
        self.assertTrue(any("needs a contactEmail" in e for e in errs))

    def test_rejects_unknown_fields(self):
        errs = radar.validate_radar({"lastChecked": "x", "races": [race(extra=1)]})
        self.assertTrue(any("unknown fields" in e for e in errs))


class Clash(unittest.TestCase):
    def c(self, date):
        return radar.clash_text(date, PROFILE["commitments"], 7)

    def test_matches_handoff_wording(self):
        self.assertEqual(self.c("2026-11-15"), "7 days after Malaga HM (8 Nov)")
        self.assertEqual(self.c("2026-11-29"), "Same day as target 5K (29 Nov)")
        self.assertEqual(self.c("2026-11-27"), "2 days before target 5K (29 Nov)")
        self.assertEqual(self.c("2026-11-28"), "1 day before target 5K (29 Nov)")

    def test_outside_window(self):
        self.assertEqual(self.c("2026-11-16"), "")
        self.assertEqual(self.c("2026-10-31"), "")

    def test_multiple_commitments(self):
        commitments = [{"date": "2026-11-08", "label": "A"}, {"date": "2026-11-10", "label": "B"}]
        self.assertEqual(radar.clash_text("2026-11-09", commitments, 7),
                         "1 day after A (8 Nov); 1 day before B (10 Nov)")


class Finalize(unittest.TestCase):
    TODAY = dt.date(2026, 10, 20)

    def run_finalize(self, prev_races, new_races):
        prev = {"lastChecked": "old", "races": prev_races}
        new = {"lastChecked": "old", "races": copy.deepcopy(new_races)}
        return radar.finalize(new, prev, PROFILE, self.TODAY, "2026-10-20T06:00:00Z")

    def test_drops_past_races_and_sets_last_checked(self):
        data, _ = self.run_finalize([], [race(id="past", date="2026-10-19"), race(date="2026-10-20")])
        self.assertEqual([r["id"] for r in data["races"]], ["test-5k-2026"])
        self.assertEqual(data["lastChecked"], "2026-10-20T06:00:00Z")

    def test_new_race_gets_today_stamps(self):
        data, changes = self.run_finalize([], [race(firstSeen="2020-01-01", updated="2020-01-01")])
        r = data["races"][0]
        self.assertEqual((r["firstSeen"], r["updated"]), ("2026-10-20", "2026-10-20"))
        self.assertEqual(changes, ["Test 5K – 20 Dec – New: Open (Entries open)"])

    def test_status_change_bumps_updated_and_keeps_first_seen(self):
        old = race()
        data, changes = self.run_finalize([old], [race(status="closed", statusText="Sold out", firstSeen="2026-10-20")])
        r = data["races"][0]
        self.assertEqual(r["updated"], "2026-10-20")
        self.assertEqual(r["firstSeen"], "2026-10-01")
        self.assertEqual(changes, ["Test 5K – 20 Dec – Closed (Sold out)"])

    def test_unchanged_race_is_untouched(self):
        old = race()
        data, changes = self.run_finalize([old], [race(why="Reworded.", updated="2026-10-20")])
        self.assertEqual(data["races"][0]["updated"], "2026-10-01")
        self.assertEqual(changes, [])

    def test_clash_stays_off_the_site_but_is_in_the_notification(self):
        data, changes = self.run_finalize([], [race(date="2026-11-15", clash="old field")])
        self.assertNotIn("clash", data["races"][0])
        self.assertEqual(changes, ["Test 5K – 15 Nov – New: Open (Entries open) ⚠ 7 days after Malaga HM (8 Nov)"])

    def test_removed_future_race_is_reported(self):
        _, changes = self.run_finalize([race()], [])
        self.assertEqual(changes, ["Test 5K – 20 Dec – Removed"])

    def test_past_race_drop_is_not_reported(self):
        _, changes = self.run_finalize([race(date="2026-10-18")], [])
        self.assertEqual(changes, [])


class PageEmails(unittest.TestCase):
    def test_decodes_cloudflare_protected_and_mailto_addresses(self):
        import page_emails
        # "ben@example.com" encoded with key 0x42, as Cloudflare does it.
        enc = "42" + "".join("%02x" % (ord(c) ^ 0x42) for c in "ben@example.com")
        raw = ('<p>Contact Ben <a href="/cdn-cgi/l/email-protection" class="__cf_email__" '
               'data-cfemail="%s">[email&#160;protected]</a> to join the waiting list.</p>'
               '<p>Info: <a href="mailto:info@example.org">email us</a></p>' % enc)
        found = dict(page_emails.page_emails(raw))
        self.assertEqual(set(found), {"ben@example.com", "info@example.org"})
        self.assertIn("waiting list", found["ben@example.com"][0])


class Build(unittest.TestCase):
    def test_build_inlines_data_safely(self):
        with tempfile.TemporaryDirectory() as d:
            out = radar.build(d).read_text(encoding="utf-8")
        self.assertNotIn("{{RADAR_JSON}}", out)
        self.assertNotIn("{{SOURCES_JSON}}", out)
        self.assertNotIn("howToCheck", out)
        self.assertTrue(out.startswith("<!doctype html>"))

    def test_embed_escapes_script_close(self):
        self.assertNotIn("</", radar.embed_json({"x": "</script>"}))


if __name__ == "__main__":
    unittest.main()
