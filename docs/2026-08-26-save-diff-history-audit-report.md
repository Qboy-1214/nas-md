# nas-md 淇濆瓨銆佽嚜鍔ㄤ繚瀛樸€丏iff 涓庣増鏈巻鍙叉灦鏋勬繁搴﹀璁℃姤鍛?
> **鎶ュ憡鏃ユ湡**锛?026-08-26
> **瀹¤鑼冨洿**锛氫繚瀛樻満鍒讹紙Save锛夈€佽嚜鍔ㄤ繚瀛橈紙Auto-save锛夈€佸樊寮傛瘮瀵癸紙Diff / LCS / SequenceMatcher锛夈€佺増鏈巻鍙诧紙Version History锛夈€佸疄鏃跺崗鍚岄€氫俊锛圫SE / Watchdog / Sync Layer锛?> **椤圭洰鐗堟湰**锛歯as-md (Web & Python Server)

---

## 鐩綍
1. [鎵ц鎽樿涓庢牳蹇冪粨璁篯(#涓€鎵ц鎽樿涓庢牳蹇冪粨璁?
2. [绯荤粺鏋舵瀯涓庢暟鎹祦鍏ㄦ櫙鍥綸(#浜岀郴缁熸灦鏋勪笌鏁版嵁娴佸叏鏅浘)
   - 2.1 [淇濆瓨涓庤嚜鍔ㄤ繚瀛樻満鍒舵灦鏋刔(#21-淇濆瓨涓庤嚜鍔ㄤ繚瀛樻満鍒舵灦鏋?
   - 2.2 [娈佃惤绾?Diff 涓庡悎骞跺紩鎿嶿(#22-娈佃惤绾?diff-涓庡悎骞跺紩鎿?
   - 2.3 [瀹炴椂鍗忓悓閫氫俊涓?SSE 浜嬩欢娴乚(#23-瀹炴椂鍗忓悓閫氫俊涓?sse-浜嬩欢娴?
   - 2.4 [鐗堟湰鍘嗗彶鎸佷箙鍖栦笌鍥炴粴鏋舵瀯](#24-鐗堟湰鍘嗗彶鎸佷箙鍖栦笌鍥炴粴鏋舵瀯)
3. [閫氫俊绔偣銆佸崗璁笌鏁版嵁濂戠害瀵圭収](#涓夐€氫俊绔偣鍗忚涓庢暟鎹绾﹀鐓?
4. [鍏ㄩ潰闂娓呭崟涓庡垎绾ц瘎瀹?(P0 ~ P3)](#鍥涘叏闈㈤棶棰樻竻鍗曚笌鍒嗙骇璇勫畾-p0--p3)
5. [娣卞害闂鍓栨瀽涓?鏄惁鍊煎緱淇"璁鸿瘉](#浜旀繁搴﹂棶棰樺墫鏋愪笌鏄惁鍊煎緱淇璁鸿瘉)
   - 5.1 [P0 鑷村懡绾ч棶棰?(Critical)](#51-p0-鑷村懡绾ч棶棰?critical)
   - 5.2 [P1 涓ラ噸绾ч棶棰?(High)](#52-p1-涓ラ噸绾ч棶棰?high)
   - 5.3 [P2 涓瓑绋嬪害闂 (Medium)](#53-p2-涓瓑绋嬪害闂-medium)
   - 5.4 [P3 杞诲井绾ч棶棰?(Low)](#54-p3-杞诲井绾ч棶棰?low)
6. [鏋舵瀯閲嶆瀯涓庝紭鍖栧疄鏂借矾绾垮浘](#鍏灦鏋勯噸鏋勪笌浼樺寲瀹炴柦璺嚎鍥?

---

## 涓€銆佹墽琛屾憳瑕佷笌鏍稿績缁撹

鏈」鐩疄鐜颁簡涓€濂楀吋椤?*鍗曟満鏈湴缂栬緫锛團ile System Access API锛?*銆?*NAS 鏈嶅姟绔寕杞斤紙REST + Optimistic Lock锛?*涓?*澶氱杞婚噺鍗忓悓锛圫SE + 娈佃惤绾?3-Way Merge + 鐗堟湰鍘嗗彶杩芥函锛?*鐨?Markdown 缂栬緫绯荤粺銆?
缁忚繃娣卞害浠ｇ爜瀹℃煡锛岀郴缁熷湪鍩烘湰鍗曚汉鍗曠缂栬緫鍦烘櫙涓嬪彲姝ｅ父杩愯锛屼絾鍦?*骞跺彂鍗忓悓銆佸揩閫熻繛缁墦瀛椾繚瀛樸€佸鏉?Markdown 璇硶锛堜唬鐮佸潡/鍏紡/琛ㄦ牸锛夈€佸ぇ鏂囦欢鍘嗗彶姣斿浠ュ強鏂綉閲嶈繛**绛夊鏉傚満鏅笅锛屽瓨鍦?**18 涓灦鏋勭己闄蜂笌閫昏緫婕忔礊**锛?- **P0 鑷村懡绾э紙2 涓級**锛氬墠绔増鏈烦璺冨叏閲忚鐩栧鑷存湭淇濆瓨杈撳叆闈欓粯涓㈠け銆佹壒閲?Diff 搴旂敤閫愭潯 `applyRemoteChange` 浣挎钀界储寮曢敊浣嶅苟澶氭閲嶇粯銆?- **P1 涓ラ噸绾э紙10 涓級**锛氭湇鍔＄ 3-Way Merge 娈佃惤绱㈠紩鍋忕Щ椋庨櫓銆佽嚜鍔ㄤ繚瀛樺紓姝ョ珵鎬佺煭绐楀彛鏈熴€佺洸鍒?`\n\n` 鎾曡澶氳浠ｇ爜鍧椾笌琛ㄦ牸銆乄indows `\r\n` 瀵艰嚧鍋?Diff銆佺増鏈巻鍙插ぇ鏂囦欢 LCS 绠楁硶鍐呭瓨鐖嗙偢锛圤OM锛夈€乄atchdog 鍗曢敭骞跺彂瑕嗙洊銆佹湇鍔＄閲嶅惎鐗堟湰鍙峰綊闆舵柇灞傘€佸崗鍚屽厜鏍囦繚鎶ら敊浣嶃€佺绾胯崏绋挎仮澶嶇己澶便€佸唴瀛樻棤娣樻卑鏈哄埗绛夈€?- **P2 涓瓑绋嬪害锛? 涓級**锛氱畻娉?Opcode 涓嶄竴鑷淬€佺増鏈仮澶嶅紓姝ユ椂搴忛闄┿€佹湯灏炬崲琛屼涪澶便€?- **P3 杞诲井绾э紙3 涓級**锛氭湰鏈烘寕杞戒繚瀛樿褰曞巻鍙茶姹傘€丼SE 缂哄皯蹇冭烦瓒呮椂閲嶈繛銆侀仐鐣欏簾寮冨吋瀹瑰眰浠ｇ爜銆?
---

## 浜屻€佺郴缁熸灦鏋勪笌鏁版嵁娴佸叏鏅浘

```mermaid
graph TD
    subgraph Frontend ["鍓嶇 (Web / Vditor / Vanilla JS)"]
        UI["鐢ㄦ埛缂栬緫鍖?(Vditor)"] -->|Input 浜嬩欢| DirtyCheck["onEditorInput 鑴忔爣璁版鏌?]
        DirtyCheck -->|1.5s Debounce| AutoSave["scheduleAutoSave 鑷姩淇濆瓨"]
        UI -->|Ctrl+S / 鐐瑰嚮淇濆瓨| ManualSave["saveFile 鎵嬪姩淇濆瓨"]

        ManualSave & AutoSave --> DiffEngine["computeParagraphDiff (瀹㈡埛绔?LCS 娈佃惤 Diff)"]
        DiffEngine --> SaveRouter{"鎸傝浇绫诲瀷鍒嗘敮"}

        SaveRouter -->|Server Mount| API_Submit["API.submitChanges (POST /api/mounts/:id/changes)"]
        SaveRouter -->|Local Mount| FSAA_Write["File System Access API (鐩存帴鍐欏叆鏈満纾佺洏)"]
        SaveRouter -->|Remote Proxy| API_Remote["API.putRemoteFile (PUT /api/remote/file)"]

        SSEClient["nasmdSSE (EventSource)"] -->|鐩戝惉 remote_edit / external_reload| SyncLayer["sync_layer.js (鍗忓悓鍚屾灞?"]
        SyncLayer -->|鎵撹ˉ涓亅 UI

        HistoryUI["version_history.js (鐗堟湰鎶藉眽闈㈡澘)"] -->|GET /api/history| HistoryAPI["API 鍘嗗彶鎺ュ彛"]
    end

    subgraph Backend ["鍚庣鏈嶅姟 (Python ThreadingHTTPServer)"]
        HTTP_Handler["MountHTTPHandler (__init__.py)"]

        HTTP_Handler -->|POST /changes| VersionStore["FileVersionStore (file_version_store.py)"]
        HTTP_Handler -->|GET /api/events| SSEHandler["sse_handler.py (SSE 骞挎挱绠＄悊)"]
        HTTP_Handler -->|GET /api/history| HistModule["version_history.py (鍘嗗彶瀛樺偍绠＄悊)"]

        VersionStore --> ParaDiff["paragraph_diff.py (鏈嶅姟绔?Diff/Merge)"]
        VersionStore --> DiskWrite["鏈湴鏂囦欢鍐欏叆 (open/write)"]
        VersionStore --> HistRecord["record_version (鍐欏叆 .version_history JSON)"]
        VersionStore --> SSEBroadcast["sse_broadcast (鍚戝叾浠栧鎴风骞挎挱)"]

        Watchdog["FileWatcher (file_watcher.py)"] -->|鐩戝惉澶栭儴鏂囦欢鍙樺姩| DiskChange["_on_external_change"]
        DiskChange --> VersionStore
    end

    API_Submit --> HTTP_Handler
    SSEBroadcast -.->|SSE 鎺ㄩ€亅 SSEClient
    DiskWrite -.->|瑙﹀彂鏂囦欢绯荤粺浜嬩欢| Watchdog
```

### 2.1 淇濆瓨涓庤嚜鍔ㄤ繚瀛樻満鍒舵灦鏋?
1. **鑴忕姸鎬佺鐞嗭紙Dirty Checking锛?*锛?   - 鐢ㄦ埛鍦?Vditor 缂栬緫鍣ㄤ腑杈撳叆鏃惰Е鍙?`onEditorInput()`锛坵eb/app.js:L3255-L3268锛夛紝閫氳繃 `_isContentDirty()` 瑙勮寖鍖栵紙`_normContent()` 鍘绘帀 `\r\n` 涓庡熬閮ㄦ崲琛屽悗姣斿锛寃eb/app.js:L8-L12锛夊綋鍓嶅€间笌 `_originalContent`銆?   - 鑻ュ浜庤剰鐘舵€佷笖寮€鍚?`state.autoSave`锛屽惎鍔?1500ms 闃叉姈璁℃椂鍣?`scheduleAutoSave()`锛坵eb/app.js:L3285-L3299锛夈€?2. **涓夋ā寮忎繚瀛樿矾鐢憋紙Triple-Path Save Router锛?*锛?   - **鏈嶅姟鍣ㄦ寕杞斤紙Server Mount锛?*锛氳皟鐢?`computeParagraphDiff(baseContent, content)` 璁＄畻娈佃惤鍙樻洿闆嗭紝鎼哄甫 `baseVersion` 鍙戦€?`POST /api/mounts/{id}/changes`锛坵eb/app.js:L3550-L3607锛夈€?   - **鏈満鎸傝浇锛圠ocal Mount锛?*锛氶€氳繃娴忚鍣ㄥ師鐢?File System Access API 鐩存帴鍐欐湰鍦扮鐩橈紝闅忓悗 best-effort 灏濊瘯璋冪敤鏈嶅姟绔褰曠増鏈揩鐓э紙web/app.js:L3499-L3549锛夈€?   - **杩滅▼浠ｇ悊鎸傝浇锛圧emote Proxy锛?*锛氱洿鎺ヤ互鍏ㄩ噺瀛楃涓插彂璧?`PUT /api/remote/file` 浠ｇ悊鍐欏叆杩滅鏈嶅姟鍣紙web/app.js:L3457-L3473锛夈€?3. **浜掓枼閿佷笌绂荤嚎瀹圭伨**锛?   - 鍓嶇缁存姢 `_saveInProgress` 鏍囧織浣嶏紙web/app.js:L3429锛夛紝闃叉骞跺彂閲嶅淇濆瓨锛涘彟鏈?15 绉掕秴鏃跺己鍒堕噴鏀撅紙web/app.js:L3448-L3453锛夈€?   - 鑻ュ浜庢柇缃戠姸鎬侊紙`!navigator.onLine`锛夛紝闄嶇骇瀛樺偍鑷?`localStorage.setItem('nasmd_draft_' + path, ...)`锛坵eb/app.js:L3489-L3495锛夈€?
### 2.2 娈佃惤绾?Diff 涓庡悎骞跺紩鎿?
- **鍒囧垎鍗忚**锛氬墠鍚庣浠ュ弻鎹㈣绗?`\n\n` 浣滀负娈佃惤杈圭晫鍒囧垎鏂囨湰锛屽苟鍓旈櫎鏈熬绾┖鐧芥銆?- **宸紓姣斿**锛?  - **鍓嶇**锛氶噰鐢ㄧ粡鍏?LCS锛堟渶闀垮叕鍏卞瓙搴忓垪锛夊姩鎬佽鍒掔煩闃碉紙web/app.js:L3629-L3721锛夛紝鍥炴函鐢熸垚鍚堝苟 opcodes锛屽啀杞崲涓?`replace`銆乣insert`銆乣delete` 鎿嶄綔搴忓垪锛堝寘鍚?0-based `paraIdx` 涓?`content`锛夈€?  - **鏈嶅姟绔?*锛氶噰鐢?Python 鏍囧噯搴?`difflib.SequenceMatcher(autojunk=False)` 鐢熸垚 `opcodes` 骞舵槧灏勪负鍙樻洿闆嗭紙nas_md/webserver/paragraph_diff.py:L14-L77锛夈€?- **涓夋柟鍚堝苟绛栫暐锛?-Way Merge锛?*锛?  - 褰撳鎴风鎻愪氦鐨?`baseVersion` 钀藉悗浜庢湇鍔＄褰撳墠鐗堟湰鏃讹紝鏈嶅姟绔幏鍙?`baseVersion + 1` 鑷虫渶鏂扮増鏈殑涓棿绱Н鍙樻洿锛屼笌瀹㈡埛绔?incoming 鍙樻洿杩涜鍚堝苟锛坣as_md/webserver/file_version_store.py:L110-L120锛夈€?  - 鍐茬獊澶勭悊鍘熷垯锛氬悓涓€娈佃惤鐨?`replace`/`delete` 瀹炶**鍚庡啓瑕嗙洊锛圠ast Write Wins锛?*锛屾墍鏈?`insert` 鎿嶄綔鍧囦簣淇濈暀锛坣as_md/webserver/paragraph_diff.py:L135-L181锛夈€?  - **搴旂敤绛栫暐**锛歚apply_changes` 閲囩敤**涓€娆℃€ч噸寤虹瓥鐣?*锛圧econstruction Strategy锛夛細灏嗗師鏂囨湰鍒囨钀藉悗鎸夌储寮曟槧灏勶紝灏嗘墍鏈?replace/delete/insert 涓€娆℃€ф秷鍖栦负缁撴灉鏁扮粍锛屽彧鍋氫竴娆?`join`锛坣as_md/webserver/paragraph_diff.py:L80-L132锛夈€?
### 2.3 瀹炴椂鍗忓悓閫氫俊涓?SSE 浜嬩欢娴?
- **瀹㈡埛绔繛鎺?*锛氭墦寮€鏂囦欢鍚庯紝鍓嶇鍒濆鍖?`EventSource('/api/events?file=mountId:path&name=...&color=...')`锛坵eb/sse_client.js:L16-L45锛夎闃呰鏂囦欢鐨?SSE 閫氶亾銆?- **鍗忓悓浜嬩欢骞挎挱**锛?  - `remote_edit`锛氬叾浠栧鎴风閫氳繃 `/changes` 鎴愬姛鏇存柊鏂囦欢鍚庯紝鐢辨湇鍔＄鍚戦櫎鎻愪氦鑰呭鐨勬墍鏈夎闃呭鎴风骞挎挱娈佃惤宸紓闆嗕笌鏈€鏂扮増鏈彿銆?  - `external_reload`锛氬閮ㄧ▼搴忥紙濡?VS Code銆丟it銆丯AS 澶栭儴鍚屾宸ュ叿锛変慨鏀圭鐩樻枃浠惰 watchdog 鎹曡幏鍚庡悜鎵€鏈夊鎴风骞挎挱銆?- **鍓嶇鍚屾灞傦紙Sync Layer锛?*锛?  - `sync_layer.js` 鎺ユ敹 `remote_edit`锛坵eb/sync_layer.js:L221-L293锛夛紝妫€娴嬪綋鍓嶅厜鏍囨槸鍚﹀湪琚慨鏀圭殑娈佃惤銆傝嫢闈炲啿绐佹钀斤紝闃叉姈 300ms 鎵归噺鎵撹ˉ涓佸埌 Vditor 骞跺睍绀烘诞鍔ㄥ崗鍚屽ご鍍忔皵娉°€?  - 鑻ユ娴嬪埌鐗堟湰钀藉悗姝ラ暱 >1锛坄myVersion !== serverVersion - 1`锛夛紝闄嶇骇璋冪敤 `fetchFullContent()` 鎷夊彇鍏ㄩ噺鍐呭鍒锋柊锛坵eb/sync_layer.js:L243-L249锛夈€?  - `handleExternalReload` 瀵?`state.dirty === true` 鐨勬儏鍐垫湁淇濇姢锛屼笉瑕嗙洊缂栬緫鍣ㄥ唴瀹癸紝浠呮彁绀猴紙web/sync_layer.js:L342-L345锛夈€?
### 2.4 鐗堟湰鍘嗗彶鎸佷箙鍖栦笌鍥炴粴鏋舵瀯

- **鏈嶅姟绔瓨鍌ㄧ粨鏋?*锛?  - 瀛樺偍璺緞锛歚storage/.version_history/<safe_filename>.json`锛坣as_md/webserver/version_history.py:L16-L20锛夈€?  - 鏁版嵁缁撴瀯锛氬崟鏂囦欢瀵瑰簲 `FileHistory`锛屼娇鐢?`deque(maxlen=50)` 淇濈暀鏈€杩?50 涓増鏈潯鐩紙`VersionEntry`锛宯as_md/webserver/version_history.py:L23-L44锛夛紝鍖呭惈鍗曡皟鑷鐗堟湰鍙枫€佹椂闂存埑銆佷綔鑰呬俊鎭€佸鎴风 IP/OS/UA銆佸彉鏇?diff 鍒楄〃浠ュ強瀹屾暣鍐呭蹇収銆?  - 棣栨璁板綍浼氳嚜鍔ㄥ啓鍏ュ熀绾跨増鏈紙`previous_content` 浣滀负鍒濆鐗堟湰锛宯as_md/webserver/version_history.py:L202-L212锛夈€?- **鍓嶇鍘嗗彶鎶藉眽锛圴ersion Drawer锛?*锛?  - `version_history.js` 娓叉煋鏃堕棿绾匡紝鏀寔鏌ョ湅鍚勭増鏈殑浣滆€呭強淇敼娈佃惤姒傝锛坵eb/version_history.js:L109-L209锛夈€?  - 鐐瑰嚮鐗瑰畾鐗堟湰瑙﹀彂棰勮妯℃€佹锛屽墠绔娇鐢ㄨ绾?LCS 璁＄畻璇ョ増鏈笌鍓嶅簭鐗堟湰鐨勮绾?`+/-` 宸紓楂樹寒锛坵eb/version_history.js:L241-L287锛夛紝骞舵彁渚涗竴閿?鎭㈠姝ょ増鏈?鎸夐挳锛坵eb/version_history.js:L450-L468锛夈€?
---

## 涓夈€侀€氫俊绔偣銆佸崗璁笌鏁版嵁濂戠害瀵圭収

| 鎺ュ彛绔偣 (Endpoint) | HTTP 鏂规硶 | 璇锋眰璐熻浇 (Payload) | 鍝嶅簲鏁版嵁 (Response) | 鏍稿績鐢ㄩ€斾笌鏈哄埗 |
| :--- | :--- | :--- | :--- | :--- |
| `/api/mounts/{id}/file` | `GET` | Query: `path`, `_t` | Body: 鏂囨湰/浜岃繘鍒? Header: `X-File-Version`, `X-Mod-Time` | 鑾峰彇鏂囦欢鍐呭鍙婂綋鍓嶇増鏈厓鏁版嵁 |
| `/api/mounts/{id}/changes` | `POST` | JSON: `{ baseVersion, changes, authorName, authorColor, os, browser }` | JSON: `{ applied, merged, newVersion, content, appliedChanges }` | **鍗忓悓淇濆瓨鏍稿績鎺ュ彛**锛氬熀浜庢钀?Diff 涓庣増鏈箰瑙傞攣鍚堝苟鎻愪氦 |
| `/api/mounts/{id}/file` | `PUT` | Body: 鍏ㄩ噺鏂囦欢瀛楄妭 | JSON: `{ status, modTime, size, conflict, newVersion }` | 鏃х増/鍏ㄩ噺鍐欏叆鍏煎鎺ュ彛锛堢敤浜庢柊寤恒€佹嫋鎷藉鍏ョ瓑锛?|
| `/api/events` | `GET` | Query: `file`, `name`, `color` | `text/event-stream` (SSE 娴? | **瀹炴椂鍗忓悓闀胯繛鎺?*锛氭帴鏀?`remote_edit`銆乣external_reload`銆乣ping` |
| `/api/history` | `GET` | Query: `file`, `limit`, `version` | JSON: `{ versions: [...] }` 鎴?`{ content, previousContent, version, ... }` | 鏌ヨ鐗堟湰鍘嗗彶鍒楄〃鎴栧崟涓増鏈殑 Diff 瀵规瘮鏁版嵁 |
| `/api/remote/file` | `GET` / `PUT` | Header: `X-Remote-Key`, Query: `src`, `path` | 杩滅鍐呭鎴栧啓鍏ュ搷搴?| 浠ｇ悊璁块棶璺ㄦ満鍣?绉佹湁杩滅 NAS-MD 鏈嶅姟 |

---

## 鍥涖€佸叏闈㈤棶棰樻竻鍗曚笌鍒嗙骇璇勫畾 (P0 ~ P3)

| 绾у埆 | 缂栧彿 | 鎵€灞炴ā鍧?| 闂鍚嶇О | 瑙﹀彂鏉′欢 | 褰卞搷鍚庢灉 | 寤鸿澶勭悊 |
| :---: | :--- | :--- | :--- | :--- | :--- | :---: |
| **P0** | ISSUE-01 | 鍓嶇鍗忓悓鍚屾 | `fetchFullContent` 寮哄埗瑕嗙洊鏈繚瀛樺唴瀹?| 鏈湴鏈夋湭淇濆瓨杈撳叆鏃舵敹鍒拌法鐗堟湰杩滅▼鍙樻洿 | 鏈湴姝ｅ湪杈撳叆鐨勬枃瀛楄闈欓粯鎶归櫎 | **蹇呴』淇** |
| **P0** | ISSUE-02 | 鍓嶇鍗忓悓鍚屾 | 鎵归噺鍙樻洿閫愭潯 `applyRemoteChange` 绱㈠紩閿欎綅 | 鍗曟鏀跺埌澶氫釜娈佃惤鐨勬贩鍚堝鍒犳敼 | 淇敼閿欎綅锛屽娆￠噸缁樺崱椤?| **蹇呴』淇** |
| **P1** | ISSUE-03 | 鏈嶅姟绔増鏈瓨鍌?| 3-Way Merge 娈佃惤绱㈠紩鍋忕Щ | 涓や汉骞跺彂淇濆瓨涓斾腑闂寸増鏈湁娈佃惤澧炲垹 | replace/delete 浣滅敤鍦ㄩ敊璇钀戒笂 | **蹇呴』淇** |
| **P1** | ISSUE-04 | 鑷姩淇濆瓨 | `markClean()` 鐭獥鍙ｇ珵鎬?| 鑷姩淇濆瓨閫斾腑鐢ㄦ埛鎸佺画鎵撳瓧鍚庡叧闂〉闈?| 鏋佺煭绐楀彛鍐呮柊杈撳叆鍙兘涓㈠け | **寤鸿淇** |
| **P1** | ISSUE-05 | Diff 寮曟搸 | `\n\n` 鐩插垏鎾曡浠ｇ爜鍧椾笌琛ㄦ牸 | Markdown 鍚┖琛岀殑浠ｇ爜鍧?琛ㄦ牸/鍏紡 | 璇硶鍧楄鎴柇鎹熷潖 | **蹇呴』淇** |
| **P1** | ISSUE-06 | 璺ㄥ钩鍙?| 鏈鑼冨寲 CRLF 鎹㈣绗?| Windows 鐜缂栬緫 | 铏氬亣鍙樻洿涓庝贡鐮?| **蹇呴』淇** |
| **P1** | ISSUE-07 | 鐗堟湰鍘嗗彶 | 琛岀骇 LCS O(M*N) 鐭╅樀 | 鏌ョ湅鏁板崈琛屾枃妗ｇ増鏈巻鍙?| 涓荤嚎绋嬪崱姝?/ OOM | **蹇呴』淇** |
| **P1** | ISSUE-08 | Watchdog | `mark_expected` 鍗曢敭瑕嗙洊绔炴€?| 杩炵画楂橀鑷姩淇濆瓨 | 璇姤"鏂囦欢琚閮ㄤ慨鏀? | **蹇呴』淇** |
| **P1** | ISSUE-09 | 鏈嶅姟绔姸鎬?| 閲嶅惎鍚庣増鏈彿褰掗浂鏂眰 | 鏈嶅姟绔噸鍚悗棣栨缂栬緫 | 鐗堟湰鍙峰€掗€€鍐茬獊 | **蹇呴』淇** |
| **P1** | ISSUE-10 | 鍗忓悓鍏夋爣 | DOM 绱㈠紩涓?MD 绱㈠紩閿欎綅 | 宓屽鍒楄〃/琛ㄦ牸涓崗鍚岀紪杈?| 鍏夋爣淇濇姢澶辨晥 | **寤鸿淇** |
| **P1** | ISSUE-11 | 绂荤嚎鍚屾 | 绂荤嚎鑽夌鑱旂綉鍚庢湭鑷姩鍚屾 | 鏂綉缂栬緫鍚庨噸鏂拌仈缃?| 鑽夌婊炵暀涓嶄笂浼?| **蹇呴』淇** |
| **P1** | ISSUE-12 | 鍐呭瓨绠＄悊 | 鍐呭瓨瀛楀吀鏃犳窐姹版満鍒?| 闀挎湡杩愯缂栬緫澶ч噺鏂囦欢 | 鍐呭瓨鎸佺画鑶ㄨ儉 | **寤鸿淇** |
| **P2** | ISSUE-13 | 绠楁硶涓€鑷存€?| 鍓嶇 LCS 涓庡悗绔?SequenceMatcher 宸紓 | 澶氭涔卞簭淇敼 | 鍙樻洿鎻忚堪寰皬宸紓 | **寤鸿淇** |
| **P2** | ISSUE-14 | 鐗堟湰鎭㈠ | `setTimeout(200ms)` 纭紪鐮?| 鎭㈠澶ф枃妗ｇ増鏈?| 娓叉煋鏈畬鎴愬嵆淇濆瓨 | **寤鸿淇** |
| **P2** | ISSUE-15 | 娈佃惤鍒囧垎 | 鑷姩涓㈠純鏂囨。鏈熬绌鸿 | 鏂囨湯鏈夋剰淇濈暀鎹㈣绗?| 鏍煎紡淇濈湡搴﹀彈鎹?| **寤鸿淇** |
| **P3** | ISSUE-16 | 鏈満鎸傝浇 | best-effort 鍚戞湇鍔＄鎻愪氦鍘嗗彶 | 鏈満鎸傝浇涓旀湇鍔＄鏃犲搴旀寕杞?| 鎺у埗鍙?warn 鏃ュ織 | **鍙殏缂?* |
| **P3** | ISSUE-17 | SSE 杩炴帴 | 缂哄皯蹇冭烦瓒呮椂閲嶈繛 | 缃戠粶鎶栧姩鎴栦紤鐪犲敜閱?| 渚濊禆鍘熺敓閲嶈繛鏈哄埗 | **鍙殏缂?* |
| **P3** | ISSUE-18 | 鏃х増 API | `PUT /file` 閬楃暀鍏煎灞?| 姝ｅ父缂栬緫涓嶈Е鍙?| 缁存姢璐熸媴 | **鍙殏缂?* |

---

## 浜斻€佹繁搴﹂棶棰樺墫鏋愪笌"鏄惁鍊煎緱淇"璁鸿瘉

---

### 5.1 P0 鑷村懡绾ч棶棰?(Critical)

#### ISSUE-01: `handleRemoteEdit` 鐗堟湰璺ㄥ害澶ф椂 `fetchFullContent` 寮哄埗瑕嗙洊鏈繚瀛樺唴瀹?
- **浠ｇ爜浣嶇疆**锛歸eb/sync_layer.js:L241-L249銆亀eb/sync_layer.js:L295-L321
- **鍘熺悊鍓栨瀽**锛?  褰撳鎴风鐗堟湰涓庤繙绔増鏈樊璺濆ぇ浜?1 鏃讹紙渚嬪鐭椂绂荤嚎鎴栬繙绔繛缁彁浜や簡 2 娆＄紪杈戯級锛屼唬鐮佽Е鍙?`fetchFullContent()`锛?  ```javascript
  // sync_layer.js L243-L249
  if (myVersion !== serverVersion - 1) {
    state.baseVersion = serverVersion;
    var versionKey0 = data.mountId + ':' + data.path;
    if (state.fileVersions) state.fileVersions[versionKey0] = serverVersion;
    fetchFullContent(data.mountId, data.path, serverVersion);
    return;
  }
  ```
  鍦?`fetchFullContent` 涓細
  ```javascript
  // sync_layer.js L297-L301
  API.getFile(mountId, path).then(function (result) {
    if (!result || !result.content) return;
    _applyingRemote = true;
    window._vditor.setValue(result.content); // 鏆村姏瑕嗙洊褰撳墠缂栬緫鍣紒
    window._originalContent = result.content;
    ...
  });
  ```
  濡傛灉鏈湴鐢ㄦ埛姝ｅ湪缂栬緫锛坄state.dirty === true`锛夛紝鏈繚瀛樼殑鑽夌浼氳鐬棿鎶归櫎锛屾病鏈変换浣曟彁绀恒€佺‘璁ゆ垨澶囦唤銆?
  **瀵规瘮**锛歚handleExternalReload` 璺緞鏈?dirty 淇濇姢锛坵eb/sync_layer.js:L342-L345锛夛紝浣?`fetchFullContent` 璺緞瀹屽叏缂哄け姝や繚鎶ゃ€?- **鏄惁鍊煎緱淇**锛?*銆愬繀椤讳慨澶嶃€?*
- **鐞嗙敱**锛氱洿鎺ヨ繚鑳?鏁版嵁涓嶄涪澶?搴曠嚎鍘熷垯銆傝櫧鐒惰Е鍙戞潯浠惰緝涓ユ牸锛堥渶瑕佺増鏈樊璺?=2锛夛紝浣嗗湪寮辩綉鎴栧浜哄崗鍚屾椂瀹规槗鍑虹幇銆?- **淇鏂规**锛氬湪 `fetchFullContent` 鍐呮鏌?`state.dirty`锛岃嫢涓?`true` 搴斿脊鍑烘ā鎬佹鎻愮ず鐢ㄦ埛瀛樺湪鍐茬獊锛屾彁渚?淇濈暀鎴戠殑淇敼骞舵殏瀛?鎴?鏀惧純鏈湴淇敼"閫夐」銆傚弬鑰?`handleExternalReload` 鐨勪繚鎶ら€昏緫銆?
---

#### ISSUE-02: `sync_layer.js` 鎵归噺鍙樻洿閫愭潯 `applyRemoteChange` 浜х敓娈佃惤绱㈠紩閿欎綅骞跺娆￠噸缁?
- **浠ｇ爜浣嶇疆**锛歸eb/sync_layer.js:L151-L204銆亀eb/sync_layer.js:L278-L292
- **鍘熺悊鍓栨瀽**锛?  鍦ㄩ槻鎶栬鏃跺櫒鍒版湡鍚庯紝浠ｇ爜閬嶅巻鍙樻洿鍒楄〃锛?  ```javascript
  // sync_layer.js L282-L283
  for (var j = 0; j < batch.length; j++) {
    applyRemoteChange(batch[j].change, batch[j].author);
  }
  ```
  `applyRemoteChange` 涓瘡娆¤皟鐢ㄩ兘锛?  1. `getValue()` 鍙栧綋鍓嶅唴瀹瑰苟 `split('\n\n')` 鍒囨钀?  2. 瀵?`paragraphs` 鎵ц `splice(change.paraIdx, 1)` 绛夋搷浣?  3. `join('\n\n')` 鍚庤皟鐢?`window._vditor.setValue(newContent)`

  **鏍稿績闂**锛氭瘡涓?change 鐨?`paraIdx` 鏄熀浜?*鏈嶅姟绔師濮嬫枃鏈?*鐨勭储寮曘€傜涓€鏉?delete 鎿嶄綔鏀瑰彉浜嗘钀芥暟鍚庯紝绗簩鏉?change 鐨?`paraIdx` 灏变細鍛戒腑閿欒鐨勬钀姐€傚悓鏃舵瘡鏉″彉鏇撮兘鎵ц涓€娆?`setValue()`锛屽鑷村娆?DOM 閲嶇粯锛屽厜鏍囪烦鍔ㄣ€佺晫闈㈤棯鐑併€?- **鏄惁鍊煎緱淇**锛?*銆愬繀椤讳慨澶嶃€?*
- **鐞嗙敱**锛氬彧瑕佷竴娆¤繙绋嬫彁浜ゅ寘鍚?2 澶勪互涓婄殑澧炲垹娈佃惤锛屽鎴风鍚屾娓叉煋缁撴灉蹇呭畾閿欎贡銆?- **淇鏂规**锛氬簲鍙傝€冩湇鍔＄ `apply_changes` 鐨勪竴娆℃€ч噸寤虹畻娉曪紙nas_md/webserver/paragraph_diff.py:L80-L132锛夛紝鍦ㄥ唴瀛樹腑灏嗘墍鏈?batch 鍙樻洿缁熶竴搴旂敤鐢熸垚鏈€缁堝瓧绗︿覆锛岀劧鍚庡彧璋冪敤涓€娆?`setValue()`銆?
---

### 5.2 P1 涓ラ噸绾ч棶棰?(High)

#### ISSUE-03: 3-Way Merge 娈佃惤绱㈠紩鍋忕Щ鈥斺€斾腑闂寸増鏈钀藉鍒犲鑷?incoming changes 鐨?`paraIdx` 閿欎綅

- **浠ｇ爜浣嶇疆**锛歯as_md/webserver/file_version_store.py:L110-L120
- **鍘熺悊鍓栨瀽**锛?  ```python
  # file_version_store.py L110-L120
  merged = True
  accumulated_changes = []
  for v in range(base_version + 1, fv.version + 1):
      prev = fv.changes_by_version.get(v, [])
      accumulated_changes = merge_changes(accumulated_changes, prev)
  merged_changes = merge_changes(accumulated_changes, changes)
  new_content = apply_diff(fv.content, merged_changes)
  ```
  `apply_changes`锛坣as_md/webserver/paragraph_diff.py:L80-L132锛夐噰鐢?*閲嶅缓绛栫暐**锛氫互杈撳叆 `text` 鐨勬钀藉垪琛ㄤ负鍩哄噯锛屽皢 `paraIdx` 浣滀负璇ュ垪琛ㄤ笂鐨勭储寮曞仛涓€娆℃€ф槧灏勩€傚洜姝や笉浼氬嚭鐜?insert 琚簩娆℃彃鍏ラ噸澶?鐨勬儏鍐碘€斺€擿apply_changes` 鍙墽琛屼竴娆′笖涓嶅仛绱姞銆?
  **鐪熸鐨勯闄?*鍦ㄤ簬锛歚accumulated_changes` 涓?`changes` 鐨?`paraIdx` 閮藉熀浜庡悇鑷殑鍩虹嚎鏂囨湰銆傜粡杩?`merge_changes` 鍚堝苟鍚庯紝`merged_changes` 涓殑 `paraIdx` 浠嶇劧鍩轰簬**鍘熷鍩虹嚎**鐨勭储寮曘€備絾 `fv.content` 宸茬粡杩囦腑闂寸増鏈殑娈佃惤澧炲垹锛屾钀芥€绘暟鍜屼綅缃凡鏀瑰彉銆傚皢鍩轰簬鏃у熀绾跨储寮曠殑 `merged_changes` 搴旂敤鍒版钀芥暟宸插彉鍖栫殑 `fv.content` 涓婏紝鍙兘瀵艰嚧 replace/delete 浣滅敤鍦ㄩ敊璇殑娈佃惤涓娿€?
  **绀轰緥**锛?  - 鍩虹嚎鏈夋钀?[A, B, C]锛堝叡 3 娈碉級
  - 涓棿鐗堟湰鍦ㄧ储寮?0 鍓嶆彃鍏?X锛宖v.content 鍙樹负 [X, A, B, C]
  - 瀹㈡埛绔熀浜庡熀绾夸慨鏀圭 2 娈?C锛宑hange: `{type: "replace", paraIdx: 2, content: "C'"}`
  - merge 鍚?`paraIdx: 2` 浠嶄负 2锛屼絾 fv.content 鐨勭 2 娈电幇鍦ㄦ槸 B锛堜笉鏄?C锛夆€斺€?*閿欎綅**
- **鏄惁鍊煎緱淇**锛?*銆愬繀椤讳慨澶嶃€?*
- **鐞嗙敱**锛氬湪澶氫汉鍗忓悓涓斾腑闂寸増鏈湁娈佃惤澧炲垹鏃讹紝鍚堝苟缁撴灉浼氫慨鏀瑰埌閿欒鐨勬钀姐€備絾鍦ㄥ崟浜轰娇鐢ㄦ垨浣庨淇濆瓨鐨勫満鏅笅涓嶈Е鍙戙€?- **淇鏂规**锛?  - **鏂规 A锛圤T 鍋忕Щ鍙樻崲锛?*锛氬皢 incoming changes 鐨?`paraIdx` 鏍规嵁 `accumulated_changes` 涓殑 insert/delete 杩涜鍋忕Щ鍙樻崲鍚庡啀 apply 鍒?`fv.content`銆?  - **鏂规 B锛堜笁鏂规枃鏈悎骞讹級**锛氬湪鏈嶅姟绔繚瀛?`base_version` 瀵瑰簲鐨勬枃鏈揩鐓э紙鍙粠 `version_history` 璇诲彇锛夛紝浠ュ熀绾挎枃鏈负涓績鍋氭爣鍑?3-Way Merge銆?
---

#### ISSUE-04: 鑷姩淇濆瓨寮傛鎵ц鏈熼棿鐢ㄦ埛缁х画鎵撳瓧锛宍markClean()` 浜х敓鐭獥鍙ｇ珵鎬?
- **浠ｇ爜浣嶇疆**锛歸eb/app.js:L3431-L3624
- **鍘熺悊鍓栨瀽**锛?  1. `saveFile()` 鍚姩鏃舵崟鑾?`content = window._vditor.getValue()`锛圠3482锛夊苟鍙戝嚭缃戠粶璇锋眰銆?  2. 璇锋眰鍦ㄩ€旓紙50~300ms锛夋湡闂达紝鐢ㄦ埛鏁插叆鏂板崟璇?"hello"銆?  3. `onEditorInput()` 瑙﹀彂锛宍_isContentDirty()` 妫€娴嬪埌宸紓锛岀疆 `state.dirty = true`銆?  4. 缃戠粶璇锋眰鎴愬姛杩斿洖锛屾墽琛?`markClean()`锛圠3592锛夛紝閲嶇疆 `state.dirty = false`銆?  5. **缂撹В鏈哄埗**锛歚finally` 鍧楋紙web/app.js:L3614-L3623锛変細閲嶆柊妫€鏌?`state.dirty`锛?     ```javascript
     } finally {
       _saveInProgress = false;
       ...
       if (state.dirty && state.autoSave && state.currentPath) {
         scheduleAutoSave(); // 鑻ヤ粛 dirty 鍒欏啀娆¤皟搴︿繚瀛?       }
     }
     ```
     浣嗘鏃?`state.dirty` 宸茶 `markClean()` 缃负 `false`锛屾墍浠ヤ笉浼氳Е鍙戦噸鏂拌皟搴︺€傞渶瑕佺瓑鍒扮敤鎴?*涓嬩竴娆?*鎵撳瓧瑙﹀彂 `onEditorInput` 鎵嶄細閲嶆柊妫€娴?dirty銆?  6. **瀹為檯绐楀彛鏈?*锛氫粠 `markClean()` 鎵ц鍒颁笅涓€娆?`onEditorInput` 瑙﹀彂鐨勯棿闅欙紙杩炵画鎵撳瓧鏃堕€氬父涓烘绉掔骇锛夈€傝嫢鐢ㄦ埛鎭板ソ鍦ㄦ绐楀彛鍏抽棴椤甸潰锛屽垯 "hello" 浼氫涪澶便€?- **鏄惁鍊煎緱淇**锛?*銆愬缓璁慨澶嶃€?*
- **鐞嗙敱**锛氬瓨鍦ㄧ湡瀹炰絾绐勭殑绔炴€佺獥鍙ｃ€傛鐜囪櫧浣庯紝浣嗚嚜鍔ㄤ繚瀛樼殑鏍稿績鎵胯鏄?涓嶄涪鏁版嵁"銆?- **淇鏂规**锛氬湪 `markClean` 鍓嶅啀娆℃瘮瀵瑰綋鍓嶇紪杈戝櫒鐨勫疄闄呭唴瀹逛笌鏈鎴愬姛淇濆瓨鐨勫唴瀹癸紱鑻ヤ粛鏈夊樊寮傚垯淇濇寔 `dirty = true`銆?
---

#### ISSUE-05: 浣跨敤 `\n\n` 鍒囧垎娈佃惤锛岀矇纰庝唬鐮佸潡銆佽〃鏍笺€佸叕寮忓潡绛夊琛?Markdown 缁撴瀯

- **浠ｇ爜浣嶇疆**锛歯as_md/webserver/paragraph_diff.py:L6-L11銆亀eb/app.js:L3633-L3637銆亀eb/sync_layer.js:L155
- **鍘熺悊鍓栨瀽**锛?  浠ｇ爜鍧楋紙```` ``` ````锛夊唴閮ㄣ€佸琛屽叕寮忓潡锛坄$$`锛夈€佽〃鏍间箣闂寸粡甯稿寘鍚┖琛屻€傜畝鍗曚娇鐢?`text.split("\n\n")` 浼氬皢涓€娈靛畬鏁寸殑浠ｇ爜鍧楁í鍒囨垚鑻ュ共涓吉娈佃惤锛屽鑷?diff 璁＄畻涓庡崗鍚屽悎骞舵椂璇硶鍧楄鎴柇鎹熷潖銆?- **鏄惁鍊煎緱淇**锛?*銆愬繀椤讳慨澶嶃€?*
- **鐞嗙敱**锛歯as-md 鏄妧鏈煡璇嗙鐞嗚蒋浠讹紝浠ｇ爜鍧楀拰琛ㄦ牸鏄渶楂橀鐨勬牳蹇冨厓绱犮€?*璇ラ棶棰樺湪鍗曚汉浣跨敤鏃朵篃楂橀瑙﹀彂**銆?- **淇鏂规**锛氬紩鍏ヨ交閲忕骇 Markdown 鍧楃骇瑙ｆ瀽鍣紝璇嗗埆 Fenced Code Blocks銆丮ath Blocks 鍜?Frontmatter锛屽皢鍏朵綔涓轰笉鍙垎鍓茬殑鍗曚竴娈佃惤鍘熷瓙澶勭悊锛涙垨灏嗘钀界骇 Diff 鍗囩骇涓鸿绾?Diff 寮曟搸銆?
---

#### ISSUE-06: 鏈仛 CRLF 瑙勮寖鍖栵紝Windows `\r\n` 瀵艰嚧 Diff 閿欎綅鍙婂巻鍙蹭贡鐮?
- **浠ｇ爜浣嶇疆**锛歯as_md/webserver/paragraph_diff.py:L6-L11銆亀eb/app.js:L3633-L3637
- **鍘熺悊鍓栨瀽**锛?  Windows 鏂囦欢鐨?`\r\n\r\n` 鐢?`split("\n\n")` 鍒囧垎鍚庯紝姣忎釜娈佃惤鏈熬閮藉甫鏈?`\r`銆傚墠绔?`_isContentDirty()` 宸叉湁 `_normContent()` 鍋?CRLF 瑙勮寖鍖栵紙web/app.js:L8-L9锛夛紝浣嗚繖浠呯敤浜庤剰鏍囪姣斿锛?*Diff 璁＄畻鐨?`computeParagraphDiff` 鍜?`split_paragraphs` 鍧囨湭鍋氳鑼冨寲**銆?- **鏄惁鍊煎緱淇**锛?*銆愬繀椤讳慨澶嶃€?*
- **鐞嗙敱**锛歐indows 涓?Linux / macOS 璺ㄨ澶囪闂櫘閬嶏紝琛屽熬绗︽贩涔卞鑷寸増鏈巻鍙插叏鏄亣鍙樻洿銆傝椤圭洰鏈韩灏卞湪 Windows 涓婂紑鍙戯紙paragraph_diff.py 鑷韩鍗充负 CRLF 缂栫爜锛夈€?- **淇鏂规**锛氬湪 `split_paragraphs`锛堝墠鍚庣锛夊拰 `computeParagraphDiff` 杈撳叆鍏ュ彛缁熶竴鎵ц CRLF -> LF 瑙勮寖鍖栥€?
---

#### ISSUE-07: `version_history.js` 琛岀骇 LCS 绠楁硶閲囩敤鍏ㄩ噺 O(M*N) 鐭╅樀锛屽ぇ鏂囦欢鍐荤粨/宕╂簝娴忚鍣?
- **浠ｇ爜浣嶇疆**锛歸eb/version_history.js:L241-L287
- **鍘熺悊鍓栨瀽**锛?  `computeLineDiff` 鍦ㄦ祻瑙堝櫒涓荤嚎绋嬬洿鎺ユ瀯閫犲畬鏁?(M+1) x (N+1) 鐭╅樀銆傚綋鎵撳紑 3000~5000 琛岀殑闀挎枃妗ｆ煡鐪嬬増鏈樊寮傛椂锛屾暟缁勫崰鐢ㄦ暟鐧惧厗鍐呭瓨锛屽鑷撮〉闈㈠け鍘诲搷搴旀垨宕╂簝銆?- **鏄惁鍊煎緱淇**锛?*銆愬繀椤讳慨澶嶃€?*
- **鐞嗙敱**锛氬ぇ鏂囦欢鏌ョ湅鍘嗗彶鍗冲埢宕╂簝锛屼弗閲嶅奖鍝嶆牳蹇冨姛鑳藉彲鐢ㄦ€с€?- **淇鏂规**锛氭浛鎹负 Myers 宸紓绠楁硶锛堟垨浣跨敤涓よ婊氬姩鏁扮粍浼樺寲绌洪棿鑷?O(N)锛屼笖澧炲姞琛屾暟鎴柇闄愬埗/Web Worker 寮傛璁＄畻锛夈€?
---

#### ISSUE-08: 鏂囦欢鐩戞帶 Watchdog `mark_expected` 鍗曢敭骞跺彂绔炴€佸鑷磋瑙﹀彂 `external_reload`

- **浠ｇ爜浣嶇疆**锛歯as_md/webserver/file_watcher.py:L156-L177
- **鍘熺悊鍓栨瀽**锛?  `_expected` 瀛楀吀浠?`"mountId:rel_path"` 涓哄崟涓€閿瓨鍌ㄦ湡鏈涘唴瀹广€傝繛缁繚瀛樹袱娆℃椂锛岀浜屾瑕嗙洊浜嗙涓€娆＄殑鏈熸湜鍊笺€傚綋绗竴涓啓浜嬩欢寤惰繜鍒拌揪鏃讹紝`is_expected` 鐨?one-shot pop 娑堣垂浜嗙浜屾鐨勬湡鏈涘€硷紝瀵艰嚧绗簩娆＄湡姝ｇ殑鍐欎簨浠跺埌杈炬椂璇垽涓哄閮ㄤ慨鏀广€?- **鏄惁鍊煎緱淇**锛?*銆愬繀椤讳慨澶嶃€?*
- **鐞嗙敱**锛氱敤鎴锋鍦ㄦ甯告墦瀛椾繚瀛樻椂锛岀粡甯歌寮瑰嚭鐨?鏂囦欢宸茶澶栭儴淇敼"骞叉壈銆?- **淇鏂规**锛氬皢 `_expected` 鏀逛负鎸夋枃浠惰矾寰勭淮鎶ょ殑 FIFO 闃熷垪锛坄collections.deque`锛夛紝鎴栨敼鐢ㄥ熀浜庣煭鏈?mtime/鍝堝笇鐨勬牎楠岄泦鍚堛€?
---

#### ISSUE-09: 鏈嶅姟绔噸鍚悗 `FileVersionStore` 鐗堟湰鍙峰綊闆朵笌纾佺洏鍘嗗彶鐗堟湰鍙峰啿绐佹柇灞?
- **浠ｇ爜浣嶇疆**锛歯as_md/webserver/file_version_store.py:L51-L60銆乶as_md/webserver/version_history.py:L196-L200
- **鍘熺悊鍓栨瀽**锛?  `FileVersionStore.init_file` 纭紪鐮?`version=0`銆傛湇鍔＄閲嶅惎鍚庡垵娆″姞杞芥枃浠剁増鏈彿浠?0 寮€濮嬶紝鑰岀鐩樹笂鐨?`.version_history` 鍙兘宸茶褰曞埌鐗堟湰 20銆傚悗缁繚瀛樹骇鐢熺殑鐗堟湰 1銆? 浼氳杩藉姞锛屽鑷寸増鏈簭鍒楀嚭鐜伴潪鍗曡皟鏂眰銆?*璇ラ棶棰樺湪鍗曚汉浣跨敤鏃朵篃浼氬湪姣忔鏈嶅姟绔噸鍚悗瑙﹀彂銆?*
- **鏄惁鍊煎緱淇**锛?*銆愬繀椤讳慨澶嶃€?*
- **鐞嗙敱**锛氱増鏈彿鐨勫崟璋冭嚜澧炴槸涔愯骞跺彂鎺у埗涓庡巻鍙茶拷韪殑鍩虹銆?- **淇鏂规**锛歚init_file` 鏃朵粠 `version_history` 涓鍙栧凡鎸佷箙鍖栫殑鏈€鏂扮増鏈彿浣滀负鍩哄噯銆?
---

#### ISSUE-10: 鍓嶇鍗忓悓鍏夋爣淇濇姢 `_cursorParaIdx` DOM 绱㈠紩涓?Markdown 绱㈠紩閿欎綅

- **浠ｇ爜浣嶇疆**锛歸eb/sync_layer.js:L29-L46
- **鍘熺悊鍓栨瀽**锛?  `getCursorParagraphIndex()` 閫氳繃 DOM `querySelectorAll('p, h1, ..., table, hr')` 鑾峰彇搴忓彿銆備絾 Vditor 鐨?DOM 鍏冪礌宓屽锛堝垪琛ㄥ唴鐨?li/p锛岃〃鏍煎唴鐨?td 绛夛級瀵艰嚧 DOM 绱㈠紩杩滃ぇ浜?Markdown 娈佃惤绱㈠紩锛屼袱鑰呭潗鏍囩郴鑴辫妭銆?- **鏄惁鍊煎緱淇**锛?*銆愬缓璁慨澶嶃€?*
- **鐞嗙敱**锛氫繚鎶ゆ満鍒跺舰鍚岃櫄璁撅紝涓嶄粎鏃犳硶淇濇姢褰撳墠娈佃惤锛岃繕鍙兘閿欒闃绘柇鍏朵粬娈佃惤鐨勬洿鏂般€?- **淇鏂规**锛氬熀浜?Markdown 鏂囨湰鍏夋爣瀛楃鍋忕Щ閲忓弽鏌ユ钀界储寮曘€?
---

#### ISSUE-11: 绂荤嚎鑽夌鍦ㄨ仈缃戝悗浠庢湭鑷姩鍚屾鎴栨彁绀?
- **浠ｇ爜浣嶇疆**锛歸eb/app.js:L3489-L3495銆亀eb/app.js:L4158-L4195
- **鍘熺悊鍓栨瀽**锛?  鏂綉鏃跺墠绔皢鑽夌鍐欏叆 `localStorage` 骞舵彁绀?鎭㈠杩炴帴鍚庤嚜鍔ㄥ悓姝?銆備絾 `online` 浜嬩欢澶勭悊锛坵eb/app.js:L4187-L4191锛変粎璋冪敤 `performSync()` 鍚屾鏂囦欢鏍戯紝浠庢湭閬嶅巻 `nasmd_draft_*` 鏉＄洰銆?- **鏄惁鍊煎緱淇**锛?*銆愬繀椤讳慨澶嶃€?*
- **鐞嗙敱**锛氱粰鐢ㄦ埛閫犳垚浜?宸茬绾夸繚瀛樹笖浼氳嚜鍔ㄤ笂浼?鐨勫亣璞°€?- **淇鏂规**锛氬湪 `online` 浜嬩欢鍥炶皟涓鍔犳湰鍦拌崏绋挎壂鎻忎笌鑷姩鎻愪氦娴佺▼銆?
---

#### ISSUE-12: 鍐呭瓨瀛楀吀鏃犳窐姹版満鍒讹紝闀挎椂闂磋繍琛屽唴瀛樻硠婕?
- **浠ｇ爜浣嶇疆**锛歯as_md/webserver/file_version_store.py:L48銆乶as_md/webserver/version_history.py:L133
- **鍘熺悊鍓栨瀽**锛?  鍏ㄥ眬瀛楀吀 `_histories` 鍜?`_files` 闅忔瘡娆¤闂柊鏂囦欢涓嶆柇澧炲姞锛屾湭璁剧疆 LRU 娣樻卑銆傚疄闄呬娇鐢ㄤ腑閫氬父鍙湁鎵撳紑缂栬緫鐨勬枃浠舵墠鍔犺浇鍒板唴瀛樸€?- **鏄惁鍊煎緱淇**锛?*銆愬缓璁慨澶嶃€?*
- **鐞嗙敱**锛歂AS 闀挎湡杩愯锛堟暟鏈堣嚦鏁板勾锛夛紝鍐呭瓨浼氭寔缁闀裤€?- **淇鏂规**锛氬紩鍏?`OrderedDict` 鎴?`functools.lru_cache`锛岄檺鍒跺父椹诲唴瀛樻枃浠舵暟涓婇檺銆?
---

### 5.3 P2 涓瓑绋嬪害闂 (Medium)

#### ISSUE-13: 鍓嶇 LCS 涓庡悗绔?`SequenceMatcher` 鍦ㄩ潪瀵归綈鍦烘櫙鐢熸垚涓嶅悓 Opcode

- **浠ｇ爜浣嶇疆**锛歸eb/app.js:L3629-L3721 vs nas_md/webserver/paragraph_diff.py:L14-L77
- **鍘熺悊鍓栨瀽**锛?  鍓嶇浣跨敤鏍囧噯 LCS 绠楁硶锛屽悗绔娇鐢ㄥ惎鍙戝紡 Gestalt Pattern Matching锛坄SequenceMatcher`锛夈€傚綋鍓嶈璁′腑瀹㈡埛绔绠?diff 鍚庡彂閫佺粰鏈嶅姟绔洿鎺?apply锛坒ast path锛夛紝鏈嶅姟绔粎鍦?`PUT /file` 鍏煎璺緞涓婁娇鐢ㄨ嚜宸辩殑 `compute_diff`锛屾棩甯告祦绋嬩腑涓や釜绠楁硶涓嶇洿鎺ヤ氦浜掋€?- **鏄惁鍊煎緱淇**锛?*銆愬缓璁慨澶嶃€?*
- **鐞嗙敱**锛氱粺涓€鍓嶅悗绔?Diff 琛屼负鏈夊姪浜庨檷浣庡崗鍚岀姸鎬佹満鐨勪笉纭畾鎬с€?
---

#### ISSUE-14: 鐗堟湰鎭㈠娴佺▼渚濊禆 `setTimeout(200ms)`

- **浠ｇ爜浣嶇疆**锛歸eb/version_history.js:L450-L468
- **鍘熺悊鍓栨瀽**锛?  鎭㈠鐗堟湰浣跨敤 `setTimeout(..., 200)` 绛夊緟 Vditor 娓叉煋鍚庝繚瀛橈紝鏃堕棿鏄剢寮辩殑纭紪鐮併€備唬鐮佷繚鐣?`state.baseContent` 涓嶅彉锛堟湁鎰忚璁★紝鐢ㄤ簬姝ｇ‘璁＄畻 diff锛夛紝閫昏緫涓婂悎鐞嗭紝浣?200ms 鍦ㄥぇ鏂囨。鏃跺彲鑳戒笉瓒炽€?- **鏄惁鍊煎緱淇**锛?*銆愬缓璁慨澶嶃€?*
- **淇鏂规**锛氱洃鍚?Vditor 娓叉煋瀹屾垚鍥炶皟浠ｆ浛纭紪鐮?setTimeout銆?
---

#### ISSUE-15: `split_paragraphs` 鑷姩涓㈠純鏂囨。鏈熬绌鸿

- **浠ｇ爜浣嶇疆**锛歯as_md/webserver/paragraph_diff.py:L9-L10銆亀eb/app.js:L3635
- **鍘熺悊鍓栨瀽**锛?  `while paras.pop()` 閫昏緫瀵艰嚧鏂囨湯绌鸿琚己鍒跺幓闄ゃ€?- **鏄惁鍊煎緱淇**锛?*銆愬缓璁慨澶嶃€?*
- **鐞嗙敱**锛氱牬鍧忔牸寮忎繚鐪熷害锛屼絾 Markdown 灏鹃儴绌鸿閫氬父鏃犺涔夊奖鍝嶃€?
---

### 5.4 P3 杞诲井绾ч棶棰?(Low)

#### ISSUE-16: 鏈満鎸傝浇淇濆瓨鍚?best-effort 鍚戞湇鍔＄鎻愪氦鍘嗗彶璁板綍

- **浠ｇ爜浣嶇疆**锛歸eb/app.js:L3518-L3532
- **鍘熺悊鍓栨瀽**锛?  浠ｇ爜宸茬敤 try/catch 鍖呰９涓斾粎 `console.warn`锛屽睘浜庢湁鎰忕殑 best-effort 璁捐銆傚綋鏈嶅姟绔敞鍐屼簡鍚岀洰褰曟寕杞芥椂鍙甯稿伐浣溿€?- **鏄惁鍊煎緱淇**锛?*銆愬彲鏆傜紦淇銆?*

---

#### ISSUE-17: SSE 缂哄皯鑷畾涔夊績璺宠秴鏃堕噸杩炴満鍒?
- **浠ｇ爜浣嶇疆**锛歸eb/sse_client.js:L27-L44
- **鏄惁鍊煎緱淇**锛?*銆愬彲鏆傜紦淇銆?*
- **鐞嗙敱**锛氭祻瑙堝櫒鍘熺敓 `EventSource` 鑷甫鏂嚎閲嶈繛锛屽湪灞€鍩熺綉鍦烘櫙涓嬪熀鏈弧瓒宠姹傘€?
---

#### ISSUE-18: `PUT /file` 閬楃暀鍏煎灞備唬鐮?
- **浠ｇ爜浣嶇疆**锛歯as_md/webserver/__init__.py:L1454-L1560
- **鍘熺悊鍓栨瀽**锛?  鎺ュ彛宸叉爣璁颁负 `DEPRECATED`锛屽唴閮ㄥ凡閲嶆瀯涓鸿皟鐢?`FileVersionStore.apply_changes`銆備粛淇濈暀鐢ㄤ簬鏂囦欢鍒涘缓銆佹嫋鎷藉鍏ャ€侀潪 Markdown 鏂囦欢鍐欏叆绛夊満鏅€?- **鏄惁鍊煎緱淇**锛?*銆愬彲鏆傜紦淇銆?*
- **鐞嗙敱**锛氶潪绠€鍗曢仐鐣?stub锛屽鏂囦欢鍒涘缓/瀵煎叆浠嶆湁瀹為檯鐢ㄩ€斻€傚彲鍦ㄥ悗缁笓椤逛腑璇勪及鎷嗗垎銆?
---

## 鍏€佹灦鏋勯噸鏋勪笌浼樺寲瀹炴柦璺嚎鍥?
```mermaid
flowchart TD
    subgraph Step1 ["绗竴闃舵: 鏍稿績鏁版嵁闃叉崯涓庝慨澶?(P0 + 楂橀 P1)"]
        A1["淇 sync_layer fetchFullContent<br/>澧炲姞 state.dirty 淇濇姢<br/>绂佹闈欓粯鎶归櫎鏈湴 dirty 鍐呭"]
        A2["淇 sync_layer 鎵归噺鎵撹ˉ涓佺畻娉?br/>鏀逛负鏁翠綋閲嶅缓 + 鍗曟 setValue"]
        A3["澧炲己 Diff 寮曟搸瀵逛唬鐮佸潡/琛ㄦ牸鐨勫師瀛愪繚鎶?br/>锛堝崟浜轰娇鐢ㄤ篃楂橀瑙﹀彂锛?]
        A4["鍒濆鍖?Store 鏃朵粠纾佺洏鍘嗗彶璇诲彇鍩哄噯鐗堟湰鍙?br/>锛堝崟浜轰娇鐢ㄦ瘡娆￠噸鍚繀瑙﹀彂锛?]
    end

    subgraph Step2 ["绗簩闃舵: 鍋ュ．鎬т笌椴佹鎬ф彁鍗?(P1)"]
        B1["閲嶆瀯 FileVersionStore 鍚堝苟閫昏緫<br/>澧炲姞 paraIdx 鍋忕Щ鍙樻崲<br/>娑堥櫎绱㈠紩閿欎綅椋庨櫓"]
        B2["浼樺寲 scheduleAutoSave 鑴忔爣璁扮敓鍛藉懆鏈?br/>markClean 鍓嶅鍔犲唴瀹归噸鏍￠獙"]
        B3["缁熶竴鎹㈣绗﹁鑼冨寲 (CRLF -> LF)"]
        B4["浼樺寲 version_history.js LCS 绠楁硶涓?Myers<br/>娑堥櫎澶ф枃浠?OOM 鍗℃"]
        B5["Watchdog mark_expected 鏀逛负 FIFO 闃熷垪"]
        B6["瀹屽杽绂荤嚎鑽夌鑷姩鍚屾涓庢彁绀烘満鍒?]
    end

    subgraph Step3 ["绗笁闃舵: 鎬ц兘涓庢灦鏋勬暣娲?(P2 & P3)"]
        C1["淇鍏夋爣淇濇姢鍧愭爣绯诲亸宸?]
        C2["寮曞叆鏈嶅姟绔唴瀛?LRU 娣樻卑鏈哄埗"]
        C3["缁熶竴鍓嶅悗绔?Diff 绠楁硶"]
        C4["娓呯悊閬楃暀鍏煎浠ｇ爜"]
    end

    Step1 --> Step2 --> Step3
```

**浼樺厛绾у缓璁?*锛氬湪涓汉/灏忓洟闃?NAS 绗旇绠＄悊鐨勪富瑕佷娇鐢ㄥ満鏅笅锛屽ぇ閮ㄥ垎鏃堕棿涓哄崟浜哄崟绔紪杈戙€傚缓璁?*绗竴闃舵浼樺厛淇 ISSUE-05锛堜唬鐮佸潡鎾曡锛夊拰 ISSUE-09锛堢増鏈彿褰掗浂锛?*鈥斺€旇繖涓や釜闂鍦ㄥ崟浜烘棩甯镐娇鐢ㄤ腑鍗抽珮棰戣Е鍙戯紝浣撻獙褰卞搷鏈€澶с€?
