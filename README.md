# WhitePrintAudioEngine — Deliberation

TRIVIUM 3-Agent Consensus Engine — 三賢者合議。

`GRAMMATICA · LOGICA · RHETORICA → weighted median merge`

## 役割

Auditionの分析を受け取り、**全DSPパラメータを3つのAIが独立に判断**。
加重中央値マージで最終パラメータを確定する。

## AIが決定する全パラメータ（42項目）

| カテゴリ | パラメータ |
|---|---|
| **入力** | input_gain_db |
| **EQ ゲイン** | eq_low_shelf_gain_db, eq_low_mid_gain_db, eq_high_mid_gain_db, eq_high_shelf_gain_db |
| **EQ 周波数** | eq_low_shelf_freq, eq_low_mid_freq, eq_high_mid_freq, eq_high_shelf_freq |
| **EQ Q値** | eq_low_mid_q, eq_high_mid_q |
| **M/S** | ms_side_high_gain_db, ms_mid_low_gain_db |
| **コンプレッサー** | comp_threshold_db, comp_ratio, comp_attack_sec, comp_release_sec, comp_makeup_db |
| **リミッター** | limiter_ceil_db, limiter_release_ms |
| **サチュレーション** | transformer_saturation/mix, triode_drive/bias/mix, tape_saturation/mix/speed |
| **ダイナミックEQ** | dyn_eq_enabled |
| **ステレオ** | stereo_low_mono, stereo_high_wide, stereo_width |
| **パラレル** | parallel_wet, parallel_drive |

**ハードコードされた音質判断は一切存在しない。** デフォルト値は全てバイパス（0.0 / 1:1）。

## API (Internal)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/internal/deliberate` | analysis JSON → adopted_params |
| GET | `/health` | Liveness probe |

## Deploy

```bash
gcloud run deploy whiteprintaudioengine-deliberation \
  --source . --region asia-northeast1 \
  --memory 512Mi --cpu 1 --concurrency 10 --ingress internal
```

© YOMIBITO SHIRAZU — WhitePrintAudioEngine
