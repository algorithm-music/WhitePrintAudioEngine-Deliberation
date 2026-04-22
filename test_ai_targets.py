"""See ALL keys from the first opinion's raw parsed data."""
import httpx, json

r = httpx.post('http://localhost:8082/internal/deliberate', json={
    'analysis_data': {
        'track_identity': {'title': 'Test Track', 'bpm': 128},
        'whole_track_metrics': {'integrated_lufs': -18.0, 'true_peak_dbtp': -0.5, 'crest_db': 12.0},
        'detected_problems': [],
        'time_series_circuit_envelopes': {}
    },
    'target_platform': 'streaming',
    'target_lufs': -14.0,
    'target_true_peak': -1.0
}, timeout=60)

d = r.json()
ops = d.get('opinions', [])
for op in ops:
    name = op.get('agent_name')
    print(f"\n=== {name} ===")
    # Print ALL keys
    for k in sorted(op.keys()):
        v = op[k]
        if isinstance(v, (str,)) and len(v) > 100:
            v = v[:100] + "..."
        print(f"  {k}: {v}")
