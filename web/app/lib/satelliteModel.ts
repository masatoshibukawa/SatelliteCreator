import * as THREE from "three";
import { buildEquipment } from "./equipmentModels";
import type { SatelliteView } from "./types";

/** Minimum rail width, CubeSat Design Specification Rev. 14.1, 2.2.5. */
const RAIL_WIDTH_M = 0.0085;
/** Drawing choice so the panels sit behind the rails; not a design value. */
const PANEL_INSET_M = 0.0015;
/** The 6U envelope is two 3U stacks side by side. */
const UNITS_ALONG_LENGTH: Readonly<Record<string, number>> = { "1U": 1, "2U": 2, "3U": 3, "6U": 3 };

const PANEL_COLOR = 0x8fa6c4;
const RAIL_COLOR = 0x59616e;
const LINE_COLOR = 0x33415a;

function unitRing(width: number, depth: number, z: number): THREE.LineLoop {
  const halfWidth = width / 2;
  const halfDepth = depth / 2;
  const points = [
    new THREE.Vector3(-halfWidth, z, -halfDepth),
    new THREE.Vector3(halfWidth, z, -halfDepth),
    new THREE.Vector3(halfWidth, z, halfDepth),
    new THREE.Vector3(-halfWidth, z, halfDepth),
  ];
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  return new THREE.LineLoop(geometry, new THREE.LineBasicMaterial({ color: LINE_COLOR }));
}

/**
 * The launch envelope from the API, its four rails and the chosen equipment. The CubeSat Z axis
 * points up in the scene.
 */
export function buildSatelliteModel(satellite: SatelliteView, equipment: readonly string[]): THREE.Group {
  const group = new THREE.Group();
  const { width_m: width, depth_m: depth, length_m: length } = satellite;

  const panels = new THREE.Mesh(
    new THREE.BoxGeometry(width - PANEL_INSET_M * 2, length, depth - PANEL_INSET_M * 2),
    new THREE.MeshStandardMaterial({ color: PANEL_COLOR, metalness: 0.25, roughness: 0.6 }),
  );
  group.add(panels);

  const railGeometry = new THREE.BoxGeometry(RAIL_WIDTH_M, length, RAIL_WIDTH_M);
  const railMaterial = new THREE.MeshStandardMaterial({ color: RAIL_COLOR, metalness: 0.6, roughness: 0.4 });
  const offsetX = width / 2 - RAIL_WIDTH_M / 2;
  const offsetZ = depth / 2 - RAIL_WIDTH_M / 2;
  for (const [signX, signZ] of [[1, 1], [1, -1], [-1, 1], [-1, -1]] as const) {
    const rail = new THREE.Mesh(railGeometry, railMaterial);
    rail.position.set(signX * offsetX, 0, signZ * offsetZ);
    group.add(rail);
  }

  const units = UNITS_ALONG_LENGTH[satellite.form_factor] ?? 1;
  for (let index = 1; index < units; index += 1) {
    group.add(unitRing(width, depth, -length / 2 + (length * index) / units));
  }
  // The mission end is -Z, as in the OPT-CUBE layout, so the equipment model is turned over.
  const fitted = new THREE.Group();
  fitted.rotation.z = Math.PI;
  fitted.add(...buildEquipment({ width, depth, length }, equipment));
  group.add(fitted);
  return group;
}

export function disposeGroup(group: THREE.Group): void {
  group.traverse((node) => {
    if (node instanceof THREE.Mesh || node instanceof THREE.Line) {
      node.geometry.dispose();
      const materials: THREE.Material[] = Array.isArray(node.material) ? node.material : [node.material];
      materials.forEach((material) => material.dispose());
    }
  });
}
