# 證據（EVIDENCE）

這份說明這次發版實際量了什麼、每條方法規則從哪來、哪些由程式強制、哪些不宣稱。
行號以 v1.0.2 的 `reference-impl/` 為準，每次發版重新核對（發版步驟 2）。

## 實測（v1.0.2）

環境：Windows 11、Python 3.12.7、pytest 9.1.1、PyMuPDF 1.26.7、`idutils` 1.7.0 與 `jsonschema` 4.26.0（K1e、K1h、K2 會用到；`verify/requirements.txt`）。
以上皆為 `verify/controls_run.txt` 環境行印出的版本；授權見 `THIRD_PARTY_NOTICES.md`。

**PyMuPDF 是選用**：裝了，K1k 會多跑 20 個頁指標案例（一份 3 頁合成 PDF 加一本假的 OCR 書，驗頁指標與雜湊），共 105 例；
沒裝，K1k 跑 85 例，結尾會寫「page-pointer cases skipped: no PyMuPDF」——略過不算通過。v1.0.1 以前沒裝 PyMuPDF 時 K1k 直接報錯（外部回饋在 macOS 上量到，2026-11-07）。

**控制項不讀已安裝的 `~/.claude`**：`run_controls.py` 把 `CLAUDE_CONFIG_DIR` 指到暫存區裡的空資料夾、`LSE_HOST_POLICY` 指到 repo 內的政策檔。
v1.0.1 以前 K1a、K6 會去讀機器上已安裝的政策檔，所以在「沒裝過的新機器」上是 17/19（同一則回饋量到；本機用空的假家目錄重現）。
v1.0.2 的紀錄另以空的假家目錄重跑一次，結果相同（19/19）。

**驗收控制（`verify/controls_run.txt`）：19 of 19 ok，2 undetermined（不計入）。** 每一行都印出實際斷言的值：

| id | 正確版（實際值） | 突變版（實際值） |
|---|---|---|
| K1a | `access_policy.py --selftest` exit 0：未列名的主機在相同次數仍被拒（對照組） | 內含 |
| K1b | `pdf_index.py --selftest`：6 cases（4 must-parse / 2 must-degrade-without-inventing），0 broken | 內含 |
| K1c | `probe.py --selftest`：5 cases，0 broken | 內含 |
| K1d | `zotero_local.py --selftest` exit 0 | 內含；該 selftest 自己註明只校準引文格式與出處標記，不讀真實資料庫 |
| K1e | `idkey.py --selftest`：17 cases（12 must-parse / 4 must-unresolve / 1 must-differ），0 broken | 內含 |
| K1f | `inbox.py --selftest`：PASS | 內含 |
| K1g | `reflux.py --selftest`：5 cases（2 must-reject / 3 must-accept），0 broken | 內含 |
| K1h | `runs.py --selftest`：calibrated | 內含 |
| K1i | `fetchsrc.py --selftest`：0 broken，calibrated | 內含（被拒主機、挑戰頁、每主機上限，皆為 stub 傳輸） |
| K1j | `staleclaim.py --selftest`：8 cases（5 must-pass / 3 must-fail），0 broken | 內含 |
| K1k | `citecheck.py --selftest --offline`：105 cases（53 must-pass / 52 must-fail），0 broken | 內含（v1.0.2 新增 4 例：全空白 span、壞掉的帳本列、空帳本、缺 run.json；各在舊版會失敗） |
| K2 | `loop/tests` pytest：53 passed | 內含（v1.0.2 新增：citecheck.json 有 FAIL 時 register 必須拒絕） |
| K3 | `test_literature_host_guard.py`：ALL TESTS PASSED | 內含（D-* 拒絕案例） |
| K4 | `test_secret_file_guard.py`：must-deny 50、must-pass 53，failures 0（另有 3 個 undetermined、3 個 unclassifiable shape 走 fail-open，皆不計入） | 內含 |
| K5 | citecheck 支撐檢查：原 span **OK** | span 的 22 um 與主張的 22 ± 都改成 48：**FAIL** |
| K6 | hook 收到 arXiv 的 WebFetch：**allow (silent)** | 收到 IEEE Xplore 文件頁的 WebFetch：**deny** |
| K7 | `profile-lint.py` 對出貨版：(0 FAIL, 0 WARN) | `routing-collision` 夾具：(2, 6)；`frontmatter-drift` 夾具：(2, 0) |
| K8 | `eval-impact.py`：改 `method-selection.md` 要重跑 **3** 個案例（2、3、5） | 改 `deliverables.md`：**0** 個 |
| K9 | 新增一列 manifest 但沒有檔案：**1** FAIL，closure 訊息出現 | 同一列加上未填的 `_template.md` 副本：closure 訊息消失，**11** FAIL（範本佔位符） |

兩個 undetermined：`connectors/local_find.py --selftest`（exit 2）與 `connectors/textbook_ocr.py --selftest`（exit 1）都需要本機教科書庫，
這台乾淨環境沒有，所以不算通過也不算失敗；transcript 的原文是「UNDETERMINED: no textbook library on this machine」。

K5 與 K1k 都用 `--offline`：識別碼解析（Crossref / Semantic Scholar）被跳過並標為 WARN，所以控制項證明的是
「span 逐字比對」「數字比對」「provenance」「政策拒絕」，**不是**識別碼真的存在。

## 規則來源（origin records）

這些規則不是一次寫成的，而是原作者在自己的文獻波次（literature wave）上出錯、補洞後留下的。來源紀錄留在各檔案的出處行（provenance line）裡，日期與 lesson id 保留：

- **引用支撐 span（P4.5、failure mode #8）**：`verify/citecheck.py` 開頭引用兩項公開量測——ALCE（arXiv:2305.14627）指出在 ELI5 資料集上，最佳系統仍有約一半回答的引用不完整支撐其主張（這是 ELI5 上的量測，不是所有任務的通則），
  Search Arena（arXiv:2506.05334）指出人類評審會因引用數量較多而給較高分，即使被引內容並不直接支撐。結論是危險的失敗不是捏造的 DOI，而是真實來源被引來支撐它沒說的事；
  腳本不能判斷「支撐」，但能證明「所引的字確實在取回的文字裡」。
- **provenance 與 access route 的 FAIL 升級日 2026-09-12（`LEGACY_CUTOFF`）**：該日期之後建立的 run 必須帶 `sources/manifest.json` 與 `access_route`，舊 run 只 WARN。
- **主機存取政策（2026-09-10 的一個文獻波次）**：VPN 讓四個付費出版商變得可連，下一個念頭是用已登入的無頭瀏覽器；
  這促成 `rules/literature-access.md` 與 `hooks/literature-host-policy.json`。IEEE Xplore 的使用條款（Institutional Subscribers，禁止以機器人或智慧代理存取、搜尋或系統性下載）
  是 `agent_banned` 類別的依據；挑戰頁（202、403、418、JS 插頁、CAPTCHA）是路由訊號，不是困難。
- **fetchsrc 事件（L-075）**：派工單把受檢查的取回路徑排除，工作者就改用沒有上限的手寫取回器；因此規則要求派工單「點名路由表」而不是排除它。
- **每 session 上限（2026-10-04）**：某個小上限的 landing 主機在三個 session 內被 WebFetch 12、8、6 次，每次都是不同網址；`fetchsrc.py` 只數自己發出的請求，所以 hook 加了 per-session 上限。
- **未列名主機的通知（2026-11-03，G10）**：一次證據 run 在 `unlisted_default` 的上限 1 之下由純腳本打了約 11 次同一個 metadata API，沒有任何計數器看見；
  之後上限改為 run 層共享計數，hook 只發通知、不拒絕（原因與升級條件寫在 hook 檔頭）。
- **Gate A Step 0.5（2026-08-24，eval case 11 負對照）**：純檢索請求（「找 5 篇論文、整理成 evidence table」）原本被顧問流程整套觸發，3 of 4 斷言失敗；
  加入 Step 0.5 scope check 後 4 of 4 通過。這是模型模擬的案例評估，不是腳本控制。
- **profile 一致性閘（FM-CLOSURE，2026-09-02）**：profile 的產生式 front-matter 卡片與 manifest 列不一致時 FAIL；
  關鍵詞重疊與弱錨點（short ASCII infix）是 WARN，因為「是否有意重疊」不可判定。

## 強制對照表（Enforcement map）

「程式強制」= 違反時腳本或 hook 判 FAIL / deny（標 WARN 的就是只警告）；「流程規則」= 寫在 SKILL.md 或規則文件裡，靠代理人遵守，沒有腳本判；
「不宣稱」= 本 repo 沒有證據，也不主張。路徑皆在 `reference-impl/` 之下。

| 方法規則（出處） | 強制方式 | 位置 |
|---|---|---|
| 零捏造：識別碼必須能解析（literature SKILL.md「Operating stance」、failure mode #1） | 程式強制（FAIL）；`--offline` 時只 WARN | `skills/literature-search-extract/verify/citecheck.py:532`、`:553`、`:557`、`:561`、`:565` |
| 支撐 span 必須逐字出現在取回的文字（P4.5） | 程式強制（FAIL） | `citecheck.py:617`（沒有 span）、`:642`（頁指標）、`:673`（文字檔） |
| 主張裡的數字必須在 span 裡 | 程式強制：不在 span 也不在全文 = FAIL；只在全文別處 = WARN | `citecheck.py:696`（FAIL）、`:700`（WARN） |
| 空白或只有空白字元的 span 不算「在原文裡」 | 程式強制（FAIL；v1.0.2 前全空白 span 會被判 OK） | `citecheck.py:178` |
| 帳本完整：讀不懂的列、空帳本都不算通過 | 程式強制（exit 1；v1.0.2 前略過並 exit 0） | `citecheck.py:1540`、`:1543` |
| 沒有 `run.json` 的 run 當新 run 判，不享舊 run 的 WARN | 程式強制（v1.0.2 前缺 run.json 就當舊 run，provenance 只 WARN） | `citecheck.py:1498` |
| 引用查核有 FAIL 的 run 不得登記為已交付 | 程式強制（`runs.py register` 拒絕；v1.0.2 前只有事後的 `check` V8 報） | `loop/runs.py:512` |
| 「span 真的支撐主張」 | 不宣稱（腳本只證明在場，不證明蘊含；見下方） | — |
| 存取標籤誠實（`[full]/[partial]/[abstract]/[secondary]`，P3） | 部分程式強制：標籤須在列舉內、OCR 稀疏頁不得標 `[full]`、`[full]` 但文字過短 WARN、`hand_to_user` 不得搭配含文字的標籤 | `citecheck.py:526`、`:649`、`:678`、`:812` |
| 「`[abstract]` 只能抽取摘要有的內容」 | 流程規則 | literature `SKILL.md`「P3」 |
| 文字來源 provenance：文字不是 `fetchsrc.py` 產生，或取回後被改過 | 程式強制（FAIL；run 建於 2026-09-12 之前只 WARN） | `citecheck.py:759`、`:796`（sha256 與 manifest 不符） |
| 主機存取政策：`agent_banned` / `institutional_only` 不給任何表面 | 程式強制（hook deny、fetchsrc 拒絕、citecheck FAIL） | `hooks/literature_host_guard.py:223`（judge）、`:232`、`:479`；`connectors/access_policy.py:146`；`verify/fetchsrc.py:315`；`citecheck.py:823` |
| 轉址：每一跳在送出前先判主機（例：doi.org 轉到被禁的出版商，那一跳不會送出） | 程式強制（`fetchsrc.py` 自己跟轉址，最多 5 跳；v1.0.2 前由 urllib 自動跟，請求送出後才判主機、只丟棄內容） | `verify/fetchsrc.py:185`、`:206` |
| 瀏覽器表面不在 `agent_surfaces` 內就拒絕；未量測的訂閱出版商不給瀏覽器 | 程式強制（hook deny） | `literature_host_guard.py:227`（未量測出版商）、`:235`（表面不在清單） |
| 挑戰頁交給使用者，不換 User-Agent / 瀏覽器 / profile 重試 | 部分程式強制：`fetchsrc.py` 遇挑戰標記只打一次、記入 manifest、印 `HAND-TO-USER:`、exit 3；agent 自己用別的工具重試，只有在該主機本來就被政策拒絕時才會被 hook 擋 | `verify/fetchsrc.py:75`、`:163`、`:297`、`:341` |
| 每主機 / 每 run 上限（`max_per_run`、三個未列名主機上限） | 程式強制（`fetchsrc.py` 與 `access_policy.py` 拒絕；腳本呼叫共用同一計數） | `access_policy.py:155`、`:159`；`fetchsrc.py:315`、`:327` |
| 每 session 上限（小上限的 landing 主機） | 程式強制（hook deny）；未列名主機的檢索腳本超過上限只發通知 | `literature_host_guard.py:240`、`:470`；通知 `:301` |
| 授權版全文不留存、只留摘錄（copyright boundary） | 部分程式強制：非 OA 主機依政策 `retention` 存 scratch 並只導出 span 周圍視窗；未導出前 citecheck 拒絕 | `fetchsrc.py:356`、`:443`、`:503`；`citecheck.py:663` |
| 「引文短、改寫為主、不重製整節」 | 流程規則 | literature `SKILL.md`「Copyright boundary」、`rules/literature-access.md` |
| 撤稿檢查（P3、credibility-rubric §3） | 程式強制：被引作品有撤稿通知且未標「以撤稿引用」= FAIL，關注聲明 = WARN；需要網路 | `citecheck.py:575`–`:591` |
| 召回檢查：「查無」之前要有 withheld 已知項目的對照（P2） | 流程規則（沒有腳本判斷「查無」是否經過召回檢查） | literature `SKILL.md`「Recall check」；`references/search-sources.md:539` |
| 來源衝突不平均、不默默擇一（P4） | 流程規則 | literature `SKILL.md`「Note disagreements verbatim」 |
| 數值需帶單位、不確定度、條件（P4） | 流程規則（只有「數字須在 span 裡」被腳本檢查） | literature `SKILL.md`「Preserve exactness」 |
| 連線金鑰不進對話：agent 不得讀 `connectors/.env` | 程式強制（hook deny，所有權限模式） | `hooks/secret_file_guard.py:468`（Read）、`:479`（Grep）、`:496`、`:507`、`:516`（Bash / PowerShell）；K4 |
| Gate A Step 0：domain 路由由 `_routing.md` manifest 決定 | 流程規則；manifest 本身的結構由 profile-lint 檢查（下列各列） | advisor `SKILL.md`「Gate A」 |
| Step 0.5 scope check：純檢索不跑 tier 診斷 | 流程規則（以 eval case 11 負對照模擬評估，非腳本） | advisor `SKILL.md`「Step 0.5」；`evals/evals.json:148` |
| manifest closure：manifest 的每列都要有檔案，每個檔案都要有列 | 程式強制（FAIL） | `skills/scientific-research-guide/tools/profile-lint.py:426`、`:475`；K9 |
| 關鍵詞重疊 / 弱錨點 | 程式強制，但只 WARN（不可判定是否有意） | `profile-lint.py:265`（KEYWORD-OVERLAP）、`:283`（WEAK-ANCHOR）、`:298`（REDUNDANT-VARIANT） |
| 重疊登記表不得指向不存在的列、不得是「什麼都沒消掉」的死列 | 程式強制（FAIL） | `profile-lint.py:438`（指向不存在的列）、`:452`（死列） |
| frontmatter closure：產生式卡片與 manifest 列一致 | 程式強制（FAIL） | `tools/profile_frontmatter.py:135`–`:149`，由 `profile-lint.py:486` 呼叫；K7 的 `frontmatter-drift` 夾具 |
| 改動後要重跑哪些 eval 案例 | 程式強制（依宣告的依賴選案例，不是檔案交集） | `tools/eval-impact.py`；K8 |
| Gate B：方法 / 標準 / 工具事實先查證再斷言 | 流程規則 | advisor `SKILL.md`「Gate B」 |
| Gate C：未被要求不寫程式、不改資料、不 commit；破壞性動作先確認 | 流程規則（沒有 hook 擋；hook 只管金鑰檔與文獻主機） | advisor `SKILL.md`「Gate C」 |
| Gate D：預設開新檔、不覆寫研究文件 | 流程規則 | advisor `SKILL.md`「Gate D」 |
| 更新 `research-state.md` 必須使用者同意、只追加 | 流程規則 | advisor `SKILL.md`「Gate D」「Research-state update」 |
| Gate E：同一症狀第二次出現就停止修補，改做對照比較 | 流程規則 | advisor `SKILL.md`「Gate E」 |
| 診斷與建議的內容對不對 | 不宣稱 | — |

## 不宣稱

- 不宣稱引用「支撐」主張：`citecheck.py` 只證明 span 是取回文字裡的原句、數字吻合、識別碼與 metadata 對得上、provenance 與路由合規；
  span 的意思是否真的蘊含主張，仍須人判斷。
- 不宣稱 `--offline` 的控制項涵蓋識別碼解析、撤稿查詢、arXiv / Crossref 的網路行為；K5 與 K1k 沒有打網路，撤稿與識別碼解析在這次發版**沒有**實際執行。
- 不宣稱 hook 能阻止所有越權取回：`literature_host_guard.py` 只判斷它對應得到的工具名稱與 URL；政策檔不可讀時 hook 會放行並記一筆 `policy_unreadable`
  （與 `access_policy.py` 失敗即拒絕的設計不同）；未列名主機的 shell 檢索只發通知。
- 不宣稱顧問流程的品質：evals 只出貨 5 個與領域無關的案例（1、2、3、5、11），結果是 2026-08-24 以模型逐案模擬（每案一個 subagent）得到的，
  不屬於這次的 19 個控制項，也沒有在出貨的空 manifest 上重跑。案例 2（三組 n=6 劑量比較）的第三條斷言在 2026-11-07 收緊為「要說出符合設計的事後檢定（Dunnett 或趨勢檢定）」，
  由維護者自己在協定層重新評分（舊版判斷表會不通過、新版通過），不是重新模擬。領域案例與領域 profile 依擁有者 2026-11-07 的決定不出貨。
- **威脅模型：這些閘門是防代理人粗心的安全帶，不是防代理人蓄意規避的圍欄。** `sources/manifest.json` 沒有簽章，
  代理人自己打一份文字、自己算 sha256 寫進 manifest，citecheck 會判 OK；hook 只看字面上的 URL，用變數拼出來的網址看不到；
  `secret_file_guard.py` 遇到指令裡的 `[user-approved-secret-read]` 標記就放行，而標記誰都打得出來（檔頭的 KNOWN BOUNDARY 有寫）。
  閘門擋得住的是「順手編一句」「抄錯數字」「忘了走 fetchsrc」，擋不住一個刻意繞路的代理人。
- 不宣稱在 Windows 以外能跑；macOS / Linux 未由維護者實測。一位外部讀者在 macOS 上跑出 16/19，三項失敗的原因（PyMuPDF 必裝、讀已安裝的政策檔）已在 v1.0.2 修正，
  但修正後沒有在 macOS 上重跑。
- 不宣稱真實文獻上的表現：出貨的夾具（`good-run`、`bad-run`、profile-lint 夾具）都是虛構的。
- `local_find.py` 與 `textbook_ocr.py` 在沒有教科書庫的機器上是 UNDETERMINED，不是通過。
- 不宣稱真實 PDF 版面已被驗收：K1k 的頁指標案例用的是 3 頁合成 PDF；`verify/pagestore.py` 只用 PyMuPDF 的 `get_text()`，
  雙欄排版與表格的文字順序沒有任何控制項驗過。
- 不宣稱顧問的統計建議經過驗證：`method-selection.md` 的判斷表在 v1.0.2 依外部審閱改正（小樣本不再優先 Bootstrap、預設 Welch、加入事後比較與混合模型、AUC-PR 不再一律優於 AUC-ROC），
  並附上出處，但 evals 是「規則有沒有接上」的協定層評分，不驗「規則對不對」。
