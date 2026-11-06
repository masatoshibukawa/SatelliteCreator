"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

const BACKGROUND = 0xf6f8fb;

export interface Stage {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  /** Runs before each frame, with the seconds since the previous one. */
  onFrame: ((seconds: number) => void) | null;
}

export function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

const VIEW_DIRECTION = new THREE.Vector3(1, 0.55, 1.3).normalize();

export function fitToView(stage: Stage, model: THREE.Object3D, direction = VIEW_DIRECTION): void {
  const box = new THREE.Box3().setFromObject(model);
  const center = box.getCenter(new THREE.Vector3());
  const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 1e-3);
  // The margin keeps the model clear of the overlays at the top and bottom of the view.
  const distance = (radius / Math.sin((stage.camera.fov * Math.PI) / 360)) * 1.5;
  stage.camera.position.copy(center).addScaledVector(direction, distance);
  stage.camera.near = distance / 100;
  stage.camera.far = distance * 20;
  stage.camera.updateProjectionMatrix();
  stage.controls.target.copy(center);
  stage.controls.minDistance = radius * 0.8;
  stage.controls.maxDistance = distance * 4;
  stage.controls.update();
}

export function addStudioLight(stage: Stage): void {
  stage.scene.add(new THREE.HemisphereLight(0xffffff, 0x8a94a6, 1.5));
  const sun = new THREE.DirectionalLight(0xffffff, 2);
  sun.position.set(1, 2, 1.5);
  stage.scene.add(sun);
}

function createStage(host: HTMLDivElement): Stage {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  host.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(BACKGROUND);
  const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 100);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  return { renderer, scene, camera, controls, onFrame: null };
}

/** One renderer per mount, as in RocketCreater's ModelViewer. `setup` runs once it exists. */
export function useThreeStage(
  hostRef: RefObject<HTMLDivElement | null>,
  setup: (stage: Stage) => void,
): { stageRef: RefObject<Stage | null>; unavailable: boolean } {
  const stageRef = useRef<Stage | null>(null);
  const setupRef = useRef(setup);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (host === null) return;
    let stage: Stage;
    try {
      stage = createStage(host);
    } catch {
      setUnavailable(true);
      return;
    }
    setupRef.current(stage);
    stageRef.current = stage;

    const resize = (): void => {
      const { clientWidth: width, clientHeight: height } = host;
      if (width === 0 || height === 0) return;
      stage.renderer.setSize(width, height);
      stage.camera.aspect = width / height;
      stage.camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();
    const clock = new THREE.Clock();
    stage.renderer.setAnimationLoop(() => {
      stage.onFrame?.(clock.getDelta());
      stage.controls.update();
      stage.renderer.render(stage.scene, stage.camera);
    });

    return () => {
      observer.disconnect();
      stage.renderer.setAnimationLoop(null);
      stage.controls.dispose();
      stage.renderer.dispose();
      stage.renderer.domElement.remove();
      stageRef.current = null;
    };
  }, [hostRef]);

  return { stageRef, unavailable };
}
