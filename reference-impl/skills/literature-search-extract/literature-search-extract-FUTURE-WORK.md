# literature-search-extract — 未結項清單

> **時間戳規約（2026-08-27 訂）**：本檔任何數量、行數、篇數、比例，一律寫成
> 「數值（量測日期）」並在旁邊留下重取的指令。沒有量測日期的數字視為過期。
> 理由見 A2 的更正紀錄——一個沒有日期的數字停留了五週，然後被下一手當成基線。
>
> **這條規約有機器在檢查，不是靠記性**：`python verify/staleclaim.py`
> ——對「某檔 N 行」這種可判定的宣稱直接重量測，不符即 FAIL。
> 它的正對照是**把五週前那個真實的錯誤檔案從 git 取出重放**，必須擋下來
> （第一版擋不下來，合成測試卻全過）。涵蓋範圍刻意窄：只驗行數，
> 「116 篇」「47%」這類無法從文字重推的數字它只會 WARN——那部分靠這條規約本身。

> 本檔只放**尚未完成**的事項。歷史完成紀錄（P1–P7 全部 21 項）原封存於
> `2026-07-12-lse-update-plans/TODO.md`；該目錄在後續清理中已消失（2026-08-26
> 查證）；當時記下的最後一份副本放在 `archive/` 底下（從未進 git），2026-09-19
> 查證也已不在磁碟上——P1–P7 的逐項紀錄**已無法取回**，只剩各次 commit message。
> 勿在此重複。事項完成後：從本檔移除，並在 commit message 留紀錄即可。

## A. 待使用者決定

### A1. 分享版打包（原 TODO item 19）
若日後要把本 skill 分享到本機以外：走 skill-share-packaging Mode A——
剔除個人檔案（PDF-GUIDE / FUTURE-WORK / sample-run / evals 個人備註）、
generalize prism 字樣為 provider-neutral local-corpus slot、移除 frontmatter 的
trigger-dict 引用，只出貨 SKILL.md + references/ + evals.json。
**現況**：可攜性核心已由 `references/portability.md` 出貨（2026-07-12，P7），
剩的只是「打包剝離」這一步。不分享就不用做。

### A2. SKILL.md 行數（**現況：未超標，剩 9 行餘裕**）

> **2026-08-27 更正三處數字。** 本項先前的敘述有三個錯，且都不是抄寫失誤，
> 是「沿用上一手的數字而沒有量測」：
> 1. 「261 行」在 2026-07-12（`482d05c`）為真，2026-07-19（`23ec0ba`）已降到
>    250 行，此處的 261 從此停留了五週沒更新。
> 2. 本輪我把那個 261 直接當基線做加減，**沒有先量**，於是「新增 28 行」也錯——
>    真實基線 250，round 1 後 289，即 **+39**。
> 3. 「超過 250 行軟上限、hook 會持續提示」兩句都不成立：實際預算是
>    **~300 行**（`ops/40-maintenance.md` §3 表；`hooks/ops_health_nudge.py`
>    `BODY_CAP = 300`），所以 250 這個門檻不存在，hook 在 291 行時也沒有在叫。

**量測（2026-08-27 00:51，逐筆 `git show <sha>:… | wc -l` 取得）**

| 時點 | 行數 | 說明 |
|---|---|---|
| `23ec0ba` 2026-07-19 | 250 | 本 session 之前的真實基線 |
| `31bf625` round 1 | 289 | +39（P2 connector 分流、P4.5 驗證關卡、failure mode #8、reference map 兩條） |
| `a702278` prism 掃除 | **291** | +2（P2 分流行由 2 行改寫成 4 行） |
| 2026-08-31（研究專案回合後） | **316** | +25 **超支 16 行**——failure mode #9、P3 PDF 加密探測配方、P5 Zotero 收尾三批新增**都沒有先量**，正是本項自己寫的那條規約被違反 |
| 2026-09-03 架構掃描回合後 | **300** | 無損提取：PDF 配方→`search-sources.md`、Zotero 收尾→`connectors.md`、#8 量測證據與 channel 時戳去重；再加 A1 召回檢查（7 行）＋ A2 scope 改寫 |
| 2026-09-03 閉路施工後（LSEL-09，`wc -l` 實量） | **300** | 行數中性改寫：Known callers 段 → 登錄表指標（−2）、result contract 加 `run_id`（+1）、P2 local-corpus 括號去舊（−2）、reference map 加 `feedback-loop.md`（+3）、其餘四處同行改寫（0） |
| 2026-09-11 圖書館指南升級後（`wc -l` 實量） | **300** | 無損提取：P1 需求→出處表（9 行）→ `extraction-playbook.md` §0、P2 工具優先段 11→7 行；新增：P1 前提檢查（2）、P2 存取政策＋fetchsrc（5）、詞彙帳／錨定回合（+2）、P3 hand-to-user 改寫（0）、P4.5 v2 檢查（2）、P5 AI 使用揭露（1）、failure mode #11（2）、reference map 兩行改寫（0）；四處各縮 1 行收回超支 |
| 2026-09-14 researcher.tw 借用回合（`(Get-Content).Count` 實量） | **300** | 行數中性：P2 詞彙帳 bullet 同行數改寫（加近期種子、年份×引用讀法）、citation chasing bullet 3→2 行、format catalog +1 列（Concept matrix） |
| 預算 | 300 | 餘裕 **0 行** |

**現況：貼齊上限，餘裕為零。** 下一次要往 SKILL.md 加任何東西，必須**先做一次無損提取**
（把具體配方／指令搬進 references，規則與分流留在原地），不得直接加。真的提取不出來時，
`ops/40-maintenance.md` §3 允許帶著那次提取的證據把 cap 抬上去——但那是最後手段，不是預設。

**已用掉的回收提案**：原本記在這裡的「output format catalog 可移出約 12 行」**不能做**——
SKILL.md Mode 1 明文依賴該表的 "Use when" 欄推斷 `output_format`（第 46–47 行），
移走會斷掉一條活規則。2026-09-03 改為提取 PDF 配方與 Zotero 收尾，效果相同且無損。

**方法論教訓（比數字本身重要）**：這個 skill 的整套 P4.5 就是為了防「沿用未經
查證的數字」，而這份清單自己犯了同一個錯，還跨了五週沒被發現。凡是寫進本檔的
數量，格式一律為「數值＋量測日期＋量測指令」，否則不要寫。

### A3. 借用帳延後項 B-6：期刊可信度的具名檢查來源（researcher.tw 借用回合，2026-09-14）
`credibility-rubric.md` §4 加 Think. Check. Submit. 作為具名檢查清單；§1 venue tier 把 SJR 分區列為參考輸入之一（**不等於**等級）。
**延後原因**：不是本輪核心（核心＝B-3 種子融合、B-1 概念矩陣、B-9 PoP）；SJR 分區是會變動的外部數值，折入當下要重查。
**觸發**：下一次真實 run 碰到不熟的期刊、需要判讀其可信度時。紀錄：`~/.claude/outputs/researcher-tw-borrow-review-2026-09-14.md` §3。

### A4. 概念帳：Threads 五個 Claude 學術 repo 掃描（2026-09-22）
**使用者裁定（2026-09-22）：完全不借用程式碼／檔案，只採概念，由我們自己設計實作。** 來源貼文 `threads.com/@aiaccesshub_daily/post/DdfXAlkE6pD`；五個 repo 僅作概念出處，不列為依賴。
- **C1 參考文獻字串衛生**：從已驗證識別碼重建書目字串，並對殘留標記、標點毀損、近似重複標題、DOI 年份與標示年份衝突做機械檢查 → `verify/`。
- **C2 文獻集層級的共同引用收斂**：對整個 corpus 的參考文獻清單計頻，找出「多數成員都引用」的節點，補 per-seed 追引之不足；區分「抓取失敗」與「零參考文獻」→ `search-sources.md` §Citation chasing（standard／exhaustive）。
- **C3 內文引用 ↔ 書目互解**：撰寫型交付物中，每個內文引用恰好對應一筆書目、無歧義 → `verify/`。
- **C4 抓取後篩檢**：付費牆殘頁／stub 偵測、標題作者與內容不符的偵測，進 ledger 前擋下 → `fetchsrc.py` 之後。
- **C5 無識別碼時的模糊去重**：標題＋作者＋年份 → `loop/idkey.py` 退路。
- 非本 skill 職權、僅記路由：C6 模擬輸出數值 ↔ 文稿主張一致性（scientific-research-guide／comsol-agent-pipeline）；C7 渲染後頁面交給獨立視覺審查者（paper-story，已有 `scripts/shot.py`）；C8 平行審查者去身分盲評（dispatch 模式，ops 層）；C9 版面感知的本機 PDF→MD（先評 8GB VRAM 可行性）。
**觸發**：下一次真實 `standard`／`exhaustive` 深度 run（C1–C5 各自以該 run 碰到的缺陷為準，沒碰到不做）。

## B. MANUAL-VERIFY（等待真實使用情境驗收）

| # | 驗收項 | 驗收時機與判準 |
|---|---|---|
| ~~B1~~ | ~~本地 PDF 庫支援（P4 item 14）~~ | **部分結案 2026-08-27**：已接為 live connector（root = Zotero storage；**116 篇建索引（2026-08-27），重取：`python connectors/pdf_index.py --build`**），`pdf_index.py` 的檔名解析有 4 必解析／2 必降級的兩面校準，`--stats` 產出可引用的收藏偏誤數字。**仍未驗的是真實調用**：下次真的用本地庫回答文獻題時，看 `[full]` 標籤有沒有正確落下、偏誤數字有沒有真的進 search_trail |
| B2 | portability 能力自評（P7 item 21） | 下次 codex（或任何非 Claude 環境）調用本 skill 時：有先讀 portability.md 做能力盤點、交付物聲明 profile 與降級 |
| B3 | eval 6 重測（source-provided 全文萃取） | 原測試因 Science 付費牆 1 條 assertion 留 null；改用 open-access 指定來源或本地 PDF 重跑補值 |
| B4 | **P4.5 證據帳本 (evidence ledger) 的實務成本**（2026-09-03 前提已變，仍未驗） | 下次真實 `standard` 深度文獻題：每條承重主張寫一列 ledger、跑 `verify/citecheck.py`。要看的不是「會不會過」，而是**成不成本**。**2026-09-03 已先行採取本項預告的收斂**：scope 改為「claim kind 優先、depth 其次」——數值型與爭議型主張不分深度都要一列，其餘照舊（`verification-gate.md` §When to run it）。所以要量的問題換成：**在這個窄化之後，一次 run 平均幾列？** 若仍不可負擔，下一步仍是繼續窄化（只留數值型），**不是**放寬 span 檢查。**首筆量測（2026-09-03，`quick`，run `20260903_concave-si-micromirror-roughness`）**：3 來源 → 3 列（Ow 2010 兩個數值主張、Bao 2017 一個），寫列約 2 分鐘，`citecheck` 0 FAIL（兩個 Crossref 解析）；`quick` 深度可負擔。`standard` 深度仍未量，B4 保持開放 |
| B7 | **A1 召回檢查 (recall check) 的實效**（2026-09-03 新增；**首筆量測 2026-09-03**） | 下次真的要回報「查無」時：有沒有真的扣住一個已知項當正對照、有沒有落進 `search_trail`。要看兩件事——(1) 正對照**真的會失敗嗎**？一個從不 miss 的對照等於沒有對照（可用刻意寫壞的檢索式反證）；(2) 成本是不是一輪查詢就結束。無對照可用時，交付物有沒有真的印出那句降級聲明。**量測（run `20260903_concave-si-micromirror-roughness`，`runs.py find` 重取）**：對照 Bao 2017 扣住標題與 DOI，Zotero 查詢 rank 2、web 查詢 rank 1 皆 FOUND；刻意錯詞查詢 `oxidised dimple reflector cavity` → MISSED——對照會失敗，是儀器不是裝飾。成本：一輪本地查詢。n=1，該 run 未宣稱「查無」，B7 仍開放到第一次真實 absence claim |
| B8 | **B1 新來源類別的首次實跑**（2026-09-03 新增） | 下次碰到材料常數／機構報告／學位論文題目時：`reference_data_compilations` 的 cite-through 規則有沒有真的把引用落在**原始來源**而非彙編上；NTRS 的參數細節（NASA 自己的 OpenAPI 文件停在 2021-04-26）是否與實際行為相符；OSTI `links[rel=fulltext]` 是否真的給得出 `[full]` |
| B5 | **connector 分流實測** | 下次真的需要專利前案時：先 `connectors/probe.py --id patentsgrabber`，確認 contract 綠燈再走 `/api/query`；驗 `provenance`／`missing`／`truncated` 有沒有真的落進交付物的 sources 與 gaps |
| B6 | **`[abstract]` 列的 span 檢查是否過嚴** | 本輪把 span 檢查從「只查 full/partial」改成「只要有存下原文就查」。摘要用詞常被改寫成句，若實測誤判率高，退回門檻應該是「摘要列改 WARN」而非關掉檢查 |
| B9 | **存取政策與 hook 的實戰誤判率**（2026-09-11 新增，設計 `~/.claude/references/lse-access-verification-upgrade-design.md`） | 下一次真實文獻 run：(1) `hooks/literature_host_guard.py` 有沒有擋到不該擋的（`telemetry/literature-host-nav.jsonl` 的 `deny` 列逐筆看；誤判走 `report_fp.py --hook literature_host_guard`，3 筆即改列不改 hook）；(2) `fetchsrc.py` 的 `HAND-TO-USER:` 有沒有真的變成交付物的 query pack；(3) 未列主機一輪 3 個的上限會不會在真實 run 裡先撞到——撞到即補列，不放寬 |
| B10 | **citecheck v2 的數值／metadata 檢查在真實 ledger 上的成本與誤判**（2026-09-11 新增） | 下一次 `standard` 深度 run：每列多填 `expect_title`／`expect_authors`／`access_route` 的實際時間；`numeric` WARN（數字在全文不在 span）出現幾次、有幾次是 span 該延長；`doi-not-yet-active` 有沒有真的碰到。校準 40 案（18 過／22 擋）是想像出來的案例——真實 ledger 才是儀器的驗收（`verification-gate.md` §Why the calibration is not decoration） |
| B12 | **`textbook_library` connector 首次真實調用**（2026-09-13 新增；定位評估 `~/.claude/references/lse-textbook-corpus-positioning-eval_2026-09-13.md`，規則 `references/textbook-extraction.md`，工具 `connectors/textbook_ocr.py`／`textbook_index.py`） | 下一次要「教科書怎麼定義 X」或研究專案前置詞彙（`canonical_definition` 預設）時：(1) `--search` 命中後有沒有真的只讀命中的頁範圍；(2) ledger 列的 locator 是不是印刷頁碼＋版本、`--locate` 換算與頁首實測一致；(3) 落在 OCR 排除頁時有沒有寫成 gaps 而不是猜；(4) 出處欄位是否只寫「哪本書、哪裡」（使用者裁定 Q1）。**人工必驗（A）尚未做**：抽 2 頁 OCR 文字對照原書、抽 3 個目錄條目核對印刷頁碼、抽 5 條索引詞核對頁碼——做完把結果記回定位評估 §9 |
| B11 | **撤稿批掃首次真跑**（2026-09-11 新增；工具 `verify/citecheck.py --retraction-sweep`，登錄列 `a3-retraction-sweep` 可由 planned → live） | 下一次 Zotero 收尾：對專案 bib JSON 跑一次、記錄 N 筆／耗時／`?` 列數；任何 `RETRACTED` 走 `reflux.py retraction` → `runs.py affected` |

## C. 長期選項（ops 層，非本 skill 職權）

- interop.py 擴 skills-compile profile，取代手動複製到 `~/.agents`/`~/.codex`
  （裁決紀錄：`~/.claude/ops/lessons.md` L-003；決定權在使用者）。
