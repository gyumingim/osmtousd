from isaacsim import SimulationApp

app = SimulationApp({"headless": False})

import omni.usd
import omni.kit.commands

stage_path = "/home/karma/OSMtoUSD/kmit/gumi.usda"
omni.usd.get_context().open_stage(stage_path)

while app.is_running():
    app.update()

app.close()
