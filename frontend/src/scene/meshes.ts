import * as THREE from "three";
import type { Look } from "../types";

// ------------------------------------------------------------------ materials
const gradient = (() => {
  const tex = new THREE.DataTexture(new Uint8Array([110, 185, 255]), 3, 1, THREE.RedFormat);
  tex.minFilter = THREE.NearestFilter;
  tex.magFilter = THREE.NearestFilter;
  tex.needsUpdate = true;
  return tex;
})();

const cache = new Map<string, THREE.Material>();

/** Shared cel-shaded material for a color (storybook look). */
export function toon(color: string | number, opts: { emissive?: string; transparent?: number } = {}): THREE.MeshToonMaterial {
  const key = `${color}|${opts.emissive ?? ""}|${opts.transparent ?? ""}`;
  let m = cache.get(key) as THREE.MeshToonMaterial | undefined;
  if (!m) {
    m = new THREE.MeshToonMaterial({ color, gradientMap: gradient });
    if (opts.emissive) {
      m.emissive = new THREE.Color(opts.emissive);
      m.emissiveIntensity = 0;
      m.userData.glow = true;
    }
    if (opts.transparent !== undefined) {
      m.transparent = true;
      m.opacity = opts.transparent;
      m.depthWrite = false;
    }
    cache.set(key, m);
  }
  return m;
}

export function glowMaterials(): THREE.MeshToonMaterial[] {
  return [...cache.values()].filter((m) => m.userData.glow) as THREE.MeshToonMaterial[];
}

export const vertexToon = new THREE.MeshToonMaterial({ vertexColors: true, gradientMap: gradient });
export const instanceToon = () => new THREE.MeshToonMaterial({ color: "#ffffff", gradientMap: gradient });

// ------------------------------------------------------------------ geometry helpers
const geo = {
  box: new THREE.BoxGeometry(1, 1, 1),
  sphere: new THREE.SphereGeometry(1, 20, 14),
  lowSphere: new THREE.IcosahedronGeometry(1, 1),
  cyl: new THREE.CylinderGeometry(1, 1, 1, 18),
  cone: new THREE.ConeGeometry(1, 1, 16),
  torus: new THREE.TorusGeometry(1, 0.18, 10, 24),
};

function part(g: THREE.BufferGeometry, color: string, sx: number, sy: number, sz: number, x = 0, y = 0, z = 0, mat?: THREE.Material): THREE.Mesh {
  const m = new THREE.Mesh(g, mat ?? toon(color));
  m.scale.set(sx, sy, sz);
  m.position.set(x, y, z);
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}

const box = (c: string, sx: number, sy: number, sz: number, x = 0, y = 0, z = 0) => part(geo.box, c, sx, sy, sz, x, y + sy / 2, z);
const ball = (c: string, r: number, x = 0, y = 0, z = 0, sy = 1) => part(geo.sphere, c, r, r * sy, r, x, y, z);
const blob = (c: string, r: number, x = 0, y = 0, z = 0) => part(geo.lowSphere, c, r, r, r, x, y, z);
const cyl = (c: string, r: number, h: number, x = 0, y = 0, z = 0) => part(geo.cyl, c, r, h, r, x, y + h / 2, z);
const cone = (c: string, r: number, h: number, x = 0, y = 0, z = 0) => part(geo.cone, c, r, h, r, x, y + h / 2, z);

export function shade(hex: string, amount: number): string {
  const c = new THREE.Color(hex);
  const hsl = { h: 0, s: 0, l: 0 };
  c.getHSL(hsl);
  c.setHSL(hsl.h, hsl.s, Math.max(0, Math.min(1, hsl.l + amount)));
  return `#${c.getHexString()}`;
}

// ------------------------------------------------------------------ residents
export interface Figure {
  root: THREE.Group;
  body: THREE.Group;
  head: THREE.Group;
  legL: THREE.Mesh;
  legR: THREE.Mesh;
  hit: THREE.Mesh;
}

/** A chunky storybook resident: big round head, small body, simple face. */
export function buildResident(look: Look, id: string): Figure {
  const root = new THREE.Group();
  const body = new THREE.Group();
  root.add(body);
  const legL = cyl(look.pants, 0.075, 0.22, -0.09, 0, 0);
  const legR = cyl(look.pants, 0.075, 0.22, 0.09, 0, 0);
  body.add(legL, legR);
  body.add(ball(shade(look.pants, -0.12), 0.09, -0.09, 0.02, 0.04, 0.6), ball(shade(look.pants, -0.12), 0.09, 0.09, 0.02, 0.04, 0.6));
  const torso = part(new THREE.CapsuleGeometry(0.2, 0.18, 6, 16), look.shirt, 1, 1, 0.85, 0, 0.42, 0);
  body.add(torso);
  body.add(ball(look.skin, 0.065, -0.24, 0.36, 0), ball(look.skin, 0.065, 0.24, 0.36, 0));
  if (look.accessory === "apron") body.add(box("#fbfbf6", 0.3, 0.3, 0.04, 0, 0.26, 0.17));
  if (look.accessory === "scarf") body.add(part(geo.torus, "#e8546a", 0.17, 0.17, 0.17, 0, 0.62, 0, undefined).rotateX(Math.PI / 2));

  const head = new THREE.Group();
  head.position.set(0, 0.86, 0);
  body.add(head);
  head.add(ball(look.skin, 0.31));
  // face (front is +z)
  head.add(ball("#2b2533", 0.045, -0.1, 0.03, 0.28, 1.3), ball("#2b2533", 0.045, 0.1, 0.03, 0.28, 1.3));
  head.add(ball("#ffffff", 0.014, -0.09, 0.06, 0.315), ball("#ffffff", 0.014, 0.11, 0.06, 0.315));
  head.add(ball("#f39a9a", 0.05, -0.18, -0.06, 0.23, 0.55), ball("#f39a9a", 0.05, 0.18, -0.06, 0.23, 0.55));
  const smile = part(new THREE.TorusGeometry(0.05, 0.012, 6, 12, Math.PI), "#8a4b4b", 1, 1, 1, 0, -0.08, 0.29);
  smile.rotation.z = Math.PI;
  head.add(smile);
  // hair
  const hair = look.hair;
  if (look.hair_style !== "bald") {
    const cap = part(geo.sphere, hair, 0.325, 0.27, 0.325, 0, 0.08, -0.02);
    head.add(cap);
  }
  switch (look.hair_style) {
    case "long":
      head.add(part(geo.cyl, hair, 0.3, 0.42, 0.18, 0, -0.08, -0.17));
      break;
    case "bun":
      head.add(ball(hair, 0.13, 0, 0.33, -0.08));
      break;
    case "bob":
      head.add(part(geo.sphere, hair, 0.34, 0.24, 0.3, 0, -0.02, -0.04));
      break;
    case "curly":
      for (let k = 0; k < 7; k++) {
        const a = (k / 7) * Math.PI * 2;
        head.add(ball(hair, 0.09, Math.cos(a) * 0.24, 0.18 + Math.sin(k) * 0.03, Math.sin(a) * 0.2 - 0.04));
      }
      break;
    case "spiky":
      for (let k = 0; k < 5; k++) head.add(cone(hair, 0.07, 0.16, -0.16 + k * 0.08, 0.2, -0.04 + (k % 2) * 0.05));
      break;
  }
  switch (look.accessory) {
    case "glasses": {
      const ringL = part(geo.torus, "#3b3346", 0.065, 0.065, 0.065, -0.1, 0.03, 0.3);
      const ringR = part(geo.torus, "#3b3346", 0.065, 0.065, 0.065, 0.1, 0.03, 0.3);
      head.add(ringL, ringR, box("#3b3346", 0.06, 0.012, 0.012, 0, 0.03, 0.3));
      break;
    }
    case "beanie":
      head.add(part(geo.sphere, "#d9534f", 0.33, 0.24, 0.33, 0, 0.12, -0.01), ball("#f6f1e9", 0.06, 0, 0.36, 0));
      break;
    case "cap":
      head.add(part(geo.sphere, "#3a6fc4", 0.33, 0.2, 0.33, 0, 0.14, 0), box("#3a6fc4", 0.26, 0.03, 0.18, 0, 0.14, 0.27));
      break;
    case "bow":
      head.add(cone("#ef6aa2", 0.06, 0.12, -0.08, 0.3, -0.05).rotateZ(Math.PI / 2), cone("#ef6aa2", 0.06, 0.12, 0.08, 0.3, -0.05).rotateZ(-Math.PI / 2));
      break;
    case "headphones":
      head.add(part(new THREE.TorusGeometry(0.33, 0.025, 6, 20, Math.PI), "#2f3140", 1, 1, 1, 0, 0.02, 0));
      head.add(cyl("#2f3140", 0.07, 0.06, -0.33, -0.04, 0).rotateZ(Math.PI / 2), cyl("#2f3140", 0.07, 0.06, 0.33, -0.04, 0).rotateZ(Math.PI / 2));
      break;
  }
  const hit = new THREE.Mesh(new THREE.SphereGeometry(0.55, 8, 6), new THREE.MeshBasicMaterial({ visible: false }));
  hit.position.y = 0.6;
  hit.userData.resident = id;
  root.add(hit);
  root.scale.setScalar(1.05);
  return { root, body, head, legL, legR, hit };
}

// ------------------------------------------------------------------ catalog items
/** A placed item, built in a 1-tile-per-unit footprint of w x h centred on the origin. */
export function buildItem(shape: string, w: number, h: number, color: string): THREE.Group {
  const g = new THREE.Group();
  const wood = "#b98a5e";
  const dark = shade(color, -0.18);
  const light = shade(color, 0.14);
  const add = (...m: THREE.Object3D[]) => g.add(...m);
  switch (shape) {
    case "armchair":
      add(box(color, 0.7, 0.28, 0.7, 0, 0.08), box(dark, 0.7, 0.45, 0.16, 0, 0.08, -0.28), box(dark, 0.14, 0.3, 0.7, -0.33, 0.1), box(dark, 0.14, 0.3, 0.7, 0.33, 0.1));
      break;
    case "rug":
      add(box(dark, w * 0.92, 0.03, h * 0.92), box(light, w * 0.72, 0.035, h * 0.72));
      break;
    case "cart":
      add(box(wood, 0.6, 0.06, 0.4, 0, 0.42), box(wood, 0.6, 0.06, 0.4, 0, 0.18), ball(color, 0.1, -0.12, 0.6), ball("#fff7ef", 0.07, 0.14, 0.55));
      for (const [x, z] of [[-0.25, -0.15], [0.25, -0.15], [-0.25, 0.15], [0.25, 0.15]]) add(cyl("#5c5048", 0.05, 0.04, x, 0.02, z));
      break;
    case "swing":
      add(cyl(wood, 0.05, 1.1, -w / 2 + 0.15, 0), cyl(wood, 0.05, 1.1, w / 2 - 0.15, 0), box(wood, w - 0.2, 0.08, 0.1, 0, 1.08), box(color, w * 0.6, 0.08, 0.38, 0, 0.45));
      break;
    case "stall":
      add(box(wood, w * 0.9, 0.55, 0.6), box(color, w * 0.95, 0.06, 0.8, 0, 1.0));
      for (let k = 0; k < 4; k++) add(box(k % 2 ? "#ffffff" : color, (w * 0.95) / 4, 0.12, 0.82, -w * 0.36 + (k * w * 0.95) / 4, 1.06));
      add(cyl(wood, 0.04, 1.0, -w * 0.42, 0, 0.3), cyl(wood, 0.04, 1.0, w * 0.42, 0, 0.3), ball("#e8b45c", 0.1, -0.2, 0.62), ball("#d97b5d", 0.1, 0.15, 0.62));
      break;
    case "planter":
      add(box(wood, 0.7, 0.3, 0.7), box("#6b4b33", 0.6, 0.04, 0.6, 0, 0.3));
      for (let k = 0; k < 5; k++) add(ball(["#ff8fb1", "#ffd166", "#ffffff", color, "#c49cf2"][k], 0.08, Math.cos(k * 1.3) * 0.18, 0.42, Math.sin(k * 1.3) * 0.18));
      add(blob("#5cb35a", 0.16, 0, 0.36, 0));
      break;
    case "birdbath":
      add(cyl("#d8d2c6", 0.08, 0.5), cyl("#e3ddd2", 0.3, 0.08, 0, 0.5), cyl("#8fd3f0", 0.25, 0.02, 0, 0.57), ball(color, 0.06, 0.12, 0.66, 0.05));
      break;
    case "potted_plant":
      add(cyl(color, 0.18, 0.28), blob("#4fa654", 0.25, 0, 0.5, 0), blob("#64b85c", 0.16, 0.12, 0.66, 0.05));
      break;
    case "hedge":
      add(box("#4f9a4d", 0.95, 0.7, 0.95), blob("#5cae58", 0.3, -0.2, 0.75, 0.1), blob("#5cae58", 0.28, 0.22, 0.72, -0.12));
      break;
    case "tree":
      add(cyl("#8a5a3c", 0.1, 0.8), blob(color, 0.55, 0, 1.15, 0), blob(light, 0.38, 0.25, 1.45, 0.1), blob(dark, 0.32, -0.28, 1.0, -0.12));
      break;
    case "arch":
      add(cyl(wood, 0.06, 1.2, -w / 2 + 0.15, 0), cyl(wood, 0.06, 1.2, w / 2 - 0.15, 0));
      {
        const arc = part(new THREE.TorusGeometry(w / 2 - 0.15, 0.06, 8, 24, Math.PI), wood, 1, 1, 1, 0, 1.2, 0);
        add(arc);
        for (let k = 0; k <= 8; k++) {
          const a = (k / 8) * Math.PI;
          add(ball(k % 2 ? color : "#ff9fc0", 0.08, Math.cos(a) * (w / 2 - 0.15), 1.2 + Math.sin(a) * (w / 2 - 0.15), 0.04));
        }
      }
      break;
    case "bookshelf":
      add(box(wood, 0.8, 1.25, 0.35));
      for (let r = 0; r < 3; r++) for (let k = 0; k < 4; k++) add(box(["#e86f5a", "#4a82dd", "#f0c24c", "#58b368", color][(r + k) % 5], 0.14, 0.26, 0.28, -0.26 + k * 0.17, 0.12 + r * 0.38, 0.03));
      break;
    case "desk":
      add(box(wood, 0.8, 0.06, 0.55, 0, 0.55), box(dark, 0.08, 0.55, 0.5, -0.34), box(dark, 0.08, 0.55, 0.5, 0.34), box("#f6f1e6", 0.22, 0.02, 0.28, 0.1, 0.61), cyl(color, 0.05, 0.14, -0.22, 0.61));
      break;
    case "reading_nook":
      add(box(color, 1.5, 0.3, 0.65, -0.1, 0.08), box(dark, 1.5, 0.5, 0.16, -0.1, 0.08, -0.26), cyl("#3f3a48", 0.04, 1.1, 0.75, 0, -0.2), cone(light, 0.18, 0.22, 0.75, 1.05, -0.2));
      break;
    case "notice_board":
      add(cyl(wood, 0.05, 0.9, -0.3), cyl(wood, 0.05, 0.9, 0.3), box(color, 0.75, 0.5, 0.06, 0, 0.6));
      for (let k = 0; k < 4; k++) add(box(["#fff4d6", "#ffe0e8", "#dff1ff", "#e6f7df"][k], 0.16, 0.16, 0.02, -0.22 + k * 0.15, 0.75 - (k % 2) * 0.18, 0.04));
      break;
    case "telescope":
      add(cyl("#5b5f6e", 0.03, 0.6, -0.12, 0, 0.08), cyl("#5b5f6e", 0.03, 0.6, 0.12, 0, 0.08), cyl("#5b5f6e", 0.03, 0.6, 0, 0, -0.14));
      {
        const tube = cyl(color, 0.09, 0.7, 0, 0.55, 0);
        tube.rotation.z = Math.PI / 3;
        add(tube);
      }
      break;
    case "jukebox":
      add(box(color, 0.7, 0.9, 0.5), part(geo.cyl, light, 0.35, 0.5, 0.35, 0, 0.9, 0), box("#fff3c2", 0.45, 0.25, 0.04, 0, 0.45, 0.26));
      add(part(geo.box, "#fff2b3", 0.5, 0.06, 0.05, 0, 0.82, 0.25, toon("#fff2b3", { emissive: "#ffd36b" })));
      break;
    case "string_lights":
      add(cyl("#5c5048", 0.04, 1.3, -0.4), cyl("#5c5048", 0.04, 1.3, 0.4));
      for (let k = 0; k < 7; k++) {
        const t = k / 6;
        add(part(geo.sphere, "#ffe48a", 0.06, 0.06, 0.06, -0.4 + t * 0.8, 1.2 - Math.sin(t * Math.PI) * 0.25, 0, toon(["#ffe48a", "#ff9fc0", "#9fd6ff", color][k % 4], { emissive: "#ffe9a8" })));
      }
      break;
    case "party_table":
      add(box("#fbf3ea", w * 0.9, 0.06, 0.6, 0, 0.5), box(color, w * 0.9, 0.2, 0.62, 0, 0.32), cyl("#f6d2e2", 0.15, 0.16, -0.3, 0.56), cyl("#ffffff", 0.16, 0.04, -0.3, 0.72), ball("#ff6b8b", 0.05, -0.3, 0.8));
      add(cyl(light, 0.05, 0.12, 0.25, 0.56), cyl(dark, 0.05, 0.12, 0.45, 0.56));
      break;
    case "stage":
      add(box(wood, w * 0.95, 0.25, h * 0.95), box(color, w * 0.95, 1.0, 0.08, 0, 0.25, -h * 0.45), box(dark, 0.12, 1.2, 0.12, -w * 0.45, 0.25, -h * 0.4), box(dark, 0.12, 1.2, 0.12, w * 0.45, 0.25, -h * 0.4));
      break;
    case "cannon":
      add(cyl("#4b4f5c", 0.18, 0.12, -0.2, 0.08).rotateZ(Math.PI / 2), cyl("#4b4f5c", 0.18, 0.12, 0.2, 0.08).rotateZ(Math.PI / 2));
      {
        const barrel = cyl(color, 0.16, 0.7, 0, 0.3, 0);
        barrel.rotation.x = -Math.PI / 4;
        add(barrel, ball("#ffd166", 0.05, 0.1, 0.8, 0.3), ball("#ff8fb1", 0.05, -0.1, 0.9, 0.25));
      }
      break;
    case "easel": {
      const legA = box(wood, 0.05, 1.1, 0.05, -0.2, 0, 0.1);
      const legB = box(wood, 0.05, 1.1, 0.05, 0.2, 0, 0.1);
      legA.rotation.z = 0.12;
      legB.rotation.z = -0.12;
      add(legA, legB, box(wood, 0.05, 1.05, 0.05, 0, 0, -0.2), box("#fffaf2", 0.55, 0.42, 0.04, 0, 0.55, 0.13), box(color, 0.3, 0.14, 0.01, 0.02, 0.68, 0.16));
      break;
    }
    case "workbench":
      add(box(wood, w * 0.9, 0.1, 0.6, 0, 0.55), box(dark, 0.1, 0.55, 0.55, -w * 0.4), box(dark, 0.1, 0.55, 0.55, w * 0.4), box(color, 0.3, 0.08, 0.18, -0.3, 0.65), cyl("#8c8f99", 0.03, 0.25, 0.3, 0.65).rotateZ(Math.PI / 2));
      break;
    case "fence":
      for (const x of [-0.38, 0, 0.38]) add(box(color, 0.1, 0.6, 0.1, x), cone(color, 0.07, 0.1, x, 0.6));
      add(box(color, 0.95, 0.07, 0.05, 0, 0.2), box(color, 0.95, 0.07, 0.05, 0, 0.42));
      break;
    case "pottery_wheel":
      add(cyl(dark, 0.28, 0.4), cyl(color, 0.25, 0.04, 0, 0.42), part(geo.sphere, "#c97b55", 0.12, 0.16, 0.12, 0, 0.6, 0));
      break;
    case "sculpture":
      add(box("#ece6dc", 0.55, 0.4, 0.55));
      {
        const knot = part(new THREE.TorusKnotGeometry(0.2, 0.07, 64, 8), color, 1, 1, 1, 0, 0.75, 0);
        add(knot);
      }
      break;
    case "bench":
      add(box(color, w * 0.9, 0.08, 0.42, 0, 0.38), box(color, w * 0.9, 0.3, 0.07, 0, 0.5, -0.2));
      for (const x of [-w * 0.38, w * 0.38]) add(box("#5c5048", 0.08, 0.38, 0.36, x));
      break;
    case "mailbox":
      add(cyl(wood, 0.05, 0.75), part(new THREE.CapsuleGeometry(0.15, 0.2, 6, 12), color, 1, 1, 1, 0, 0.85, 0).rotateX(Math.PI / 2), box("#e8546a", 0.03, 0.18, 0.1, 0.17, 0.85));
      break;
    case "picnic_table":
      add(box(color, w * 0.85, 0.08, 0.8, 0, 0.55), box(dark, w * 0.85, 0.06, 0.3, 0, 0.32, -0.65), box(dark, w * 0.85, 0.06, 0.3, 0, 0.32, 0.65));
      for (const x of [-w * 0.32, w * 0.32]) add(box(wood, 0.08, 0.55, 1.4, x));
      add(box("#ffffff", 0.5, 0.01, 0.5, 0, 0.6), box("#e8546a", 0.25, 0.012, 0.25, 0, 0.61));
      break;
    case "lamp_post":
      add(cyl("#3f4250", 0.06, 1.6), box("#3f4250", 0.3, 0.06, 0.3, 0, 1.6), part(geo.box, "#fff1b8", 0.24, 0.3, 0.24, 0, 1.43, 0, toon("#fff1b8", { emissive: "#ffd77a" })), cone(color, 0.22, 0.18, 0, 1.66));
      break;
    case "fountain":
      add(cyl("#e3ddd2", w * 0.48, 0.35), cyl("#8fd3f0", w * 0.42, 0.02, 0, 0.33), cyl("#e3ddd2", 0.12, 0.85), cyl(color, 0.35, 0.1, 0, 0.85), cyl("#a8e2f7", 0.28, 0.02, 0, 0.94), ball("#c9eefc", 0.1, 0, 1.05));
      break;
    case "gazebo":
      add(cyl("#e9dfcf", w * 0.45, 0.15));
      for (let k = 0; k < 6; k++) {
        const a = (k / 6) * Math.PI * 2;
        add(cyl("#ffffff", 0.06, 1.4, Math.cos(a) * w * 0.38, 0.15, Math.sin(a) * w * 0.38));
      }
      add(cone(color, w * 0.55, 0.8, 0, 1.5), ball(light, 0.1, 0, 2.35));
      break;
    default:
      add(box(color, w * 0.8, 0.5, h * 0.8));
  }
  return g;
}

// ------------------------------------------------------------------ map objects (furniture of the original town)
export function buildMapObject(name: string, w: number, h: number, accent: string): THREE.Group {
  const g = new THREE.Group();
  const n = name.toLowerCase();
  const wood = "#b48a63";
  const add = (...m: THREE.Object3D[]) => g.add(...m);
  const W = Math.max(0.6, w * 0.85);
  const H = Math.max(0.6, h * 0.85);
  if (/\bbed\b/.test(n)) {
    add(box(wood, W, 0.25, H), box("#fbfaf6", W * 0.92, 0.1, H * 0.92, 0, 0.25), box(accent, W * 0.92, 0.06, H * 0.55, 0, 0.33, H * 0.18), box("#ffffff", W * 0.6, 0.1, 0.22, 0, 0.35, -H * 0.32));
  } else if (/refrigerator/.test(n)) {
    add(box("#f4f6f8", 0.7, 1.3, 0.6), box("#cfd6dd", 0.04, 0.3, 0.02, 0.25, 0.75, 0.31));
  } else if (/closet|wardrobe/.test(n)) {
    add(box(wood, Math.min(W, 1), 1.25, 0.5), box(shade(wood, -0.1), 0.02, 1.1, 0.02, 0, 0.08, 0.26));
  } else if (/bookshelf|shelf/.test(n)) {
    add(box(wood, W, 1.2, 0.4));
    for (let k = 0; k < Math.max(3, Math.round(W * 4)); k++) add(box(["#e86f5a", "#4a82dd", "#f0c24c", "#58b368"][k % 4], 0.12, 0.28, 0.3, -W / 2 + 0.1 + k * 0.17, 0.5, 0.02));
  } else if (/cooking|stove|toaster|oven/.test(n)) {
    add(box("#e7e2da", W, 0.75, 0.6), box("#3d3f48", W * 0.9, 0.04, 0.5, 0, 0.75), cyl("#2b2d33", 0.1, 0.02, -0.15, 0.79), cyl("#2b2d33", 0.1, 0.02, 0.15, 0.79));
  } else if (/sink/.test(n)) {
    add(box("#e9edf1", Math.min(W, 0.8), 0.75, 0.55), cyl("#bfe4f2", 0.18, 0.02, 0, 0.75), cyl("#b9c0c8", 0.03, 0.2, 0, 0.75, -0.18));
  } else if (/toilet/.test(n)) {
    add(cyl("#f7f9fb", 0.2, 0.35), box("#f7f9fb", 0.4, 0.45, 0.15, 0, 0.1, -0.2));
  } else if (/shower/.test(n)) {
    add(box("#dff2f8", 0.8, 0.05, 0.8), part(geo.box, "#bde6f5", 0.8, 1.2, 0.8, 0, 0.65, 0, toon("#bde6f5", { transparent: 0.35 })));
  } else if (/sofa|couch/.test(n)) {
    add(box(accent, W, 0.3, 0.7, 0, 0.06), box(shade(accent, -0.15), W, 0.5, 0.18, 0, 0.06, -0.28));
  } else if (/piano/.test(n)) {
    add(box("#2b2a33", 1.1, 0.8, 0.55), box("#ffffff", 1.0, 0.05, 0.18, 0, 0.78, 0.22));
  } else if (/guitar|harp/.test(n)) {
    add(part(geo.sphere, "#c98b4f", 0.2, 0.28, 0.08, 0, 0.35, 0), box("#7a4f2c", 0.06, 0.6, 0.04, 0, 0.45));
  } else if (/microphone/.test(n)) {
    add(cyl("#3f4250", 0.04, 1.1), ball("#5b5f6e", 0.08, 0, 1.15));
  } else if (/easel/.test(n)) {
    add(box(wood, 0.06, 1.1, 0.06, -0.15), box(wood, 0.06, 1.1, 0.06, 0.15), box("#fffaf2", 0.55, 0.42, 0.04, 0, 0.55, 0.06), box(accent, 0.3, 0.12, 0.01, 0, 0.66, 0.09));
  } else if (/blackboard/.test(n)) {
    add(box("#2f5d4a", Math.min(W, 2.2), 0.8, 0.08, 0, 0.4), box(wood, Math.min(W, 2.2), 0.06, 0.12, 0, 0.36));
  } else if (/pool table/.test(n)) {
    add(box("#6b4a2f", W, 0.7, H), box("#2f8a55", W * 0.88, 0.04, H * 0.82, 0, 0.7));
  } else if (/computer|console|television/.test(n)) {
    add(box(wood, 0.7, 0.6, 0.45), box("#2f3140", 0.45, 0.32, 0.05, 0, 0.62), part(geo.box, "#9fd6ff", 0.38, 0.24, 0.01, 0, 0.66, 0.03, toon("#9fd6ff", { emissive: "#7cc4ff" })));
  } else if (/weight/.test(n)) {
    add(box("#3f4250", 0.9, 0.3, 0.35), cyl("#3f4250", 0.18, 0.08, -0.4, 0.45).rotateZ(Math.PI / 2), cyl("#3f4250", 0.18, 0.08, 0.4, 0.45).rotateZ(Math.PI / 2));
  } else if (/seating|table|desk|counter|podium|bar\b/.test(n)) {
    // spread small furniture units over large areas (cafe seating, classroom desks)
    const isCounter = /counter|bar\b|podium/.test(n);
    if (isCounter || w * h <= 4) {
      add(box(isCounter ? accent : wood, W, isCounter ? 0.85 : 0.55, Math.min(H, isCounter ? 0.6 : H), 0, 0), box(shade(isCounter ? accent : wood, 0.1), W, 0.05, Math.min(H, 0.65), 0, isCounter ? 0.85 : 0.55));
    } else {
      for (let x = 0; x < w; x += 2) {
        for (let y = 0; y < h; y += 2) {
          const ox = x - (w - 1) / 2;
          const oz = y - (h - 1) / 2;
          add(cyl(wood, 0.28, 0.05, ox, 0.5, oz), cyl(shade(wood, -0.15), 0.05, 0.5, ox, 0, oz), cyl(accent, 0.13, 0.32, ox + 0.45, 0, oz), cyl(accent, 0.13, 0.32, ox - 0.45, 0, oz));
        }
      }
    }
  } else if (/product|supply|store/.test(n)) {
    add(box(wood, W, 1.0, 0.45));
    for (let k = 0; k < Math.max(3, Math.round(W * 3)); k++) add(box(["#f0c24c", "#e86f5a", "#4a82dd", "#58b368"][k % 4], 0.18, 0.18, 0.18, -W / 2 + 0.15 + k * 0.24, 1.0));
  } else {
    add(box(accent, Math.min(W, 1.2), 0.45, Math.min(H, 1.2)));
  }
  return g;
}

export function buildSparkle(color: string): THREE.Group {
  const g = new THREE.Group();
  const star = new THREE.Mesh(new THREE.OctahedronGeometry(0.22, 0), toon(color, { emissive: color }));
  star.scale.set(0.8, 1.3, 0.8);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.32, 0.03, 6, 24), toon("#ffffff", { emissive: "#ffffff" }));
  ring.rotation.x = Math.PI / 2;
  g.add(star, ring);
  g.position.y = 0.9;
  return g;
}
