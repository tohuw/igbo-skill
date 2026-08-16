#!/usr/bin/env python3
"""Igbo dictionary CLI backed by the Igbo API dataset (github.com/nkowaokwu/igbo_api).

Data: 8.2k rich headwords (word class, definitions, variations, stems),
~1.7k attested bilingual example sentences, 55k normalized Igbo->English
keys (incl. phrases), 212k English->Igbo reverse index, Nsibidi dictionary.

On first use the dictionaries are downloaded from the upstream repo and
compiled into a local SQLite database; every later run is offline.

Usage:
  igbo.py lookup <igbo word/phrase>   full entries, diacritic-insensitive
  igbo.py en <english word/phrase>    English -> Igbo candidates
  igbo.py search <substring>          substring search across Igbo forms
  igbo.py examples <query>            search attested example sentences
  igbo.py gloss "<igbo sentence>"     per-chunk gloss (greedy longest match)
  igbo.py nsibidi <query>             Nsibidi characters by symbol/pron/meaning
  igbo.py stats                       table counts and dataset provenance
  igbo.py update                      rebuild if upstream dictionaries changed
  igbo.py build [--repo PATH] [--ref REF]
                                      (re)compile the database; --repo reads a
                                      local igbo_api checkout instead of the
                                      network, --ref picks a branch/tag/commit

Environment:
  IGBO_SKILL_DB    override the database path
  CLAUDE_PLUGIN_DATA  used automatically when running as a Claude Code plugin
"""

import json
import os
import re
import sqlite3
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Igbo needs dot-below vowels (ị ọ ụ) and tone marks. Windows still defaults the
# console to cp1252, which cannot encode them and would abort mid-answer, so
# pin both streams to UTF-8 before anything is written.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (ValueError, OSError):  # already detached or not a text stream
            pass

UPSTREAM = "nkowaokwu/igbo_api"
DICT_PATH = "src/dictionaries"
DEFAULT_REF = "master"

SOURCES = [
    "ig-en/ig-en_expanded.json",
    "ig-en/ig-en_normalized_expanded.json",
    "en-ig/en-ig_normalized_expanded.json",
    "ig-en/ig-en_1000_common.json",
    "nsibidi/nsibidi_dictionary.ts",
]

TABLES = ("entries", "ig2en", "en2ig", "examples", "nsibidi")


def db_path():
    """Where the compiled database lives.

    Deliberately outside the skill directory: a Claude Code plugin is installed
    into a per-version cache directory, so a DB stored next to the script would
    be thrown away (and re-downloaded) on every plugin update.
    """
    explicit = os.environ.get("IGBO_SKILL_DB")
    if explicit:
        return explicit
    plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if plugin_data:
        return os.path.join(plugin_data, "igbo.db")
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "igbo-skill", "igbo.db")


DB_PATH = db_path()

WORD_CLASSES = {
    "ADJ": "adjective", "ADV": "adverb", "AV": "active verb",
    "MV": "medial verb", "PV": "passive/stative verb", "CJN": "conjunction",
    "DEM": "demonstrative", "NM": "name", "NNC": "noun",
    "ND": "nominal modifier", "NNP": "proper noun", "CD": "number",
    "PREP": "preposition", "PRN": "pronoun", "FW": "foreign word",
    "QTF": "quantifier", "WH": "interrogative", "INTJ": "interjection",
    "ISUF": "inflectional suffix", "ESUF": "extensional suffix",
    "SYM": "punctuation",
}


def norm(s):
    """Lowercase and strip all diacritics (tone marks AND dot-below), so
    lookups work regardless of how carefully the input was typed."""
    s = unicodedata.normalize("NFD", s.lower().strip())
    return "".join(c for c in s if not unicodedata.combining(c))


# ---------------------------------------------------------------- fetching

def _get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "igbo-skill"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    return data if binary else data.decode("utf-8")


def upstream_sha(ref=DEFAULT_REF):
    """Newest commit touching src/dictionaries upstream, or None if the GitHub
    API is unreachable or rate-limited (unauthenticated: 60 requests/hour)."""
    url = (f"https://api.github.com/repos/{UPSTREAM}/commits"
           f"?path={DICT_PATH}&sha={ref}&per_page=1")
    try:
        commits = json.loads(_get(url))
    except (urllib.error.URLError, ValueError, TimeoutError):
        return None
    return commits[0]["sha"] if commits else None


def fetch_sources(dest, ref=DEFAULT_REF):
    """Download the dictionary files into dest, mirroring their layout."""
    base = f"https://raw.githubusercontent.com/{UPSTREAM}/{ref}/{DICT_PATH}"
    for rel in SOURCES:
        out = os.path.join(dest, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        print(f"  fetching {rel}", file=sys.stderr)
        try:
            blob = _get(f"{base}/{rel}", binary=True)
        except urllib.error.URLError as e:
            sys.exit(f"error: could not download {rel} from {UPSTREAM}@{ref}: {e}\n"
                     "       (offline? use: igbo.py build --repo /path/to/igbo_api)")
        with open(out, "wb") as f:
            f.write(blob)
    return dest


# ---------------------------------------------------------------- build

def build(repo=None, ref=DEFAULT_REF):
    """Compile the SQLite DB, either from a local checkout or from upstream."""
    tmp = None
    if repo:
        dic = os.path.join(repo, "src", "dictionaries")
        if not os.path.isdir(dic):
            sys.exit(f"error: {dic} not found (is --repo an igbo_api checkout?)")
        source = f"local:{os.path.abspath(repo)}"
        sha = None
    else:
        print(f"(downloading dictionaries from {UPSTREAM}@{ref} — one-time step)",
              file=sys.stderr)
        tmp = tempfile.mkdtemp(prefix="igbo-skill-")
        dic = fetch_sources(tmp, ref)
        source = f"{UPSTREAM}@{ref}"
        sha = upstream_sha(ref)

    try:
        _compile(dic, source, sha)
    finally:
        if tmp:
            _rmtree(tmp)


def _rmtree(path):
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(path)


def _compile(dic, source, sha):
    def load(rel):
        with open(os.path.join(dic, rel.replace("/", os.sep)), encoding="utf-8") as f:
            return json.load(f)

    expanded = load("ig-en/ig-en_expanded.json")
    ig2en = load("ig-en/ig-en_normalized_expanded.json")
    en2ig = load("en-ig/en-ig_normalized_expanded.json")
    common = load("ig-en/ig-en_1000_common.json")

    # nsibidi_dictionary.ts is `export default [...]` of plain object literals
    nsibidi_path = os.path.join(dic, "nsibidi", "nsibidi_dictionary.ts")
    with open(nsibidi_path, encoding="utf-8") as f:
        ts = f.read()
    body = ts[ts.index("export default") + len("export default"):].strip().rstrip(";")
    nsibidi = parse_ts_array(body)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE entries(word TEXT, word_norm TEXT, word_class TEXT,
            definitions TEXT, variations TEXT, stems TEXT, examples TEXT,
            is_common INTEGER);
        CREATE TABLE ig2en(key TEXT, key_norm TEXT, defs TEXT);
        CREATE TABLE en2ig(en TEXT, ig TEXT);
        CREATE TABLE examples(igbo TEXT, igbo_norm TEXT, english TEXT,
            english_lower TEXT, headword TEXT);
        CREATE TABLE nsibidi(sym TEXT, pro TEXT, pro_norm TEXT, form TEXT, defs TEXT);
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
        """
    )

    common_norm = {norm(k) for k in common}
    for word, terms in expanded.items():
        for t in terms:
            db.execute(
                "INSERT INTO entries VALUES(?,?,?,?,?,?,?,?)",
                (
                    word,
                    norm(word),
                    t.get("wordClass") or "",
                    json.dumps(t.get("definitions") or [], ensure_ascii=False),
                    json.dumps(t.get("variations") or [], ensure_ascii=False),
                    json.dumps(t.get("stems") or [], ensure_ascii=False),
                    json.dumps(t.get("examples") or [], ensure_ascii=False),
                    1 if norm(word) in common_norm else 0,
                ),
            )
            for ex in t.get("examples") or []:
                ig, en = ex.get("igbo", ""), ex.get("english", "")
                if ig and en:
                    db.execute(
                        "INSERT INTO examples VALUES(?,?,?,?,?)",
                        (ig, norm(ig), en, en.lower(), word),
                    )

    for key, defs in ig2en.items():
        if isinstance(defs, str):
            defs = [defs]
        db.execute("INSERT INTO ig2en VALUES(?,?,?)",
                   (key, norm(key), json.dumps(defs, ensure_ascii=False)))

    for en, ig in en2ig.items():
        if isinstance(ig, str):
            ig = [ig]
        db.execute("INSERT INTO en2ig VALUES(?,?)",
                   (en.lower(), json.dumps(ig, ensure_ascii=False)))

    for ch in nsibidi:
        db.execute(
            "INSERT INTO nsibidi VALUES(?,?,?,?,?)",
            (ch.get("sym") or "", ch.get("pro") or "",
             norm(ch.get("pro") or ""), ch.get("form") or "", ch.get("defs") or ""),
        )

    for k, v in (("source", source), ("sha", sha or "")):
        db.execute("INSERT INTO meta VALUES(?,?)", (k, v))

    db.executescript(
        """
        CREATE INDEX idx_entries_norm ON entries(word_norm);
        CREATE INDEX idx_ig2en_norm ON ig2en(key_norm);
        CREATE INDEX idx_en2ig ON en2ig(en);
        CREATE INDEX idx_examples_norm ON examples(igbo_norm);
        """
    )
    db.commit()
    counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    db.close()
    size = os.path.getsize(DB_PATH) / 1e6
    print(f"built {DB_PATH} ({size:.1f} MB) from {source}: " +
          ", ".join(f"{k}={v}" for k, v in counts.items()), file=sys.stderr)


def parse_ts_array(body):
    """Parse the nsibidi TS array of flat object literals (sym/pro/form/defs,
    single-quoted strings or null) without needing node."""
    items = []
    for obj in re.finditer(r"\{(.*?)\}", body, re.S):
        item = {}
        for m in re.finditer(r"(\w+):\s*(?:'((?:[^'\\]|\\.)*)'|null)", obj.group(1)):
            val = m.group(2)
            item[m.group(1)] = val.replace("\\'", "'") if val is not None else None
        if item:
            items.append(item)
    return items


# ---------------------------------------------------------------- queries

def connect():
    """Open the DB, downloading and compiling it first if it does not exist."""
    if not os.path.exists(DB_PATH):
        build()
    return sqlite3.connect(DB_PATH)


def meta_get(db, key):
    try:
        row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def like(s):
    return "%" + s.replace("%", "").replace("_", " ") + "%"


def print_entry(word, wc, defs, variations, stems, examples, is_common):
    wc_label = WORD_CLASSES.get(wc, wc) if wc else "?"
    flags = " [common]" if is_common else ""
    print(f"{word}  ({wc or '?'} = {wc_label}){flags}")
    for d in json.loads(defs):
        print(f"  - {d}")
    v = json.loads(variations)
    if v:
        print(f"  variations: {', '.join(v)}")
    s = json.loads(stems)
    if s:
        print(f"  stems: {', '.join(s)}")
    for ex in json.loads(examples):
        print(f"  ex: {ex.get('igbo', '')}  =  {ex.get('english', '')}")


def cmd_lookup(db, query, limit=25):
    q = norm(query)
    rows = db.execute(
        "SELECT word, word_class, definitions, variations, stems, examples, is_common"
        " FROM entries WHERE word_norm = ? ORDER BY is_common DESC LIMIT ?",
        (q, limit)).fetchall()
    for r in rows:
        print_entry(*r)
    # normalized index catches phrases and forms missing from the rich entries
    extra = db.execute(
        "SELECT key, defs FROM ig2en WHERE key_norm = ? LIMIT ?", (q, limit)).fetchall()
    for key, defs in extra:
        print(f"{key}  ->  {'; '.join(json.loads(defs)[:15])}  [normalized index]")
    if not rows and not extra:
        print(f"no exact match for {query!r}; trying substring search:")
        cmd_search(db, query, limit=10)


def cmd_en(db, query, limit=40):
    q = query.lower().strip()
    row = db.execute("SELECT ig FROM en2ig WHERE en = ?", (q,)).fetchone()
    hits = []
    if row:
        hits = json.loads(row[0])
        print(f"{q}  ->  {', '.join(hits)}")
    # also surface rich entries whose definitions contain the word, for context
    rows = db.execute(
        "SELECT word, word_class, definitions, variations, stems, examples, is_common"
        " FROM entries WHERE definitions LIKE ? ORDER BY is_common DESC,"
        " LENGTH(definitions) LIMIT ?", (like(q), limit)).fetchall()
    pat = re.compile(r"\b" + re.escape(q) + r"\b", re.I)
    shown = 0
    for r in rows:
        if any(pat.search(d) for d in json.loads(r[2])):
            print_entry(*r)
            shown += 1
            if shown >= 12:
                break
    if not row and not shown:
        print(f"no match for {query!r} (try a simpler/singular form)")


def cmd_search(db, query, limit=20):
    q = norm(query)
    found = 0
    for r in db.execute(
        "SELECT word, word_class, definitions, variations, stems, examples, is_common"
        " FROM entries WHERE word_norm LIKE ? ORDER BY is_common DESC,"
        " LENGTH(word_norm) LIMIT ?", (like(q), limit)):
        print_entry(*r)
        found += 1
    for key, defs in db.execute(
        "SELECT key, defs FROM ig2en WHERE key_norm LIKE ?"
        " AND key_norm NOT IN (SELECT word_norm FROM entries)"
        " ORDER BY LENGTH(key_norm) LIMIT ?", (like(q), limit)):
        print(f"{key}  ->  {'; '.join(json.loads(defs)[:15])}  [normalized index]")
        found += 1
    if not found:
        print(f"no Igbo forms contain {query!r}"
              " (this searches Igbo words; for English->Igbo use: en <word>)")


def cmd_examples(db, query, limit=20):
    q = norm(query)
    rows = db.execute(
        "SELECT igbo, english, headword FROM examples"
        " WHERE igbo_norm LIKE ? OR english_lower LIKE ? LIMIT ?",
        (like(q), like(query.lower()), limit)).fetchall()
    for ig, en, hw in rows:
        print(f"{ig}\n  = {en}   [{hw}]")
    if not rows:
        print("no examples found")


def cmd_gloss(db, sentence, max_ngram=4):
    # split off elided prepositions/prefixes: n'Àba -> n' + Àba
    sentence = re.sub(r"(\w['’])(?=\w)", r"\1 ", sentence)
    tokens = [t for t in re.split(r"[\s,;:!?.]+", sentence) if t]
    # n' / m' are elisions of na
    tokens = ["na" if re.fullmatch(r"[nm]['’]", t) else t for t in tokens]
    i = 0
    while i < len(tokens):
        hit = None
        for n in range(min(max_ngram, len(tokens) - i), 0, -1):
            chunk = " ".join(tokens[i:i + n])
            q = norm(chunk)
            defs = []
            for (d,) in db.execute(
                    "SELECT definitions FROM entries WHERE word_norm = ?", (q,)):
                defs.extend(json.loads(d))
            if not defs:
                for (d,) in db.execute(
                        "SELECT defs FROM ig2en WHERE key_norm = ?", (q,)):
                    defs.extend(json.loads(d))
            if defs:
                uniq = list(dict.fromkeys(defs))
                hit = (chunk, n, uniq)
                break
        if hit:
            chunk, n, defs = hit
            print(f"{chunk}  ->  {'; '.join(defs[:6])}")
            i += n
        else:
            print(f"{tokens[i]}  ->  ??? (not in dictionary — check affixes/stem)")
            i += 1


def cmd_nsibidi(db, query, limit=20):
    q = norm(query)
    rows = db.execute(
        "SELECT sym, pro, form, defs FROM nsibidi"
        " WHERE sym LIKE ? OR pro_norm LIKE ? OR defs LIKE ? LIMIT ?",
        (like(query), like(q), like(query.lower()), limit)).fetchall()
    for sym, pro, form, defs in rows:
        print(f"{sym}  pron: {pro or '-'}  form: {form or '-'}  =  {defs}")
    if not rows:
        print("no nsibidi match")


def cmd_stats(db):
    for t in TABLES:
        n = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t}: {n}")
    source = meta_get(db, "source")
    if source:
        print(f"source: {source}")
    sha = meta_get(db, "sha")
    if sha:
        print(f"sha: {sha}")


def cmd_update(db, ref=DEFAULT_REF):
    """Rebuild only if upstream's dictionaries moved since the DB was built."""
    source, sha = meta_get(db, "source"), meta_get(db, "sha")
    db.close()
    if source and source.startswith("local:"):
        print(f"database was built from {source}; rebuild with:"
              f"\n  igbo.py build --repo {source[len('local:'):]}")
        return
    latest = upstream_sha(ref)
    if latest is None:
        sys.exit("error: could not reach the GitHub API to check for updates")
    if sha and sha == latest:
        print(f"up to date ({UPSTREAM}@{ref} {sha[:8]})")
        return
    print(f"upstream dictionaries changed ({(sha or 'unknown')[:8]} -> {latest[:8]});"
          " rebuilding")
    build(ref=ref)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, rest = args[0], args[1:]

    ref = DEFAULT_REF
    if "--ref" in rest:
        i = rest.index("--ref")
        ref = rest[i + 1]
        del rest[i:i + 2]

    if cmd == "build":
        repo = None
        if "--repo" in rest:
            i = rest.index("--repo")
            repo = rest[i + 1]
            del rest[i:i + 2]
        build(repo=repo, ref=ref)
        return

    db = connect()
    query = " ".join(rest)
    if cmd == "lookup":
        cmd_lookup(db, query)
    elif cmd == "en":
        cmd_en(db, query)
    elif cmd == "search":
        cmd_search(db, query)
    elif cmd == "examples":
        cmd_examples(db, query)
    elif cmd == "gloss":
        cmd_gloss(db, query)
    elif cmd == "nsibidi":
        cmd_nsibidi(db, query)
    elif cmd == "stats":
        cmd_stats(db)
    elif cmd == "update":
        cmd_update(db, ref)
    else:
        sys.exit(f"unknown command {cmd!r} — see --help")


if __name__ == "__main__":
    main()
