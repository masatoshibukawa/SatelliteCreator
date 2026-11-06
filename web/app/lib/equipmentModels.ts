import * as THREE from "three";

/** Illustrative shapes, not design values. The scene's +Y is the CubeSat +Z axis. */
const CELL_COLOR = 0x1d3a6e;
const LENS_COLOR = 0x10151f;
const WHITE = 0xe8ecf2;
const GOLD = 0xc9a24b;
const COPPER = 0xb5683a;
const STEEL = 0x8b95a5;

const CELL_THICKNESS_M = 0.002;
const CELL_COVERAGE = 0.86;
const WING_SPAN_RATIO = 1.5;
const WHIP_LENGTH_M = 0.17;
const WHIP_TILT_RAD = Math.PI / 3;

export interface Body {
  width: number;
  depth: number;
  length: number;
}

function material(color: number, metalness = 0.3): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, metalness, roughness: 0.5 });
}

function cylinder(radius: number, height: number, color: number): THREE.Mesh {
  return new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, height, 32), material(color));
}

function box(x: number, y: number, z: number, color: number): THREE.Mesh {
  return new THREE.Mesh(new THREE.BoxGeometry(x, y, z), material(color));
}

function placed(mesh: THREE.Mesh, x: number, y: number, z: number): THREE.Mesh {
  mesh.position.set(x, y, z);
  return mesh;
}

function telescope(top: number, radius: number, height: number, color: number): THREE.Object3D[] {
  return [
    placed(cylinder(radius, height, color), 0, top + height / 2, 0),
    placed(cylinder(radius * 0.8, 0.002, LENS_COLOR), 0, top + height + 0.001, 0),
  ];
}

function bodyCells({ width, depth, length }: Body): THREE.Object3D[] {
  const height = length * CELL_COVERAGE;
  return [
    placed(box(CELL_THICKNESS_M, height, depth * CELL_COVERAGE, CELL_COLOR), width / 2, 0, 0),
    placed(box(CELL_THICKNESS_M, height, depth * CELL_COVERAGE, CELL_COLOR), -width / 2, 0, 0),
    placed(box(width * CELL_COVERAGE, height, CELL_THICKNESS_M, CELL_COLOR), 0, 0, depth / 2),
    placed(box(width * CELL_COVERAGE, height, CELL_THICKNESS_M, CELL_COLOR), 0, 0, -depth / 2),
  ];
}

function wings(body: Body): THREE.Object3D[] {
  const span = body.width * WING_SPAN_RATIO;
  const offset = body.width / 2 + span / 2;
  const height = body.length * CELL_COVERAGE;
  return [
    ...bodyCells(body),
    placed(box(span, height, CELL_THICKNESS_M, CELL_COLOR), offset, 0, 0),
    placed(box(span, height, CELL_THICKNESS_M, CELL_COLOR), -offset, 0, 0),
  ];
}

function whips({ length }: Body): THREE.Object3D[] {
  return [0, 1, 2, 3].map((index) => {
    const pivot = new THREE.Group();
    pivot.position.y = -length / 2;
    pivot.rotation.y = (index * Math.PI) / 2 + Math.PI / 4;
    const rod = cylinder(0.0012, WHIP_LENGTH_M, STEEL);
    rod.rotation.z = WHIP_TILT_RAD;
    rod.position.set(Math.sin(WHIP_TILT_RAD) * (WHIP_LENGTH_M / 2), -Math.cos(WHIP_TILT_RAD) * (WHIP_LENGTH_M / 2), 0);
    pivot.add(rod);
    return pivot;
  });
}

const BUILDERS: Readonly<Record<string, (body: Body) => THREE.Object3D[]>> = {
  camera_small: ({ length }) => telescope(length / 2, 0.018, 0.015, LENS_COLOR),
  camera_large: ({ length }) => telescope(length / 2, 0.038, 0.09, WHITE),
  atmosphere_sensor: ({ length }) => [
    placed(box(0.05, 0.02, 0.05, GOLD), 0, length / 2 + 0.01, 0),
    placed(cylinder(0.003, 0.08, STEEL), 0, length / 2 + 0.06, 0),
    placed(new THREE.Mesh(new THREE.SphereGeometry(0.012, 24, 16), material(GOLD)), 0, length / 2 + 0.105, 0),
  ],
  optical_terminal: ({ length }) => [
    placed(cylinder(0.03, 0.012, STEEL), 0, length / 2 + 0.006, 0),
    placed(new THREE.Mesh(new THREE.SphereGeometry(0.03, 32, 24), material(WHITE)), 0, length / 2 + 0.04, 0),
    placed(cylinder(0.016, 0.004, LENS_COLOR), 0, length / 2 + 0.07, 0),
  ],
  body_cells: bodyCells,
  deployed_panels: wings,
  uhf_radio: whips,
  s_band_radio: ({ length }) => [
    placed(box(0.06, 0.004, 0.06, WHITE), 0, -length / 2 - 0.002, 0),
    placed(box(0.04, 0.003, 0.04, GOLD), 0, -length / 2 - 0.005, 0),
  ],
  magnetorquer: ({ depth }) => {
    const coil = new THREE.Mesh(new THREE.TorusGeometry(0.03, 0.004, 12, 40), material(COPPER, 0.6));
    coil.position.z = depth / 2 + 0.005;
    return [coil];
  },
  reaction_wheels: ({ depth }) =>
    [-0.03, 0, 0.03].map((offset) => {
      const wheel = cylinder(0.013, 0.008, GOLD);
      wheel.rotation.x = Math.PI / 2;
      wheel.position.set(offset, 0, depth / 2 + 0.006);
      return wheel;
    }),
};

export function buildEquipment(body: Body, selected: readonly string[]): THREE.Object3D[] {
  return selected.flatMap((id) => BUILDERS[id]?.(body) ?? []);
}
