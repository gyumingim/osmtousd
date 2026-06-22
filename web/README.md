# 합성데이터 포털 (과업 3)

packages/*.zip 메타데이터를 카탈로그로 노출하는 데이터 포털.

## 실행
```bash
python3 -m pip install -r web/backend/requirements.txt
python3 -m uvicorn web.backend.main:app --port 8000
# 브라우저: http://localhost:8000
```

## 구성
- `backend/main.py` — FastAPI 카탈로그 API (DB 없이 ZIP 메타 직접 read)
  - GET /api/datasets?type=&scenario= — 카탈로그
  - GET /api/datasets/{id} — 상세
  - GET /api/datasets/{id}/preview?frame= — 합성 PNG 미리보기
  - GET /api/datasets/{id}/download — ZIP
  - GET /api/stats/scenarios — 시나리오별 통계
- `frontend/index.html` — 정적 SPA (Tailwind CDN, 빌드 불필요)
