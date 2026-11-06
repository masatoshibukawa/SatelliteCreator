"use client";

/** 3D view of the satellite. The model is rebuilt when the satellite or its equipment changes. */

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { buildSatelliteModel, disposeGroup } from "../lib/satelliteModel";
import type { EquipmentCategory, SatelliteView } from "../lib/types";
import { prefersReducedMotion, useThreeStage, type Stage } from "../lib/useThreeStage";

const VIEW_DIRECTION = new THREE.Vector3(1, 0.55, 1.3).normalize();

function fitToView(stage: Stage, model: THREE.Object3D): void {
  const box = new THREE.Box3().setFromObject(model);
  const center = box.getCenter(new THREE.Vector3());
  const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 1e-3);
  // The margin keeps the model clear of the overlays at the top and bottom of the view.
  const distance = (radius / Math.sin((stage.camera.fov * Math.PI) / 360)) * 1.5;
  stage.camera.position.copy(center).addScaledVector(VIEW_DIRECTION, distance);
  stage.camera.near = distance / 100;
  stage.camera.far = distance * 20;
  stage.camera.updateProjectionMatrix();
  stage.controls.target.copy(center);
  stage.controls.minDistance = radius * 0.8;
  stage.controls.maxDistance = distance * 4;
  stage.controls.update();
}

function lightScene(stage: Stage): void {
  stage.scene.add(new THREE.HemisphereLight(0xffffff, 0x8a94a6, 1.5));
  const sun = new THREE.DirectionalLight(0xffffff, 2);
  sun.position.set(1, 2, 1.5);
  stage.scene.add(sun);
  stage.controls.autoRotate = !prefersReducedMotion();
  stage.controls.autoRotateSpeed = 1;
}

function formatSize(satellite: SatelliteView): string {
  const millimetres = [satellite.width_m, satellite.depth_m, satellite.length_m];
  return millimetres.map((value) => Math.round(value * 10000) / 10).join(" × ");
}

interface SatelliteViewerProps {
  satellite: SatelliteView | null;
  equipment: EquipmentCategory[];
}

export default function SatelliteViewer({ satellite, equipment }: SatelliteViewerProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const { stageRef, unavailable } = useThreeStage(hostRef, lightScene);
  const selectedKey = equipment.map((item) => item.selected).join(",");

  useEffect(() => {
    const stage = stageRef.current;
    if (stage === null || satellite === null) return;
    const model = buildSatelliteModel(satellite, selectedKey === "" ? [] : selectedKey.split(","));
    stage.scene.add(model);
    fitToView(stage, model);
    return () => {
      stage.scene.remove(model);
      disposeGroup(model);
    };
  }, [satellite, selectedKey, stageRef]);

  return (
    <section className="panel viewer" aria-label="衛星">
      <h2 className="viewer-title">衛星</h2>
      <div className="viewer-canvas" ref={hostRef} hidden={satellite === null || unavailable} />
      {unavailable && <p className="viewer-empty">この環境では 3D 表示を使えません。</p>}
      {satellite === null && !unavailable && (
        <p className="viewer-empty">衛星の大きさが決まると、ここに表示します。</p>
      )}
      {satellite !== null && (
        <>
          <dl className="viewer-facts">
            <div>
              <dt>形状</dt>
              <dd>{satellite.form_factor}</dd>
            </div>
            <div>
              <dt>外形</dt>
              <dd>{formatSize(satellite)} mm</dd>
            </div>
          </dl>
          <p className="viewer-note">
            {equipment.length > 0 ? "機器の形は説明用です。" : "この大きさの機器構成は未登録です。"}
          </p>
        </>
      )}
    </section>
  );
}
