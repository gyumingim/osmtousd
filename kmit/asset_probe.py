"""에셋 서버에서 사용 가능한 차량/사람 에셋 목록 조회."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True})

import json
import omni.client
from isaacsim.storage.native import get_assets_root_path

root = get_assets_root_path()
out = {"root": root, "dirs": {}}

DIRS = [
    "/Isaac/Robots",
    "/Isaac/Props",
    "/Isaac/People/Characters",
    "/Isaac/Samples",
    "/Isaac/Environments",
]
for d in DIRS:
    try:
        res, entries = omni.client.list(root + d)
        out["dirs"][d] = sorted(e.relative_path for e in entries)
    except Exception as e:
        out["dirs"][d] = f"ERR: {e}"

with open("/home/karma/OSMtoUSD/kmit/output/asset_list.json", "w",
          encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print("[PROBE] root:", root)
print("[PROBE] DONE")
app.close()
