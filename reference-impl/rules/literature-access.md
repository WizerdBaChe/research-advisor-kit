---
paths:
  - "**/verify/*facts*.json"
  - "**/verify/w1*_*.json"
  - "**/*evidence*.{json,md}"
  - "**/record/W*證據表*.md"
  - "**/02_文獻證據/**"
  - "**/references/*.bib"
  - "**/fetch_*.py"
  - "**/*_wave*.py"
  - "**/literature-search-extract/**"
  - "**/EvidenceRuns/**"
  - "**/literature-host-policy.json"
review-when: the VPN resolves to an institution other than the one this policy was written under (a different licence governs, the allowlist is void); a routed publisher changes its Terms of Use; an official TDM API appears for a host on the hand-it-to-the-user row; a publisher blocks the institution's IP range (retires the whole automated row)
enforced-by: hooks/literature_host_guard.py, hooks/literature-host-policy.json
origin: a research-project literature wave 2026-09-10 (a VPN made four paywalled publishers reachable; the next thought was a headless browser with a logged-in profile); the IEEE Xplore ToU and library argument: skills/literature-search-extract/references/output-templates.md; fetchsrc incident L-075
---

# Literature access: the evidence artifact records how it was obtained, and never defeats an access control

- **A citation-bearing evidence artifact states, per source, the access route it came through and the licence basis for that route,** and never contains content obtained by circumventing a technical access control.
- **A source row whose `access` field says only "read the paper" is incomplete.** The field names the route (`open access` · `institutional IP via VPN, browser, human-paced` · `publisher TDM API` · `abstract only` · `handed to the user`) and, for an institutional route, that the reader was a Licensed User of that subscription.
- **An artifact may hold a quotation, a number and a citation obtained under a subscription,** never a redistributable copy of the licensed full text, and no deliverable built from it ships that copy onward (a proposal, deck or published page is not the Licensed Users audience).
- **Circumvention is out of scope, not merely risky:** the technical control IS the licensor's enforcement of the licence term. IEEE Xplore's Terms bar institutional subscribers from using robots or intelligent agents to ACCESS, SEARCH or systematically download; a person reading is licensed, a program is not, whatever its volume.
- **The consequence is institutional:** publishers suspend the subscribing institution's IP range, taking every researcher there offline, so this is a redline, not a judgement about volume. A headless browser or live SSO profile only makes access look human; a session never enters credentials to obtain access.

## Routing: try in this order, stop at the first that answers

- **1 Open access, preprint, repository, government report** (arXiv, OSTI, PMC, institutional repositories, publisher OA): no licence question, full text, quotable. Look here first even when the paywalled copy is reachable.
- **2 An official programmatic interface** where the project is entitled (Crossref, Unpaywall, OpenAlex for metadata; a publisher's own TDM API for text): the ONLY route on which systematic retrieval is legitimate.
- **3 Ordinary HTTP retrieval of hosts that serve it,** at human pace, for named targets, never a sweep. Measured hosts in `ops/environment.md` are facts with a shelf life, not a permission.
- **4 The in-app browser at human pace for a NAMED article,** on a host whose terms do not ban agent access: one target, one fetch, the citation recorded. This is the agent's boundary on a subscription.
- **5 Hand it to the user** for any host that bans agent access outright (IEEE Xplore) or answers with an anti-bot challenge: name the article, give the DOI and URL, and let the user open it.
- **An anti-bot challenge (202, 403, 418, a JS interstitial, a CAPTCHA, a proof-of-work page) is a routing signal, never a difficulty:** stop, record the host as hand-to-the-user for this wave, move on. Retrying with another user agent, cookie jar, headless browser or logged-in profile is the prohibited act; a CAPTCHA is never solved or bypassed.
- **The surface-escalation ladder is one act over four calls** (curl, WebFetch, headless browser, the user's logged-in browser): the last rung is the most prohibited.
- **Do not read a licence verdict out of a hook that is not about licences:** `browser_pane_scope_guard` denies third-party hosts in the in-app pane for blast-radius reasons and names claude-in-chrome as the alternative, which settles nothing about the publisher's terms. The licence question has no hook; check the host's terms before any surface is chosen.
- **This binds the dispatcher first:** a wave prompt that names a browser for a banned host has committed the violation. Name the routing table, not a surface, and keep step 5 reachable.
- **Recovery for a source already read this way:** keep the citation, mark its route non-compliant, and have the user (a Licensed User) re-open it and confirm any load-bearing quote; neither keep it silently nor delete the finding silently.

## What a wave may do

- **Named targets only:** "has anyone published X" is a metadata search (step 2) plus individual retrievals (steps 1, 3, 4), never a crawl of a publisher's corpus.
- **No mirroring:** a fetched PDF is working material in scratch; the repository gets the quote, the numbers and the citation.
- **The `still_open` list is part of the deliverable:** a gap whose only source sits behind a step-5 host is recorded as "not retrieved, hand-to-user, DOI …", never as "not found".
- **One quote per claim, as short as carries the fact;** a verbatim page of a paywalled article is redistribution.

## The instrument side

- **A fetch helper a project keeps prints, per source, the host, the route taken and the HTTP status,** so a paywall reads differently from an absence and a challenge from a 404; "no source found" for a target whose only host answered 403 misreports a routing outcome as an evidentiary one.
- **`fetchsrc.py` is the one fetch command a wave's brief names** (`ops/20-dispatch.md` §4a): it checks the host policy before every request, keeps per-host and per-run caps and prints `HAND-TO-USER:` itself. A brief that excludes the checked route instead of naming it sends the worker to an uncapped hand-written fetcher (L-075).
- **The caps are deliberately not in `literature_host_guard`** (no run to count in). Promotion trigger: L-075 at `hits: 3` moves this to an end-of-subagent notice (`ops/40-maintenance.md` §2a).
