"""End-to-end tests for the Igbo skill CLI.

Stdlib only — run with `python3 -m unittest discover tests`.

The first test class builds the database over the network exactly the way a new
user does, so the whole download-and-compile path is covered rather than mocked.
Set IGBO_SKILL_TEST_REPO=/path/to/igbo_api to build from a local checkout
instead (useful offline).
"""

import os
import subprocess
import sys
import tempfile
import unittest

CLI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "skills", "igbo", "scripts", "igbo.py")

_TMP = tempfile.mkdtemp(prefix="igbo-skill-test-")
DB = os.path.join(_TMP, "igbo.db")


def run_cli(*args):
    env = dict(os.environ, IGBO_SKILL_DB=DB, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, CLI, *args],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=300,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"igbo.py {' '.join(args)} exited {proc.returncode}\n{proc.stderr}")
    return proc.stdout


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


if __name__ == "__main__":
    unittest.main()
