"""omni.anim.people 걷기 보행자 헬퍼 (sensor_drive에서 사용).

검증된 흐름: biped(애니그래프 릭) 로드 → 캐릭터 로드 → anim graph 바인딩 →
CharacterBehavior 스크립트 → command 파일(GoTo) → 타임라인 play 시 걷기.
전부 방어적: 실패하면 enabled=False 반환 → 호출측이 기존 정적 보행자로 fallback.
"""
import os

_CMD_FILE = "/tmp/oap_command.txt"
_commands = []
_ready = False


def enable_extensions():
    from isaacsim.core.utils.extensions import enable_extension
    for ext in ["omni.anim.graph.core", "omni.anim.graph.bundle",
                "omni.anim.navigation.core", "omni.kit.scripting",
                "omni.anim.people", "isaacsim.replicator.agent.core"]:
        try:
            enable_extension(ext)
        except Exception:
            pass


def setup_biped(app):
    """biped 릭 + 애니그래프 셋업. 성공 시 True."""
    global _ready, _commands
    try:
        import carb
        from isaacsim.replicator.agent.core.stage_util import CharacterUtil
        s = carb.settings.get_settings()
        s.set("/exts/omni.anim.people/navigation_settings/navmesh_enabled", False)
        s.set("/exts/omni.anim.people/command_settings/random_command_enabled",
              False)
        CharacterUtil.load_default_biped_to_stage()
        for _ in range(5):
            app.update()
        _commands = []
        _ready = True
        return True
    except Exception as e:
        print(f"[people_anim] biped 셋업 실패: {e}", flush=True)
        _ready = False
        return False


def spawn_walking_ped(usd, x, y, z, yaw_deg, goal_xy, name):
    """걷는 보행자 1명 배치 + GoTo 명령 기록. 반환: prim 또는 None."""
    if not _ready:
        return None
    try:
        import omni.kit.app
        from isaacsim.replicator.agent.core.stage_util import CharacterUtil
        cprim = CharacterUtil.load_character_usd_to_stage(
            usd, [float(x), float(y), float(z)], float(yaw_deg), name)
        cname = cprim.GetPath().name
        skel = CharacterUtil.get_character_skelroot_by_root(cprim)
        biped = CharacterUtil.get_default_biped_character()
        ag = CharacterUtil.get_anim_graph_from_character(biped)
        CharacterUtil.setup_animation_graph_to_character([skel], ag)
        ext_path = (omni.kit.app.get_app().get_extension_manager()
                    .get_extension_path_by_module("omni.anim.people"))
        script = ext_path + "/omni/anim/people/scripts/character_behavior.py"
        CharacterUtil.setup_python_scripts_to_character([skel], script)
        _commands.append(
            f"{cname} GoTo {goal_xy[0]:.2f} {goal_xy[1]:.2f} 0 _")
        return cprim
    except Exception as e:
        print(f"[people_anim] 보행자 spawn 실패: {e}", flush=True)
        return None


def finalize_commands():
    """기록된 GoTo 명령을 command 파일로 저장하고 설정."""
    if not _ready or not _commands:
        return
    try:
        import carb
        with open(_CMD_FILE, "w") as f:
            f.write("\n".join(_commands) + "\n")
        carb.settings.get_settings().set(
            "/exts/omni.anim.people/command_settings/command_file_path",
            _CMD_FILE)
    except Exception as e:
        print(f"[people_anim] command 파일 실패: {e}", flush=True)


def character_pos(prim):
    """캐릭터 현재 월드 위치 (x,y) — ego반응/궤적 동기용."""
    try:
        from isaacsim.replicator.agent.core.stage_util import CharacterUtil
        p = CharacterUtil.get_character_pos(prim)
        return float(p[0]), float(p[1])
    except Exception:
        return None
