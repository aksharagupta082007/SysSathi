# Gnani AI API Notes (Prisma & Timbre)

Study based directly on official documentation at `https://docs.gnani.ai` (Vachana Speech Platform).

---

## 1. Authentication
All Gnani APIs (REST, SSE, WebSocket) authenticate using the API key in the request header:
```http
X-API-Key-ID: <GNANI_API_KEY>
```
*(Loaded from `.env` via `GNANI_API_KEY`)*.

---

## 2. Prisma v3.0 (Speech-to-Text / STT)

### 2.1 REST Inference Endpoint
- **URL**: `POST https://api.vachana.ai/stt/v3`
- **Content-Type**: `multipart/form-data`
- **Headers**:
  - `X-API-Key-ID: <GNANI_API_KEY>`
- **Form Parameters**:
  - `audio_file`: Audio file to transcribe (`.wav`, `.mp3`, `.ogg`, `.flac`, `.aac`, `.m4a`). Maximum length: **30 seconds**.
  - `model`: `"prisma-v3.0"` (defaults to `prisma-v2.5` if omitted).
  - `language_code`: `"indic-auto"` (for automatic language detection across Indic languages + English) or specific language code (e.g. `"hi-IN"`, `"en-IN"`).
  - `format`: Output mode per request — `"codemix"`, `"verbatim"`, `"transcribe"` (ITN for numbers/dates), or `"transliterate"`. Default for SysSathi: `"codemix"`.
  - `keyterms`: Comma-separated or JSON list of key terms (up to 200 terms, e.g. `"Chrome, Teams, Spotify, OneDrive, Edge, Zoom"`).
- **Response Format**:
  ```json
  {
    "success": true,
    "request_id": "...",
    "transcript": "Mera laptop slow chal raha hai",
    "model": "prisma-v3.0",
    "detected_language_code": "hi-IN",
    "processing_time": 0.62,
    "end_to_end_latency": 0.71
  }
  ```

### 2.2 Realtime Streaming STT (WebSocket)
- **URL**: `wss://api.vachana.ai/stt/v3/stream`
- **Protocol**: WebSocket Secure (WSS).
- **Connection Headers** (passed on HTTP upgrade handshake):
  - `X-API-Key-ID: <GNANI_API_KEY>`
  - `x-model: prisma-v3.0`
  - `language_code: indic-auto` (or `hi-IN`)
  - `format: codemix`
- **Audio Format**:
  - Stream continuous binary frames of **raw 16-bit linear PCM** (single channel/mono, 8 kHz or 16 kHz).
- **Server Response**:
  - Incremental JSON transcription frames received in real-time as speech progresses.

---

## 3. Timbre v3.0 (Text-to-Speech / TTS)

### 3.1 REST Inference Endpoint
- **URL**: `POST https://api.vachana.ai/api/v1/tts/inference`
- **Headers**:
  - `Content-Type: application/json`
  - `X-API-Key-ID: <GNANI_API_KEY>`
- **Request Body JSON**:
  ```json
  {
    "text": "Ek second, check karta hoon",
    "model": "timbre-v3.0",
    "voice": "Shivani",
    "language": "hi-IN",
    "speed": 1.0,
    "audio_config": {
      "encoding": "linear_pcm",
      "container": "wav",
      "sample_rate": 48000,
      "num_channels": 1,
      "sample_width": 2
    }
  }
  ```
- **Response**: Full audio binary (e.g. WAV bytes).

### 3.2 Streaming SSE Endpoint
- **URL**: `POST https://api.vachana.ai/api/v1/tts/sse`
- **Headers**:
  - `Content-Type: application/json`
  - `X-API-Key-ID: <GNANI_API_KEY>`
- **Request Body**: Same schema as REST inference.
- **Response**: Server-Sent Events with audio chunks.

### 3.3 Realtime WebSocket Endpoint
- **URL**: `wss://api.vachana.ai/api/v1/tts`
- **Connection Headers**: `X-API-Key-ID: <GNANI_API_KEY>`
- **Payload**: Send synthesis request JSON over socket, receive base64 chunked audio in JSON with `is_final` flag.

### 3.4 Production Voice Catalog for Timbre v3.0
- **Feminine**: `Shivani` (default / support), `Lakshmi` (narration), `Kalpana`, `Chetana`, `Vasudha`, `Riyaa`, `Tarika`, `Kavitha`.
- **Masculine**: `Avinash`, `Shubham`, `Prakash`, `Devansh`, `Yashraj`.
- Every Timbre v3.0 voice natively supports all 10 Indian languages and Hinglish code-switching.

### 3.5 Roman-Letter Hinglish vs Devanagari
- Timbre handles Devanagari Hindi with Latin technical terms natively (`devanagari_mixed`).
- For Roman-letter Hinglish (`latin`), Timbre converts phonetically, but quality/pronunciation may vary by voice; hence the side-by-side audio test in `gnani_probe.py`.

---

## 4. Unspecified / Platform Notes
- Rate limits and concurrent connection quotas per API key tier are not published in public docs.
- WebSocket ping/pong interval recommendations are not strictly defined; standard 30s heartbeat is recommended.

