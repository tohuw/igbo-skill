---
name: igbo
description: Igbo dictionary and translation assistant backed by the Igbo API dataset (8k+ rich headwords, 1.7k attested bilingual examples, 267k lookup keys, Nsibidi). Use whenever the user asks to translate to/from Igbo, asks what an Igbo word or phrase means, asks about Igbo grammar/tone/spelling, or mentions Nsibidi script. LLM built-in Igbo knowledge is weak — always consult this dictionary instead of answering from memory.
---

# Igbo dictionary skill

All queries go through one zero-dependency CLI (Python 3 stdlib + SQLite).
Run it from this skill's directory:

```
python3 scripts/igbo.py <command> <query>
```

On first use it downloads the dictionaries from
[nkowaokwu/igbo_api](https://github.com/nkowaokwu/igbo_api) and compiles them
into a local SQLite database (~19 MB, a few seconds). Every run after that is
offline. No API key, no setup.

Once the data passes a week old, the next query checks upstream and rebuilds
only if the dictionaries actually changed — so staleness costs one HTTP
round-trip a week, not a download. If that check fails (offline, rate-limited),
the query is still answered from the data on disk; you'll see a note on stderr.
Nothing you need to manage: `update` is only for forcing it early.

| command | purpose |
|---|---|
| `lookup <igbo>` | Igbo → English, diacritic-insensitive; full entries (word class, definitions, variations, stems, examples) |
| `en <english>` | English → Igbo: reverse-index hit + rich entries whose definitions contain the word |
| `search <substr>` | substring search across Igbo forms |
| `examples <query>` | search the 1.7k attested bilingual sentences (matches either language) |
| `gloss "<igbo sentence>"` | per-chunk gloss, greedy longest phrase match; handles n'/m' elision |
| `nsibidi <query>` | Nsibidi characters by symbol, pronunciation, or meaning |
| `stats` | table counts, which upstream commit the data came from, and its age |
| `report` | environment block to paste into a bug report |
| `update` | check upstream now rather than waiting for the weekly check |
| `build [--repo PATH] [--ref REF]` | force a rebuild; `--repo` reads a local igbo_api checkout instead of the network |

Run several lookups in one shell call (`cmd1; cmd2; ...`) to save round-trips.

## Data trust levels

1. **Rich entries and examples** (from `lookup`, `en`, `examples`) — hand-curated,
   authoritative. Tone-marked. Prefer these always.
2. **`[normalized index]` lines** — machine-expanded, NOISY (spurious synonyms like
   "housefly" under ụlọ). Use only as leads; confirm via a rich entry or example.
3. The dataset leans Onitsha/older-source in places (e.g. house appears as ụnò in
   rich entries, ụlọ in the modern index). Note dialect variation when relevant.

## Translation workflow — non-negotiable discipline

LLMs hallucinate plausible-sounding Igbo. Never emit an Igbo word you have not
verified this session via `lookup`/`en`/`examples`.

**English → Igbo:**
1. `en <word>` each content word; pick candidates from rich entries, noting word class.
2. `lookup` each chosen candidate to confirm the gloss round-trips and to get
   correct diacritics; copy spelling exactly (dot-below vowels and tone marks).
3. `examples <word>` for attested sentences — reuse their constructions as
   translation memory rather than composing syntax from scratch.
4. Assemble using the grammar crib below; state uncertainty honestly when the
   dictionary lacks an attested pattern.

**Igbo → English:**
1. `gloss "<sentence>"` first. For `???` tokens, strip affixes (see crib) and
   `lookup` the stem; verbs are listed with a leading hyphen (`-ri`, `-gba`).
2. `examples <key word>` to check idioms — many multi-word entries are idiomatic.

## When the user says the answer is wrong

Take it seriously and work out *what kind* of wrong it is before doing anything
else. The user is usually a better speaker of Igbo than this dataset is a record
of it. Do not argue, and do not just re-answer with a different guess.

**1. Get specifics.** Which word or sentence, what you said, what it should be,
and how they know (native speaker, their dialect, a teacher, a text).

**2. Reproduce against the dataset.** Re-run the exact lookups and classify:

| what you find | cause | where it goes |
|---|---|---|
| The right answer *is* in a rich entry or example, but your answer did not use it | this skill surfaced or ranked it badly, or `gloss` chunked wrong | `tohuw/igbo-skill` |
| The CLI errored, hung, or printed something malformed | this skill | `tohuw/igbo-skill` |
| The dataset genuinely lacks the word or sense, or records it wrongly | the dictionary data | upstream `nkowaokwu/igbo_api` |
| The dataset differs because it leans Onitsha/older-source | **usually not a bug** | see below |

**Dialect is not automatically an error.** This is one record of a language with
real regional variation. "We don't say it that way" most often means the user's
variety differs from the source — worth saying plainly in your answer, not worth
filing. File upstream only when a sense is genuinely absent, plainly wrong, or
misspelled, and name the variety the correction comes from.

**3. Offer to file it, and make it effortless.** Never file anything without
showing the exact title and body first and getting a clear yes — it goes out
under their name. Then, in this order:

- **`gh` present and authenticated** (`gh auth status` succeeds) — offer to file
  it now. Before filing upstream, resolve the real home with
  `gh repo view <repo> --json isFork,parent`; if it is a fork, file against the
  parent instead. Then `gh issue create --repo <repo> --title ... --body ...`,
  and give them the URL.
- **`gh` present but not authenticated** — hand them `gh auth login` to run
  themselves (it is interactive), or fall back to the file below.
- **`gh` missing** — ask first whether they have a GitHub account. If they do,
  offer to install it (`winget install GitHub.cli`, `brew install gh`, or their
  package manager).
- **No GitHub account** — don't drop it there. Their correction is worth
  preserving, and they may not realise how small the step is: offer to walk them
  through creating one at https://github.com/signup (free, a couple of minutes,
  needs only an email). Say plainly why it's worth it — a filed correction
  reaches every future user of the dictionary, where a comment in a chat window
  does not. If they'd rather not, that is completely fine: write the file below,
  and point them at https://nkowaokwu.com/volunteer where they can raise it with
  the maintainers directly without an account.
- **Anything declined, or no account** — write the report to
  `igbo-feedback-<slug>.md` in the working directory. That file must stand on its
  own: the issue title, the full body ready to paste, the exact URL to open, and
  one line saying what to click. Mention they can also reach the dictionary
  maintainers at https://nkowaokwu.com/volunteer.

**4. Always include** the output of `python3 scripts/igbo.py report`, the exact
command you ran, and its output. For a data report, name the dialect or region.

Declining any of this is completely fine. Say so once and move on.

## Orthography

- Igbo alphabet includes ị ọ ụ (dot below) and ṅ — these are distinct letters, not
  decoration. i/ị, o/ọ, u/ụ distinguish words.
- Tone marks in this dataset: acute = high, grave = low, macron (ō) = downstep.
  Everyday Igbo text usually omits tone marks but keeps dots. When answering, give
  the dictionary's tone-marked form at least once, then the plain-dotted form.
- `n'` is elided `na` (in/at/and) before vowels: `n'ụlọ` = `na ụlọ`.

## Grammar crib

- Word order SVO. No grammatical gender; `ọ/o` = he/she/it.
- Vowel harmony: two sets {i e o u} vs {ị a ọ ụ}; prefixes/suffixes harmonize with
  the stem (e.g. infinitive i-/ị-: iri "to eat", ịsa "to wash").
- Verb tense/aspect: progressive `na-` + participle (ọ na-eri "s/he is eating");
  future `ga-` (ọ ga-eri); past/factative suffix -rV echoing stem vowel (o riri
  "s/he ate"); perfect -la/-le (o riela); negation -ghị (ọ righị).
- Word classes in output: AV=active verb, PV=passive/stative verb, MV=medial verb,
  NNC=noun, ND=nominal modifier, ISUF/ESUF=inflectional/extensional suffix,
  CJN, DEM, PRN, PREP, WH=interrogative, QTF, INTJ, CD=number, FW=foreign word.
  Extensional suffixes (-kwa, -ghị, -la, -pụ...) stack on verb stems — strip them
  when a gloss fails.
- `[common]` flag marks the ~1000 highest-frequency words; prefer them when
  multiple candidates fit.

## Notes

The compiled database lives outside this skill directory (under the platform
cache dir, `$CLAUDE_PLUGIN_DATA` when installed as a plugin, or `$IGBO_SKILL_DB`
if set) so plugin updates do not discard it. Delete it any time to force a clean
rebuild.

`IGBO_SKILL_MAX_AGE_DAYS` changes the staleness threshold (`0` disables the
check); `IGBO_SKILL_NO_AUTO_UPDATE` turns it off outright.

The hosted https://igboapi.com API additionally offers audio pronunciations and
dialect data behind an API key, but this skill is offline by design after the
initial download.
