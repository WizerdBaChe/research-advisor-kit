# Connector layer — contract

How this skill reaches a data-collection system that is not a web search: a
local tool, a keyed API, a reference manager, a patent database. Three files:
this contract, `registry.json` (routing table + capability wishlist), and
`probe.py` (the only code allowed to touch a credential).

Read this before adding a connector or before routing P2 to one.

## C1 — The secret boundary is one-way, and it is enforced

**The agent may RUN a program that holds a credential. The agent may never READ
the credential.** Not "should not" — `~/.claude/hooks/secret_file_guard.py`
denies `Read`, `Grep`, `Bash` and `PowerShell` calls that reference a
credential-shaped filename, machine-wide, in every permission mode including
bypass (verified end-to-end 2026-08-26 by attempting `cat` on a real `.env`).

The property belongs to the FILE, not to a directory or a workflow: a file whose
name marks it as a credential store is unreadable wherever it sits. Templates
(`.env.example`, `.env.sample`, `.env.template`) are explicitly readable — that
is how the agent learns which variables a connector needs without learning their
values. Two-sided calibration: `~/.claude/tools/secret-guard-test/` (12
must-deny, 15 must-pass — a guard that denies everything is not a guard).

What follows from C1, and is the whole reason the boundary is usable:

- A key can be added to this machine **without the agent ever being in the
  room**. The user edits a `.env`; the agent's next probe simply starts
  reporting `present`.
- A key **cannot leak through the transcript**, because it is never in context.
  Session archives, compaction digests, and any future share/export inherit
  this for free.
- The agent debugging a 401 has exactly one move: run the probe and read
  `present (48 chars)` / `placeholder` / `absent`. It cannot "just check the
  key", so it cannot paste one.

## C2 — What a connector must provide

| Requirement | Why |
|---|---|
| An **invoke surface** the agent can call without a secret — a loopback HTTP endpoint or a CLI entrypoint | The connector loads its own credential; the caller passes only a query |
| A **probe** that answers live/dead cheaply and **spends no metered quota** | Routing decisions must not cost the user money or credits |
| **Redaction evidence** — a named place in the connector's code that keeps values out of stdout, logs and tracebacks | Verified once, cited in the registry (PatentsGrabber: `config.py OpsConfig.describe()`/`__repr__`) |
| A declared **access ceiling** (`full`/`partial`/`abstract`) | Feeds the P3 access tag directly; a connector that can only return metadata must never yield a `[full]` tag |
| A declared **cost meter** and a `search_trail_label` | The skill's cost-transparency rule needs a name for what was spent |
| A declared **terms boundary** | Some connectors carry contractual limits (EPO OPS 3.2 forbids redistributing OPS data publicly) that bind the DELIVERABLE, not just the call |

## C3 — Probe before route, every session

`probe.py` checks four things, and the order reflects what actually goes wrong:

1. `reachable` — is the process up.
2. `contract` — do the endpoints `registry.json` promises still **exist in the
   running process**. This check exists because of a measured failure: on
   2026-08-26 the live PatentsGrabber server was older than its own source and
   had no `/api/query`. Without this check the skill routes to a 404 and reads
   it as **"no results"** — a silent false negative, the worst failure shape
   this skill has.
3. `credential` — present / placeholder / absent, by length only.
4. `leak` — no credential value appears in any response body captured during
   the probe. The scanner has its own two-sided calibration (`--selftest`): a
   scanner that never fires is not a scanner.

Severity follows the gate-severity-by-consumer ruling (2026-08-26):

- **FAIL** — `leak` and `contract`. A leak is a security invariant; contract
  drift means a hard call to something that is not there. Do not route.
- **WARN** — `reachable`, `credential`. An LLM reads these and degrades the run
  honestly. **Named promotion trigger:** a WARN becomes a FAIL the moment a
  deliverable cites that connector as a source. Unreachable is a legitimate
  reason to skip a channel; it is never a legitimate reason to cite it anyway.

## C4 — How a connector enters P2

A connector is a **rung on the P2 tool-priority ladder**, above web discovery
when it holds authoritative primary documents and above nothing when it does
not. Registered connectors do not change the pipeline — P1 targets, P3 triage,
P4 locators, P5 gaps all apply unchanged. They change only *where a source came
from*, which means:

- `search_trail` names the connector and what it spent (`search_trail_label`).
- The access tag comes from what was actually read, capped by
  `access_ceiling` — never above it.
- A connector's `terms.boundary` is copied into the deliverable when the user
  might publish it.

## C5 — Adding one

1. Add the entry to `registry.json`. Never a credential value — only the
   variable NAME and the file PATH.
2. Confirm the redaction evidence by reading the connector's own config code,
   and cite it in the entry.
3. `python probe.py --id <new> ` until `contract` and `leak` are OK.
4. If it needs a key, tell the user which variable and which file. Then stop —
   they fill it, and the probe confirms without either of you naming a value.
5. Add a routing line to `references/connectors.md` so P2 can find it.

## C7 — Ambient capabilities (a VPN) get inverted rules

Everything above assumes a capability is **scoped**: a key reaches one connector,
consent is per-service, and a decline stays declined. A campus client VPN is the
opposite — it is **ambient**. While it is up it changes the network identity of
every call the machine makes, including ones that have nothing to do with the
entitlement it was connected for.

So the rules invert. For a scoped connector the question is "is it available?"
For an ambient one it is "should this particular call be inside the window?"

| | Scoped (key, local tool) | Ambient (VPN) |
|---|---|---|
| Who turns it on | either; the probe reports state | **the user only** — it is a credential login, and the agent never even asks for it mid-task |
| Default | use it when it matches the source class | **do not route through it**; use only for already-identified documents needing full text |
| Blast radius of being wrong | one channel degrades | every channel's traffic becomes institutionally attributable |
| The failure that costs something | a wasted call | **the user's institutional account**, suspended for systematic downloading |
| Consent | per-service, recorded in the registry | per-**window**, and narrow: connect, fetch the named documents, disconnect |

Two consequences worth stating separately because they are easy to miss:

- **Do discovery and identifier resolution OUTSIDE the window.** Resolving forty
  DOIs against Crossref while the VPN is up makes forty institutional requests
  the user never intended. Narrow the window to the fetches that actually need
  the entitlement.
- **A run that wants twenty documents through it is a bulk download wearing a
  different name.** Past roughly five, stop and ask — the number is not the
  danger, the shape of the request is.

## C6 — What this layer is NOT

Not a general secret manager, not a credential broker, not a way to grant the
agent access to anything. It is the opposite: a structure that lets the user
add capability **while shrinking** what the agent can read. Every connector
added makes the agent more capable and no more trusted.
