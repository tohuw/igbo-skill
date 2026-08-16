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
/plugin marketplace add tohuw/igbo-skill
/plugin install igbo-skill@igbo-skill
```

**Codex CLI**, or any agent that reads the open `SKILL.md` format:

```bash
git clone https://github.com/tohuw/igbo-skill
cp -r igbo-skill/skills/igbo ~/.agents/skills/igbo     # Codex, user scope
cp -r igbo-skill/skills/igbo ~/.claude/skills/igbo     # Claude Code, no plugin
```

Cloning the repo and opening an agent *inside it* also works with no install
step — `.agents/skills/igbo` and `.claude/skills/igbo` are symlinks to
`skills/igbo`, so both agents discover it at project scope.

Requires **Python 3.8+**. Nothing else — no pip install, no API key, no Node.

## How the data gets there

On first use the CLI downloads the dictionary files from
`nkowaokwu/igbo_api@master` and compiles them into a local SQLite database
(~19 MB, about two seconds). Every query after that is offline.

`igbo.py stats` reports which upstream commit the data came from, and
`igbo.py update` rebuilds only if those files have changed upstream.

The database is stored **outside** the skill directory — under
`$CLAUDE_PLUGIN_DATA` when installed as a plugin, otherwise your platform cache
directory (`%LOCALAPPDATA%\igbo-skill` or `~/.cache/igbo-skill`), overridable
with `$IGBO_SKILL_DB`. That way a plugin update doesn't throw the database away.

## The CLI on its own

No agent required:

```bash
python3 skills/igbo/scripts/igbo.py lookup ùdù                  # Igbo → English
python3 skills/igbo/scripts/igbo.py en drum                     # English → Igbo
python3 skills/igbo/scripts/igbo.py search udu                  # substring search
python3 skills/igbo/scripts/igbo.py examples market             # attested sentences
python3 skills/igbo/scripts/igbo.py gloss "Òbìàgèlì bì n'Àba"   # per-word gloss
python3 skills/igbo/scripts/igbo.py nsibidi mud                 # Nsibidi characters
python3 skills/igbo/scripts/igbo.py stats                       # counts + provenance
python3 skills/igbo/scripts/igbo.py update                      # refresh from upstream
```

Lookups are diacritic-insensitive, so `lookup udu` finds `ùdù`. Answers give the
tone-marked form from the dictionary.

Working from a local `igbo_api` checkout instead of the network:

```bash
python3 skills/igbo/scripts/igbo.py build --repo /path/to/igbo_api
python3 skills/igbo/scripts/igbo.py build --ref some-branch     # or pin a ref
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
