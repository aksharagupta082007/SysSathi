# SysSathi Safety & Policy Guide 🛡️

This document details the safety guarantees, access controls, process protection policies, and source curation principles governing SysSathi.

---

## 1. Action Authorization & Proposal Lifecycle

SysSathi strictly separates **read-only information gathering** from **system state modification**.

### 1.1 Read-Only Tools (Unrestricted)
The following tools do not alter system state and can be executed without user confirmation:
- `diagnose_slowness`
- `get_top_processes`
- `list_startup_apps`
- `get_battery_report`
- `search_sources`
- `get_tool_recommendations`
- `explain_term`

### 1.2 State-Changing Tools (Approval Gated)
Any action that can alter the system state (e.g. terminating a process group) requires a strict two-phase authorization flow:

1. **Proposal Generation (`propose_close`)**:
   - The agent or user identifies a heavy process group to terminate.
   - The tool generates a proposal containing:
     - `action_id`: Cryptographically secure random identifier.
     - `expires_at`: Strict 60-second expiration timestamp.
     - `target_pids`: Snapshot of active process IDs and creation times.
   - The proposal is displayed with a live countdown timer in the user interface.

2. **Explicit User Approval**:
   - **UI Click Only**: Authorization requires an explicit user button click on the Approve button in the Web PWA.
   - **Voice CANNOT Approve**: Voice commands cannot authorize proposals under any circumstances. Voice can only issue cancellations (e.g. "cancel" or "rehne do").
   - **Session-Bound Nonce**: The approval request must include a session nonce (`X-SysSathi-Nonce`) matching the server-issued session cookie.
   - **Single-Use**: Once executed or expired, an `action_id` is immediately purged and cannot be replayed.
   - **Execute-Time Re-Verification**: At the moment of termination, target PIDs are re-checked to ensure they still belong to the intended process and have not been recycled by Windows for system tasks.

---

## 2. Process Protection Policy

SysSathi will refuse any request to terminate critical operating system processes or components essential to machine operation.

### 2.1 Protected Process Blocklist
The following process names cannot be targeted for closure:
- **Windows Core**: `system`, `idle`, `registry`, `smss`, `csrss`, `wininit`, `winlogon`, `services`, `lsass`, `svchost`, `fontdrvhost`
- **User Shell & Desktop**: `explorer`, `dwm`, `sihost`, `taskhostw`, `shellexperiencehost`, `searchhost`, `startmenuexperiencehost`
- **Security Subsystem**: `securityhealthservice`, `msmpeng`, `nissrv`
- **Application Runtime**: The current Python interpreter process executing SysSathi (`python`, `pythonw`).

### 2.2 Closable Targets Rule (S5, S6)
A process group may only be proposed for closure if:
1. It appeared in the most recent diagnostic snapshot (`diagnose_slowness`), OR
2. It belongs to the explicitly curated user application allowlist (`CURATED_SAFE_CLOSABLE`: e.g. browsers, chat apps, media players).

Any attempt to terminate unknown or system processes is rejected with `RefusalCode.PROTECTED` or `RefusalCode.NOT_IN_DIAGNOSIS`.

---

## 3. Curated Sources Policy (Decision 3: Educate, Don't Block)

SysSathi indexes curated community knowledge directories, including FreeMediaHeckYeah (FMHY), Wikipedia, Microsoft Learn, and the Electronic Frontier Foundation (EFF SSD).

### 3.1 Transparent Education
- **No Censorship**: No category or entry from curated sources is arbitrarily filtered out or hidden.
- **Context, Not Blocks**: Rather than blocking search results, SysSathi equips users with technical context, risk indicators, and safety education so they can make informed decisions.

### 3.2 Context & Risk Labeling
Every recommendation is tagged:
- **Safe Utilities & Creative Tools**:
  - Labeled `RiskLevel.SAFE`.
  - Accompanied by standard download hygiene tips: download only from official project domains, beware deceptive banner advertisements, and scan installers with Windows Defender or VirusTotal.
- **P2P, Streaming & Downloader Tools**:
  - Labeled `RiskLevel.CAUTION`.
  - Accompanied by neutral legal notes explaining that copyright legality depends on local jurisdiction.
  - Accompanied by technical explanations: torrent swarms expose public IP addresses to peers, requiring trusted VPN interfaces and hash verification.

---

## 4. Input Sanitization & Anti-Injection (§2 S9)

To prevent terminal injection, prompt spoofing, or display corruption:
- All process names, window titles, and registry entries are sanitized through `src/syssathi/mcp_server/sanitize.py`.
- Strips C0 and C1 control characters (`\x00`–`\x1f`, `\x7f`–`\x9f`).
- Strips Unicode category `Cf` formatting characters (such as right-to-left bidi override characters `\u202E`, zero-width spaces, and invisible joiners).
- Normalizes path separators and file extensions.

