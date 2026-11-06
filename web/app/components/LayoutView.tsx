"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { buildLayoutModel, EXTERNAL_KEY, highlightItem, ITEM_KEY } from "../lib/layoutModel";
import { disposeGroup } from "../lib/satelliteModel";
import type { LayoutItem, SatelliteLayout, SatelliteView } from "../lib/types";
import { addStudioLight, fitToView, useThreeStage } from "../lib/useThreeStage";

const CLICK_TOLERANCE_PX = 5;

function pickItem(event: PointerEvent, canvas: HTMLCanvasElement, camera: THREE.Camera, model: THREE.Group): string | null {
  const box = canvas.getBoundingClientRect();
  const pointer = new THREE.Vector2(
    ((event.clientX - box.left) / box.width) * 2 - 1,
    -((event.clientY - box.top) / box.height) * 2 + 1,
  );
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObject(model, true).filter((item) => item.object.userData[ITEM_KEY] !== undefined);
  // An interior part seen through a see-through outer part is what the click is aimed at.
  const hit = hits.find((item) => !item.object.userData[EXTERNAL_KEY]) ?? hits[0];
  return hit === undefined ? null : (hit.object.userData[ITEM_KEY] as string);
}

function Cutaway({
  satellite,
  items,
  selectedId,
  onSelect,
}: {
  satellite: SatelliteView;
  items: LayoutItem[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const modelRef = useRef<THREE.Group | null>(null);
  const { stageRef, unavailable } = useThreeStage(hostRef, addStudioLight);

  useEffect(() => {
    const stage = stageRef.current;
    if (stage === null) return;
    const model = buildLayoutModel(satellite, items);
    stage.scene.add(model);
    modelRef.current = model;
    fitToView(stage, model);
    return () => {
      stage.scene.remove(model);
      disposeGroup(model);
      modelRef.current = null;
    };
  }, [items, satellite, stageRef]);

  useEffect(() => {
    if (modelRef.current !== null) highlightItem(modelRef.current, selectedId);
  }, [items, satellite, selectedId]);

  useEffect(() => {
    const stage = stageRef.current;
    if (stage === null) return;
    const canvas = stage.renderer.domElement;
    let startX = 0;
    let startY = 0;
    const down = (event: PointerEvent): void => {
      startX = event.clientX;
      startY = event.clientY;
    };
    const up = (event: PointerEvent): void => {
      const moved = Math.hypot(event.clientX - startX, event.clientY - startY);
      if (moved > CLICK_TOLERANCE_PX || modelRef.current === null) return;
      onSelect(pickItem(event, canvas, stage.camera, modelRef.current));
    };
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointerup", up);
    return () => {
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointerup", up);
    };
  }, [onSelect, stageRef]);

  return (
    <section className="panel viewer" aria-label="内部の立体図">
      <h2 className="viewer-title">内部（クリックで機器を選択）</h2>
      <div className="viewer-canvas" ref={hostRef} hidden={unavailable} />
      {unavailable && <p className="viewer-empty">この環境では 3D 表示を使えません。</p>}
      <p className="viewer-note">色は系統を表します。寸法は説明用の暫定値です。</p>
    </section>
  );
}

function SlotButton({ item, selected, onSelect }: { item: LayoutItem; selected: boolean; onSelect: (id: string) => void }) {
  return (
    <button
      type="button"
      className="layout-slot"
      style={{ flexGrow: item.size_mm[2] }}
      aria-pressed={selected}
      onClick={() => onSelect(item.id)}
    >
      {item.label}
    </button>
  );
}

function StackDiagram({
  layout,
  selectedId,
  onSelect,
}: {
  layout: SatelliteLayout;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const stack = layout.items.filter((item) => !item.external);
  const outside = layout.items.filter((item) => item.external);
  const free = layout.internal_length_mm - layout.stack_height_mm;

  return (
    <section className="panel layout-diagram" aria-label="機器の配置図">
      <h2 className="panel-title">配置図（模式図）</h2>
      <span className="layout-axis">+Z 側</span>
      <div className="layout-body">
        {stack.map((item) => (
          <SlotButton key={item.id} item={item} selected={item.id === selectedId} onSelect={onSelect} />
        ))}
        {free > 0 && (
          <div className="layout-free" style={{ flexGrow: free }}>
            空き {free} mm
          </div>
        )}
      </div>
      <span className="layout-axis">−Z 側（ミッション）</span>
      {free < 0 && <p className="msg-warning">内部の長さを {-free} mm 超えています。</p>}
      <span className="layout-axis">外側の機器</span>
      <div className="option-list">
        {outside.map((item) => (
          <button
            key={item.id}
            type="button"
            className="chip-option"
            aria-pressed={item.id === selectedId}
            onClick={() => onSelect(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function ItemInfo({ item }: { item: LayoutItem | null }) {
  if (item === null) {
    return (
      <section className="panel layout-info" aria-label="機器の説明">
        <h2 className="panel-title">機器の説明</h2>
        <p className="muted">立体図か配置図の機器をクリックすると、ここに説明を表示します。</p>
      </section>
    );
  }
  return (
    <section className="panel layout-info" aria-label="機器の説明">
      <h2 className="panel-title">{item.label}</h2>
      <p>{item.role}</p>
      <dl className="diagram-facts">
        <div>
          <dt>系統</dt>
          <dd>{item.group}</dd>
        </div>
        <div>
          <dt>質量</dt>
          <dd>{item.mass_g === null ? "未割り当て" : `${item.mass_g} g`}</dd>
        </div>
        <div>
          <dt>平均電力</dt>
          <dd>{item.average_power_w === null ? "機器ごとは未計算" : `${item.average_power_w} W`}</dd>
        </div>
        <div>
          <dt>寸法（暫定）</dt>
          <dd>{item.size_mm.join(" × ")} mm</dd>
        </div>
      </dl>
    </section>
  );
}

interface LayoutViewProps {
  satellite: SatelliteView | null;
  layout: SatelliteLayout | null;
}

export default function LayoutView({ satellite, layout }: LayoutViewProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (satellite === null || layout === null) {
    return (
      <section className="panel timeline" aria-label="機器配置">
        <p className="viewer-empty">機器構成が決まると、ここに配置図を表示します。</p>
      </section>
    );
  }

  const selected = layout.items.find((item) => item.id === selectedId) ?? null;
  return (
    <div className="layout-view">
      <Cutaway satellite={satellite} items={layout.items} selectedId={selectedId} onSelect={setSelectedId} />
      <StackDiagram layout={layout} selectedId={selectedId} onSelect={setSelectedId} />
      <ItemInfo item={selected} />
    </div>
  );
}
