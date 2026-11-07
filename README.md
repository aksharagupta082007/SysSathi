# SysSathi

Voice assistant that finds why a Windows laptop is slow and answers in Hinglish.
Built on Gnani AI models (Prisma, Evon, Timbre).

## Quick start

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env        # fill in API keys
python -m syssathi.host.cli # CLI mode
# or Web push-to-talk UI:
uvicorn syssathi.web.app:app --host 127.0.0.1 --port 8000
```

## Privacy

Audio and process names leave the machine via Gnani speech APIs and
the Evon endpoint. This system is **not** fully local.
