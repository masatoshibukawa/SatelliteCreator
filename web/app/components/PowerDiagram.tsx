"use client";

import { minutes } from "../lib/format";
import type { DiagramData } from "../lib/types";
import { useElementSize } from "../lib/useElementSize";

const AXIS_HEIGHT_PX = 24;
const HEADROOM_RATIO = 1.25;
const SUNLIT_FILL = "#f6d48a";
const ECLIPSE_FILL = "#d9e0e8";
const LOAD_STROKE = "#c23a3a";

interface PowerValues {
  sunlight: number;
  eclipse: number;
  generated: number;
  consumed: number;
}

function PowerChart({ sunlight, eclipse, generated, consumed }: PowerValues) {
  const { ref, width, height } = useElementSize<HTMLDivElement>();
  const plot = Math.max(height - AXIS_HEIGHT_PX, 0);
  const top = Math.max(generated, consumed) * HEADROOM_RATIO;
  const sunWidth = (width * sunlight) / (sunlight + eclipse);
  const barHeight = (plot * generated) / top;
  const loadY = plot - (plot * consumed) / top;

  return (
    <div className="diagram-stage" ref={ref}>
      {width > 0 && height > 0 && (
        <svg width={width} height={height} role="img" aria-label="1 周回の発電電力と消費電力">
          <rect x={0} y={0} width={width} height={plot} fill="#f6f8fb" />
          <rect x={0} y={plot - barHeight} width={sunWidth} height={barHeight} fill={SUNLIT_FILL} />
          <rect x={sunWidth} y={0} width={width - sunWidth} height={plot} fill={ECLIPSE_FILL} />
          <line x1={0} x2={width} y1={loadY} y2={loadY} stroke={LOAD_STROKE} strokeWidth={2} />
          <text x={8} y={plot - barHeight + 18} fill="#1f2933">
            発電 {generated.toFixed(1)} W
          </text>
          <text x={width - 8} y={Math.max(loadY - 6, 16)} textAnchor="end" fill={LOAD_STROKE}>
            消費 {consumed.toFixed(1)} W
          </text>
          <text x={sunWidth / 2} y={height - 6} textAnchor="middle" fill="#6b7684">
            日照 {minutes(sunlight)}
          </text>
          <text x={sunWidth + (width - sunWidth) / 2} y={height - 6} textAnchor="middle" fill="#6b7684">
            日陰 {minutes(eclipse)}
          </text>
        </svg>
      )}
    </div>
  );
}

export default function PowerDiagram({ diagrams }: { diagrams: DiagramData | null }) {
  const sunlight = diagrams?.min_sunlight_s ?? null;
  const eclipse = diagrams?.max_eclipse_s ?? null;
  const generated = diagrams?.usable_sunlit_power_w ?? null;
  const consumed = diagrams?.average_consumed_power_w ?? null;
  const ready = sunlight !== null && eclipse !== null && generated !== null && consumed !== null;
  const energyIn = diagrams?.orbit_generated_energy_j ?? null;
  const energyOut = diagrams?.orbit_consumed_energy_j ?? null;
  const depth = diagrams?.battery_depth_of_discharge_ratio ?? null;

  return (
    <section className="panel diagram" aria-label="電源">
      <h2 className="panel-title">電源（1 周回）</h2>
      {!ready && <p className="viewer-empty">機器構成と軌道が決まると、ここに表示します。</p>}
      {ready && (
        <>
          <PowerChart sunlight={sunlight} eclipse={eclipse} generated={generated} consumed={consumed} />
          <dl className="diagram-facts">
            {energyIn !== null && energyOut !== null && (
              <div>
                <dt>発電 / 消費</dt>
                <dd className={energyIn < energyOut ? "diagram-bad" : undefined}>
                  {(energyIn / 1000).toFixed(1)} / {(energyOut / 1000).toFixed(1)} kJ
                </dd>
              </div>
            )}
            {depth !== null && (
              <div>
                <dt>放電深度</dt>
                <dd>{(depth * 100).toFixed(1)} %</dd>
              </div>
            )}
          </dl>
        </>
      )}
    </section>
  );
}
