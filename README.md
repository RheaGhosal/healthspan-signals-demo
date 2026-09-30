# Healthspan Signals

A non-clinical live dashboard prototype. It uses a transparent routine-consistency score and a local, editable wellness-reference knowledge base—not an external AI service or medical assessment.

## Local knowledge base

`knowledge/wellness_reference.json` contains the plain-language references and conversation prompts used by the dashboard. The server reads it on startup; no ChatGPT API key, account, or paid request is required. The references are intended for conversation and human review only, not diagnosis, prescribing, triage, or emergency decisions.

## Run locally

```bash
python3 server.py
```

Open `http://localhost:8787`.

## Live-demo API

- `GET /api/state` returns the current simulated rolling window.
- `POST /api/ingest` accepts only four numeric demo fields: `sleep_hours`, `resting_hr`, `movement_minutes`, and `steps_today`.

The process retains only a rolling in-memory window. It deliberately stores no names, locations, photos, ECG files, or other person identifiers.
