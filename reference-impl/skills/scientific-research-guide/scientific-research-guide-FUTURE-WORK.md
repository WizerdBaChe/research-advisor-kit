# scientific-research-guide — Future Expansion Notes (planned 2026-07-07, not yet implemented)

> Context: skill v1 + the plasmonic domain profile merged to main on 2026-07-07
> (commit aaa167d). This file records expansion items that have already been
> evaluated and are awaiting a future session's decision/implementation, ordered
> by value-to-risk ratio.
> On resuming work: reading this file alone should be enough to rebuild context —
> no need to re-read the original conversation.

## Backlog (priority order)

### ① Research-state file mechanism — IMPLEMENTED 2026-07-12
- Goal: zero re-explaining across sessions. Each research project maintains a
  `research-state.md` (current Tier, per-section completion, iteration log —
  i.e. a living-document version of the tier-framework §7.4 output artifact).
- Done: SKILL.md Gate A gained a "Continuity check (fires before Step 0)" that
  reads `research-state.md` first and rebuilds state without re-asking; Gate D
  gained a consent-gated update rule (offer on tier/decision/iteration advance,
  write only on yes, append-only iteration log). Template added to
  deliverables.md (跨 Session 進度追蹤器). Eval case 5 + fixture
  (evals/fixtures/research-state.example.md) added and run.
- Branch: feat/research-state-mechanism.

### ② scripts/ deterministic analysis tools (wait for repeated need to emerge; don't build ahead of time)
- Candidates: statistical-test selector, Bootstrap 95% CI (>=10,000 resamples, interval type stated; method-selection.md [S1]),
  four-panel residual diagnostics, PRISMA counter.
- Principle: skill-creator's "package only once you see repetition" — the same
  analysis must be hand-written ≥2 times in actual use before it's worth
  promoting into scripts/.
- Boundary: execution still falls under Gate C (only runs on explicit request),
  consistent with "semi-automatic = propose → confirm → execute."

### ③ Tier 1 literature-scan dispatch (don't extend this skill — compose instead) — HOOKED UP 2026-07-07
- Primary route (targeted search + extraction with citation traceability): delegate
  to the `literature-search-extract` skill (Mode 2, request/result contract). This is
  now wired into SKILL.md Gate B and tier-framework.md §1. Use it for locating sources
  and extracting methods/parameters/limits per §1.1/1.3/1.4/1.6.
- Secondary route (broad multi-source topic reconnaissance): the SAME skill at
  `depth: exhaustive` (PRISMA record, per-claim ledger). The `deep-research` skill this
  bullet once named never existed on this machine (verified 2026-09-03; tombstoned in
  the trigger dict). An uncited wide sweep is a T4 research dispatch (`ops/20-dispatch.md` §6).
- Constraint: subagent model cap is haiku/sonnet (see memory:
  subagent-model-cost-cap); workflow-level multi-agent dispatch requires
  explicit user request each time.

### ④ settings.json hooks — evaluated, **not adopted**
- Reason: a global hook would pollute non-research conversations, which
  conflicts with this skill's on-demand trigger nature; item ① achieves the
  same goal at lower cost.

## Fixed procedure for adding a new domain — MOVED (2026-08-25)
The canonical, current version of this procedure is `domains/domain-expansion-guide.md` §9
("Authoring pipeline: from source packet to registered profile"). It supersedes the 5-step
list that used to live here (that list predated the Source Ledger requirement, the lint
script, the sibling-cluster shape, and the Node-8 abolition). Do not follow a copy from this
file; open the guide.

## Other open items
- **B-2 回顧類型分類＋Boote & Beile 自評（researcher.tw 借用帳，2026-09-14 延後）**：§1 在 PRISMA
  之前先選回顧類型（敘述性／整合性／範疇性／系統性；Grant & Booth 2009、Snyder 2019），只有系統性回顧
  才走 PRISMA；Boote & Beile 2005 五維當學位論文文獻回顧章的自評表。延後原因：一手文獻未讀，不從二手
  摘要折入；本輪核心是 B-7。觸發：使用者寫學位論文的文獻回顧章，或本 skill 對一章敘述性回顧建議 PRISMA
  時。紀錄：`~/.claude/outputs/researcher-tw-borrow-review-2026-09-14.md` §3。
- ~~B-4 投稿段~~ **2026-09-14 已做**（使用者同意 R1 建議形狀）：tier-framework §6.7＋deliverables.md T6b 模板
  與 T6 清單一項；未動 SKILL.md、未加觸發詞，Tier 6 才載入。待驗：第一次真實「準備投稿」對話是否真的展開
  §6.7、且沒有在非投稿的 Tier 6 問題（例如只問誤差棒）上硬塞投稿步驟。
- **既有技術債（2026-09-14 發現，本輪未修）**：tier-framework §1.1 仍寫「若 prism MCP 可用」——prism 已於
  2026-08-27 退役（literature-search-extract registry 的 tombstone 列）。
- The description-trigger optimization loop (skill-creator's run_loop, 20
  should/should-not queries) has never been run; run it if under- or
  over-triggering is observed.
- config-self-audit has not yet run a formal audit on this skill.

## Status log
- 2026-08-24 — step 4 of the fixed procedure ("wire in at three places") executed for the
  whole backlog at once: SKILL.md's description now lists all nine domain families,
  `~/.claude/skill-trigger-dict.md` gained the nine-profile entry + the packaging-cluster
  disambiguation, and evals/evals.json gained routing cases 6-11. Eleven cases run (sonnet,
  one subagent each): 11/11 pass, 47/47 assertions — but case 11, the negative control,
  failed 3 of 4 on first run and forced a real fix to SKILL.md (Gate A Step 0.5, scope
  check). Lesson worth keeping: five profiles had shipped over three weeks with the eval
  step deferred each time, and the first negative control written found a defect
  immediately. Deferring step 4 per-domain is what let it accumulate; do it in the same
  change as the profile.
- 2026-07-12 — evals/evals.json executed for the first time (4 cases, sonnet /
  Sonnet 5, protocol-level grading via 4 subagents): 4/4 pass, 15/15 assertions.
  One known limitation recorded in the file's `run.known_limitation` (generic
  metrics have no calibrated range-check; only loaded domain profiles do).
  Behaviour is now verified, not just designed. See STATUS.md for the full picture.
- Note on backlog item ②: scripts/ is a DELIBERATE deferral (build only once the
  same analysis is hand-written ≥2×), NOT an unfinished gap — do not treat as
  incomplete in a future audit.
