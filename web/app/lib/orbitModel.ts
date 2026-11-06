import * as THREE from "three";

/** Drawing scale only: the orbit is drawn in Earth radii. */
const EARTH_RADIUS_M = 6378137;
const EARTH_COLOR = 0x3f7fc4;
const GRID_COLOR = 0xbcd4ee;
const SUNLIT_COLOR = 0xe39a1f;
const ECLIPSE_COLOR = 0x33415a;
const SATELLITE_COLOR = 0xc23a3a;
const SUN_COLOR = 0xf5c542;
const SUN_DISTANCE = 1.9;
const TUBE_RADIUS = 0.018;
const GRID_STEP_DEG = 30;

export interface OrbitScene {
  group: THREE.Group;
  /** Moves the satellite to a phase in radians. Phase 0 faces the Sun. */
  setPhase: (phase: number) => void;
}

function arc(radius: number, start: number, length: number, color: number): THREE.Mesh {
  const mesh = new THREE.Mesh(
    new THREE.TorusGeometry(radius, TUBE_RADIUS, 8, 160, length),
    new THREE.MeshBasicMaterial({ color }),
  );
  mesh.rotation.set(Math.PI / 2, 0, start);
  return mesh;
}

function circleLine(radius: number, y: number): THREE.LineLoop {
  const points = Array.from({ length: 72 }, (_, index) => {
    const angle = (index / 72) * Math.PI * 2;
    return new THREE.Vector3(Math.cos(angle) * radius, y, Math.sin(angle) * radius);
  });
  return new THREE.LineLoop(
    new THREE.BufferGeometry().setFromPoints(points),
    new THREE.LineBasicMaterial({ color: GRID_COLOR }),
  );
}

function earth(): THREE.Group {
  const group = new THREE.Group();
  group.add(
    new THREE.Mesh(
      new THREE.SphereGeometry(1, 64, 48),
      new THREE.MeshStandardMaterial({ color: EARTH_COLOR, roughness: 0.8 }),
    ),
  );
  for (let latitude = -60; latitude <= 60; latitude += GRID_STEP_DEG) {
    const angle = THREE.MathUtils.degToRad(latitude);
    group.add(circleLine(Math.cos(angle) * 1.002, Math.sin(angle) * 1.002));
  }
  for (let longitude = 0; longitude < 180; longitude += GRID_STEP_DEG) {
    const meridian = circleLine(1.002, 0);
    meridian.rotation.set(Math.PI / 2, THREE.MathUtils.degToRad(longitude), 0, "YXZ");
    group.add(meridian);
  }
  return group;
}

/**
 * The Sun lies in the orbit plane, the worst case for eclipse that the core calculates, so the
 * dark arc is centred opposite the Sun and its length is the eclipse share of the period.
 */
export function buildOrbitScene(altitudeM: number, inclinationDeg: number, eclipseShare: number | null): OrbitScene {
  const group = new THREE.Group();
  group.add(earth());
  const radius = 1 + altitudeM / EARTH_RADIUS_M;
  const eclipse = (eclipseShare ?? 0) * Math.PI * 2;

  const plane = new THREE.Group();
  plane.rotation.x = -THREE.MathUtils.degToRad(inclinationDeg);
  plane.add(arc(radius, eclipse === 0 ? 0 : Math.PI + eclipse / 2, Math.PI * 2 - eclipse, SUNLIT_COLOR));
  if (eclipse > 0) plane.add(arc(radius, Math.PI - eclipse / 2, eclipse, ECLIPSE_COLOR));
  const satellite = new THREE.Mesh(
    new THREE.SphereGeometry(0.05, 20, 14),
    new THREE.MeshBasicMaterial({ color: SATELLITE_COLOR }),
  );
  plane.add(satellite);
  group.add(plane);

  const sun = new THREE.Mesh(
    new THREE.SphereGeometry(0.14, 24, 16),
    new THREE.MeshBasicMaterial({ color: SUN_COLOR }),
  );
  sun.position.set(SUN_DISTANCE, 0, 0);
  group.add(sun);
  const light = new THREE.DirectionalLight(0xffffff, 2.6);
  light.position.set(SUN_DISTANCE, 0, 0);
  group.add(light);

  const setPhase = (phase: number): void => {
    satellite.position.set(Math.cos(phase) * radius, 0, Math.sin(phase) * radius);
  };
  setPhase(0);
  return { group, setPhase };
}
