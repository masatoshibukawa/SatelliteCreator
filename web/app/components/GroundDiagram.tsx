"use client";

import { kilometres } from "../lib/format";
import type { DiagramData } from "../lib/types";
import { useElementSize } from "../lib/useElementSize";

const STATION_X_RATIO = 0.16;
const SATELLITE_X_RATIO = 0.82;
const SATELLITE_Y_RATIO = 0.2;
const GROUND_Y_RATIO = 0.74;
const LINK_COLOR = "#2f6fed";

function LinkChart({ range, elevation }: { range: number; elevation: number }) {
  const { ref, width, height } = useElementSize<HTMLDivElement>();
  const stationX = width * STATION_X_RATIO;
  const groundY = height * GROUND_Y_RATIO;
  const satelliteX = width * SATELLITE_X_RATIO;
  const satelliteY = height * SATELLITE_Y_RATIO;
  const middleX = (stationX + satelliteX) / 2;
  const middleY = (groundY + satelliteY) / 2;

  return (
    <div className="diagram-stage" ref={ref}>
      {width > 0 && height > 0 && (
        <svg width={width} height={height} role="img" aria-label="衛星と地上局の位置関係">
          <path
            d={`M 0 ${groundY} Q ${width / 2} ${groundY - height * 0.1} ${width} ${groundY + height * 0.08} L ${width} ${height} L 0 ${height} Z`}
            fill="#cfe3d4"
          />
          <line
            x1={stationX}
            y1={groundY - 8}
            x2={satelliteX}
            y2={satelliteY}
            stroke={LINK_COLOR}
            strokeWidth={2}
            strokeDasharray="7 5"
          />
          <path
            d={`M ${stationX - 12} ${groundY - 2} L ${stationX} ${groundY - 18} L ${stationX + 12} ${groundY - 2} Z`}
            fill="#33415a"
          />
          <rect x={satelliteX - 10} y={satelliteY - 10} width={20} height={20} fill="#8fa6c4" stroke="#33415a" />
          <rect x={satelliteX - 34} y={satelliteY - 5} width={22} height={10} fill="#1d3a6e" />
          <rect x={satelliteX + 12} y={satelliteY - 5} width={22} height={10} fill="#1d3a6e" />
          <text x={satelliteX} y={satelliteY - 18} textAnchor="middle" fill="#1f2933">
            衛星
          </text>
          <text x={stationX} y={groundY + 22} textAnchor="middle" fill="#1f2933">
            地上局
          </text>
          <text x={middleX + 8} y={middleY + 22} fill={LINK_COLOR}>
            最大 {kilometres(range)}
          </text>
          <text x={stationX + 34} y={groundY + 22} fill="#6b7684">
            最低仰角 {elevation} 度
          </text>
        </svg>
      )}
    </div>
  );
}

export default function GroundDiagram({ diagrams }: { diagrams: DiagramData | null }) {
  const range = diagrams?.slant_range_m ?? null;
  const elevation = diagrams?.min_elevation_deg ?? null;
  const margin = diagrams?.link_margin_db ?? null;
  const frequency = diagrams?.downlink_frequency_hz ?? null;
  const rate = diagrams?.downlink_rate_bps ?? null;
  const ready = range !== null && elevation !== null && margin !== null;

  return (
    <section className="panel diagram" aria-label="通信局">
      <h2 className="panel-title">通信局（模式図）</h2>
      {!ready && <p className="viewer-empty">機器構成と軌道が決まると、ここに表示します。</p>}
      {ready && (
        <>
          <LinkChart range={range} elevation={elevation} />
          <dl className="diagram-facts">
            {frequency !== null && (
              <div>
                <dt>周波数</dt>
                <dd>{(frequency / 1e9).toFixed(3)} GHz</dd>
              </div>
            )}
            {rate !== null && (
              <div>
                <dt>伝送速度</dt>
                <dd>{(rate / 1000).toFixed(1)} kbps</dd>
              </div>
            )}
            <div>
              <dt>回線マージン</dt>
              <dd className={margin < 0 ? "diagram-bad" : undefined}>{margin.toFixed(1)} dB</dd>
            </div>
          </dl>
        </>
      )}
    </section>
  );
}
