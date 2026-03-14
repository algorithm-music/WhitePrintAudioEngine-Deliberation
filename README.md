# WhitePrintAudioEngine — Deliberation

TRIVIUM 3-Agent Consensus Engine.

`GRAMMATICA · LOGICA · RHETORICA → weighted median merge`

## API (Internal)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/internal/deliberate` | analysis JSON → adopted_params |
| GET | `/health` | Liveness probe |

## Deploy

```bash
gcloud run deploy aimastering-deliberation \
  --source . --region asia-northeast1 \
  --memory 512Mi --cpu 1 --concurrency 10 --ingress internal
```

© YOMIBITO SHIRAZU — WhitePrintAudioEngine
