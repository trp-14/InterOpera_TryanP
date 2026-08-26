# RFC: An Auditable Compliance Pipeline

## 1. How the LLM is structurally unable to source any number

The system does not ask the LLM to be honest; it makes the LLM's dishonesty
harmless by construction. Four separate mechanisms combine to do this, and
each one is redundant with the others on purpose — if any single one were
disabled, the others would still hold.

The first is dependency isolation. The `anthropic` package is imported in
exactly one file across the entire codebase: the narrative generator. Every
other module that could plausibly touch a number — the graph builder, the
figure computation engine, the reconciliation logic — has no code path that
could reach the LLM SDK even if a developer wanted it to, because the import
simply isn't there. This is checked mechanically, not just by convention: a
test walks the abstract syntax tree of every file under the graph and
compute packages and fails if any of them imports the LLM SDK or the
narrative package. A reviewer doesn't have to trust a comment saying "we
don't do that here"; the test fails the build if it stops being true.

The second is input restriction. The narrative generator receives one
argument: the already-computed, already-formatted list of figures — the
exact JSON that also gets written to disk and filled into the Excel report.
It does not receive the holdings CSV, the guidelines PDF, or the graph. An
LLM that has never seen a raw number cannot smuggle a plausible-looking but
fabricated one into its own output and have it look native to the source
data, because it genuinely has no access to any number that didn't already
pass through the deterministic compute layer first.

The third is firewall verification, which is the backstop for the case
where the first two hold and the LLM invents a number anyway — restating a
real figure inexactly, or fabricating a plausible-sounding one out of thin
air. Every numeric token in the generated narrative is extracted, normalised,
and checked against the set of numbers that actually appear in the computed
figures' value, limit, and utilization fields. A narrow, explicit whitelist
covers numbers that are legitimately not figures — a year, a reference to a
guideline section number, a duration written with its unit ("24 hours", "5
business days") — because those really do belong in compliance commentary
and rejecting them would make the firewall useless in practice. Anything
else causes the entire narrative to be discarded; the run still succeeds
with all 13 figures intact, just without prose commentary that day. Nothing
about this check calls a model — it's regular expressions and set
arithmetic, chosen deliberately, because verifying an LLM's claim with a
second LLM call would only add a second point of failure with the same
failure mode.

The fourth is the acceptance test that ties the first three together: with
`ANTHROPIC_API_KEY` unset, the narrative generator returns immediately
without attempting a network call, and `run` still produces a complete,
byte-for-byte identical set of 13 figures — only the narrative field comes
back empty. This was not just asserted; it was run. The practical
consequence is that the LLM is optional in the strongest possible sense: not
"optional but the numbers might be slightly different," but "optional, full
stop." A auditor can disable network access entirely and get the same
compliance report.

## 2. How a figure traces through the graph to its source

Every figure is the end of a real walk through the graph, and the walk
itself — not a string someone typed — is what produces the citation. Take a
simple allocation figure: the compute layer looks up the `AssetClass` node
for, say, Singapore Government Securities, follows its one `HAS_LIMIT` edge
to a `Limit` node, and that traversal (which nodes were visited, in what
order, over which edge types) is rendered into the `graph_path` string
attached to the figure's output. The `Limit` node itself carries the exact
page number and chunk ID it was extracted from during ingestion, because
that's where regex matching against the PDF's text found the "20% / 60%"
pair for that row — the citation isn't reconstructed after the fact, it's
the same provenance data that was attached to the node when the graph was
built.

More interesting figures make this concrete in ways a fixed example
couldn't. The aggregate non-investment-grade figure is normally satisfied by
two `AssetClass` nodes (High Yield, Structured Credit) that were wired to
the `Aggregate` node with `CONTRIBUTES_TO` edges back when the graph was
built — but under Firm B's method, one more position (a downgraded
corporate bond whose asset class is still nominally "Investment Grade")
qualifies through its credit rating, not through that pre-built edge. The
code does not pretend an edge exists that doesn't; it walks
`Position -[BELONGS_TO]-> AssetClass` for that one position instead and
appends that as its own segment in the path. Running `trace aggregate_non_ig
--firm A` and the same command with `--firm B` prints genuinely different
`graph_path` strings, not just genuinely different numbers, because the
underlying route through the graph really is different. If a figure's
citation cannot be resolved at all — a corrupted graph, a node that got
disconnected — the compute layer does not fall back to a bare number; it
catches the failure and reports that one figure as an explicit error, while
every other figure in the same run computes normally.

## 3. How a firm's method is expressed and switched

Every place two firms could plausibly disagree is represented as a value in
a YAML file, validated against a pydantic schema at load time, and read by
name from the compute layer — never as a branch on which firm is running.
Concretely, three things vary: how utilization is presented (a percentage
versus truncated basis points, with its own rounding rule), which positions
count toward the aggregate non-investment-grade exposure figure (an
asset-class list, optionally extended with a credit-rating rule), and how
government-related-entity issuers are grouped for the concentration figure
(by their own name, or by their parent's name). The compute code that
consumes these settings has no conditional that reads "if this is firm B" —
it reads `config.presentation.utilization.format`,
`config.figures["aggregate_non_ig"].include`, and
`config.figures["gre_concentration"].group_by`, whichever config object it
was handed. This was not just designed to be true; it was measured to be
true. Running the report for Firm A and then Firm B back to back, with
nothing edited in between, leaves every file under `src/` byte-identical —
checked directly, not inferred from the design.

Concretely, extending this to a third firm's method means writing
`config/firm_c.yaml`, expressing whatever it changes using the same
`include`/`filter`/`group_by`/`presentation` vocabulary already validated by
the config schema. The compute engine itself needs no changes to support it.
The one place a firm letter is still spelled out in code is the command-line
argument parser, which maps `--firm C` to a config file name — a
one-line addition to a lookup table in the CLI's entry point, not a change
to any file that computes a number. That file lives outside the boundary
the "no firm knowledge" rule actually draws (`src/compute`, `src/graph`,
`src/ingestion`); it exists precisely because *something* has to decide
which YAML file to open, and that responsibility belongs at the edge of the
system, not buried in the arithmetic.

## 4. How output reconciles to an answer key, and what tolerance is claimed

Reconciliation is an exact string match on the figure's value, its status,
and its limit text against the provided answer key — not a numeric
comparison with an epsilon, and not a percentage-based tolerance. This is a
deliberate choice, not an oversight. Both sides of the comparison are
already-rounded, already-formatted display strings — "35.0%", "OK",
"20–60%" — because the rounding rule itself (`ROUND_HALF_UP` to one decimal
place for percentages, two for duration, applied once, at presentation time)
is part of the specification the answer key was generated against. Given a
fixed rounding rule and correct arithmetic, the output is either exactly
right or it reveals a real bug; a fuzzy tolerance would only paper over the
difference between "computed correctly and displayed at the wrong
precision" and "computed incorrectly," which are not the same failure and
should not be hidden behind the same threshold. For a compliance report
that answers whether a fund breached a regulatory limit, "close enough" is
not a meaningful standard in the first place.

The one place this would have silently gone wrong is the DV01 figure, and
it's worth stating plainly because the guidelines document warns about it
explicitly: DV01 is computed from the portfolio's *unrounded* weighted-average
modified duration (3.879 years), not from the 3.88 that gets displayed for
the duration figure itself. Using the rounded value would produce 38,800
instead of the correct 38,790 — an error that would only show up as a
failed reconciliation, not as an obviously wrong number. The fix is
structural rather than a special case: rounding happens exactly once,
inside the formatting layer, immediately before a value is turned into a
display string, and never at any earlier point in a calculation that
another figure might depend on.

No separate answer-key workbook was provided for Firm B. `evaluate --firm B`
derives its reference by taking Firm A's answer key and overriding exactly
the two figures that Firm B's brief documents as different, then applies the
same exact-match comparison. Every other figure is expected to match Firm
A's answer key precisely, which is itself part of the claim being tested —
Firm B's method should only ever produce different numbers where it's
supposed to.

## A note on ingestion's honesty

CLAUDE.md's design allows non-numeric extraction during ingestion (breach
actions, owners, retention periods) to be LLM-assisted, gated behind a
verbatim-span check and a human-review threshold on extraction confidence.
That gate is real and wired up — any node below the confidence threshold
routes to a review file and blocks auto-approval. In this implementation,
however, no LLM call actually happens during ingestion: the guidelines
document's breach-action column parses cleanly with the same kind of regex
extraction used for the numeric limits, so the LLM-assisted path was never
exercised. One column did not parse cleanly at all — the section 4 retention
table has genuinely corrupted, character-interleaved text in the source PDF
— and rather than reach for an LLM to guess at it, that data is left as an
explicit `None` with the raw corrupted text preserved for a human to read,
because it's metadata, not a figure, and guessing at it would violate the
same principle the rest of this system is built around.
