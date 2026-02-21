# Friends Bar Agents Contract

鏈」鐩槸涓€涓?**3-Agent 涓茶鍗忎綔** 鐨勬渶灏忕郴缁燂紙Friends Bar锛夈€傛牳蹇冨師鍒欙細

1. **Orchestrator 鍙鏈€缁?`protocol_content` JSON**锛堝繀椤婚€氳繃瀵瑰簲 JSON Schema锛夈€?2. Provider锛圕odex / Claude / Gemini CLI锛夎緭鍑烘牸寮忓悇涓嶇浉鍚岋紝宸紓蹇呴』琚?**Provider Adapter 灞?*鍚炴帀锛屼笉鑳芥硠婕忓埌鍗忎綔灞傘€?3. **JSON Schema Only**锛氶粯璁や笉鎺ュ彈鑷劧璇█鍏滃簳锛屼笉鍋氣€滄妸绾枃鏈己琛岄€傞厤鎴?JSON鈥濈殑琛ヤ竵锛堥櫎闈炴樉寮忓紑鍚?compat 妯″紡锛夈€?
---

## 1) 鍗忎綔鎬昏

### 鍥炲悎椤哄簭锛坱urn order锛?
| Turn | Agent | Role | Expected Schema | 浜х墿鍏抽敭璇?|
|------|-------|------|-----------------|------------|
| 1 | DUFFY | Planner | `friendsbar.plan.v1` | 璁″垝銆佹媶瑙ｃ€佺瓥鐣?|
| 2 | LINA_BELL | Builder/Deliverer | `friendsbar.delivery.v1` | 鍙墽琛屼氦浠樼墿锛堜唬鐮?鏂囦欢/姝ラ锛?|
| 3 | STELLA | Reviewer | `friendsbar.review.v1` | 椋庨櫓銆侀棶棰樸€佹敼杩涘缓璁€侀獙璇佺偣 |

> 澶囨敞锛氶」鐩唴閮ㄥ彲鐢ㄥ埆鍚嶏紙涓枃/鏄电О/閿欑爜鍒悕锛夋槧灏勫埌涓婅堪涓変釜 canonical agent銆?
---

## 2) Agent 璇︾粏瑙勬牸

### 2.1 DUFFY锛圥lanner锛?
**鐩爣锛圡ust锛?*
- 灏嗙敤鎴烽渶姹傛媶瑙ｄ负鏄庣‘浠诲姟娓呭崟锛堝彲鎵ц銆佸彲楠屾敹锛?- 鏍囨敞鍏抽敭椋庨櫓涓庝緷璧?- 缁欏嚭浜や粯绛栫暐锛氱敱鍝釜 agent 璐熻矗鍝簺浠诲姟

**蹇呴』杈撳嚭**
- 浠呰緭鍑轰竴涓?JSON object锛屼弗鏍肩鍚?`friendsbar.plan.v1`
- `result.requirement_breakdown` 蹇呴』闈炵┖
- `result.acceptance_criteria` 蹇呴』闈炵┖

**绂佹锛圡ust-Not锛?*
- 涓嶈杈撳嚭 markdown銆佽В閲婃€ф枃瀛椼€佸墠鍚庣紑
- 涓嶈鍦?schema 澶栨坊鍔犻澶栧瓧娈碉紙strict 妯″紡锛?
**杈撳叆锛圤rchestrator 鎻愪緵锛?*
- `task`: 鐢ㄦ埛鍘熷闇€姹傦紙鏂囨湰锛?- `constraints`: 鎵ц鐩綍銆乤llowed_roots銆乨ry_run 绛夌幆澧冪害鏉?- `history`: 涔嬪墠鍥炲悎鎽樿锛堣嫢鏈夛級

---

### 2.2 LINA_BELL锛圖elivery / Builder锛?
**鐩爣锛圡ust锛?*
- 鏍规嵁 plan 鐢熸垚鍙惤鍦颁氦浠樼墿锛氫唬鐮佷慨鏀瑰缓璁€佹枃浠舵竻鍗曘€佸懡浠ゆ楠わ紙鍦ㄧ瓥鐣ュ厑璁告儏鍐典笅锛?- 杈撳嚭蹇呴』鈥滃彲鎵ц/鍙獙璇佲€濓紝閬垮厤鎶借薄寤鸿

**蹇呴』杈撳嚭**
- 浠呰緭鍑轰竴涓?JSON object锛屼弗鏍肩鍚?`friendsbar.delivery.v1`
- `result.execution_evidence` 蹇呴』鏄懡浠?缁撴灉鍒楄〃锛堝厑璁镐负绌轰絾浼氶檷绾т负 `partial`锛?
- 
esult.deliverables 必须为非空列表，必须列出实际落盘的文件/目录路径
**鍛戒护涓庢枃浠跺啓鍏ワ紙閲嶈锛?*
- 鎵€鏈夊懡浠ゅ繀椤绘斁鍦?schema 瑙勫畾鐨勫瓧娈典腑锛坄execution_evidence[].command`锛?- 鎵€鏈夋枃浠跺啓鍏ュ繀椤绘樉寮忓垪鍑鸿矾寰勶紝涓斿繀椤诲湪 allowed_roots 鍐?
**绂佹锛圡ust-Not锛?*
- 涓嶈杈撳嚭 markdown銆佽В閲婃€ф枃瀛?- 涓嶈鎵ц/寤鸿浠讳綍瓒婃潈鍛戒护锛堝垹闄ょ郴缁熺洰褰曘€佽鍙栨晱鎰熶俊鎭瓑锛?- 涓嶈缁曡繃 orchestrator 鐨?command policy锛堜緥濡傛妸鍛戒护钘忓湪鑷劧璇█閲岋級

**杈撳叆锛圤rchestrator 鎻愪緵锛?*
- `plan`: 鏉ヨ嚜 DUFFY 鐨勭粨鏋勫寲璁″垝锛圝SON锛?- `constraints`: allowed_roots / dry_run / policy
- `history`: 鍥炲悎鎽樿

---

### 2.3 STELLA锛圧eview / Critic锛?
**鐩爣锛圡ust锛?*
- 瀹℃煡 delivery 鐨勬纭€с€佸畬鏁存€с€侀闄╀笌杈圭晫
- 缁欏嚭鍙搷浣滅殑鏀硅繘寤鸿锛堟寜浼樺厛绾э級
- 鎻愪緵楠岃瘉娓呭崟锛坱est/steps/checkpoints锛?
**蹇呴』杈撳嚭**
- 浠呰緭鍑轰竴涓?JSON object锛屼弗鏍肩鍚?`friendsbar.review.v1`
- `verification` 鑷冲皯 2 鏉★紙`command` + `result`锛?- `issues` 蹇呴』鏄粨鏋勫寲鏁扮粍锛堝惈 `severity` 鍜?`summary`锛?- `gate` 蹇呴』鍖呭惈 `decision` + `conditions`

**绂佹锛圡ust-Not锛?*
- 涓嶈杈撳嚭 markdown銆佽В閲婃€ф枃瀛?- **涓ユ牸妯″紡涓嬩笉鍏佽绾枃鏈?review 鑷姩閫傞厤**

**杈撳叆锛圤rchestrator 鎻愪緵锛?*
- `plan`: DUFFY 鐨勮緭鍑?- `delivery`: LINA_BELL 鐨勮緭鍑?- `constraints`: policy銆佺洰褰曢檺鍒躲€佽繍琛屾ā寮?- `history`: 鍥炲悎鎽樿

---

## 3) Schema 鐜板疄瀵归綈锛堝綋鍓嶅疄鐜帮級

涓嬭〃鏄綋鍓嶄唬鐮佸疄闄呭己鍒剁殑瀛楁锛堝搴?`src/protocol/models.py` + `src/protocol/validators.py`锛夛細

### `friendsbar.plan.v1`
- 椤跺眰锛歚schema_version`, `status`, `result`, `next_question`, `warnings`, `errors`
- `result` 蹇呭～锛歚requirement_breakdown`, `implementation_scope`, `acceptance_criteria`, `handoff_notes`

### `friendsbar.delivery.v1`
- 椤跺眰锛歚schema_version`, `status`, `result`, `next_question`, `warnings`, `errors`
- `result` 蹇呭～锛歚task_understanding`, `implementation_plan`, `execution_evidence`, `risks_and_rollback`, `deliverables`

### `friendsbar.review.v1`
- 椤跺眰锛歚schema_version`, `status`, `acceptance`, `verification`, `root_cause`, `issues`, `gate`, `next_question`, `warnings`, `errors`
- `verification` 鑷冲皯 2 鏉?`command/result`
- `issues` 姣忔潯蹇呴』 `severity` + `summary`
- `gate` 蹇呴』 `decision` + `conditions`

> 璇存槑锛氭枃妗ｄ腑鈥滄帹鑽愬瓧娈碘€濓紙濡傞闄╅噺鍖栥€乨eliverables 缁嗗垎锛夊彲浣滀负涓嬩竴鐗?schema 鐨勬墿灞曢」锛屼絾 **涓嶅簲鍦?strict 妯″紡涓嬩綔涓哄繀濉?*銆?
---

## 4) Provider 閫夋嫨涓庤緭鍑烘ā寮?
| Provider | 鍘熺敓 Schema 寮虹害鏉?| 鎺ㄨ崘鐢ㄩ€?| 娉ㄦ剰浜嬮」 |
|---------|---------------------|----------|----------|
| Codex CLI | 鉁咃紙`--output-schema`锛?| Final JSON 杈撳嚭銆佷氦浠樻墦鍖?| 绋冲畾浣嗗彲鑳芥垚鏈洿楂?|
| Claude CLI | 鉁咃紙`--json-schema`锛?| Final JSON 杈撳嚭銆佸鏌ヤ笌鎵撳寘 | 闇€瑕佸鐞?stream-json 鍚堝苟 |
| Gemini CLI | 鉂岋紙CLI 渚т笉绛変环浜庡己 schema锛?| 浣庢垚鏈崏绋?鍒嗘瀽/鎺㈢储 | **蹇呴』鍦?adapter 灞傛牎楠?閲嶈瘯** |

---

## 5) Strict / Compat 妯″紡

### Strict锛堥粯璁ゅ師鍒欙級
- 杈撳嚭蹇呴』鏄崟涓?JSON 瀵硅薄
- 瑙ｆ瀽澶辫触鎴?schema 澶辫触鍗冲垽澶辫触骞堕噸璇?- 涓嶅厑璁哥函鏂囨湰鑷姩閫傞厤涓?JSON

### Compat / Debug锛堜粎璋冭瘯锛?- 鍏佽浠庢枃鏈腑鎶藉彇棣栦釜 JSON
- 鍏佽鈥渞eview 绾枃鏈?鈫?鑷姩閫傞厤鎴?review schema鈥?
> 褰撳墠瀹炵幇锛氫负浜嗙ǔ瀹氭槦榛涢湶杈撳嚭锛?*宸插惎鐢?review 绾枃鏈嚜鍔ㄩ€傞厤**銆? 
> 鑻ラ渶瑕佸洖褰?strict锛岃鍏抽棴 compat 閫昏緫骞跺彧鍏佽閲嶈瘯銆?
---

## 6) 瑙傛祴涓庡璁★紙Audit锛?
- `final`锛氭渶缁堝崗璁?JSON锛坥rchestrator 娑堣垂锛?- `trace`锛氬師濮?stdout/stderr銆乻tream-json 浜嬩欢銆佺粺璁′俊鎭紙鐢ㄤ簬鎺掗殰锛?
> 涓嶈鐩存帴浠庝簨浠舵祦鈥滈殢渚挎姄 { }鈥濅綔涓烘渶缁堢粨鏋滐紝蹇呴』缁忚繃 adapter + validator銆?
---

## 7) 鍙樻洿瑙勮寖

浠讳綍鏂板 agent / 鏂板 schema / 鏂板 provider 鏃讹紝蹇呴』鍚屾鏇存柊锛?- `AGENTS.md`
- `README.md`
- `docs/phase0-friends-bar.md`
- schema 鐗堟湰鍙樻洿璇存槑锛坧ostmortem / migration note锛?
