# reddit-research (claude/)

Prompt-driven Reddit research tool. See `../v1.spec` for the full design.

## Install

```powershell
cd claude
python -m pip install -e .[dev]
```

Requires Ollama running locally with `qwen3-coder:30b` (or pass `--model`).

## Quick start

```powershell
reddit-research ask "how do people secure home networks"
reddit-research ask "NVDA outlook after earnings" --ticker NVDA --emit-sentiment "$env:USERPROFILE\.tradingagents\reddit_sentiment\"
reddit-research recall --latest
```

## Test

```powershell
pytest tests/test_smoke_offline.py -q   # deterministic, no network
pytest tests/test_smoke_online.py -q    # hits r/test + Ollama
```
