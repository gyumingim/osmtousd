"""ZIP 패키지 유효성 검사 (TODO 검증도구 validate_zip.py)

packages/*.zip 각각에 대해:
  - 아카이브 무결성 (CRC) — testzip
  - 필수 구조: data/(png≥1), labels/(json≥1), meta/metadata.json, README.md
  - metadata.json 파싱 + 필수 키, frame_count == 실제 data png 수
  - 캘리브/궤적 동봉 여부(권고)

Usage:
    python3 pipeline/validate_zip.py [packages_dir]
"""
import os
import sys
import glob
import json
import zipfile

PKG = sys.argv[1] if len(sys.argv) > 1 else "/home/karma/OSMtoUSD/packages"
REQ_META = {"scenario", "scenario_name", "frame_count", "source"}


def check(zp):
    issues, warns = [], []
    try:
        z = zipfile.ZipFile(zp)
    except Exception as e:
        return [f"열기 실패: {e}"], []
    with z:
        bad = z.testzip()
        if bad:
            issues.append(f"CRC 손상: {bad}")
        names = z.namelist()
        pngs = [n for n in names if n.startswith("data/") and n.endswith(".png")]
        jsons = [n for n in names
                 if n.startswith("labels/") and n.endswith(".json")]
        if not pngs:
            issues.append("data/ PNG 없음")
        if not jsons:
            issues.append("labels/ JSON 없음")
        if "meta/metadata.json" not in names:
            issues.append("meta/metadata.json 없음")
        else:
            try:
                m = json.loads(z.read("meta/metadata.json"))
                miss = REQ_META - set(m)
                if miss:
                    issues.append(f"metadata 필수키 누락 {miss}")
                fc = m.get("frame_count")
                if fc is not None and fc != len(pngs):
                    issues.append(f"frame_count {fc} != data png {len(pngs)}")
            except Exception as e:
                issues.append(f"metadata 파싱 실패 {e}")
        if "README.md" not in names:
            issues.append("README.md 없음")
        if "meta/calibration.json" not in names:
            warns.append("calibration 미동봉")
        if "labels/trajectories.json" not in names:
            warns.append("trajectories 미동봉")
    return issues, warns


def main():
    zips = sorted(glob.glob(os.path.join(PKG, "*.zip")))
    print(f"=== ZIP 검증: {len(zips)}개 ===\n")
    total = 0
    for zp in zips:
        issues, warns = check(zp)
        total += len(issues)
        name = os.path.basename(zp)
        st = "✅" if not issues else f"❌ {len(issues)}건"
        wtag = f"  ⚠️{','.join(warns)}" if warns else ""
        print(f"{st} {name}{wtag}")
        for i in issues:
            print(f"     ❌ {i}")
    print(f"\n=== 종합: {len(zips)}개, 결함 {total}건 ===")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
