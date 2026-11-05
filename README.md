# SysSathi

Voice assistant that finds why a Windows laptop is slow and answers in Hinglish.
Built on Gnani AI models (Prisma, Evon, Timbre).

## Quick start

```bash
pip install -e ".[dev]"
cp .env.example .env        # fill in API keys
python -m syssathi.host.cli
```

## Privacy

Audio and process names leave the machine via Gnani speech APIs and
the Evon endpoint. This system is **not** fully local.

