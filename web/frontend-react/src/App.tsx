import { useEffect, useState } from "react";
import { api, Dataset, ScenarioStat } from "./api";

const SCENARIOS = [
  { v: "", label: "전체" },
  { v: "scenario_01", label: "① 극한기상" },
  { v: "scenario_02", label: "② AMR 물류" },
  { v: "scenario_03", label: "③ VRU" },
  { v: "scenario_04", label: "④ V2X" },
  { v: "scenario_05", label: "⑤ 사고·충돌" },
];

export default function App() {
  const [stats, setStats] = useState<ScenarioStat[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [filter, setFilter] = useState("");
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.stats().then((d) => setStats(d.scenarios));
  }, []);
  useEffect(() => {
    api.datasets(filter || undefined).then((d) => setDatasets(d.datasets));
  }, [filter]);

  const totFrames = stats.reduce((a, s) => a + s.frames, 0);
  const totDs = stats.reduce((a, s) => a + s.datasets, 0);

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-700 px-6 py-4 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">
            구미 1산단 디지털트윈 — 합성데이터 포털
          </h1>
          <p className="text-slate-400 text-sm">
            Isaac Sim 기반 자율주행 합성 데이터셋 카탈로그
          </p>
        </div>
        <a href="/map" className="bg-slate-700 hover:bg-slate-600 px-4 py-2 rounded text-sm">
          🗺️ 교차로 지도
        </a>
      </header>

      <main className="px-6 py-6 max-w-7xl mx-auto">
        <section className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
          <Card big={totDs} label="데이터셋" />
          <Card big={totFrames} label="총 프레임" />
          {stats.map((s) => (
            <Card key={s.scenario} big={s.frames} label={s.name || s.scenario} />
          ))}
        </section>

        <div className="flex gap-3 mb-4 items-center">
          <label className="text-sm text-slate-400">시나리오</label>
          <select
            className="bg-slate-800 border border-slate-600 rounded px-3 py-1 text-sm"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            {SCENARIOS.map((s) => (
              <option key={s.v} value={s.v}>
                {s.label}
              </option>
            ))}
          </select>
          <span className="text-sm text-slate-400">{datasets.length}개</span>
        </div>

        <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {datasets.map((ds) => (
            <div
              key={ds.id}
              className="bg-slate-800 rounded-lg overflow-hidden cursor-pointer hover:ring-2 ring-emerald-500"
              onClick={() => api.dataset(ds.id).then(setDetail)}
            >
              <img
                src={api.previewUrl(ds.id)}
                className="w-full h-40 object-cover bg-slate-900"
                loading="lazy"
              />
              <div className="p-3">
                <div className="font-semibold">{ds.scenario_name || ds.scenario}</div>
                <div className="text-xs text-slate-400">
                  {ds.variant} · {ds.frame_count}프레임 ·{" "}
                  {(ds.size_bytes / 1e6).toFixed(1)}MB
                </div>
                <div className="mt-1 flex gap-1 flex-wrap">
                  {Object.values(ds.environment || {}).map((v, i) => (
                    <span key={i} className="text-[10px] bg-slate-700 rounded px-1.5 py-0.5">
                      {v}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </section>
      </main>

      {detail && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50"
          onClick={() => setDetail(null)}
        >
          <div
            className="bg-slate-800 rounded-lg max-w-3xl w-full max-h-[90vh] overflow-auto p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between mb-3">
              <h2 className="text-xl font-bold">
                {String(detail.scenario_name)} — {String(detail.variant)}
              </h2>
              <button onClick={() => setDetail(null)} className="text-2xl">
                &times;
              </button>
            </div>
            <img
              src={api.previewUrl(String(detail.id))}
              className="w-full rounded mb-3 bg-slate-900"
            />
            <pre className="text-xs bg-slate-900 rounded p-3 overflow-auto">
              {JSON.stringify(detail, null, 2)}
            </pre>
            <a
              href={api.downloadUrl(String(detail.id))}
              className="inline-block mt-3 bg-emerald-600 hover:bg-emerald-500 px-4 py-2 rounded text-sm font-semibold"
            >
              ZIP 다운로드
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

function Card({ big, label }: { big: number; label: string }) {
  return (
    <div className="bg-slate-800 rounded p-3">
      <div className="text-2xl font-bold">{big}</div>
      <div className="text-xs text-slate-400">{label}</div>
    </div>
  );
}
