# 합성데이터 포털 — React 프론트엔드 (제안서 2차연도 스택)

제안서 명시 스택: **React 19 + TypeScript + Vite 7 + Tailwind + Leaflet + Axios**.
백엔드(`web/backend`)의 카탈로그 API를 그대로 소비.

## 빌드/실행 (node 18+ 필요)
```bash
cd web/frontend-react
npm install
npm run dev        # http://localhost:5173 (/api → :8000 프록시)
# 또는 배포 빌드
npm run build      # dist/ 생성
```

## 구성
- `src/api.ts` — 카탈로그 API 클라이언트(axios)
- `src/App.tsx` — 통계·시나리오 필터·데이터셋 그리드·상세 모달·ZIP 다운로드
- 교차로 지도(`/map`)는 백엔드가 서빙하는 Leaflet 페이지 재사용

> node 미설치 환경에서는 빌드 없이 동작하는 정적 SPA(`web/frontend/index.html`)를
> 백엔드가 `/` 로 서빙한다. 두 프론트는 동일 API 계약을 사용한다.
