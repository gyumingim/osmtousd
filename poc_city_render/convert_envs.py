"""환경 에셋 GLB/OBJ → USD 변환 (omni.kit.asset_converter, 텍스처 보존)."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 640, "height": 480})
import os, asyncio
import omni.usd
import omni.kit.asset_converter as ac

A = "/home/karma/OSMtoUSD/assets"
JOBS = [
    (f"{A}/env_airport/uploads_files_6830356_modern+airport+terminal+3d+model.glb",
     f"{A}/env_airport/airport.usd"),
    (f"{A}/env_forest/uploads_files_3676240_tree+asset(1).obj",
     f"{A}/env_forest/tree.usd"),
]

async def _convert(inp, outp):
    ctx = ac.AssetConverterContext()
    task = ac.get_instance().create_converter_task(inp, outp, lambda a, b: None, ctx)
    ok = await task.wait_until_finished()
    return ok, task.get_status(), task.get_error_message()

for inp, outp in JOBS:
    print(f"변환: {os.path.basename(inp)} -> {os.path.basename(outp)}", flush=True)
    if not os.path.exists(inp):
        print(f"  [SKIP] 입력없음 {inp}", flush=True); continue
    fut = asyncio.ensure_future(_convert(inp, outp))
    while not fut.done():
        app.update()
    ok, status, err = fut.result()
    sz = os.path.getsize(outp)//1024 if os.path.exists(outp) else 0
    print(f"  ok={ok} status={status} err={err} usd={sz}KB", flush=True)

print("CONVERT_DONE", flush=True)
app.close()
