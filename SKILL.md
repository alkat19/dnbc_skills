---
name: lookdnbc
description: >-
  Look up DNBC (Danish National Birth Cohort) study variables by topic across all
  questionnaire waves. Use this whenever the user asks to find, list, or identify DNBC
  variables related to a concept (e.g. "find variables about smoking", "which variables
  cover maternal depression / breastfeeding / infections / childhood adversity?"), asks
  what variables exist in a given wave, needs variable names, descriptions, or answer
  labels from the DNBC codebooks, or is deciding which variables to pull during
  preprocessing. Searches a pre-built dictionary of ~7,900 variables from the Interview
  1-4, 7-year, 11-year (child & adult) and 18-year follow-up codebooks and returns
  matches grouped by wave with each variable's name, description, and value labels.
  Trigger this even when the user only names a topic and asks "what DNBC variables are
  there for this?", or references a codebook, a wave, or a variable code such as A018,
  E_QDATE, Z004_1, or A031_5.
---

# lookdnbc — DNBC variable finder

Help find the right DNBC variables for a topic. Given a concept, return the matching
variables across waves with their **name**, **description**, and **answer labels** — the
information needed to decide what to load and how to recode it during preprocessing.

The searchable data is already built into this skill (no PDF parsing at query time):

- **[references/dnbc_variables.tsv](references/dnbc_variables.tsv)** — the dictionary,
  7,989 rows, one variable per line, tab-separated:
  `wave · var · page · description · labels · depends_on · section · source`.
  Fully self-contained per line, so a single match shows everything.
- **[references/topics.tsv](references/topics.tsv)** — curated `concept → terms` maps
  behind `--topic`.
- **[references/text/](references/text/)** — the clean full text of each codebook (`i1.txt`
  … `y18.txt`). `--context` reads these for you; open one directly only when you need
  more than it shows.

## Waves covered

| slug | wave | code prefixes |
|------|------|---------------|
| `i1` | Interview 1 — prenatal, ~12 wk gestation | A |
| `i2` | Interview 2 — prenatal, ~30 wk gestation | B |
| `i3` | Interview 3 — postnatal, ~6 months | C, P |
| `i4` | Interview 4 — postnatal, ~18 months | D, S, R, O, T |
| `y7` | 7-year follow-up | Z |
| `y11c` | 11-year follow-up — child self-report | E, E_ |
| `y11a` | 11-year follow-up — adult/parent report | F, F_ |
| `y18` | 18-year follow-up | G, G_ |

## The `source` column — how much to trust a row

Every row is a real data column, but not every row's wording came straight off the page.

| `source` | n | what it means |
|----------|---|---------------|
| `extracted` | 4,205 | lifted verbatim from the codebook |
| `expanded` | 3,524 | a column the codebook names only in passing — a member of a folded range (`A031_1-A031_40`, "see master list"), or a sub-code listed inside its parent's text (`A009_1. regular pills`). The code is real; the description is inherited from the parent |
| `range-header` | 248 | the codebook's own range shorthand (`P061.1-47`). Useful for full-text search, **not** a column name — the real columns use the underscore form |
| `stem-inherited` | 12 | a bare tick-box option (`Z004_1  1. Crêche`) reunited with the question printed above it |

`search.py` marks these in output: `~` expanded, `#` range-header, `^` stem-inherited.
When precision matters on a marked row, confirm with `--context <CODE>`.

### Known gap: matrix-layout questions

A few questions are printed as a grid, with the codes sitting *inside* the row rather than
at the start of a line:

```
High blood pressure    Z112ADU 1.    Z112AAND 1.
High cholesterol       Z112BDU 1.    Z112BAND 1.
```

The extractor is line-anchored, so those cells get no row of their own — the parental
lifestyle-health grid (`Z112*`/`Z113*`, where `DU` = the respondent and `AND` = the other
biological parent) is the main example. If a code lookup comes back empty and the code has
a letter suffix, **run `--context <CODE>`** — the grid is fully readable in the wave text
file even when the dictionary has no row for it.

## How to search

```bash
python3 scripts/search.py <term> [<term> ...] [--topic NAME] [--all] [--wave i1,y11c]
                          [--var REGEX] [--names] [--top N] [--section] [--exact]
python3 scripts/search.py --context A127 [--lines 8]
python3 scripts/search.py --list-topics
```

- **Default = ANY term** (broad recall). `--all` requires every term (narrowing).
- `--topic smoking` pulls curated terms from `topics.tsv` — start here when the concept is
  a common one. `--list-topics` shows all 18.
- `--wave` restricts to wave slugs. `--var REGEX` matches the variable code only
  (`--var "^E_"` for key variables, `--var "^A031_5$"` to identify one column).
- `--names` is one compact line per hit — good for a first scan.
- `--top N` caps output (ranked best-first). **The default is 0 — everything.** Pass a
  limit only when the user explicitly asks for a short list; never trim a search they
  intend to use for variable selection.
- `--html PATH` writes a polished, light-theme HTML report of the matches (see
  **Offer the HTML report**). `--title` sets its heading and `--subtitle` the line under
  it; the default subtitle names the waves covered.
- `--recode [r|stata|sas]` emits paste-ready recode code (R/dplyr by default). Ask which
  they use if it is not obvious; `--html` embeds whichever language was chosen: every column is mapped onto its
  own answer labels and every missing code sent to NA, so whether an item is coded
  `1=yes 2=no` or the reverse never has to be reasoned about. Offer it whenever someone is
  heading into preprocessing.
- `--table` emits the finished markdown table (see **Presenting the results**) — this is
  the normal way to answer a variable-lookup question.
- `--full-labels` prints every answer option verbatim. By default the missing-value tail
  is collapsed to `missing: 3,4,9,10` and a `!` line flags coding that will surprise you.

### Reading the output

```
 A128       p40   Do you smoke now?  [gates 51]
            = 1=yes, every day - 2=yes, less than every day - 3=no   missing: 4,5,9,10
            ! "no" is 3, not 2 (3 levels, several mean yes)
```

- **`[gates N]`** — N other variables are only asked if this one was answered. A high
  number means this is the screener for the topic, so **lead the "Start here" table with
  it**; results are ranked to put these first.
- **`=`** — the informative answer options.
- **`missing:`** — codes to recode to NA before use.
- **`!`** — the coding will catch you out: either a reversed binary (`1=No 2=Yes`) or a
  multi-level item where "no" is not 2. Always repeat this in the answer.
- `--section` also matches a variable's questionnaire section banner. Off by default
  because one banner is shared by hundreds of variables; the footer tells you how many
  extra hits it would add.
- `--context CODE` prints the codebook text around a code — its question stem, its skip
  logic, its neighbours. Use it instead of opening the text files by hand.

### Terms are expanded for you

The codebooks are **English**, written up from Danish questionnaires — you never need to
search Danish (about 30 Danish words survive in 118,000, and they are cigarette brands,
vitamin tins and town names). What you do need to survive is the wording drift, which runs
*within* a single book: Interview 3 alone spells breastfeeding six ways — `breast feeding`
×18, `breastfeeding` ×7, `breast-feed` ×2, `breast-fed` ×2, `breastfeed` ×1,
`breast feedings` ×1. British and American spellings sit side by side too (`colour` ×3
next to `color` ×10, `centre` ×16 next to `center` ×1).

`search.py` handles this: every term is stemmed (`smoking` → `smok`) and matched again
with all spaces and hyphens squashed out, so one term catches every compound spelling.
`breastfeed` now returns 45 hits where the raw phrase returns 5. Pass `--exact` for plain
regex when you want literal control.

**Still worth doing:** pass 3–6 synonyms, not one word, because synonyms are a different
problem from spelling. `--topic` does this for the common concepts:

| User asks for… | Run |
|----------------|-----|
| a common concept | `search.py --topic smoking` (see `--list-topics`) |
| something else | `search.py <4–6 synonyms>` — e.g. `search.py rash itch eczema dermatit` |

When results look thin, add synonyms or shorten a stem. When results are noisy, narrow
with `--all` or `--wave`.

## Presenting the results

**Run `--table` and paste what it gives you.** It emits the finished deliverable — the
columns an epidemiologist needs before writing a model — so there is nothing left to
compose:

```bash
python3 scripts/search.py --topic smoking --wave i1 --top 8 --table
```

```
### Interview 1 (prenatal, ~12 wk gestation)

| Variable | Measures | Type | Recode | Asked of |
|---|---|---|---|---|
| `A127` * | Did you smoke during pregnancy? | binary | 1=yes · 2=no  |  NA: 3,4,9,10 | all respondents |
| `A128` * | Do you smoke now? | categorical | 1=daily · 2=less · 3=no  |  NA: 4,5,9,10 | if A127 answered |

**Check the coding:** `A128`: "no" is 3 here, not 2

`*` = screener; the others are only asked of people who answered it.
```

Why these columns: **Type** decides the model term; **Recode** is the line of code they
have to write; **Asked of** is the one an aggregate table normally hides — 53% of
variables are gated by a prior answer, so their missingness is structural and a
complete-case model on one silently conditions on its gate.

### Offer the HTML report

**After presenting the table, always offer the report** — one line, at the end:

> Want this as a formatted HTML report? I can generate one with the tables, the coding
> cautions and a paste-ready recode block.

If they say yes:

```bash
python3 scripts/search.py --topic smoking --wave i1,i2 --title "Smoking in pregnancy" --html dnbc_smoking.html
python3 scripts/search.py --topic smoking --recode stata --title "Smoking in pregnancy" --html dnbc_smoking.html
```

**Always pass `--title`, naming the concept the user asked about** — the report is a
document they will send on, and its heading should read as a subject ("Psychotic
experiences"), not as the query that found it. Without it the heading falls back to the
topic or the term list, and a `--var` search — where the query is a code regex that must
never reach the page — is headed only "Selected variables". The default subtitle names the
waves covered, which is usually what you want; pass `--subtitle` when a sentence of
framing helps ("Child self-report at 11 and 18, with maternal history from the prenatal
waves").

It writes a standalone light-theme page (no dark mode, by design) holding the same rows,
the same cautions and the same recode block as the terminal output — built from the
dictionary, not composed, so it cannot say anything the data does not. Name the file after
the concept. Offer once; if they decline, do not ask again in that conversation.

### The whole response, in order

1. **One line** naming the concept, the waves, and the child's age at each. Temporality is
   the first thing an epidemiologist checks — no preamble, no restating the question.
2. **The `--table` output**, unedited.
3. **At most two lines** afterwards, and only if they prevent a mistake — a differing "no"
   code, a variable that lives in the registry rather than the questionnaires, a wave that
   asks retrospectively rather than contemporaneously.

That is the whole answer. Resist adding sections: a background paragraph, a "how to use
this" section, or restating the coding in prose all make it harder to act on.

### Rules

- **Never invent a dataset, file, or column name.** This dictionary holds variable codes,
  waves and page numbers — it does **not** know what the SAS/Stata files are called, so do
  not guess one. Naming a file you have actually read from the user's own code is fine and
  useful (`Pre_Processing.R` reads `i1_samlet.sas7bdat`); say where you got it.
- **Always carry a `!` warning through** into the "Check the coding" line. It fires on
  only 216 of 7,989 rows, so when it fires it matters: 120 are two-level items coded
  `1=No 2=Yes`, the reverse of the convention used across most of the DNBC, and the rest
  are multi-level items where several options mean yes. It stays silent on conventional
  0/1 tick-box dummies and on ordinal scales where "no" is simply the low anchor.
- **Expand a multi-select only when asked.** `A132` is one row reading
  `multi-select set (7)`, not seven rows.
- **Define a term the first time it appears** — say "one yes/no column per option
  (`A130_1` is week 1)", not "master list".
- **Say when a row is `expanded` or `range-header`** and exact wording matters — one clause.

If the concept lives in the **registry** datasets rather than the questionnaires (see the
project's `CLAUDE.md`) — birth weight, income quartiles, clinical diagnoses — say so in one
line rather than implying it doesn't exist.

## Maintenance

The dictionary is prebuilt and committed: there is nothing to install and nothing to
rebuild at query time. The extractor, the regression suite, and the eval harness are
maintained separately and are not distributed with the skill. If a row looks wrong,
report it as an issue — do not try to regenerate the dictionary from here.

## Raw grep fallback

`search.py` is the primary path. If it is ever unavailable, the TSV is plain grep-friendly
since each line is one complete record — but note grep gets none of the stem/compound
expansion, so search short stems:

```bash
grep -iP "\t[^\t]*(depress|sad|mood)" references/dnbc_variables.tsv   # by any term
grep -iP "\tE_QDATE\t" references/dnbc_variables.tsv                  # by exact code
cut -f1,2,4 references/dnbc_variables.tsv | grep -i breast            # wave, code, desc
```
