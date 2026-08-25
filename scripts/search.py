#!/usr/bin/env python3
"""
search.py - Search the DNBC variable dictionary and print matches grouped by wave.

The codebooks are English written up from Danish questionnaires, and the wording drifts
*within* a single book: Interview 3 alone spells breastfeeding six ways ("breast feeding",
"breastfeeding", "breast-feed", "breast-fed", "breastfeed", "breast feedings"). Searching
one exact phrase silently misses most of the matches, so every term is expanded before
matching: it is stemmed, and it is also compared with all spaces and hyphens squashed out,
so one term catches every compound spelling. Pass --exact for plain regex.

Usage:
    python3 scripts/search.py smok cigaret tobacco       # ANY term (broad, default)
    python3 scripts/search.py --topic smoking            # curated terms from topics.tsv
    python3 scripts/search.py --all depress medic        # ALL terms (narrow)
    python3 scripts/search.py --wave y11c,y11a sdq       # restrict to waves
    python3 scripts/search.py --var "^A0" --wave i1      # match on variable code
    python3 scripts/search.py --names smok               # one line per hit, no labels
    python3 scripts/search.py --context A127             # read the codebook around a code

Wave slugs: i1 i2 i3 i4 (interviews 1-4), y7, y11c (child), y11a (adult), y18.
Match is against variable code + description + labels + section unless --var is given.
"""

import argparse
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(os.path.dirname(HERE), "references")
TSV = os.path.join(REFS, "dnbc_variables.tsv")
TOPICS = os.path.join(REFS, "topics.tsv")
TEXT_DIR = os.path.join(REFS, "text")

# Map wave slug -> substring that identifies the wave label in the TSV.
SLUG_TO_LABEL = {
    "i1": "Interview 1", "i2": "Interview 2", "i3": "Interview 3", "i4": "Interview 4",
    "y7": "7-year", "y11c": "11-year follow-up (child", "y11a": "11-year follow-up (adult",
    "y18": "18-year",
}
LABEL_TO_SLUG = [(v, k) for k, v in SLUG_TO_LABEL.items()]
# Preserve a sensible wave ordering in the output.
WAVE_ORDER = ["Interview 1", "Interview 2", "Interview 3", "Interview 4",
              "7-year", "11-year follow-up (child", "11-year follow-up (adult", "18-year"]

# Rows reconstructed from a parent's text are real data columns but their wording is
# inferred, so they are marked in the output and ranked below verbatim ones.
SOURCE_MARK = {"expanded": "~", "range-header": "#", "stem-inherited": "^"}

# One answer option, "3. do not know" / "10) irrelevant".
LABEL_ITEM = re.compile(r"^\s*(\d{1,3})[.)]?\s+(.+?)\s*$")
# Options that are not answers but missing-value markers. Every one of these must be
# recoded to NA before the variable is used -- 9 appears on 1,040 variables, 99 on 496.
MISSING_TEXT = re.compile(
    r"^(do ?n[o']?t (know|want to answer|wish to answer)"
    r"|undefined|irrelevant|not applicable|not answered|not asked|no answer)\b", re.I)
# A plain "no" option. "No, but the child gets mother's milk" is a real answer, not this.
PLAIN_NO = re.compile(r"^no$", re.I)


def warn_for(levels):
    """Flag only coding that will actually catch someone out.

    Warning on everything that is not "1=yes 2=no" buries the signal: 944 rows are plain
    0/1 dummies, which is the conventional coding for a tick-box column, and 59 are
    ordinal scales where "no" is simply the low anchor. What genuinely bites is a two-level
    item whose polarity is flipped against the convention used everywhere else in the
    DNBC -- 1=No, 2=Yes -- because a hand-written `== 2` then silently selects "yes".
    """
    pairs = [(x.split("=", 1)[0], x.split("=", 1)[1].lower())
             for x in levels if "=" in x]
    if not pairs:
        return ""
    codes = [c for c, _ in pairs]
    texts = [t for _, t in pairs]
    if not any(t.startswith("yes") for t in texts):
        return ""                                    # ordinal: no "yes" to reverse
    if codes[:2] == ["0", "1"] and texts[0] == "no":
        return ""                                    # conventional 0/1 dummy
    no_at = next((c for c, t in pairs if PLAIN_NO.match(t)), None)
    if no_at is None or no_at == "2":
        return ""
    if len(pairs) == 2:
        return "REVERSED: %s=no, %s=yes -- the opposite of most DNBC items" % (
            no_at, codes[0] if codes[0] != no_at else codes[1])
    return '"no" is %s, not 2 (%d levels, several mean yes)' % (no_at, len(pairs))


def format_labels(labels, full=False):
    """Return (compact_labels, missing_codes, warning).

    Answer coding is where a variable gets silently misused: "no" is 2 on only 601 of the
    1,007 yes/no variables -- it is 1 on 248, 3 on 72, 0 on 70. Surfacing that beside the
    variable is the difference between a correct recode and a quietly wrong one.
    """
    if not labels:
        return "", [], ""
    parts = labels.split(" | ")
    # Some options are printed on a single line ("1. no 2. a little 3. a lot"), so they
    # arrive as one unsplit string and the whole thing reads as a single level.
    if len(parts) == 1 and len(re.findall(r"(?:^|\s)\d{1,3}\.\s", labels)) >= 2:
        parts = [x.strip() for x in re.split(r"(?<=\s)(?=\d{1,3}\.\s)", labels) if x.strip()]
    items = [LABEL_ITEM.match(x) for x in parts]
    if not any(items):
        return labels, [], ""

    real, missing = [], []
    for m, raw in zip(items, parts):
        if not m:
            real.append(raw.strip())
            continue
        code, text = m.group(1), m.group(2)
        (missing if MISSING_TEXT.match(text) else real).append("%s=%s" % (code, text))

    warning = warn_for(real)

    if full:
        return labels, [m.split("=", 1)[0] for m in missing], warning
    # Join with a middle dot, not a comma: label text contains commas of its own
    # ("yes, every day"), and a comma-joined list reads as one run-on option.
    return " \u00b7 ".join(real), [m.split("=", 1)[0] for m in missing], warning

# The 7-year questionnaire was personalised per child ("about your son/daughter", per its
# own introduction), but the printed codebook documents mostly the daughter variant: 36 of
# its question lines say "your daughter" against 2 saying "your son", and no other wave
# does this. Read literally the wording looks girls-only, so say once that it is not.
GENDERED = re.compile(r"\byour (daughter|son)\b|\bother (girls|boys) (her|his) age\b", re.I)
GENDERED_NOTE = ('The 7-year codebook prints the "your daughter" variant of a questionnaire '
                 'that was personalised per child - these items apply to all children.')

SQUASH = re.compile(r"[^a-z0-9]+")

# Squashing spaces out of the haystack is what lets one term catch "breast feeding",
# "breast-fed" and "breastfeed" alike -- but it also lets a short term match straight
# across a word boundary ("sad" inside "ha[s a d]octor", "question wa[s ad]ded"). Only
# terms long enough for that collision to be implausible get the squashed comparison;
# shorter ones are matched as plain regex, which is already enough for inflections.
MIN_SQUASH_LEN = 5


def squash(text):
    """'breast feeding' and 'breast-fed' both collapse toward 'breastfeed...'."""
    return SQUASH.sub("", text.lower())


def squash_indexed(text):
    """Squashed text, plus the offsets in it where a word began.

    Squashing deletes word boundaries, which is the point for compounds -- but it also
    lets a term land mid-word: "mental" sits inside "develop[mental]", so a depression
    search returned two child-development questions. Requiring a match to start where a
    word started keeps the compound win and drops that whole class of false positive.
    """
    out, starts, at_start = [], set(), True
    for ch in text.lower():
        if ch.isalnum():
            if at_start:
                starts.add(len(out))
                at_start = False
            out.append(ch)
        else:
            at_start = True
    return "".join(out), starts


def squash_hit(term, text):
    """True if `term` occurs in the squashed text starting at a word boundary."""
    hay, starts = squash_indexed(text)
    i = hay.find(term)
    while i != -1:
        if i in starts:
            return True
        i = hay.find(term, i + 1)
    return False


def stem(term):
    """Trim one English inflection so 'smoking' also finds 'smoked' and 'smoker'."""
    t = term.lower()
    for suf, keep in (("ies", 5), ("ing", 4), ("ions", 5), ("ion", 5),
                      ("ed", 4), ("es", 5), ("s", 4)):
        if t.endswith(suf) and len(t) - len(suf) >= keep:
            base = t[: -len(suf)]
            # "stopping" -> "stopp" -> "stop"
            if suf == "ing" and len(base) > 4 and base[-1] == base[-2] and base[-1] not in "aeiou":
                base = base[:-1]
            return base
    return t


def load_rows():
    if not os.path.exists(TSV):
        sys.exit("Dictionary not found: %s\nRun: python3 scripts/build_index.py" % TSV)
    rows = []
    with open(TSV) as fh:
        next(fh)  # header
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 8:
                parts += [""] * (8 - len(parts))
            wave, var, page, desc, labels, depends, section, source = parts[:8]
            rows.append({"wave": wave, "var": var, "page": page, "desc": desc,
                         "labels": labels, "depends": depends, "section": section,
                         "source": source or "extracted"})
    return rows


NUMERIC_RANGE = re.compile(r"\(\s*\d+\s*-\s*\d+\s*\)")
SUBITEM_CODE = re.compile(r"^[A-Za-z]\d{3}[._]\d+$")
VERSION_LIMITED = re.compile(r"only in version|not in version|only the versions"
                             r"|not a part of the|only in v\d", re.I)


def variable_type(row, n_levels):
    """The modelling shape of a variable, inferred from its code and answer options."""
    if SUBITEM_CODE.match(row["var"]):
        return "multi-select (0/1)"
    base = re.split(r"[._]", row["var"])[0]
    # A folded range names only its endpoints ("A130_1-A130_40"), so counting the codes
    # that appear gives 2 for a set of 40. Measure the span, not the mentions.
    span = re.search(r"\b%s[._](\d+)\s*-\s*(?:%s[._])?(\d+)\b"
                     % (re.escape(base), re.escape(base)), row["desc"])
    if span:
        lo, hi = int(span.group(1)), int(span.group(2))
        if 0 < hi - lo < 200:
            return "multi-select set (%d)" % (hi - lo + 1)
    kids = set(re.findall(r"\b%s[._](\d+)\b" % re.escape(base), row["desc"]))
    if len(kids) >= 2:
        return "multi-select set (%d)" % len(kids)
    if NUMERIC_RANGE.search(row["desc"]) and n_levels <= 1:
        return "numeric"
    if n_levels == 2:
        return "binary"
    if 3 <= n_levels <= 7:
        return "categorical"
    if n_levels > 7:
        return "categorical (%d lvl)" % n_levels
    return "free text" if not row["labels"] else "other"


def asked_of(row):
    """Who actually answered this. 53% of variables are gated, so their missingness is
    structural -- a complete-case model on a gated variable silently conditions on the
    gate."""
    notes = []
    if row["depends"].startswith("Depends on:"):
        codes = row["depends"][len("Depends on:"):].split()
        notes.append("if " + "/".join(codes[:3]) + (" ..." if len(codes) > 3 else "") + " answered")
    if VERSION_LIMITED.search(row["desc"]):
        notes.append("some questionnaire versions only")
    return "; ".join(notes) if notes else "all respondents"


def short_question(text, limit=None):
    """First sentence of the question, trimmed at a word boundary.

    A member of a folded range carries its meaning as a trailing " - week 12" /
    " - do not know", which is the only thing distinguishing it from its siblings --
    so that tail survives the trim even when the question itself does not.
    """
    # `--table` passes no limit: a cut-off description ("...where you did not...") hides
    # the one thing the column exists to convey. `--recode` still trims, because there it
    # is a trailing code comment rather than the content.
    if limit is None:
        return text
    tail = ""
    m = re.search(r"\s-\s((?:week \d+|do not [a-z ]+))$", text)
    if m:
        tail = " - " + m.group(1)
        text = text[:m.start()]
    text = text.split("?")[0].strip() + ("?" if "?" in text else "")
    for sep in (" - ", " (", " If ", ": "):
        if sep in text and len(text.split(sep)[0]) >= 20:
            text = text.split(sep)[0].rstrip(" ,-") + ("?" if text.endswith("?") else "")
            break
    if len(text) <= limit:
        return text + tail
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "..." + tail


def cell(text):
    """Make a value safe to sit inside a markdown table row."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def emit_table(scored, gates):
    """A ready-to-paste markdown table -- the deliverable, not raw console output.

    Emitting the finished table is what keeps an answer short: there is nothing left to
    compose, only a table to paste and at most a line or two of prose around it.
    """
    by_wave = {}
    for _, r in scored:
        by_wave.setdefault(r["wave"], []).append(r)
    for wave in sorted(by_wave, key=lambda w: next(
            (i for i, t in enumerate(WAVE_ORDER) if t in w), len(WAVE_ORDER))):
        print("### %s\n" % wave)
        print("| Variable | Measures | Type | Recode | Asked of |")
        print("|---|---|---|---|---|")
        warnings = []
        for r in by_wave[wave]:
            compact, missing, warn = format_labels(r["labels"])
            levels = [x for x in compact.split(" \u00b7 ") if x.strip()] if compact else []
            if len(levels) > 3:
                recode = " \u00b7 ".join(levels[:2]) + " ... (%d levels)" % len(levels)
            else:
                recode = " \u00b7 ".join(levels) if levels else "-"
            if missing:
                recode += "  |  NA: %s" % ",".join(missing)
            # A gating chain (C001 -> C003 -> C004) makes every link gate the rest, so
            # gate-count alone stars them all. The entry point is the one nothing gates.
            n_gated = gates.get((r["wave"], r["var"]), 0)
            is_entry = n_gated >= 20 and not r["depends"].startswith("Depends on:")
            star = " *" if is_entry else ""
            print("| `%s`%s | %s | %s | %s | %s |" % (
                r["var"], star, cell(short_question(r["desc"])),
                variable_type(r, len(levels)), cell(recode), cell(asked_of(r))))
            if warn:
                warnings.append("`%s`: %s" % (r["var"], warn))
        print()
        if warnings:
            print("**Check the coding:** " + "; ".join(warnings) + "\n")
        if "7-year" in wave and any(GENDERED.search(r["desc"]) for r in by_wave[wave]):
            print("_%s_\n" % GENDERED_NOTE)
        if any(gates.get((r["wave"], r["var"]), 0) >= 20
               and not r["depends"].startswith("Depends on:") for r in by_wave[wave]):
            print("`*` = the screener everything else hangs off; start here.\n")


MAX_RECODE_LEVELS = 12


def _levels(row):
    """(code, label) pairs for the informative options, plus the missing-value codes."""
    compact, missing, warn = format_labels(row["labels"])
    pairs = []
    for x in compact.split(" \u00b7 "):
        code, sep, text = x.partition("=")
        if sep and code.strip().isdigit() and text.strip():
            pairs.append((code.strip(), text.strip()))
    return pairs, missing, warn


def _why(row):
    note = short_question(row["desc"], 62)
    if row["depends"].startswith("Depends on:"):
        note += "   [%s]" % asked_of(row)
    return note


def _q(text):
    return '"%s"' % text.replace("\\", "").replace('"', "'").strip()


def _skip(row, pairs):
    """Reason this variable cannot be mechanically recoded, or None."""
    if not pairs and NUMERIC_RANGE.search(row["desc"]):
        return "numeric"
    if not pairs:
        kind = variable_type(row, 0)
        if kind.startswith("multi-select set"):
            return "is a %s - recode its members" % kind
        return "is free text; nothing to recode"
    if len(pairs) > MAX_RECODE_LEVELS:
        return "has %d levels - run --full-labels to expand" % len(pairs)
    if [c for c, _ in pairs] == ["0", "1"]:
        return "is already a clean 0/1 flag"
    return None


def render_r(rows, by_wave, ordered, gates):
    out = ["# Generated by lookdnbc. Each column is mapped onto its own answer labels and",
           "# every missing-value code is set to NA, so the source coding does not matter.",
           "dat <- dat |> mutate("]
    for wave in ordered:
        out.append("\n  ## %s" % wave)
        for r in by_wave[wave]:
            pairs, missing, _ = _levels(r)
            out.append("  # %s" % _why(r))
            why = _skip(r, pairs)
            if why == "numeric":
                out.append("  %s = if_else(%s %%in%% c(%s), NA_real_, %s)," %
                           (r["var"], r["var"], ", ".join(missing), r["var"])
                           if missing else "  # %s is numeric; no missing codes" % r["var"])
            elif why == "is already a clean 0/1 flag":
                out.append("  %s = if_else(%s %%in%% c(%s), NA_integer_, %s)," %
                           (r["var"], r["var"], ", ".join(missing), r["var"])
                           if missing else "  # %s is already a clean 0/1 flag" % r["var"])
            elif why:
                out.append("  # %s %s" % (r["var"], why))
            else:
                arms = ", ".join("%s ~ %s" % (c, _q(t)) for c, t in pairs)
                out.append("  %s = case_match(%s, %s,\n                        "
                           ".default = NA_character_) |> factor()," % (r["var"], r["var"], arms))
    out.append(")")
    return "\n".join(out)


def render_stata(rows, by_wave, ordered, gates):
    out = ["* Generated by lookdnbc. Value labels come from the codebook; mvdecode clears",
           "* every missing-value code, so the source coding does not matter."]
    for wave in ordered:
        out.append("\n* ---- %s" % wave)
        for r in by_wave[wave]:
            pairs, missing, _ = _levels(r)
            out.append("* %s" % _why(r))
            why = _skip(r, pairs)
            if why and why != "numeric" and why != "is already a clean 0/1 flag":
                out.append("* %s %s" % (r["var"], why))
                continue
            if not why:
                out.append("label define %s_lbl %s, replace"
                           % (r["var"], " ".join('%s %s' % (c, _q(t)) for c, t in pairs)))
                out.append("label values %s %s_lbl" % (r["var"], r["var"]))
            if missing:
                out.append("mvdecode %s, mv(%s)" % (r["var"], " ".join(missing)))
            elif why:
                out.append("* %s %s; no missing codes to clear" % (r["var"], why))
    return "\n".join(out)


def render_sas(rows, by_wave, ordered, gates):
    fmts, steps = [], []
    for wave in ordered:
        steps.append("\n  /* ---- %s */" % wave)
        for r in by_wave[wave]:
            pairs, missing, _ = _levels(r)
            steps.append("  /* %s */" % _why(r))
            why = _skip(r, pairs)
            if not why:
                fmts.append("  value %s_f%s;" % (
                    r["var"][:26], "".join("  %s = %s" % (c, _q(t)) for c, t in pairs)))
            elif why != "numeric" and why != "is already a clean 0/1 flag":
                steps.append("  /* %s %s */" % (r["var"], why))
                continue
            if missing:
                steps.append("  if %s in (%s) then %s = .;"
                             % (r["var"], ", ".join(missing), r["var"]))
            if not why:
                steps.append("  format %s %s_f.;" % (r["var"], r["var"][:26]))
    out = ["/* Generated by lookdnbc. Formats carry the codebook labels; the data step",
           "   clears every missing-value code, so the source coding does not matter. */"]
    if fmts:
        out += ["", "proc format;"] + fmts + ["run;"]
    out += ["", "data dat;", "  set dat;"] + steps + ["run;"]
    return "\n".join(out)


RECODE_LANGS = {
    # `tok` is the language's own comment marker -- it labels each tab, so the control
    # tells you something true about the language rather than just naming it.
    "r":     {"name": "R", "flavour": "dplyr", "tok": "#",  "render": render_r},
    "stata": {"name": "Stata", "flavour": "",  "tok": "*",  "render": render_stata},
    "sas":   {"name": "SAS", "flavour": "",    "tok": "/*", "render": render_sas},
}
LANG_ORDER = ["r", "stata", "sas"]


def emit_recode(scored, gates, lang):
    by_wave = {}
    for _, r in scored:
        by_wave.setdefault(r["wave"], []).append(r)
    ordered = sorted(by_wave, key=lambda w: next(
        (i for i, t in enumerate(WAVE_ORDER) if t in w), len(WAVE_ORDER)))
    print(RECODE_LANGS[lang]["render"]([r for _, r in scored], by_wave, ordered, gates))


HTML_CSS = """
/* Light theme only, by design: this is a reference sheet meant to be read and printed. */
:root{
  --paper:#FCFCFA; --surface:#FFFFFF; --ink:#101820; --muted:#6B7785;
  --rule:#E4E8EC; --hair:#F0F3F5; --accent:#2B4C7E; --accent-wash:#EEF3FA;
  --flag:#C2410C; --flag-wash:#FDF1EA; --rail:#C7D2E0;
  --display:system-ui,-apple-system,"Segoe UI","Helvetica Neue",Arial,sans-serif;
  --body:Georgia,"Times New Roman",Times,serif;
  --data:ui-monospace,"SF Mono",Menlo,Consolas,"Cascadia Mono","Liberation Mono",monospace;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--body);
  font-size:16.5px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:1160px;margin:0 auto;padding:0 32px 100px}
header.top{padding:64px 0 0}
.kicker{font-family:var(--data);font-size:11px;letter-spacing:.2em;text-transform:uppercase;
  color:var(--accent);margin:0 0 18px}
h1{font-family:var(--display);font-weight:700;font-size:clamp(34px,5vw,54px);line-height:1;
  letter-spacing:-.03em;margin:0}
.sub{font-size:18px;color:var(--muted);margin:14px 0 0;max-width:56ch}
.tally{display:flex;flex-wrap:wrap;margin:34px 0 0;border-top:1px solid var(--ink);
  border-bottom:1px solid var(--rule)}
.tally div{padding:16px 26px 16px 0;margin-right:26px;border-right:1px solid var(--rule)}
.tally div:last-child{border-right:none;margin-right:0}
.tally b{display:block;font-family:var(--display);font-weight:700;font-size:27px;
  line-height:1;letter-spacing:-.02em}
.tally span{font-family:var(--data);font-size:10.5px;letter-spacing:.11em;
  text-transform:uppercase;color:var(--muted);display:block;margin-top:7px}
.tally .flagged b{color:var(--flag)}
section{margin-top:52px}
.wavehead{display:flex;align-items:baseline;justify-content:space-between;gap:16px;
  padding-bottom:11px;border-bottom:2px solid var(--ink)}
.wavehead h2{font-family:var(--display);font-weight:600;font-size:21px;letter-spacing:-.01em;margin:0}
.wavehead em{font-family:var(--data);font-style:normal;font-size:11px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted);white-space:nowrap}
.tablewrap{overflow-x:auto;background:var(--surface);border:1px solid var(--rule);border-top:none}
table{border-collapse:collapse;width:100%;min-width:940px}
thead th{font-family:var(--data);font-size:10px;font-weight:500;letter-spacing:.12em;
  text-transform:uppercase;color:var(--muted);text-align:left;padding:12px 18px;
  border-bottom:1px solid var(--rule);background:var(--surface);position:sticky;top:0;z-index:2}
td{padding:16px 18px;border-bottom:1px solid var(--hair);vertical-align:top}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:#FBFCFD}
td.code{width:206px;white-space:nowrap;font-family:var(--data);position:relative}
.d1{padding-left:38px}.d2{padding-left:58px}.d3{padding-left:78px}
.tie{position:absolute;left:18px;top:14px;width:11px;height:10px;
  border-left:1px solid var(--rail);border-bottom:1px solid var(--rail)}
.d2 .tie{left:38px}.d3 .tie{left:58px}
.vcode{font-size:14px;font-weight:600;color:var(--accent);letter-spacing:-.01em}
.screener{display:inline-block;font-family:var(--data);font-size:9px;letter-spacing:.09em;
  text-transform:uppercase;color:var(--accent);border:1px solid var(--accent);
  border-radius:2px;padding:1px 5px;margin-left:8px;vertical-align:2px}
.gates{display:block;font-size:10.5px;color:var(--muted);margin-top:5px}
td.q{max-width:0}
.qtext{display:block;font-size:15.5px;line-height:1.45}
.qmeta{display:block;font-family:var(--data);font-size:10.5px;color:var(--muted);margin-top:8px}
td.opts{width:330px}
.opt{display:inline-flex;font-family:var(--data);font-size:11.5px;border:1px solid var(--rule);
  border-radius:3px;overflow:hidden;margin:0 6px 6px 0;max-width:100%}
.opt b{background:var(--accent-wash);color:var(--accent);font-weight:600;padding:3px 7px;
  border-right:1px solid var(--rule)}
.opt i{font-style:normal;padding:3px 8px;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;max-width:210px}
.opt.rev b{background:var(--flag-wash);color:var(--flag);border-right-color:#F3D9CB}
.nas{display:block;font-family:var(--data);font-size:10.5px;color:var(--muted);margin-top:3px}
.nas b{color:var(--flag);font-weight:500}
.plain{font-family:var(--data);font-size:11.5px;color:var(--muted)}
.type{font-family:var(--data);font-size:10px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--muted);white-space:nowrap}
td.type-cell{width:118px}
.flagrow td{background:var(--flag-wash)}
.flagnote{display:block;font-family:var(--data);font-size:11px;color:var(--flag);margin-top:8px}
.wavenote{font-size:13.5px;color:var(--muted);margin:12px 0 0;padding-left:14px;
  border-left:2px solid var(--rule);max-width:70ch}
.codehead{display:flex;align-items:baseline;gap:14px;margin:56px 0 18px}
.codehead h2{font-family:var(--display);font-weight:600;font-size:21px;margin:0}
.codehead span{font-family:var(--data);font-size:11px;color:var(--muted)}

/* Tabs are CSS-only: the radios drive both the strip and the panes, so switching
   languages works with scripting disabled. JS only adds copy and remembering. */
.codeblock{position:relative}
.tabin{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}
.tabs{display:flex;align-items:stretch;gap:0;border-bottom:2px solid var(--ink)}
.tabs label{display:inline-flex;align-items:baseline;gap:8px;cursor:pointer;
  font-family:var(--display);font-weight:600;font-size:14px;padding:9px 18px;
  color:var(--muted);border-bottom:2px solid transparent;margin-bottom:-2px;
  transition:color .12s ease,border-color .12s ease}
.tabs label:hover{color:var(--ink)}
.tabs label em{font-family:var(--data);font-style:normal;font-size:13px;font-weight:500;
  color:var(--rail)}
.tabs label span{font-family:var(--data);font-size:10.5px;font-weight:400;color:var(--muted)}
.copy{margin-left:auto;align-self:center;font-family:var(--data);font-size:10.5px;
  letter-spacing:.09em;text-transform:uppercase;color:var(--muted);background:none;
  border:1px solid var(--rule);border-radius:2px;padding:5px 11px;cursor:pointer;
  transition:color .12s ease,border-color .12s ease}
.copy:hover{color:var(--accent);border-color:var(--accent)}
.copy[data-done="1"]{color:var(--accent);border-color:var(--accent)}
.codeblock pre{display:none}
pre{background:var(--surface);border:1px solid var(--rule);border-top:none;
  padding:22px 24px;overflow-x:auto;font-family:var(--data);font-size:12.5px;line-height:1.7;
  margin:0}
pre .cm{color:var(--muted)}
#L-r:checked ~ .p-r,#L-stata:checked ~ .p-stata,#L-sas:checked ~ .p-sas{display:block}
#L-r:checked ~ .tabs label[for=L-r],
#L-stata:checked ~ .tabs label[for=L-stata],
#L-sas:checked ~ .tabs label[for=L-sas]{color:var(--ink);border-bottom-color:var(--accent)}
#L-r:checked ~ .tabs label[for=L-r] em,
#L-stata:checked ~ .tabs label[for=L-stata] em,
#L-sas:checked ~ .tabs label[for=L-sas] em{color:var(--accent)}
#L-r:focus-visible ~ .tabs label[for=L-r],
#L-stata:focus-visible ~ .tabs label[for=L-stata],
#L-sas:focus-visible ~ .tabs label[for=L-sas]{outline:2px solid var(--accent);outline-offset:-2px}
@media (prefers-reduced-motion:reduce){.tabs label,.copy{transition:none}}
footer{margin-top:64px;padding-top:20px;border-top:1px solid var(--rule);
  font-family:var(--data);font-size:11px;color:var(--muted);line-height:1.9}
footer code{color:var(--accent)}
@media (max-width:720px){.wrap{padding:0 18px 72px}.tally div{padding-right:16px;margin-right:16px}}
@media print{body{background:#fff}.tablewrap{overflow:visible;border:none}table{min-width:0}
  thead th{position:static}section{break-inside:avoid}}
"""


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def chain_depth(recs):
    """How deep each variable sits in its wave's skip chain, for the indent rail."""
    by_code = {r["var"]: r for r in recs}
    depth, resolving = {}, set()

    def d(code):
        if code in depth:
            return depth[code]
        r = by_code.get(code)
        if r is None or not r["depends"].startswith("Depends on:") or code in resolving:
            return 0
        resolving.add(code)
        gates = [g for g in r["depends"][len("Depends on:"):].split() if g in by_code]
        depth[code] = min(3, 1 + max([d(g) for g in gates] or [0])) if gates else 1
        resolving.discard(code)
        return depth[code]

    return {c: d(c) for c in by_code}


def emit_html(scored, gates, query, subtitle, lang, out_path):
    """Write the standalone, light-theme report.

    Two things carry the design. The skip chain is drawn as an indent rail, because a DNBC
    variable is a node in a conditional tree rather than a flat column. And answer options
    are set as numbered chips, so a reversed coding (1=No 2=Yes) is visible at a glance
    instead of having to be explained.
    """
    from datetime import date
    by_wave = {}
    for _, r in scored:
        by_wave.setdefault(r["wave"], []).append(r)
    ordered = sorted(by_wave, key=lambda w: next(
        (i for i, t in enumerate(WAVE_ORDER) if t in w), len(WAVE_ORDER)))

    n_gated = sum(1 for _, r in scored if r["depends"].startswith("Depends on:"))
    n_flag, body = 0, []

    for wave in ordered:
        recs = by_wave[wave]
        label, _, detail = wave.partition(" (")
        depths = chain_depth(recs)
        body.append('<section><div class="wavehead"><h2>%s</h2><em>%s</em></div>'
                    '<div class="tablewrap"><table>'
                    '<colgroup><col style="width:206px"><col>'
                    '<col style="width:118px"><col style="width:330px"></colgroup>'
                    '<thead><tr><th>Variable</th><th>Question</th><th>Type</th>'
                    '<th>Answer coding</th></tr></thead><tbody>'
                    % (esc(label), esc(detail.rstrip(")"))))
        for r in recs:
            pairs, missing, warn = _levels(r)
            levels_n = len(pairs) or (1 if r["labels"] else 0)
            reversed_ = warn.startswith("REVERSED")
            if warn:
                n_flag += 1
            dep = depths.get(r["var"], 0)
            n_gate = gates.get((r["wave"], r["var"]), 0)
            entry = n_gate >= 20 and not r["depends"].startswith("Depends on:")
            badge = '<span class="screener">screener</span>' if entry else ""
            gline = ('<span class="gates">gates %d</span>' % n_gate) if n_gate >= 5 else ""
            if pairs:
                chips = "".join('<span class="opt%s"><b>%s</b><i>%s</i></span>'
                                % (" rev" if reversed_ else "", esc(c), esc(t))
                                for c, t in pairs[:6])
                if len(pairs) > 6:
                    chips += '<span class="plain">+%d more</span>' % (len(pairs) - 6)
            else:
                chips = '<span class="plain">&mdash;</span>'
            if missing:
                chips += '<span class="nas">set to NA: <b>%s</b></span>' % ", ".join(missing)
            body.append(
                '<tr%s><td class="code%s">%s<span class="vcode">%s</span>%s%s</td>'
                '<td class="q"><span class="qtext">%s</span>'
                '<span class="qmeta">%s &middot; p%s</span></td>'
                '<td class="type-cell"><span class="type">%s</span></td>'
                '<td class="opts">%s%s</td></tr>'
                % (' class="flagrow"' if warn else "", " d%d" % dep if dep else "",
                   '<span class="tie"></span>' if dep else "",
                   esc(r["var"]), badge, gline, esc(r["desc"]),
                   esc(asked_of(r)), esc(r["page"]),
                   esc(variable_type(r, levels_n)), chips,
                   '<span class="flagnote">%s</span>' % esc(warn) if warn else ""))
        body.append("</tbody></table></div>")
        if "7-year" in wave and any(GENDERED.search(r["desc"]) for r in recs):
            body.append('<p class="wavenote">%s</p>' % esc(GENDERED_NOTE))
        body.append("</section>")

    rows_only = [r for _, r in scored]
    tabs, panes = [], []
    for key in LANG_ORDER:
        meta = RECODE_LANGS[key]
        src = esc(meta["render"](rows_only, by_wave, ordered, gates))
        src = re.sub(r"(^|\n)(\s*(?:#|\*|/\*)[^\n]*)",
                     lambda m: m.group(1) + '<span class="cm">%s</span>' % m.group(2), src)
        panes.append('<input class="tabin" type="radio" name="lang" id="L-%s"%s>'
                     % (key, " checked" if key == lang else ""))
        tabs.append('<label for="L-%s"><em>%s</em>%s%s</label>'
                    % (key, esc(meta["tok"]), esc(meta["name"]),
                       '<span>%s</span>' % esc(meta["flavour"]) if meta["flavour"] else ""))
        panes.append('<pre class="p-%s">%s</pre>' % (key, src))
    inputs = [x for x in panes if x.startswith("<input")]
    blocks = [x for x in panes if x.startswith("<pre")]
    code = ("".join(inputs)
            + '<div class="tabs">' + "".join(tabs)
            + '<button class="copy" type="button">Copy</button></div>'
            + "".join(blocks))

    html = HTML_DOC % {
        "q": esc(query), "sub": esc(subtitle), "css": HTML_CSS, "body": "\n".join(body),
        "shown": len(scored), "waves": len(ordered), "wp": "" if len(ordered) == 1 else "s",
        "gated": n_gated, "flag": n_flag, "cp": "" if n_flag == 1 else "s",
        "code": code,
        "date": date.today().isoformat()}
    with open(out_path, "w") as fh:
        fh.write(html)
    print("Wrote %s  (%d variables, %d wave%s, %d conditional, %d caution%s)"
          % (out_path, len(scored), len(ordered), "" if len(ordered) == 1 else "s",
             n_gated, n_flag, "" if n_flag == 1 else "s"))


HTML_DOC = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(q)s &mdash; DNBC variables</title>
<style>%(css)s</style></head>
<body><div class="wrap">
<header class="top">
  <p class="kicker">Danish National Birth Cohort</p>
  <h1>%(q)s</h1>
  <p class="sub">%(sub)s</p>
  <div class="tally">
    <div><b>%(shown)d</b><span>variables</span></div>
    <div><b>%(waves)d</b><span>wave%(wp)s</span></div>
    <div><b>%(gated)d</b><span>conditional</span></div>
    <div class="flagged"><b>%(flag)d</b><span>coding caution%(cp)s</span></div>
  </div>
</header>
%(body)s
<div class="codehead"><h2>Recode</h2><span>paste into your preprocessing script</span></div>
<div class="codeblock">%(code)s</div>
<script>
(function(){
  var box=document.querySelector('.codeblock'); if(!box) return;
  var radios=box.querySelectorAll('.tabin');
  try{ var saved=localStorage.getItem('lookdnbc-lang');
       if(saved && box.querySelector('#L-'+saved)) box.querySelector('#L-'+saved).checked=true;
  }catch(e){}
  radios.forEach(function(r){ r.addEventListener('change',function(){
    try{ localStorage.setItem('lookdnbc-lang', r.id.slice(2)); }catch(e){}
  });});
  box.querySelector('.copy').addEventListener('click',function(){
    var pane=box.querySelector('.tabin:checked ~ pre[class^=p-]:not([style*="none"])');
    var shown=Array.prototype.filter.call(box.querySelectorAll('pre'),function(p){
      return getComputedStyle(p).display!=='none'; })[0];
    var text=(shown||pane||{}).innerText||'';
    var btn=this;
    function done(){ btn.textContent='Copied'; btn.dataset.done='1';
      setTimeout(function(){ btn.textContent='Copy'; btn.dataset.done=''; },1600); }
    if(navigator.clipboard && window.isSecureContext){
      navigator.clipboard.writeText(text).then(done,select);
    } else { select(); }
    function select(){
      var r=document.createRange(); r.selectNodeContents(shown||pane);
      var s=getSelection(); s.removeAllRanges(); s.addRange(r);
      try{ document.execCommand('copy'); done(); }catch(e){ btn.textContent='Select + copy'; }
    }
  });
})();
</script>
<footer>
  <div>Indentation follows the questionnaire's skip logic: an indented variable was only
  asked of people who answered the one above it.</div>
  <div>Generated %(date)s from the DNBC codebooks.</div>
</footer>
</div></body></html>
"""


def gate_degree(rows):
    """How many variables each variable gates, from the depends_on graph.

    A question that many others hang off is the screener -- the one to lead an answer
    with. A127 gates 52 follow-ups, A128 51, A129 41, which is exactly the smoking
    "start here" set. Without this a long, synonym-rich description outranks the short
    primary question it gates.
    """
    deg, seen = {}, set()
    for r in rows:
        if not r["depends"].startswith("Depends on:"):
            continue
        for code in r["depends"][len("Depends on:"):].split():
            key = (r["wave"], r["var"], code)
            if key in seen:
                continue
            seen.add(key)
            deg[(r["wave"], code)] = deg.get((r["wave"], code), 0) + 1
    return deg


def gate_bonus(n):
    """Capped so a screener is nudged to the top, never allowed to swamp relevance."""
    if n >= 20:
        return 2.5   # only 103 variables of 7,888 gate this many: the screeners
    if n >= 5:
        return 1.0
    return 0.3 if n else 0.0


def load_topics():
    """concept -> list of search terms, from references/topics.tsv."""
    topics = {}
    if not os.path.exists(TOPICS):
        return topics
    with open(TOPICS) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                topics[parts[0].strip().lower()] = parts[1].split()
    return topics


def slug_of(wave_label):
    for label, slug in LABEL_TO_SLUG:
        if label in wave_label:
            return slug
    return None


def show_context(rows, code, n_lines):
    """Print the codebook text around a variable code -- its stem, skip logic, neighbours."""
    pat = re.compile(r"^%s$" % re.escape(code), re.I)
    waves = [r["wave"] for r in rows if pat.match(r["var"])]
    if not waves:
        base = re.split(r"[._]", code)[0]
        waves = [r["wave"] for r in rows if re.split(r"[._]", r["var"])[0] == base]
    seen = []
    for w in waves:
        if w not in seen:
            seen.append(w)
    # Matrix-layout questions put their codes mid-line, so those columns have no row at
    # all -- exactly when context is most needed. Fall back to sweeping every wave.
    targets = [(w, slug_of(w)) for w in seen] or [
        (lbl, slug) for slug, lbl in SLUG_TO_LABEL.items()]

    found_any = False
    for wave, slug in targets:
        path = os.path.join(TEXT_DIR, "%s.txt" % slug) if slug else None
        if not path or not os.path.exists(path):
            continue
        with open(path) as fh:
            lines = fh.read().split("\n")
        hits = [i for i, ln in enumerate(lines) if re.search(r"\b%s\b" % re.escape(code), ln)]
        if not hits:
            continue
        found_any = True
        # A code appears far more often as a skip-logic target ("2. no -> A127") than at
        # its own definition. Show the definition -- the line that starts with the code.
        defn = re.compile(r"^\s*%s\b" % re.escape(code))
        hits.sort(key=lambda i: 0 if defn.match(lines[i]) else 1)
        print("## %s  (%s.txt)\n" % (wave, slug))
        for i in hits[:3]:
            lo, hi = max(0, i - n_lines), min(len(lines), i + n_lines + 1)
            for j in range(lo, hi):
                print("  %s%s" % (">> " if j == i else "   ", lines[j].rstrip()))
            print()

    if not found_any:
        sys.exit("%s appears nowhere in the codebooks." % code)


def build_matchers(terms, exact):
    """Return [(regex, squashed_stem_or_None)] -- one matcher per term."""
    out = []
    for t in terms:
        try:
            rx = re.compile(t, re.I)
        except re.error as exc:
            sys.exit("Bad pattern %r: %s" % (t, exc))
        # Only plain words get stemmed and squashed. A term carrying punctuation is
        # either a possessive or a regex the caller means literally -- stemming "child's"
        # to "child'" and squashing that to "child" turns a precise query into a
        # 500-hit sweep, which is the opposite of what was asked for.
        sq = squash(stem(t)) if (not exact and t.isalpha()) else None
        out.append((rx, sq if sq and len(sq) >= MIN_SQUASH_LEN else None))
    return out


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("terms", nargs="*", help="search stems/synonyms (regex, case-insensitive)")
    ap.add_argument("--all", action="store_true", help="require ALL terms (default: ANY)")
    ap.add_argument("--exact", action="store_true", help="plain regex only, no stem/compound expansion")
    ap.add_argument("--topic", default="", help="use curated terms from references/topics.tsv")
    ap.add_argument("--wave", default="", help="comma-separated wave slugs to restrict to")
    ap.add_argument("--var", default="", help="regex matched against the variable code only")
    ap.add_argument("--names", action="store_true", help="compact one line per hit (no labels)")
    ap.add_argument("--section", action="store_true",
                    help="also match a variable's section banner (broader, noisier)")
    ap.add_argument("--top", type=int, default=80, help="max hits to print (0 = all)")
    ap.add_argument("--full-labels", action="store_true",
                    help="print every answer option verbatim instead of trimming the missing-value tail")
    ap.add_argument("--context", default="", help="print codebook text around this variable code")
    ap.add_argument("--lines", type=int, default=8, help="context lines either side (--context)")
    ap.add_argument("--list-topics", action="store_true", help="show curated topics and exit")
    ap.add_argument("--html", metavar="PATH", nargs="?", const="dnbc_report.html",
                    help="write a polished, light-theme HTML report of the matches")
    ap.add_argument("--recode", nargs="?", const="r", choices=["r", "stata", "sas"],
                    metavar="LANG",
                    help="emit paste-ready recode code: r (default), stata, or sas")
    ap.add_argument("--table", action="store_true",
                    help="emit a ready-to-paste markdown table instead of console output")
    args = ap.parse_args()

    topics = load_topics()
    if args.list_topics:
        for name in sorted(topics):
            print("%-18s %s" % (name, " ".join(topics[name])))
        return

    rows = load_rows()

    if args.context:
        show_context(rows, args.context.strip(), args.lines)
        return

    terms = list(args.terms)
    if args.topic:
        key = args.topic.strip().lower()
        if key not in topics:
            sys.exit("Unknown topic %r. Try --list-topics, or pass terms directly." % args.topic)
        terms = topics[key] + terms

    if not terms and not args.var:
        ap.error("provide at least one search term, --topic, --var, or --context")

    # Wave filter.
    if args.wave:
        wanted = [SLUG_TO_LABEL.get(s.strip(), s.strip()) for s in args.wave.split(",")]
        rows = [r for r in rows if any(w in r["wave"] for w in wanted)]

    matchers = build_matchers(terms, args.exact)
    var_pat = re.compile(args.var, re.I) if args.var else None
    gates = gate_degree(rows)

    scored, section_only = [], 0
    for r in rows:
        if var_pat and not var_pat.search(r["var"]):
            continue
        if not matchers:
            scored.append((0.0, r))
            continue
        # A section banner is shared by every variable under it, so matching on it turns
        # one smoking header into 300 hits. Keep it opt-in and count what it would add.
        fields = [(r["var"], 3.0), (r["desc"], 2.0), (r["labels"], 1.0)]
        if args.section:
            fields.append((r["section"], 0.5))
        sq_fields = list(fields)
        total, matched, strongest = 0.0, 0, 0.0
        for rx, sq in matchers:
            best = 0.0
            for (text, weight), (sqt, _) in zip(fields, sq_fields):
                if rx.search(text) or (sq and squash_hit(sq, sqt)):
                    best = max(best, weight)
            if best:
                matched += 1
                strongest = max(strongest, best)
        # Score by the STRONGEST field a term hit, with only a small bonus per extra term.
        # Summing per term instead rewards verbosity: A132 inlines its seven sub-options,
        # so it matched both "smok" and "cigaret" and outranked A127 -- the screener that
        # gates it and the obvious variable to lead an answer with.
        total = strongest + 0.3 * max(0, matched - 1)
        hit = matched > 0 and not (args.all and matched < len(matchers))
        if not hit:
            if not args.section and r["section"] and any(
                    rx.search(r["section"]) or (sq and squash_hit(sq, r["section"]))
                    for rx, sq in matchers):
                section_only += 1
            continue
        # Verbatim codebook text outranks a row reconstructed from a parent's prose.
        if r["source"] == "extracted":
            total += 0.25
        total += gate_bonus(gates.get((r["wave"], r["var"]), 0))
        scored.append((total, r))

    scored.sort(key=lambda x: -x[0])
    total_hits = len(scored)
    shown = scored if args.top <= 0 else scored[: args.top]

    by_wave = defaultdict(list)
    for _, r in shown:
        by_wave[r["wave"]].append(r)

    def wave_sort_key(w):
        for i, tag in enumerate(WAVE_ORDER):
            if tag in w:
                return i
        return len(WAVE_ORDER)

    if args.html:
        if args.topic:
            title = args.topic.strip().replace("_", " ").capitalize()
        elif args.terms:
            title = " / ".join(args.terms[:4])
        else:
            title = "Variables matching %s" % args.var
        if args.topic:
            asked = args.topic.strip().replace("_", " ")
        elif args.terms:
            t = args.terms
            asked = (t[0] if len(t) == 1
                     else "%s or %s" % (", ".join(t[:-1]), t[-1]))
        else:
            asked = "the code pattern %s" % args.var
        subtitle = "You asked for variables related to %s. Here are the results." % asked
        emit_html(shown, gates, title, subtitle, args.recode or "r", args.html)
        return

    if args.recode:
        emit_recode(shown, gates, args.recode)
        return

    if args.table:
        emit_table(shown, gates)
        if total_hits > len(shown):
            print("_%d more matches; re-run with a narrower query or --top 0._" % (total_hits - len(shown)))
        return

    mode = "ALL" if args.all else "ANY"
    query = " ".join(terms) + (("  (var~%s)" % args.var) if args.var else "")
    print("# %d variable(s) matching [%s]: %s" % (total_hits, mode, query))
    if total_hits > len(shown):
        print("# showing the %d best-ranked -- pass --top 0 for all %d" % (len(shown), total_hits))
    if section_only:
        print("# %d more sit under a matching section banner -- add --section to include them"
              % section_only)
    print()

    for wave in sorted(by_wave, key=wave_sort_key):
        recs = by_wave[wave]
        print("## %s  (%d)" % (wave, len(recs)))
        section = None
        for r in recs:
            if r["section"] and r["section"] != section:
                section = r["section"]
                print("  [%s]" % section)
            mark = SOURCE_MARK.get(r["source"], " ")
            page = "p%s" % r["page"] if r["page"] else ""
            desc = r["desc"] or "(no description text)"
            n_gated = gates.get((r["wave"], r["var"]), 0)
            gate = "  [gates %d]" % n_gated if n_gated >= 5 else ""
            print("  %s%-10s %-5s %s%s" % (mark, r["var"], page, desc, gate))
            if not args.names and r["labels"]:
                compact, missing, warning = format_labels(r["labels"], args.full_labels)
                tail = "   missing: %s" % ",".join(missing) if missing else ""
                if compact:
                    print("              = %s%s" % (compact, tail))
                elif tail:
                    print("             %s" % tail.strip())
                if warning:
                    print("              ! %s" % warning)
            if not args.names and r["depends"]:
                print("              (%s)" % r["depends"])
        print()

    if any(SOURCE_MARK.get(r["source"]) for _, r in shown):
        print("# ~ reconstructed from the parent question  # range header  ^ inherited question stem")


if __name__ == "__main__":
    main()
