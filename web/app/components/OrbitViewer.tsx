"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { kilometres, minutes } from "../lib/format";
import { buildOrbitScene } from "../lib/orbitModel";
import { disposeGroup } from "../lib/satelliteModel";
import type { DiagramData } from "../lib/types";
import { prefersReducedMotion, useThreeStage, type Stage } from "../lib/useThreeStage";

/** Seconds on screen for one orbit. A display speed, not a design value. */
const SECONDS_PER_ORBIT = 16;

function setUpStage(stage: Stage): void {
  stage.scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  stage.camera.position.set(1.6, 3.2, 8);
  stage.camera.near = 0.1;
  stage.camera.far = 50;
  stage.camera.updateProjectionMatrix();
  stage.controls.minDistance = 2.5;
  stage.controls.maxDistance = 16;
}

export default function OrbitViewer({ diagrams }: { diagrams: DiagramData | null }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const { stageRef, unavailable } = useThreeStage(hostRef, setUpStage);
  const altitude = diagrams?.altitude_m ?? null;
  const inclination = diagrams?.inclination_deg ?? null;
  const period = diagrams?.orbit_period_s ?? null;
  const eclipse = diagrams?.max_eclipse_s ?? null;
  const known = altitude !== null && inclination !== null;

  useEffect(() => {
    const stage = stageRef.current;
    if (stage === null || altitude === null || inclination === null) return;
    const share = period !== null && eclipse !== null ? eclipse / period : null;
    const orbit = buildOrbitScene(altitude, inclination, share);
    stage.scene.add(orbit.group);
    let phase = 0;
    if (!prefersReducedMotion()) {
      stage.onFrame = (seconds) => {
        phase += (seconds / SECONDS_PER_ORBIT) * Math.PI * 2;
        orbit.setPhase(phase);
      };
    }
    return () => {
      stage.onFrame = null;
      stage.scene.remove(orbit.group);
      disposeGroup(orbit.group);
    };
  }, [altitude, inclination, period, eclipse, stageRef]);

  return (
    <section className="panel viewer" aria-label="軌道">
      <h2 className="viewer-title">軌道</h2>
      <div className="viewer-canvas" ref={hostRef} hidden={!known || unavailable} />
      {unavailable && <p className="viewer-empty">この環境では 3D 表示を使えません。</p>}
      {!known && !unavailable && <p className="viewer-empty">高度と軌道傾斜角が決まると、ここに表示します。</p>}
      {known && (
        <>
          <dl className="viewer-facts">
            <div>
              <dt>高度</dt>
              <dd>{kilometres(altitude)}</dd>
            </div>
            <div>
              <dt>傾斜角</dt>
              <dd>{inclination} 度</dd>
            </div>
            {period !== null && (
              <div>
                <dt>周期</dt>
                <dd>{minutes(period)}</dd>
              </div>
            )}
            {eclipse !== null && (
              <div>
                <dt>最大の日陰</dt>
                <dd>{minutes(eclipse)}</dd>
              </div>
            )}
          </dl>
          <p className="viewer-note">橙は日照、濃い色は日陰です。太陽が軌道面にある最悪の場合です。</p>
        </>
      )}
    </section>
  );
}
