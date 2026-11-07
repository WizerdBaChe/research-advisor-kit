#!/usr/bin/env node
// Regeneration source for docs/assets/flow.<lang>.svg — the README "運作流程" / "How it flows" diagram.
// audience-fit A1 with no engineering original: reader = a first-pass README visitor. Every node and
// edge maps to a line of the two shipped SKILL.md files (R5 table: --mapping, copied into
// docs/DEVELOPER.md). Drawn per presentational-view R1-R15 with the vocabulary of the sibling repo
// diagram-audience-fit's pipeline figure: grey capsule = outside the two roles, blue = step,
// amber = what you receive, pink diamond = check; blue numbered = main path, grey = side branch,
// red dashed = sent back. Layout is hand-placed on a grid; the model asserts rule on geometry
// (R10/R11 + endpoint and edge-through-node checks) and the layout is built with zero crossings,
// which is asserted too (no line hops needed).
//
//   node docs/assets/flow.build.mjs [--lang en]  build + model asserts (exit 1 on any FAIL)
//   node docs/assets/flow.build.mjs --selftest    known-bad controls must FAIL (exit 2 if not)
//   node docs/assets/flow.build.mjs --mapping     print the R5 node/edge -> source table
//
// The PNG and the in-browser text-fit check come from build_assets.py --only flow.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const li = process.argv.indexOf('--lang');
const LANG = li > 0 ? process.argv[li + 1] : 'zh-TW';
if (!['zh-TW', 'en'].includes(LANG)) { console.error(`unknown --lang ${LANG}`); process.exit(2); }
const SIZE = {  // W node, DW diamond width, CAP capsule width, PITCH column pitch
  'zh-TW': { W: 148, DW: 176, CAP: 180, PITCH: 312 },
  en: { W: 172, DW: 196, CAP: 204, PITCH: 360 },
}[LANG];

// ── anchors (R11): every coordinate derives from these ───────────────────────
const W = SIZE.W, H = 64, DW = SIZE.DW, DH = 88, PITCH = SIZE.PITCH, CAP = SIZE.CAP;
const X0 = 40 + CAP / 2;
const COL = [0, 1, 2, 3, 4].map((i) => X0 + i * PITCH);
const PAD = { x: 28, top: 64, bottom: 56 };
const G1_TOP = 20;
const ROW1 = G1_TOP + PAD.top + DH / 2;
const G1_BOTTOM = ROW1 + DH / 2 + PAD.bottom;
const G2_TOP = G1_BOTTOM + 52;
const ROW2 = G2_TOP + PAD.top + DH / 2;
const ROW3 = ROW2 + 170;
const G2_BOTTOM = ROW3 + DH / 2 + PAD.bottom;
const ROW4 = G2_BOTTOM + 110 + H / 2;   // below the librarian group: the papers-only exit
const ROWS = { 1: ROW1, 2: ROW2, 3: ROW3, 4: ROW4 };
const ARC = 26;                  // run between a check's vertex and its send-back line
const MARK = 10;                 // arrowhead length; terminal run >= 1.5 * MARK (R10)
const RET = 40;                  // the return line keeps this far outside the librarian group
const LEGEND_Y = ROW4 + H / 2 + 40;

const C = {
  ink: '#1f2328', mute: '#57606a', bg: '#ffffff', groupFill: '#fafbfc', groupLine: '#d0d7de',
  accent: '#0969da', side: '#6e7781', back: '#cf222e',
  ext: ['#eef1f4', '#57606a'], step: ['#ddeafb', '#3b74c9'], out: ['#fcecc9', '#c58a16'], check: ['#fce4ee', '#bf1f5a'],
};

const TEXT = {  // one term per thing with README.md / README.en.md (R14 B-19)
  'zh-TW': {
    title: '運作流程',
    g1: '① 研究顧問（scientific-research-guide）', g2: '② 文獻員（literature-search-extract）',
    legend: ['主路徑：照編號讀', '旁支', '對不上時退回'],
    Q: ['你的研究問題', '卡在哪・下一步'], LOC: ['先判斷階段', '在研究的哪一步'], DIAG: ['下一步與理由', '缺什麼・風險在哪'],
    SRCH: ['依需求搜尋', '拆需求・找來源'], POL: ['准不准讀取'], EXT: ['抽取內容', '記下頁碼或表號'],
    CC: ['引用查核'], RES: ['交付結果', '出處・缺口・可信度'], U: ['交給你自己開', '記為缺口'],
    OUT: ['書單直接給你', '不做階段診斷'],
    e2: '需要文獻', e4: '准', e6: '原句在原文', e7: '交回顧問',
    sDirect: '不需文獻', sOnly: '只找文獻', sBan: '禁止或驗證碼', sGap: '列為缺口', b1: '對不上：改寫或刪除',
  },
  en: {
    title: 'How it flows',
    g1: '① Research advisor (scientific-research-guide)', g2: '② Librarian (literature-search-extract)',
    legend: ['main path: read by number', 'side branch', 'sent back on no match'],
    Q: ['Your question', 'stuck where · next'], LOC: ['Locate the stage', 'which research step'], DIAG: ['Next step', 'reasons · missing · risks'],
    SRCH: ['Search to need', 'targets · sources'], POL: ['Access allowed?'], EXT: ['Extract', 'page · table · figure'],
    CC: ['Citation check'], RES: ['Deliver results', 'sources · gaps · confidence'], U: ['Handed to you', 'recorded as a gap'],
    OUT: ['Booklist to you', 'no stage diagnosis'],
    e2: 'needs literature', e4: 'allowed', e6: 'span in source', e7: 'back to advisor',
    sDirect: 'no literature', sOnly: 'papers only', sBan: 'banned / CAPTCHA', sGap: 'as a gap', b1: 'no match: rewrite or drop',
  },
};
const T = TEXT[LANG];

const SRG = 'scientific-research-guide/SKILL.md', LSE = 'literature-search-extract/SKILL.md';
// kind: ext | step | out | check.  src = the shipped text each node depicts (R5).
const nodes = [
  { id: 'Q', kind: 'ext', col: 0, row: 1, w: CAP, src: `${SRG} L44 Gate A fires at the start of every turn` },
  { id: 'LOC', kind: 'step', col: 1, row: 1, src: `${SRG} L44-110 Gate A triage (Step 0 routing, tier mapping)` },
  { id: 'DIAG', kind: 'out', col: 2, row: 1, src: `${SRG} L111 six-part diagnosis; L252 usual turn shape` },
  { id: 'SRCH', kind: 'step', col: 1, row: 2, src: `${LSE} L85 P1 parse targets, L95 P2 search`, cut: 'P1 and P2 merged into one node' },
  { id: 'POL', kind: 'check', col: 2, row: 2, src: `${LSE} L114-117 host access policy before any fetch, L143-161 P3 access tagging; hooks/literature_host_guard.py + literature-host-policy.json`,
    cut: 'drawn as either/or: an allowed part may be extracted while the named document still goes to the user' },
  { id: 'EXT', kind: 'step', col: 3, row: 2, src: `${LSE} L167 P4 extraction, L171 locator with every item` },
  { id: 'CC', kind: 'check', col: 4, row: 2, src: `${LSE} L188 P4.5 verification gate; verify/citecheck.py`, cut: 'number-in-span and metadata checks -> README sentence' },
  { id: 'RES', kind: 'out', col: 4, row: 3, src: `${LSE} L203 P5 synthesis; L73 result contract` },
  { id: 'U', kind: 'ext', col: 2, row: 3, w: CAP, src: `${LSE} L114-117 refused or challenged host handed to the user; L160-161 recorded in gaps` },
  { id: 'OUT', kind: 'ext', col: 4, row: 4, w: CAP, src: `${SRG} L83-91 Step 0.5: a pure retrieval request gets no tier mapping or six-part diagnosis` },
];
const groups = [
  // at: where the group label sits (top-left or bottom-left); the step-2 line enters G2 from the top
  { id: 'G1', label: T.g1, at: 'top', contains: ['LOC', 'DIAG'] },
  { id: 'G2', label: T.g2, at: 'bottom', contains: ['SRCH', 'POL', 'EXT', 'CC', 'RES', 'U'] },
];

function geom(n0) {
  const n = { ...n0, name: T[n0.id][0], role: T[n0.id][1] };
  const cx = X0 + n.col * PITCH, cy = ROWS[n.row];
  const w = n.kind === 'check' ? DW : (n.w || W), h = n.kind === 'check' ? DH : H;
  return { ...n, cx, cy, w, h, l: cx - w / 2, r: cx + w / 2, t: cy - h / 2, b: cy + h / 2 };
}

// kind: main (accent, numbered) | side | back.  Points are the orthogonal polyline, tip last.
function edgesOf(N, G2R) {
  const n = (id) => N[id];
  const XR = G2R + RET;
  return [
    { id: 'e1', kind: 'main', step: 1, from: 'Q', to: 'LOC', pts: [[n('Q').r, ROW1], [n('LOC').l, ROW1]], src: `${SRG} L44` },
    { id: 's1', kind: 'side', text: T.sDirect, from: 'LOC', to: 'DIAG', pts: [[n('LOC').r, ROW1], [n('DIAG').l, ROW1]], src: `${SRG} L252 Gate A -> six-part diagnosis; the label is inferred from L132-138 (only substantive literature work is delegated)` },
    { id: 'e2', kind: 'main', step: 2, text: T.e2, from: 'LOC', to: 'SRCH', pts: [[n('LOC').cx, n('LOC').b], [n('SRCH').cx, n('SRCH').t]], src: `${SRG} L134-135 Mode 2 request contract` },
    { id: 's2', kind: 'side', text: T.sOnly, from: 'Q', to: 'SRCH',
      pts: [[n('Q').cx, n('Q').b], [n('Q').cx, ROW2], [n('SRCH').l, ROW2]], src: `${LSE} L41-48 Mode 1 direct request; ${SRG} L83-87 a retrieval-only turn is handed straight to the librarian` },
    { id: 'e3', kind: 'main', step: 3, from: 'SRCH', to: 'POL', pts: [[n('SRCH').r, ROW2], [n('POL').l, ROW2]], src: `${LSE} L143 P3` },
    { id: 'e4', kind: 'main', step: 4, text: T.e4, from: 'POL', to: 'EXT', pts: [[n('POL').r, ROW2], [n('EXT').l, ROW2]], src: `${LSE} L152-160` },
    { id: 's3', kind: 'side', text: T.sBan, from: 'POL', to: 'U', pts: [[n('POL').cx, n('POL').b], [n('U').cx, n('U').t]], src: `${LSE} L114-117 refused or challenged host; hook deny` },
    { id: 'e5', kind: 'main', step: 5, from: 'EXT', to: 'CC', pts: [[n('EXT').r, ROW2], [n('CC').l, ROW2]], src: `${LSE} L188-195 ledger then citecheck` },
    { id: 'b1', kind: 'back', text: T.b1, from: 'CC', to: 'EXT',
      pts: [[n('CC').cx, n('CC').t], [n('CC').cx, n('CC').t - ARC], [n('EXT').cx, n('CC').t - ARC], [n('EXT').cx, n('EXT').t]],
      src: 'literature-search-extract/references/verification-gate.md L182-198 repair order (rewrite the claim to the stored text, or delete it and record a gap)' },
    { id: 'e6', kind: 'main', step: 6, text: T.e6, from: 'CC', to: 'RES', pts: [[n('CC').cx, n('CC').b], [n('RES').cx, n('RES').t]], src: `${LSE} L203 P5 after the gate` },
    { id: 's4', kind: 'side', text: T.sGap, from: 'U', to: 'RES', pts: [[n('U').r, ROW3], [n('RES').l, ROW3]], src: `${LSE} L161 gaps: not retrieved, hand-to-user` },
    { id: 'e7', kind: 'main', step: 7, text: T.e7, from: 'RES', to: 'DIAG',
      pts: [[n('RES').r, ROW3], [XR, ROW3], [XR, ROW1], [n('DIAG').r, ROW1]], src: `${SRG} L135 consume its result contract` },
    { id: 's5', kind: 'side', text: T.sOnly, from: 'RES', to: 'OUT', pts: [[n('RES').cx, n('RES').b], [n('OUT').cx, n('OUT').t]],
      src: `${SRG} L83-91 answering a booklist request with a stage diagnosis is over-triggering` },
  ];
}

function groupBox(g, N) {
  const m = g.contains.map((id) => N[id]);
  const box = { ...g, l: Math.min(...m.map((x) => x.l)) - PAD.x, r: Math.max(...m.map((x) => x.r)) + PAD.x,
    t: Math.min(...m.map((x) => x.t)) - PAD.top, b: Math.max(...m.map((x) => x.b)) + PAD.bottom };
  // label box at 15 px: baseline ly, cap height 15 above, descent 4 below
  const lx = box.l + 16, ly = g.at === 'bottom' ? box.b - 16 : box.t + 26;
  return { ...box, lx, ly, lab: { l: lx, r: lx + (textW(g.label) * 15) / 14, t: ly - 15, b: ly + 4 } };
}

const textW = (s) => [...s].reduce((a, ch) => a + (/[⺀-￿]/.test(ch) ? 14 : 7.6), 0);
const len = ([a, b]) => Math.abs(b[0] - a[0]) + Math.abs(b[1] - a[1]);
const segsOf = (e) => e.pts.slice(1).map((q, i) => [e.pts[i], q]);
function chipOf(e) {
  const [a, b] = segsOf(e).reduce((best, s) => (len(s) > len(best) ? s : best));
  const w = e.kind === 'main' ? (e.text ? 22 + 6 + textW(e.text) + 10 : 22) : textW(e.text) + 20;
  const x = (a[0] + b[0]) / 2, y = (a[1] + b[1]) / 2;
  return { x, y, w, h: 22, seg: [a, b], l: x - w / 2, r: x + w / 2, t: y - 11, b: y + 11 };
}

// ── model asserts (determinable from the model: FAIL) ─────────────────────────
function asserts(N, E, G) {
  const fail = [];
  const nodesL = Object.values(N);
  const inside = (p, r) => p[0] > r.l && p[0] < r.r && p[1] > r.t && p[1] < r.b;
  const onBorder = (p, n) => {
    if (n.kind === 'check') return [[n.l, n.cy], [n.r, n.cy], [n.cx, n.t], [n.cx, n.b]].some((v) => v[0] === p[0] && v[1] === p[1]);
    const onX = p[0] >= n.l && p[0] <= n.r, onY = p[1] >= n.t && p[1] <= n.b;
    return (onX && (p[1] === n.t || p[1] === n.b)) || (onY && (p[0] === n.l || p[0] === n.r));
  };
  for (const e of E) {
    const segs = segsOf(e);
    for (const [a, b] of segs) if (a[0] !== b[0] && a[1] !== b[1]) fail.push(`${e.id}: diagonal segment (R10)`);
    if (!onBorder(e.pts[0], N[e.from])) fail.push(`${e.id}: start not on ${e.from}'s border`);
    if (!onBorder(e.pts.at(-1), N[e.to])) fail.push(`${e.id}: tip not on ${e.to}'s border`);
    if (len(segs.at(-1)) < 1.5 * MARK) fail.push(`${e.id}: terminal run ${len(segs.at(-1))} < ${1.5 * MARK} (squeezed head, R10)`);
    for (const [a, b] of segs) for (const n of nodesL) {
      if (n.id === e.from || n.id === e.to) continue;
      const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      const hit = a[0] === b[0]
        ? a[0] > n.l && a[0] < n.r && Math.max(a[1], b[1]) > n.t && Math.min(a[1], b[1]) < n.b
        : a[1] > n.t && a[1] < n.b && Math.max(a[0], b[0]) > n.l && Math.min(a[0], b[0]) < n.r;
      if (hit || inside(mid, n)) fail.push(`${e.id}: runs through ${n.id}`);
    }
    if (e.kind === 'main' || e.text) {
      const c = chipOf(e), [a, b] = c.seg;
      const vert = a[0] === b[0];
      const lo = vert ? Math.min(a[1], b[1]) : Math.min(a[0], b[0]);
      const hi = vert ? Math.max(a[1], b[1]) : Math.max(a[0], b[0]);
      const cl = vert ? c.t : c.l, ch = vert ? c.b : c.r;
      if (cl - lo < 14 || hi - ch < 14) fail.push(`${e.id}: chip clearance ${Math.min(cl - lo, hi - ch)} < 14 (R14 B-22)`);
      for (const n of nodesL) if (c.l < n.r && c.r > n.l && c.t < n.b && c.b > n.t) fail.push(`${e.id}: chip on ${n.id}`);
      for (const g of G) {
        const crossV = c.l < g.l && c.r > g.l || c.l < g.r && c.r > g.r;
        const crossH = c.t < g.t && c.b > g.t || c.t < g.b && c.b > g.b;
        if ((crossV && c.t < g.b && c.b > g.t) || (crossH && c.l < g.r && c.r > g.l)) fail.push(`${e.id}: chip on ${g.id}'s border`);
      }
    }
  }
  // two edges never cross (the layout is drawn crossing-free, so no hop is needed); shared endpoints are joins
  for (const A of E) for (const B of E) {
    if (A.id >= B.id) continue;
    for (const [a, b] of segsOf(A)) for (const [c, d] of segsOf(B)) {
      const av = a[0] === b[0], cv = c[0] === d[0];
      if (av === cv) continue;
      const [v1, v2, h1, h2] = av ? [a, b, c, d] : [c, d, a, b];
      const x = v1[0], y = h1[1];
      const inV = y > Math.min(v1[1], v2[1]) && y < Math.max(v1[1], v2[1]);
      const inH = x > Math.min(h1[0], h2[0]) && x < Math.max(h1[0], h2[0]);
      if (inV && inH) fail.push(`${A.id}/${B.id}: cross at ${x},${y}`);
    }
  }
  // parallel runs of different edges: shared or >= 20 apart (R10)
  for (const A of E) for (const B of E) {
    if (A.id >= B.id) continue;
    for (const [a, b] of segsOf(A)) for (const [c, d] of segsOf(B)) {
      const bothV = a[0] === b[0] && c[0] === d[0], bothH = a[1] === b[1] && c[1] === d[1];
      if (!bothV && !bothH) continue;
      const gap = bothV ? Math.abs(a[0] - c[0]) : Math.abs(a[1] - c[1]);
      const [p1, p2] = bothV ? [[a[1], b[1]], [c[1], d[1]]] : [[a[0], b[0]], [c[0], d[0]]];
      const overlap = Math.min(Math.max(...p1), Math.max(...p2)) - Math.max(Math.min(...p1), Math.min(...p2));
      if (overlap > 0 && gap > 0 && gap < 20) fail.push(`${A.id}/${B.id}: parallel ${gap}px apart (R10)`);
      if (overlap > 0 && gap === 0) fail.push(`${A.id}/${B.id}: drawn on top of each other for ${overlap}px (R10)`);
    }
  }
  // spacing budget: neighbours on one row at least one standard node width apart (R14 B-22)
  for (const a of nodesL) for (const b of nodesL) {
    if (a.id >= b.id || a.row !== b.row || Math.abs(a.col - b.col) > 1) continue;  // fractional columns count too
    const gap = Math.max(a.l, b.l) - Math.min(a.r, b.r);
    if (gap < W) fail.push(`${a.id}/${b.id}: gap ${gap} < ${W} (R14 B-22)`);
  }
  // groups: disjoint; no foreign node inside; an edge running along a border keeps >= 20 from it (R10)
  for (const g of G) for (const n of nodesL) {
    const inBox = n.l < g.r && n.r > g.l && n.t < g.b && n.b > g.t;
    if (inBox && !g.contains.includes(n.id)) fail.push(`${n.id} sits inside ${g.id} without being in it`);
  }
  if (G[0].b >= G[1].t) fail.push('G1 and G2 overlap');
  // a group label is text: no edge runs through it and no node or chip covers it (seen in the first render)
  for (const g of G) {
    const L = g.lab;
    for (const e of E) for (const [a, b] of segsOf(e)) {
      const hit = a[0] === b[0]
        ? a[0] >= L.l && a[0] <= L.r && Math.max(a[1], b[1]) > L.t && Math.min(a[1], b[1]) < L.b
        : a[1] >= L.t && a[1] <= L.b && Math.max(a[0], b[0]) > L.l && Math.min(a[0], b[0]) < L.r;
      if (hit) fail.push(`${e.id}: runs through ${g.id}'s label`);
    }
    for (const n of nodesL) if (n.l < L.r && n.r > L.l && n.t < L.b && n.b > L.t) fail.push(`${n.id} covers ${g.id}'s label`);
    if (L.r > g.r - 8) fail.push(`${g.id}'s label overflows its group`);
  }
  for (const e of E) for (const g of G) for (const [a, b] of segsOf(e)) {
    if (a[1] === b[1] && Math.min(a[0], b[0]) < g.r && Math.max(a[0], b[0]) > g.l)
      for (const y of [g.t, g.b]) if (Math.abs(a[1] - y) < 20) fail.push(`${e.id}: runs ${Math.abs(a[1] - y)}px from ${g.id}'s border`);
    if (a[0] === b[0] && Math.min(a[1], b[1]) < g.b && Math.max(a[1], b[1]) > g.t)
      for (const x of [g.l, g.r]) if (Math.abs(a[0] - x) < 20) fail.push(`${e.id}: runs ${Math.abs(a[0] - x)}px from ${g.id}'s border`);
  }
  return fail;
}

// ── emit ──────────────────────────────────────────────────────────────────────
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const FONT = `font-family="'Segoe UI','Microsoft JhengHei','Noto Sans TC',sans-serif"`;

function emit(N, E, G, canvas) {
  const o = [];
  o.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${canvas.w} ${canvas.h}" width="${canvas.w}" height="${canvas.h}" role="img" aria-labelledby="t d" ${FONT}>`);
  o.push(`<title id="t">${esc(T.title)}</title>`);
  o.push(`<desc id="d">${esc(E.filter((e) => e.kind === 'main').map((e) => `${e.step}. ${N[e.from].name} → ${N[e.to].name}`).join('；'))}</desc>`);
  o.push(`<defs>${['main', 'side', 'back'].map((k) => `<marker id="m-${k}" viewBox="0 0 10 8" refX="10" refY="4" markerWidth="${MARK}" markerHeight="8" markerUnits="userSpaceOnUse" orient="auto"><path d="M0 0L10 4L0 8z" fill="${{ main: C.accent, side: C.side, back: C.back }[k]}"/></marker>`).join('')}</defs>`);
  o.push(`<rect width="100%" height="100%" fill="${C.bg}"/>`);
  for (const g of G) {
    o.push(`<rect data-group="${g.id}" x="${g.l}" y="${g.t}" width="${g.r - g.l}" height="${g.b - g.t}" rx="10" fill="${C.groupFill}" stroke="${C.groupLine}" stroke-width="1.25"/>`);
    o.push(`<text data-label="${g.id}" x="${g.lx}" y="${g.ly}" font-size="15" font-weight="600" fill="${C.mute}">${esc(g.label)}</text>`);
  }
  const style = { main: `stroke="${C.accent}" stroke-width="2.25"`, side: `stroke="${C.side}" stroke-width="1.5"`, back: `stroke="${C.back}" stroke-width="1.5" stroke-dasharray="6 4"` };
  for (const e of E) o.push(`<path data-edge="${e.id}" data-kind="${e.kind}" d="M${e.pts.map((p) => p.join(' ')).join('L')}" fill="none" ${style[e.kind]} marker-end="url(#m-${e.kind})"/>`);
  for (const n of Object.values(N)) {
    const [fill, stroke] = C[n.kind];
    if (n.kind === 'check') {
      o.push(`<path data-node="${n.id}" d="M${n.cx} ${n.t}L${n.r} ${n.cy}L${n.cx} ${n.b}L${n.l} ${n.cy}z" fill="${fill}" stroke="${stroke}" stroke-width="1.5"/>`);
      o.push(`<text data-name="${n.id}" x="${n.cx}" y="${n.cy + 6}" text-anchor="middle" font-size="17" font-weight="600" fill="${C.ink}">${esc(n.name)}</text>`);
      continue;
    }
    const rx = n.kind === 'ext' ? n.h / 2 : 8;
    o.push(`<rect data-node="${n.id}" x="${n.l}" y="${n.t}" width="${n.w}" height="${n.h}" rx="${rx}" fill="${fill}" stroke="${stroke}" stroke-width="1.5"/>`);
    o.push(`<text data-name="${n.id}" x="${n.cx}" y="${n.cy - 4}" text-anchor="middle" font-size="18" font-weight="600" fill="${C.ink}">${esc(n.name)}</text>`);
    o.push(`<text data-role="${n.id}" x="${n.cx}" y="${n.cy + 19}" text-anchor="middle" font-size="13" fill="${C.mute}">${esc(n.role)}</text>`);
  }
  for (const e of E) {
    if (!(e.kind === 'main' || e.text)) continue;
    const c = chipOf(e);
    if (e.kind === 'main') {
      o.push(`<g data-chip="${e.id}"><rect x="${c.l}" y="${c.t}" width="${c.w}" height="${c.h}" rx="11" fill="#ffffff" stroke="${C.accent}" stroke-width="1"/>`);
      o.push(`<circle cx="${c.l + 11}" cy="${c.y}" r="11" fill="${C.accent}"/><text x="${c.l + 11}" y="${c.y + 4.5}" text-anchor="middle" font-size="13" font-weight="700" fill="#ffffff">${e.step}</text>`);
      if (e.text) o.push(`<text x="${c.l + 28}" y="${c.y + 5}" font-size="14" fill="${C.accent}">${esc(e.text)}</text>`);
      o.push('</g>');
    } else {
      const col = e.kind === 'back' ? C.back : C.side;
      o.push(`<g data-chip="${e.id}"><rect x="${c.l}" y="${c.t}" width="${c.w}" height="${c.h}" rx="11" fill="#ffffff" stroke="${col}" stroke-width="1"/><text x="${c.x}" y="${c.y + 5}" text-anchor="middle" font-size="14" fill="${col}">${esc(e.text)}</text></g>`);
    }
  }
  const kinds = ['main', 'side', 'back'].filter((k) => E.some((e) => e.kind === k));
  let lx = Math.min(...G.map((g) => g.l));
  for (const k of kinds) {
    const label = T.legend[['main', 'side', 'back'].indexOf(k)];
    o.push(`<path data-legend="${k}" d="M${lx} ${LEGEND_Y}L${lx + 36} ${LEGEND_Y}" fill="none" ${style[k]} marker-end="url(#m-${k})"/>`);
    o.push(`<text x="${lx + 46}" y="${LEGEND_Y + 5}" font-size="14" fill="${C.mute}">${esc(label)}</text>`);
    lx += 46 + textW(label) + 40;
  }
  o.push('</svg>');
  return o.join('\n') + '\n';
}

function model(mutate) {
  const N = Object.fromEntries(nodes.map((n) => [n.id, geom(mutate?.node?.(n) ?? n)]));
  const G = groups.map((g) => groupBox(mutate?.group?.(g) ?? g, N));
  let E = edgesOf(N, G[1].r);
  if (mutate?.edges) E = mutate.edges(E, N);
  const xr = Math.max(...E.flatMap((e) => e.pts.map((p) => p[0])));
  const canvas = { w: Math.max(xr, ...G.map((g) => g.r)) + 40, h: LEGEND_Y + 30 };
  return { N, E, G, canvas };
}

const arg = process.argv.slice(2).find((a) => a === '--mapping' || a === '--selftest');
if (arg === '--mapping') {
  console.log('| 節點 | 描繪的來源（reference-impl/skills/…） | 省略或合併 |\n|---|---|---|');
  for (const n of nodes) console.log(`| ${T[n.id][0]} | ${n.src} | ${n.cut || '—'} |`);
  const { N, E } = model();
  console.log('\n| 線 | 從 → 到 | 來源 |\n|---|---|---|');
  for (const e of E) console.log(`| ${e.id}${e.step ? ` (${e.step})` : ''}${e.text ? ` ${e.text}` : ''} | ${N[e.from].name} → ${N[e.to].name} | ${e.src} |`);
} else if (arg === '--selftest') {
  // known-bad controls: each must produce a FAIL naming ITS class (one narrow pattern per control, so a
  // control cannot pass on another check's FAIL); the known-good model must be quiet
  const controls = [
    ['near-coincident neighbour (gap < W)', { node: (n) => (n.id === 'EXT' ? { ...n, col: 2.6 } : n) }, new RegExp(`^(POL/EXT|EXT/POL): gap .* < ${W}`)],
    // the tip stays on EXT's border; only the last run shrinks to 8 px
    ['squeezed arrowhead', { edges: (E, N) => E.map((e) => (e.id === 'b1' ? { ...e, pts: e.pts.map((p, i) => (i === 1 || i === 2 ? [p[0], N.EXT.t - 8] : p)) } : e)) }, /^b1: terminal run 8 /],
    ['edge through a node', { edges: (E, N) => E.map((e) => (e.id === 'e3' ? { ...e, to: 'EXT', pts: [[N.SRCH.r, ROW2], [N.EXT.l, ROW2]] } : e)) }, /runs through POL/],
    ['crossing edges', { edges: (E, N) => E.map((e) => (e.id === 'e5' ? { ...e, to: 'RES', pts: [[N.EXT.cx, N.EXT.b], [N.EXT.cx, ROW3 + 50], [N.RES.cx, ROW3 + 50], [N.RES.cx, N.RES.b]] } : e)) }, /e5\/s4: cross at|s4\/e5: cross at/],
    ['group label in the path of the step-2 line', { group: (g) => (g.id === 'G2' ? { ...g, at: 'top' } : g) }, /e2: runs through G2's label/],
    ['two lines drawn on top of each other', { edges: (E) => [...E, { ...E.find((e) => e.id === 'e3'), id: 'x3', kind: 'side', step: undefined, text: undefined }] }, /^e3\/x3: drawn on top/],
    ['return line hugging the group border', { edges: (E) => E.map((e) => (e.id === 'e7' ? { ...e, pts: e.pts.map((p, i) => (i === 1 || i === 2 ? [p[0] - RET + 8, p[1]] : p)) } : e)) }, /from G2's border/],
  ];
  let bad = 0;
  for (const [name, m, re] of controls) {
    const { N, E, G } = model(m);
    const fail = asserts(N, E, G);
    const ok = fail.some((f) => re.test(f));
    console.log(`${ok ? 'fires' : 'SILENT'}  ${name}${ok ? `  (${fail.find((f) => re.test(f))})` : `  (got: ${fail.join('; ') || 'nothing'})`}`);
    if (!ok) bad++;
  }
  const { N, E, G } = model();
  const clean = asserts(N, E, G);
  console.log(`${clean.length ? 'FALSE ALARM' : 'quiet'}  known-good model (${clean.length} FAIL)${clean.length ? ': ' + clean.join('; ') : ''}`);
  process.exit(bad || clean.length ? 2 : 0);
} else {
  const { N, E, G, canvas } = model();
  const fail = asserts(N, E, G);
  for (const f of fail) console.log(`FAIL ${f}`);
  const out = path.join(HERE, `flow.${LANG}.svg`);
  fs.writeFileSync(out, emit(N, E, G, canvas));
  console.log(`${fail.length} FAIL · ${Object.keys(N).length} nodes · ${E.length} edges · 0 crossings asserted · canvas ${canvas.w}x${canvas.h} -> ${path.relative(process.cwd(), out)}`);
  process.exit(fail.length ? 1 : 0);
}
