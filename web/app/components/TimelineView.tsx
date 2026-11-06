"use client";

import type { Timeline } from "../lib/types";
import { useElementSize } from "../lib/useElementSize";

const AXIS_HEIGHT_PX = 24;
const BAND_GAP_PX = 26;
const BAND_COUNT = 3;
const POWER_HEADROOM_RATIO = 1.1;
const LEFT_PX = 8;
const HOURS = [0, 6, 12, 18, 24];
const SECONDS_PER_HOUR = 3600;
const DAY_S = 86400;
const BATTERY_COLOR = "#1f7f58";
const GENERATED_FILL = "#f6d48a";
const CONSUMED_COLOR = "#c23a3a";
const CONTACT_FILL = "rgba(47, 111, 237, 0.16)";
const DATA_COLOR = "#2f6fed";

interface Band {
  top: number;
  height: number;
}

function polyline(times: number[], values: number[], low: number, high: number, width: number, band: Band): string {
  const span = high - low || 1;
  return times
    .map((time, index) => {
      const x = LEFT_PX + (time / DAY_S) * width;
      const y = band.top + band.height - ((values[index] - low) / span) * band.height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function TimelineChart({ timeline }: { timeline: Timeline }) {
  const { ref, width, height } = useElementSize<HTMLDivElement>();
  const plotWidth = Math.max(width - LEFT_PX * 2, 0);
  const bandHeight = Math.max((height - AXIS_HEIGHT_PX - BAND_GAP_PX * BAND_COUNT) / BAND_COUNT, 0);
  const bands: Band[] = [0, 1, 2].map((index) => ({
    top: BAND_GAP_PX + index * (bandHeight + BAND_GAP_PX),
    height: bandHeight,
  }));
  const [batteryBand, powerBand, dataBand] = bands;
  const batteryPercent = timeline.battery_ratio.map((value) => value * 100);
  const batteryLow = Math.floor(Math.min(...batteryPercent) - 1);
  const powerPeak = Math.max(...timeline.generated_power_w, ...timeline.consumed_power_w);
  const powerHigh = powerPeak * POWER_HEADROOM_RATIO;
  const dataMegabytes = timeline.downlinked_bit.map((value) => value / 8e6);
  const dataHigh = Math.max(...dataMegabytes, 1e-6);
  const generatedLine = polyline(timeline.time_s, timeline.generated_power_w, 0, powerHigh, plotWidth, powerBand);
  const baseY = powerBand.top + powerBand.height;

  return (
    <div className="diagram-stage" ref={ref}>
      {width > 0 && height > 0 && (
        <svg width={width} height={height} role="img" aria-label="1 日の電力と通信の変化">
          {timeline.contacts.map((item) => (
            <rect
              key={item.start_s}
              x={LEFT_PX + (item.start_s / DAY_S) * plotWidth}
              y={0}
              width={Math.max(((item.end_s - item.start_s) / DAY_S) * plotWidth, 2)}
              height={height - AXIS_HEIGHT_PX}
              fill={CONTACT_FILL}
            />
          ))}
          <text x={LEFT_PX} y={batteryBand.top - 8} fill={BATTERY_COLOR}>
            バッテリ残量 {batteryLow}〜100 %
          </text>
          <polyline
            points={polyline(timeline.time_s, batteryPercent, batteryLow, 100, plotWidth, batteryBand)}
            fill="none"
            stroke={BATTERY_COLOR}
            strokeWidth={1.5}
          />
          <text x={LEFT_PX} y={powerBand.top - 8} fill="#1f2933">
            発電（黄）と消費（赤） 最大 {powerPeak.toFixed(1)} W
          </text>
          <polygon
            points={`${LEFT_PX},${baseY} ${generatedLine} ${LEFT_PX + plotWidth},${baseY}`}
            fill={GENERATED_FILL}
          />
          <polyline
            points={polyline(timeline.time_s, timeline.consumed_power_w, 0, powerHigh, plotWidth, powerBand)}
            fill="none"
            stroke={CONSUMED_COLOR}
            strokeWidth={1.5}
          />
          <text x={LEFT_PX} y={dataBand.top - 8} fill={DATA_COLOR}>
            ダウンリンクの累積 {dataHigh.toFixed(1)} MB（青の帯が通信中）
          </text>
          <polyline
            points={polyline(timeline.time_s, dataMegabytes, 0, dataHigh, plotWidth, dataBand)}
            fill="none"
            stroke={DATA_COLOR}
            strokeWidth={2}
          />
          {HOURS.map((hour) => (
            <text
              key={hour}
              x={LEFT_PX + ((hour * SECONDS_PER_HOUR) / DAY_S) * plotWidth}
              y={height - 6}
              textAnchor={hour === 0 ? "start" : hour === 24 ? "end" : "middle"}
              fill="#6b7684"
            >
              {hour} 時間
            </text>
          ))}
        </svg>
      )}
    </div>
  );
}

export default function TimelineView({ timeline }: { timeline: Timeline | null }) {
  if (timeline === null) {
    return (
      <section className="panel timeline" aria-label="時系列">
        <p className="viewer-empty">機器構成と軌道が決まると、ここに時系列を表示します。</p>
      </section>
    );
  }
  const margins = timeline.link_margin_db.filter((value): value is number => value !== null);

  return (
    <section className="panel timeline" aria-label="時系列">
      <h2 className="panel-title">通信と電源の時系列（1 日、暫定）</h2>
      <TimelineChart timeline={timeline} />
      <dl className="diagram-facts">
        <div>
          <dt>通信</dt>
          <dd>
            {timeline.contacts.length} 回、{Math.round(timeline.contact_s / 60)} 分
          </dd>
        </div>
        <div>
          <dt>ダウンリンク量</dt>
          <dd>{(timeline.downlink_bit / 8e6).toFixed(1)} MB</dd>
        </div>
        <div>
          <dt>最低のバッテリ残量</dt>
          <dd>{(timeline.min_battery_ratio * 100).toFixed(1)} %</dd>
        </div>
        {margins.length > 0 && (
          <div>
            <dt>回線マージン</dt>
            <dd>
              {Math.min(...margins).toFixed(1)}〜{Math.max(...margins).toFixed(1)} dB
            </dd>
          </div>
        )}
      </dl>
      {timeline.min_battery_ratio <= 0 && <p className="msg-warning">この 1 日の途中でバッテリが空になります。</p>}
      <p className="muted">
        地上局は{timeline.station}です。円軌道で、太陽が軌道面にある最悪の日陰を仮定しています。通信の時刻を反映するので、最低残量は設計書の放電深度と少し異なります。
      </p>
    </section>
  );
}
