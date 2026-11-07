# SysSathi End-to-End Demo Script

Follow these 5 steps to run the live demo with Chrome.

---

### Prerequisites
1. Ensure your `.env` contains:
   - `EVON_BASE_URL` and `HF_TOKEN` (when using live Evon endpoint).
   - `GNANI_API_KEY` (for live Prisma and Timbre voice).
   *(Or test offline with `SYSSATHI_LLM_BACKEND=mock`)*.
2. Launch multiple Chrome tabs on your machine so Chrome consumes notable RAM.

---

### Step 1: Start the Web Server
In your terminal, activate the virtual environment and start SysSathi:
```bash
source .venv/bin/activate
uvicorn syssathi.web.app:app --host 127.0.0.1 --port 8000
```
Open your browser to: `http://127.0.0.1:8000`.

---

### Step 2: Push-to-Talk Diagnosis Query
- **User Action**: Click and hold the **"Hold to Talk"** button, and say clearly into the microphone:
  > *"Mera laptop slow chal raha hai"*
- **System Action**: Release the button when finished speaking.

---

### Step 3: Fast-Path Immediate Filler & Diagnosis
- **Immediate Voice Filler**: SysSathi immediately plays:
  > *"Ek second, check karta hoon"*
- **Sample & Reason**: The background MCP server samples laptop CPU, RAM, disk, and processes for 3 seconds.
- **Spoken Hinglish Diagnosis**:
  SysSathi streams the diagnostic reply and asks for permission to close the heavy app:
  > *"RAM 91% use ho rahi hai. Chrome ke 14 processes 3.1 GB le rahe hain. Band kar dun?"*
- **UI State**: The Proposal box appears on screen detailing the pending action, and the **Approve Action** button turns active with a 60-second validity window.

---

### Step 4: Click Approve
- **User Action**: Click the **"Approve Action"** button.
- **Safety Gate**: The browser sends the session nonce via `X-SysSathi-Nonce` to `/api/approve`. The host server verifies the local origin and executes the action using the internal `SYSSATHI_APPROVAL_TOKEN`.
- **Termination**: Chrome processes are gracefully terminated (with forced kill for any remaining survivors).

---

### Step 5: Re-measurement & Voice Confirmation
- **Fresh Measurement**: The host immediately runs another 3-second diagnosis to measure before vs. after RAM.
- **Voice Confirmation**: SysSathi announces the drop in RAM usage:
  > *"RAM 91% se 64% ho gaya."*
- **Finish**: The proposal box hides, the Approve button resets, and the system returns to **Ready**.

