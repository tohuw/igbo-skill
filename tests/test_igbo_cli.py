"""End-to-end tests for the Igbo skill CLI.

Stdlib only — run with `python3 -m unittest discover tests`.

The first test class builds the database over the network exactly the way a new
user does, so the whole download-and-compile path is covered rather than mocked.
Set IGBO_SKILL_TEST_REPO=/path/to/igbo_api to build from a local checkout
instead (useful offline).
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

CLI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   ".agents", "skills", "igbo", "scripts", "igbo.py")

_TMP = tempfile.mkdtemp(prefix="igbo-skill-test-")
DB = os.path.join(_TMP, "igbo.db")


def run_cli(*args, **overrides):
    """Run the CLI. Keyword args become environment overrides; the age check is
    off by default so ordinary tests never touch the network."""
    env = dict(os.environ, IGBO_SKILL_DB=DB, PYTHONIOENCODING="utf-8",
               IGBO_SKILL_NO_AUTO_UPDATE="1")
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    proc = subprocess.run(
        [sys.executable, CLI, *args],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=300,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"igbo.py {' '.join(args)} exited {proc.returncode}\n{proc.stderr}")
    return proc.stdout + proc.stderr


def meta(key, db=DB):
    # Note: `with sqlite3.connect(...)` commits but does not close, and an open
    # handle stops Windows deleting the file. Close explicitly.
    conn = sqlite3.connect(db)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def set_meta(key, value, db=DB):
    conn = sqlite3.connect(db)
    try:
        conn.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, str(value)))
        conn.commit()
    finally:
        conn.close()


def parse_stats(output):
    stats = {}
    for line in output.strip().splitlines():
        key, _, value = line.partition(": ")
        stats[key] = value
    return stats


class IgboCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Force a clean compile so the tests cover the auto-build path.
        if os.path.exists(DB):
            os.remove(DB)
        local = os.environ.get("IGBO_SKILL_TEST_REPO")
        if local:
            run_cli("build", "--repo", local)
        else:
            run_cli("stats")  # triggers the download-and-compile path

    def test_builds_database_with_all_tables_populated(self):
        stats = parse_stats(run_cli("stats"))
        self.assertGreater(int(stats["entries"]), 8000)
        self.assertGreater(int(stats["examples"]), 1500)
        self.assertGreater(int(stats["ig2en"]), 50000)
        self.assertGreater(int(stats["en2ig"]), 200000)
        self.assertGreater(int(stats["nsibidi"]), 5000)

    def test_stats_records_data_provenance(self):
        stats = parse_stats(run_cli("stats"))
        self.assertIn("source", stats)
        if not os.environ.get("IGBO_SKILL_TEST_REPO"):
            self.assertEqual(stats["source"], "nkowaokwu/igbo_api@master")
            self.assertRegex(stats["sha"], r"^[0-9a-f]{40}$")

    def test_lookup_with_full_diacritics(self):
        self.assertIn("earthenware pot", run_cli("lookup", "ùdù"))

    def test_lookup_is_diacritic_insensitive(self):
        self.assertIn("earthenware pot", run_cli("lookup", "udu"))

    def test_lookup_emits_dot_below_vowels_without_encoding_error(self):
        # Regression: Windows defaults stdout to cp1252, which cannot encode ụ
        # (U+1EE5) and aborted the CLI mid-answer.
        self.assertIn("ụ", run_cli("lookup", "ụlọ"))

    def test_en_finds_igbo_candidates(self):
        output = run_cli("en", "drum")
        self.assertIn("igba", output)
        self.assertIn("egwu", output)

    def test_search_matches_substrings(self):
        self.assertIn("udu", run_cli("search", "udu").lower())

    def test_gloss_expands_the_elided_n_to_na(self):
        output = run_cli("gloss", "Òbìàgèlì bì n'Àba")
        self.assertIn("na  ->", output)
        self.assertIn("Àba", output)

    def test_examples_search_matches_either_language(self):
        self.assertIn("afịa", run_cli("examples", "market"))

    def test_nsibidi_lookup_by_meaning(self):
        self.assertIn("ápị̀tị́", run_cli("nsibidi", "mud"))

    def test_report_carries_what_a_bug_report_needs(self):
        out = run_cli("report")
        # A report without the data commit is unactionable: the same query
        # returns different answers across upstream revisions.
        self.assertRegex(out, r"skill version: \d{4}\.\d{2}\.\d{2}")
        self.assertIn("data source:", out)
        self.assertRegex(out, r"data commit:\s+([0-9a-f]{40}|unknown)")
        self.assertIn("data age:", out)
        self.assertIn("table counts:", out)
        self.assertIn("python:", out)

    def test_report_version_matches_the_plugin_manifest(self):
        # The version is duplicated in igbo.py because the skill directory is
        # often copied without the manifest. Keep the two honest.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, ".claude-plugin", "plugin.json"),
                  encoding="utf-8") as f:
            manifest = json.load(f)
        reported = [l.split(": ", 1)[1].strip()
                    for l in run_cli("report").splitlines()
                    if l.startswith("skill version:")][0]
        self.assertEqual(reported, manifest["version"])

    def test_unknown_command_fails_loudly(self):
        with self.assertRaises(AssertionError):
            run_cli("frobnicate")

    def test_help_runs_without_a_database(self):
        env = dict(os.environ, IGBO_SKILL_DB=os.path.join(_TMP, "absent.db"))
        proc = subprocess.run(
            [sys.executable, CLI, "--help"],
            capture_output=True, text=True, encoding="utf-8", env=env, timeout=60,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("igbo.py lookup", proc.stdout)
        self.assertFalse(os.path.exists(os.path.join(_TMP, "absent.db")))


# A repo slug that resolves to a 404 from the GitHub API, so the "cannot reach
# upstream" path is exercised deterministically instead of by pulling the plug.
UNREACHABLE = "tohuw/igbo-skill-no-such-repo-a1b2c3"

DAY = 86400


class AutoUpdateTest(unittest.TestCase):
    """The age check in front of every query."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(DB):
            run_cli("stats")

    def setUp(self):
        self._saved = meta("next_check")

    def tearDown(self):
        if self._saved is not None:
            set_meta("next_check", self._saved)

    def test_build_stamps_age_and_a_due_date(self):
        built_at = float(meta("built_at"))
        self.assertLess(abs(time.time() - built_at), 1800)
        due = float(self._saved)
        self.assertAlmostEqual(due - built_at, 7 * DAY, delta=120)

    def test_stats_reports_age(self):
        self.assertRegex(run_cli("stats"), r"age: \d+\.\d days")

    def test_fresh_data_is_not_checked_against_upstream(self):
        set_meta("next_check", time.time() + 7 * DAY)
        output = run_cli("lookup", "udu",
                         IGBO_SKILL_NO_AUTO_UPDATE=None,
                         IGBO_SKILL_UPSTREAM=UNREACHABLE)
        self.assertNotIn("checking", output)
        self.assertIn("earthenware pot", output)

    def test_data_older_than_a_week_checks_upstream(self):
        built = time.time() - 9 * DAY
        set_meta("built_at", built)
        set_meta("next_check", time.time() - 1)
        try:
            output = run_cli("lookup", "udu", IGBO_SKILL_NO_AUTO_UPDATE=None)
            self.assertIn("9 days old", output)
            self.assertIn("earthenware pot", output)  # answered regardless
            # Having checked, it should not check again for another week.
            self.assertGreater(float(meta("next_check")), time.time() + 6 * DAY)
            # Old data confirmed current is recorded separately from its age,
            # so `stats` can say "9 days old, verified today".
            self.assertLess(time.time() - float(meta("verified_at")), 300)
            stats = run_cli("stats")
            self.assertIn("age: 9.0 days", stats)
            self.assertIn("verified against upstream: 0.0 days ago", stats)
        finally:
            set_meta("built_at", built)

    def test_stale_data_still_answers_when_upstream_is_unreachable(self):
        set_meta("next_check", time.time() - 1)
        output = run_cli("lookup", "udu",
                         IGBO_SKILL_NO_AUTO_UPDATE=None,
                         IGBO_SKILL_UPSTREAM=UNREACHABLE)
        self.assertIn("continuing with the data on disk", output)
        self.assertIn("earthenware pot", output)
        # Backs off hours, not a full week, so a transient outage self-heals.
        due = float(meta("next_check")) - time.time()
        self.assertGreater(due, 3600)
        self.assertLess(due, DAY)

    def test_age_check_can_be_disabled(self):
        set_meta("next_check", 0)
        run_cli("lookup", "udu", IGBO_SKILL_UPSTREAM=UNREACHABLE)
        self.assertEqual(float(meta("next_check")), 0)

    def test_max_age_of_zero_disables_the_check(self):
        set_meta("next_check", 0)
        run_cli("lookup", "udu",
                IGBO_SKILL_NO_AUTO_UPDATE=None,
                IGBO_SKILL_MAX_AGE_DAYS="0",
                IGBO_SKILL_UPSTREAM=UNREACHABLE)
        self.assertEqual(float(meta("next_check")), 0)

    def test_local_builds_are_never_auto_refreshed(self):
        saved_source = meta("source")
        try:
            set_meta("source", "local:/somewhere/igbo_api")
            set_meta("next_check", 0)
            output = run_cli("lookup", "udu",
                             IGBO_SKILL_NO_AUTO_UPDATE=None,
                             IGBO_SKILL_UPSTREAM=UNREACHABLE)
            self.assertNotIn("checking", output)
            self.assertEqual(float(meta("next_check")), 0)
        finally:
            set_meta("source", saved_source)


if __name__ == "__main__":
    unittest.main()
