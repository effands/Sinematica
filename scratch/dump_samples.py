import json
from pathlib import Path

samples_file = Path("data/flow_ui_samples.json")
if samples_file.exists():
    data = json.loads(samples_file.read_text(encoding="utf-8"))
    for i, item in enumerate(data):
        print(f"=== SAMPLE {i} at {item.get('at')} ===")
        req = item.get("request_item", {})
        print(json.dumps(req, indent=2))
