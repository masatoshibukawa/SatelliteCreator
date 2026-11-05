"use client";

/**
 * 3D view of the satellite: plain three.js inside a ref, as in RocketCreater's ModelViewer.
 * One renderer per mount; the model is rebuilt when the satellite changes.
 */

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { buildSatelliteModel, disposeGroup } from "../lib/satelliteModel";
import type { SatelliteView } from "../lib/types";

const BACKGROUND = 0xf6f8fb;
const VIEW_DIRECTION = new THREE.Vector3(1, 0.55, 1.3).normalize();

interface Scene3D {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  model: THREE.Group | null;
}

function fitToView(view: Scene3D, model: THREE.Object3D): void {
  const box = new THREE.Box3().setFromObject(model);
  const center = box.getCenter(new THREE.Vector3());
  const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 1e-3);
  // The margin keeps the model clear of the overlays at the top and bottom of the view.
  const distance = (radius / Math.sin((view.camera.fov * Math.PI) / 360)) * 1.5;
  view.camera.position.copy(center).addScaledVector(VIEW_DIRECTION, distance);
  view.camera.near = distance / 100;
  view.camera.far = distance * 20;
  view.camera.updateProjectionMatrix();
  view.controls.target.copy(center);
  view.controls.minDistance = radius * 0.8;
  view.controls.maxDistance = distance * 4;
  view.controls.update();
}

function createScene(host: HTMLDivElement): Scene3D {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  host.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(BACKGROUND);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a94a6, 1.5));
  const sun = new THREE.DirectionalLight(0xffffff, 2);
  sun.position.set(1, 2, 1.5);
  scene.add(sun);

  const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 100);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.autoRotate = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  controls.autoRotateSpeed = 1;
  return { renderer, scene, camera, controls, model: null };
}

function formatSize(satellite: SatelliteView): string {
  const millimetres = [satellite.width_m, satellite.depth_m, satellite.length_m];
  return millimetres.map((value) => Math.round(value * 10000) / 10).join(" × ");
}

export default function SatelliteViewer({ satellite }: { satellite: SatelliteView | null }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<Scene3D | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (host === null) return;
    let view: Scene3D;
    try {
      view = createScene(host);
    } catch {
      setUnavailable(true);
      return;
    }
    viewRef.current = view;

    const resize = (): void => {
      const { clientWidth: width, clientHeight: height } = host;
      if (width === 0 || height === 0) return;
      view.renderer.setSize(width, height);
      view.camera.aspect = width / height;
      view.camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();
    view.renderer.setAnimationLoop(() => {
      view.controls.update();
      view.renderer.render(view.scene, view.camera);
    });

    return () => {
      observer.disconnect();
      view.renderer.setAnimationLoop(null);
      view.controls.dispose();
      if (view.model !== null) disposeGroup(view.model);
      view.renderer.dispose();
      view.renderer.domElement.remove();
      viewRef.current = null;
    };
  }, []);

  useEffect(() => {
    const view = viewRef.current;
    if (view === null) return;
    if (view.model !== null) {
      view.scene.remove(view.model);
      disposeGroup(view.model);
      view.model = null;
    }
    if (satellite === null) return;
    const model = buildSatelliteModel(satellite);
    view.scene.add(model);
    view.model = model;
    fitToView(view, model);
  }, [satellite]);

  return (
    <section className="panel viewer" aria-label="衛星の外形">
      <div className="viewer-canvas" ref={hostRef} hidden={satellite === null || unavailable} />
      {unavailable && <p className="viewer-empty">この環境では 3D 表示を使えません。</p>}
      {satellite === null && !unavailable && (
        <p className="viewer-empty">衛星の大きさが決まると、ここに外形を表示します。</p>
      )}
      {satellite !== null && (
        <>
          <dl className="viewer-facts">
            <div>
              <dt>形状</dt>
              <dd>{satellite.form_factor}</dd>
            </div>
            <div>
              <dt>打上げ時の外形</dt>
              <dd>{formatSize(satellite)} mm</dd>
            </div>
            <div>
              <dt>質量の上限</dt>
              <dd>{satellite.max_mass_kg} kg</dd>
            </div>
          </dl>
          <p className="viewer-note">外形のみを表示しています。搭載機器はまだ設計されていません。</p>
        </>
      )}
    </section>
  );
}
