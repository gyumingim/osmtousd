"""
Vworld WFS 전체 레이어를 구미시 반경 내에서 fetch해 vworld_data/ 에 GeoJSON으로 저장.
이미 파일이 있으면 skip (재실행 시 캐시로 동작).

실행: python3 vworld_fetcher.py
읽기: from vworld_fetcher import load_layer
"""

import os
import json
import math
import requests
from osm_fetch import CENTER, RADIUS

KEY = os.environ.get("VWORLD_KEY", "CE3EACDE-25CA-345C-8639-669D2CFB5A8E")
WFS_URL = "https://api.vworld.kr/req/wfs"
OUTPUT_DIR = "vworld_data"
TILE_GRID = 4       # 4x4 타일링 (1000개 제한 우회)
MAX_FEATURES = 1000

# ── 전체 레이어 목록 169종 (typename: 한글명) ──────────────────────────────
LAYERS = {
    # 경계
    "lt_c_adsido":                    "광역시도",
    "lt_c_adsigg":                    "시군구",
    "lt_c_ademd":                     "읍면동",
    "lt_c_adri":                      "리",
    "lt_c_cademd":                    "행정동경계(센서스)",
    # 관광
    "lt_p_dgtouristinfo":             "관광안내소",
    "lt_p_tradsijang":                "전통시장현황",
    # 교통
    "lt_p_utiscctv":                  "교통CCTV",
    "lt_p_moctnode":                  "교통노드",
    "lt_l_moctlink":                  "교통링크",
    "lt_l_n3a0020000":                "도로중심선",
    # 국가지명
    "lt_p_nsnmssitenm":               "국가지명",
    # 농업·농촌
    "lt_c_agrixue101":                "농업진흥지역도",
    "lt_c_agrixue102":                "영농여건불리농지도",
    # 도시계획
    "lt_c_upisuq171":                 "개발행위허가제한지역",
    "lt_c_upisuq153":                 "도시계획(공간시설)",
    "lt_c_upisuq155":                 "도시계획(공공문화체육시설)",
    "lt_c_upisuq152":                 "도시계획(교통시설)",
    "lt_c_upisuq159":                 "도시계획(기타기반시설)",
    "lt_c_upisuq151":                 "도시계획(도로)",
    "lt_c_upisuq156":                 "도시계획(방재시설)",
    "lt_c_upisuq157":                 "도시계획(보건위생시설)",
    "lt_c_upisuq154":                 "도시계획(유통공급시설)",
    "lt_c_upisuq158":                 "도시계획(환경기초시설)",
    "lt_c_upisuq161":                 "지구단위계획",
    "lt_c_lhblpn":                    "토지이용계획도",
    # 문화재
    "lt_c_uo301":                     "국가유산지정보호구역",
    "lt_p_dgmuseumart":               "박물관미술관",
    "lt_c_uo501":                     "전통사찰보존",
    # 문화예술
    "lt_p_smalllibrary":              "작은도서관",
    # 사회복지
    "lt_p_mgprtfd":                   "기타보호시설",
    "lt_p_mgprtfb":                   "노인복지시설",
    "lt_p_mgprtfc":                   "아동복지시설",
    "lt_p_mgprtfa":                   "아동안전지킴이집",
    # 산업
    "lt_c_dgmainbiz":                 "주요상권",
    "lt_p_busiincubator":             "창업보육센터",
    # 산업단지
    "lt_c_damdan":                    "산업단지경계",
    "lt_c_damyoj":                    "단지시설용지",
    "lt_c_damyod":                    "단지용도지역",
    "lt_c_damyuch":                   "단지유치업종",
    # 수자원
    "lt_c_wkmbbsn":                   "대권역",
    "lt_c_wkmmbsn":                   "중권역",
    "lt_c_wkmsbsn":                   "표준권역",
    "lt_c_wkmstrm":                   "하천망",
    # 용도지역지구
    "lt_c_ud801":                     "개발제한구역",
    "lt_c_uq129":                     "개발진흥지구",
    "lt_c_uq121":                     "경관지구",
    "lt_c_uq123":                     "고도지구",
    "lt_c_uq112":                     "관리지역",
    "lt_c_uma100":                    "자연공원용도지구",
    "lt_c_uq141":                     "국토계획구역",
    "lt_c_uq113":                     "농림지역",
    "lt_c_uq162":                     "도시자연공원구역",
    "lt_c_uq111":                     "도시지역",
    "lt_c_uq125":                     "방재지구",
    "lt_c_uq124":                     "방화지구",
    "lt_c_uq126":                     "보호지구",
    "lt_c_uf602":                     "임업및산촌진흥권역",
    "lt_c_uq114":                     "자연환경보전지역",
    "lt_c_uq128":                     "취락지구",
    "lt_c_uq130":                     "특정용도제한지구",
    # 용도지역지구(기타)
    "lt_c_um000":                     "가축사육제한구역",
    "lt_c_uo601":                     "관광지",
    "lt_c_ud610":                     "국민임대주택",
    "lt_c_up401":                     "급경사재해예방지역",
    "lt_c_um301":                     "대기환경규제지역",
    "lt_c_uf901":                     "백두대간보호지역",
    "lt_c_uh701":                     "벤처기업육성지역",
    "lt_c_ud620":                     "보금자리주택",
    "lt_c_uf151":                     "산림보호구역",
    "lt_c_um901":                     "습지보호지역",
    "lt_c_ub901":                     "시장정비구역",
    "lt_c_um221":                     "야생동식물보호",
    "lt_c_uj401":                     "온천지구",
    "lt_c_uh501":                     "유통단지",
    "lt_c_uh402":                     "자유무역지역",
    "lt_c_ud601":                     "주거환경개선지구",
    "lt_c_uo101":                     "교육환경보호구역",
    # 일반행정
    "lt_c_bldginfo":                  "건축물정보",
    "lt_c_spbd":                      "도로명주소건물",
    "lt_l_sprd":                      "도로명주소도로",
    # 임업·산촌
    "lt_c_fsdifrsts":                 "산림입지도",
    # 자연
    "lt_l_gimsfault":                 "단층",
    "lt_c_asitsoildra":               "배수등급",
    "lt_c_gimshydro":                 "수문지질단위",
    "lt_c_gimsstiff":                 "수질다이어그램",
    "lt_c_asitdeepsoil":              "심토토성",
    "lt_c_asitsoildep":               "유효토심",
    "lt_c_asitsurston":               "자갈함량",
    "lt_l_gimsec":                    "전기전도도",
    "lt_c_gimslinea":                 "지질구조밀도",
    "lt_l_gimslinea":                 "지질구조선",
    "lt_l_gimsdepth":                 "지하수등수심선",
    "lt_l_gimspoten":                 "지하수등수위선",
    "lt_l_gimsdirec":                 "지하수유동방향",
    "lt_c_gimsscs":                   "토양도",
    # 정밀도로지도
    "lt_c_c4speedbump":               "과속방지턱",
    "lt_l_b2surfacelinemark":         "노면선표시",
    "lt_c_b3surfacemark":             "노면표시(횡단보도)",
    "lt_l_c5heightbarrier":           "높이장애물",
    "lt_c_a4subsidiarysection":       "보도구간",
    "lt_p_c1trafficlight":            "신호등",
    "lt_c_b1safetysign":              "안전표지(면)",
    "lt_p_b1safetysign":              "안전표지(점)",
    "lt_c_a5parkinglot":              "주차면",
    "lt_p_a1node":                    "주행경로노드",
    "lt_l_a2link":                    "주행경로링크",
    "lt_p_c6postpoint":               "지주",
    "lt_c_a3drivewaysection":         "차도구간",
    "lt_l_c3vehicleprotectionsafety": "차량방호안전시설",
    "lt_p_c2kilopost":                "킬로포스트",
    # 재난방재
    "lt_c_kfdrssigugrade":            "산불위험예측지도",
    "lt_c_usfsffb":                   "소방서관할구역",
    "lt_c_up201":                     "재해위험지구",
    # 체육
    "lt_c_wgisnpgug":                 "국립자연공원",
    "lt_c_wgisnpgun":                 "군립자연공원",
    "lt_c_wgisnpdo":                  "도립자연공원",
    "lt_l_frstclimb":                 "등산로",
    "lt_p_bycracks":                  "자전거보관소",
    # 토지
    "lt_c_lhzone":                    "사업지구경계도",
    "lp_pa_cbnd_bubun":               "연속지적도",
    "lt_c_landinfobasemap":           "LX맵(편집지적도)",
    # 학교
    "lt_c_dhsch":                     "고등학교학교군",
    "lt_c_eadist":                    "교육행정구역",
    "lt_c_dmsch":                     "중학교학교군",
    "lt_c_desch":                     "초등학교통학구역",
    # 항공·공항
    "lt_c_aisuac":                    "(UA)초경량비행장치공역",
    "lt_c_aisaltc":                   "경계구역",
    "lt_c_aisfldc":                   "경량항공기이착륙장",
    "lt_c_aisrflc":                   "공중급유구역",
    "lt_c_aisacmc":                   "공중전투기동훈련장",
    "lt_c_aisctrc":                   "관제권",
    "lt_c_aismoac":                   "군작전구역",
    "lt_c_aisdronezone":              "드론시범사업구역",
    "lt_c_aisadzc":                   "방공식별구역",
    "lt_c_aisprhc":                   "비행금지구역",
    "lt_c_aisatzc":                   "비행장교통구역",
    "lt_c_aisfirc":                   "비행정보구역",
    "lt_c_aisresc":                   "비행제한구역",
    "lt_l_aissearchl":                "수색비행장비행구역(선)",
    "lt_p_aissearchp":                "수색비행장비행구역(점)",
    "lt_l_aisvfrpath":                "시계비행로(선)",
    "lt_p_aisvfrpath":                "시계비행로(점)",
    "lt_c_aisdngc":                   "위험구역",
    "lt_c_aistmac":                   "접근관제구역",
    "lt_l_aisrouteu":                 "제한고도",
    "lt_l_aiscorrid_ys":              "한강회랑(선-여수)",
    "lt_l_aiscorrid_gj":              "한강회랑(선-광주)",
    "lt_p_aiscorrid_ys":              "한강회랑(점-여수)",
    "lt_p_aiscorrid_gj":              "한강회랑(점-광주)",
    "lt_l_aispath":                   "항공로",
    "lt_p_aishcstrip":                "헬기장",
    "lt_c_aiscatc":                   "훈련구역",
    # 해양·수산·어촌
    "lt_c_wgispl2con":                "(2차)관리연안해역",
    "lt_c_wgispl2abs":                "(2차)보전연안해역",
    "lt_c_wgispl2use":                "(2차)이용연안해역",
    "lt_c_wgispl2spa":                "(2차)특수연안해역",
    "lt_c_wgisreplan":                "공유수면매립기본계획",
    "lt_c_wgisrecomp":                "공유수면매립준공",
    "lt_c_wgisiegug":                 "국가산업단지",
    "lt_c_wgisienong":                "농공단지",
    "lt_c_wgisarwet":                 "습지보호구역(해양)",
    "lt_c_wgisieilban":               "일반산업단지",
    "lt_c_wgisiedosi":                "첨단산업단지",
    "lt_l_toisdepcntah":              "해안선",
    "lt_c_tfismpa":                   "해양보호구역",
    # 환경보호
    "lt_p_sgisgolf":                  "골프장현황",
    "lt_c_um710":                     "상수원보호",
    "lt_p_weissiteme":                "수질측정망공단배수지점",
    "lt_p_weissitemd":                "수질측정망농업용수지점",
    "lt_p_weissitemf":                "수질측정망도시관류지점",
    "lt_p_weissitema":                "수질측정망하천수지점",
    "lt_p_weissitemb":                "수질측정망호소수지점",
    "lt_p_sgisgwchg":                 "지하수측정망(오염우려지역)",
}


def _bbox(lat, lon, radius_m):
    dlat = radius_m / 111000
    dlon = radius_m / (111000 * math.cos(math.radians(lat)))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def _fetch_tile(typename, bbox_str):
    resp = requests.get(WFS_URL, params={
        "service": "WFS", "version": "1.1.0", "request": "GetFeature",
        "typename": typename, "key": KEY,
        "bbox": bbox_str, "srsname": "EPSG:4326",
        "output": "application/json", "maxfeatures": MAX_FEATURES,
    }, timeout=30)
    resp.raise_for_status()
    return resp.json().get("features", [])


def fetch_layer(typename, lat, lon, radius_m, tile_grid=TILE_GRID):
    """타일링으로 레이어 전체 fetch.
    Returns: (features, warnings)
      warnings: list of str — 타일 실패 or 1000개 한도 초과 메시지
    """
    minx, miny, maxx, maxy = _bbox(lat, lon, radius_m)
    dx = (maxx - minx) / tile_grid
    dy = (maxy - miny) / tile_grid

    seen, features, warnings = set(), [], []
    for row in range(tile_grid):
        for col in range(tile_grid):
            bbox_str = (f"{minx + col*dx},{miny + row*dy},"
                        f"{minx + (col+1)*dx},{miny + (row+1)*dy}")
            try:
                tile = _fetch_tile(typename, bbox_str)
            except Exception as e:
                msg = f"tile({row},{col}) 실패: {e}"
                print(f"    [warn] {msg}")
                warnings.append(msg)
                continue

            if len(tile) >= MAX_FEATURES:
                msg = f"tile({row},{col}) 1000개 한도 초과 — 데이터 누락 가능"
                print(f"    [warn] {msg}")
                warnings.append(msg)

            for f in tile:
                fid = (f.get("id") or
                       str(f.get("properties", {}).get("ufid") or
                           f.get("properties", {}).get("link_id") or
                           f.get("properties", {}).get("node_id") or
                           str(f)))
                if fid not in seen:
                    seen.add(fid)
                    features.append(f)
    return features, warnings


def _is_valid_geojson(path):
    """파일이 존재하고 features가 1개 이상인 GeoJSON이면 True."""
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("features"))
    except Exception:
        return False


def save_layer(typename, features):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"{typename}.geojson")
    geojson = {"type": "FeatureCollection", "features": features}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False)
    return path


def load_layer(typename):
    """저장된 GeoJSON 읽기. 없으면 None 반환."""
    path = os.path.join(OUTPUT_DIR, f"{typename}.geojson")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fetch_all(force=False):
    lat, lon = CENTER
    total = len(LAYERS)
    saved, skipped, empty, errors = [], [], [], []
    log = {}  # typename -> {status, count, error}

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_path = os.path.join(OUTPUT_DIR, "fetch_log.json")

    for i, (typename, desc) in enumerate(LAYERS.items(), 1):
        path = os.path.join(OUTPUT_DIR, f"{typename}.geojson")
        if not force and _is_valid_geojson(path):
            print(f"[{i:3}/{total}] SKIP  {typename} ({desc})")
            skipped.append(typename)
            log[typename] = {"status": "skip", "desc": desc}
            continue

        print(
            f"[{i:3}/{total}] FETCH {typename} ({desc})...",
            end=" ", flush=True,
        )
        try:
            features, warns = fetch_layer(typename, lat, lon, RADIUS)
        except Exception as e:
            msg = str(e)
            print(f"ERROR: {msg}")
            errors.append(typename)
            log[typename] = {"status": "error", "desc": desc, "error": msg}
            continue

        if features:
            save_layer(typename, features)
            print(f"{len(features)}개 저장" + (f" [{len(warns)} 경고]" if warns else ""))
            saved.append(typename)
            log[typename] = {
                "status": "saved", "desc": desc,
                "count": len(features), "warnings": warns,
            }
        else:
            print("데이터 없음" + (f" [{len(warns)} 경고]" if warns else ""))
            empty.append(typename)
            log[typename] = {
                "status": "empty", "desc": desc,
                "count": 0, "warnings": warns,
            }

        # 매 레이어마다 로그 갱신 (중간에 죽어도 보존)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

    print("\n=== 완료 ===")
    print(f"  저장:        {len(saved)}개")
    print(f"  skip(기존):  {len(skipped)}개")
    print(f"  데이터없음:  {len(empty)}개")
    print(f"  에러:        {len(errors)}개")
    if errors:
        print(f"  에러 레이어: {errors}")
    print(f"  로그: {log_path}")


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    fetch_all(force=force)
