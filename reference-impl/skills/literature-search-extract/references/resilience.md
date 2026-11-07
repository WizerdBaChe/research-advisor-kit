# Resilience & session economy

Moved out of `SKILL.md` on 2026-10-12 (WC-15c headroom pass: the file stood at the
300-line cap), text unchanged. `SKILL.md` keeps a one-line digest of the four rules
and points here.

- **Context/token budget.** Full-text reading is the expensive step. Past ~10 `[full]`
  reads, warn the caller with a volume estimate, then narrow or batch: extract each
  source into compact target-list notes, discard the raw text, run P5 from notes only.
- **Reuse before re-search.** `loop/runs.py open` (P1) searches the evidence-run index for
  the same question and writes `reuse_check` into `run.json`; its line goes into
  `search_trail` (`register` refuses a run without it). On a hit, offer an UPDATE run: seed
  P2 with the prior `sources` + `search_trail`, search only unfilled gaps and the period since.
- **Partial failure returns a partial, resumable contract.** If the run dies mid-pipeline,
  still return the contract — `gaps` names the unprocessed portion, `search_trail` is
  complete to the failure — so a later run resumes by seeding P2 from that trail.
- **Feedback iteration.** When the caller says the extraction aimed at the wrong thing,
  do not restart: re-run P1 to rewrite the target list (at most ONE clarifying
  question), keep the P2 pool and P3 triage, redo P4→P5 only where targets changed.
