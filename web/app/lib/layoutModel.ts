import * as THREE from "three";
import type { LayoutItem, SatelliteView } from "./types";

const SHELL_COLOR = 0x8fa6c4;
const SHELL_OPACITY = 0.14;
const SELECTED_GLOW = 0x2f6fed;
/** Parts outside the body are see-through so they do not hide the interior. */
const EXTERNAL_OPACITY = 0.3;
const PALETTE = [0x4f8fd9, 0x45b08c, 0xe0a23a, 0xc76a6a, 0x8d76c9, 0x5fb3c4, 0xb9a15f];
const METRES_PER_MM = 0.001;

export const ITEM_KEY = "layoutItemId";
export const EXTERNAL_KEY = "layoutItemExternal";

function groupColor(group: string, groups: readonly string[]): number {
  return PALETTE[groups.indexOf(group) % PALETTE.length];
}

/** A see-through body with one box per item. Scene +Y is the CubeSat +Z axis. */
export function buildLayoutModel(satellite: SatelliteView, items: readonly LayoutItem[]): THREE.Group {
  const group = new THREE.Group();
  const shell = new THREE.Mesh(
    new THREE.BoxGeometry(satellite.width_m, satellite.length_m, satellite.depth_m),
    new THREE.MeshStandardMaterial({
      color: SHELL_COLOR,
      transparent: true,
      opacity: SHELL_OPACITY,
      depthWrite: false,
    }),
  );
  group.add(shell);
  const groups = [...new Set(items.map((item) => item.group))];
  for (const item of items) {
    const [sizeX, sizeY, sizeZ] = item.size_mm.map((value) => value * METRES_PER_MM);
    const [x, y, z] = item.center_mm.map((value) => value * METRES_PER_MM);
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(sizeX, sizeZ, sizeY),
      new THREE.MeshStandardMaterial({
        color: groupColor(item.group, groups),
        roughness: 0.6,
        transparent: item.external,
        opacity: item.external ? EXTERNAL_OPACITY : 1,
        depthWrite: !item.external,
      }),
    );
    mesh.position.set(x, z, y);
    mesh.userData[ITEM_KEY] = item.id;
    mesh.userData[EXTERNAL_KEY] = item.external;
    group.add(mesh);
  }
  return group;
}

export function highlightItem(model: THREE.Group, selectedId: string | null): void {
  model.traverse((node) => {
    if (!(node instanceof THREE.Mesh) || node.userData[ITEM_KEY] === undefined) return;
    const material = node.material as THREE.MeshStandardMaterial;
    material.emissive.setHex(node.userData[ITEM_KEY] === selectedId ? SELECTED_GLOW : 0x000000);
  });
}
