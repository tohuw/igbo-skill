# Igbo dictionary skill

An [Agent Skill](https://code.claude.com/docs/en/skills) that turns your coding
agent into an Igbo translator that actually checks its work.

LLMs have weak built-in Igbo and will happily invent plausible-sounding words.
This skill makes the agent look every word up in the
[Igbo API](https://github.com/nkowaokwu/igbo_api) dataset — 8.2k hand-curated
headwords, 1.7k attested bilingual example sentences, 267k lookup keys, and the
5.3k-character Nsibidi dictionary — and refuse to emit Igbo it has not verified.

> **You:** Translate "Chiamaka, come play your udu!" as a sister would say it, affectionately.

The skill triggers automatically, checks each word against the dictionary, and
shows its work.

## Install

**Claude Code** (plugin):

```
/plugin marketplace add https://github.com/tohuw/igbo-skill
/plugin install igbo-skill@igbo-skill
```

Use the full HTTPS URL, not the `tohuw/igbo-skill` shorthand. The shorthand
clones over SSH, which fails with `Host key verification failed` on any machine
that has never connected to github.com over SSH — a fresh checkout of a public
repo has no reason to have done so.

**Codex CLI**, or any agent that reads the open `SKILL.md` format:

```bash
git clone https://github.com/tohuw/igbo-skill
cp -r igbo-skill/.agents/skills/igbo ~/.agents/skills/igbo   # Codex, user scope
cp -r igbo-skill/.agents/skills/igbo ~/.claude/skills/igbo   # Claude Code, no plugin
```

**Codex also works with no install at all**: clone the repo and open Codex
inside it. Codex scans `.agents/skills` from your working directory up to the
repo root, so it finds the skill in place.

Claude Code does not scan `.agents/skills`, so use the plugin above. The repo
does ship a `.claude/settings.json` declaring itself as a plugin marketplace,
which is the documented way for a project to offer plugins to anyone who trusts
the folder — but that path only engages in an interactive session, and I have
not been able to confirm it end to end. Treat the plugin install as the
supported route.

Requires **Python 3.8+**. Nothing else — no pip install, no API key, no Node.

> The skill is a plain directory at `.agents/skills/igbo`, deliberately not a
> symlink. Git checks symlinks out as ordinary text files on Windows unless
> Developer Mode is on, which would leave a 17-byte file where the skill should
> be — so a clone behaves identically on every platform.

## How the data gets there

On first use the CLI downloads the dictionary files from
`nkowaokwu/igbo_api@master` and compiles them into a local SQLite database
(~19 MB, about two seconds). Every query after that is offline.

**It keeps itself current.** Once the data is more than a week old, the next
query asks GitHub whether `src/dictionaries` has moved and rebuilds only if it
has. The usual cost of being out of date is therefore one HTTP round-trip a
week, not a re-download. Three properties worth knowing:

- **A failed check never fails your query.** Offline or rate-limited, the CLI
  says so on stderr and answers from the data on disk, then retries in six
  hours rather than waiting out another week.
- **It checks once, not once per command.** The due date is stored in the
  database, so a burst of lookups costs a single check.
- **`--repo` builds are left alone.** If you pointed it at a local checkout,
  its freshness is yours to manage.

Tune with `IGBO_SKILL_MAX_AGE_DAYS` (default `7`, `0` disables) or switch it off
entirely with `IGBO_SKILL_NO_AUTO_UPDATE=1`. `igbo.py stats` shows the data's
age and when it was last verified; `igbo.py update` forces a check now.

The database is stored **outside** the skill directory — under
`$CLAUDE_PLUGIN_DATA` when installed as a plugin, otherwise your platform cache
directory (`%LOCALAPPDATA%\igbo-skill` or `~/.cache/igbo-skill`), overridable
with `$IGBO_SKILL_DB`. That way a plugin update doesn't throw the database away.

## The CLI on its own

No agent required:

```bash
python3 .agents/skills/igbo/scripts/igbo.py lookup ùdù                  # Igbo → English
python3 .agents/skills/igbo/scripts/igbo.py en drum                     # English → Igbo
python3 .agents/skills/igbo/scripts/igbo.py search udu                  # substring search
python3 .agents/skills/igbo/scripts/igbo.py examples market             # attested sentences
python3 .agents/skills/igbo/scripts/igbo.py gloss "Òbìàgèlì bì n'Àba"   # per-word gloss
python3 .agents/skills/igbo/scripts/igbo.py nsibidi mud                 # Nsibidi characters
python3 .agents/skills/igbo/scripts/igbo.py stats                       # counts, provenance, age
python3 .agents/skills/igbo/scripts/igbo.py update                      # check upstream now
```

Lookups are diacritic-insensitive, so `lookup udu` finds `ùdù`. Answers give the
tone-marked form from the dictionary.

Working from a local `igbo_api` checkout instead of the network:

```bash
python3 .agents/skills/igbo/scripts/igbo.py build --repo /path/to/igbo_api
python3 .agents/skills/igbo/scripts/igbo.py build --ref some-branch     # or pin a ref
```

## Tests

Stdlib `unittest`, no dependencies. The suite builds the database over the
network the same way a new user does:

```bash
python3 -m unittest discover tests -v
IGBO_SKILL_TEST_REPO=/path/to/igbo_api python3 -m unittest discover tests  # offline
```

## A note on the data

Two things worth knowing before you trust an answer:

- Lines tagged `[normalized index]` are machine-expanded and noisy — they carry
  spurious synonyms. The skill treats them as leads only and confirms against a
  hand-curated entry.
- The dataset leans Onitsha/older-source in places (*house* appears as **ụnò** in
  the rich entries but **ụlọ** in the modern index), so the skill flags dialect
  variation rather than silently picking one.

## Credits

The dictionary data is the work of [Nkọwa okwu](https://nkowaokwu.com) and the
[Igbo API](https://github.com/nkowaokwu/igbo_api) contributors, used under
Apache-2.0. This repo contains no dictionary data of its own — it downloads
theirs at runtime. Support the upstream project; it is the reason any of this
works.

The hosted [igboapi.com](https://igboapi.com) API additionally offers audio
pronunciations and dialect data behind an API key. This skill deliberately
stays offline instead.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
