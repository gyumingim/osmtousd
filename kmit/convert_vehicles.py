"""Kenney Car Kit(CC0) GLB → USD 일괄 변환.
omni.kit.asset_converter 사용. assets/vehicles/glb/*.glb → assets/vehicles/usd/*.usd

Usage:
    ./_build/linux-x86_64/release/python.sh convert_vehicles.py
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True})

import os
import glob
import asyncio

SRC = "/home/karma/OSMtoUSD/kmit/assets/vehicles/glb"
DST = "/home/karma/OSMtoUSD/kmit/assets/vehicles/usd"
os.makedirs(DST, exist_ok=True)


async def convert(in_file, out_file):
    import omni.kit.asset_converter
    ctx = omni.kit.asset_converter.AssetConverterContext()
    ctx.ignore_materials = False
    ctx.use_meter_as_world_unit = True
    inst = omni.kit.asset_converter.get_instance()
    task = inst.create_converter_task(in_file, out_file, lambda a, b: None, ctx)
    ok = False
    while True:
        ok = await task.wait_until_finished()
        if ok:
            break
        await asyncio.sleep(0.1)
    return ok


def main():
    glbs = sorted(glob.glob(os.path.join(SRC, "*.glb")))
    print(f"변환 대상 {len(glbs)}개", flush=True)
    loop = asyncio.get_event_loop()
    done = 0
    for g in glbs:
        name = os.path.splitext(os.path.basename(g))[0]
        out = os.path.join(DST, name + ".usd")
        try:
            ok = loop.run_until_complete(convert(g, out))
            print(f"  {'✅' if ok else '❌'} {name}.usd", flush=True)
            done += int(bool(ok))
        except Exception as e:
            print(f"  ❌ {name}: {e}", flush=True)
    print(f"완료 {done}/{len(glbs)}", flush=True)


main()
app.close()
