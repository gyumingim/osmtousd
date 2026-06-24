import axios from "axios";

// 백엔드 카탈로그 API (FastAPI). vite proxy로 /api → :8000
export interface Dataset {
  id: string;
  scenario: string;
  scenario_name?: string;
  variant?: string;
  environment?: Record<string, string>;
  frame_count?: number;
  size_bytes: number;
  classes?: Record<string, number>;
}

export interface ScenarioStat {
  scenario: string;
  name?: string;
  datasets: number;
  frames: number;
  bytes: number;
  classes: Record<string, number>;
}

export const api = {
  datasets: (scenario?: string) =>
    axios
      .get<{ count: number; datasets: Dataset[] }>("/api/datasets", {
        params: scenario ? { scenario } : {},
      })
      .then((r) => r.data),
  dataset: (id: string) =>
    axios.get<Record<string, unknown>>(`/api/datasets/${id}`).then((r) => r.data),
  stats: () =>
    axios
      .get<{ scenarios: ScenarioStat[] }>("/api/stats/scenarios")
      .then((r) => r.data),
  previewUrl: (id: string) => `/api/datasets/${id}/preview`,
  downloadUrl: (id: string) => `/api/datasets/${id}/download`,
};
