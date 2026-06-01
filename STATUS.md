# STATUS

## 전체 목표
OpenStreetMap 데이터를 USD (Universal Scene Description) 파일로 변환

## 세부 목표
- Phase 1: 건물 + 도로 기본 메쉬 USD 출력 ✅
- Phase 2: 재질/색상 (도로=회색, 건물=타입별)
- Phase 3: 지형 terrain (SRTM/Copernicus DEM 연동)

## 사용 기술
- osmnx: OSM 데이터 다운로드 (GeoDataFrame)
- shapely: 2D 폴리곤 처리
- mapbox_earcut: 폴리곤 삼각분할 (홀 지원)
- pyproj: WGS84 → UTM 좌표 변환
- pxr (usd-core 23.11): USD 파일 출력

## 했던 일 (완료)
- [x] OSM 데이터 조사 (건물 593개, 도로 2536개, 부산대역 1km)
- [x] 데이터 메타데이터 분석 (height/levels 커버리지, highway 타입 등)
- [x] osm_fetch.py: OSM 다운로드 + UTM 변환 + 로컬 좌표계 원점 설정
- [x] geo_to_mesh.py: polygon extrusion, road buffer, earcut 삼각분할
- [x] usd_writer.py: USD Stage 생성 (Z-up, metersPerUnit=1)
- [x] main.py: 전체 파이프라인
- [x] 출력 검증: busan_univ.usda (597 건물 메쉬 + 2536 도로 메쉬, 28213 lines)

## 하고 있는 일
없음

## 할 일
- [ ] Phase 2: UsdShade로 재질/색상 추가
- [ ] Phase 3: SRTM 고도 데이터 연동

## 문제점 및 해결방안
- height 태그 커버리지 4%로 낮음 → building 타입별 기본값 매핑으로 해결
- highway 태그가 list인 경우 있음 (e.g. [footway, steps]) → 첫 번째 값 사용
- MultiPolygon 존재 → geoms로 분리 후 각각 처리
