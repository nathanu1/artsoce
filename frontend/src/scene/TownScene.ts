import * as THREE from "three";
import type { ShownItem } from "../lib/build";
import { addressAt, KIND, tileHash, type TownMap } from "../lib/map";
import type { CatalogItem, Frame, Info, Sparkle, Tile } from "../types";
import { buildItem, buildMapObject, buildResident, buildSparkle, glowMaterials, instanceToon, shade, toon, vertexToon, type Figure } from "./meshes";

export type ScenePick =
  | { kind: "resident"; id: string }
  | { kind: "item"; key: string }
  | { kind: "object"; address: string }
  | { kind: "sparkle"; id: string }
  | { kind: "tile"; tile: Tile }
  | null;

export interface OverlayPoint {
  x: number;
  y: number;
  visible: boolean;
}

export interface OverlayLabel {
  key: string;
  text: string;
  x: number;
  y: number;
}

export interface GhostPart {
  catalogId: string;
  x: number;
  y: number;
  rot: number;
  paint: string | null;
  ok: boolean;
}

const COLORS = {
  grass: ["#a3d672", "#97cd66", "#aedc7e"],
  road: ["#ecdcb9", "#e4d1aa"],
  plaza: ["#efe8dc", "#e2d9ca"],
  lawn: ["#abdc80", "#9fd473"],
  soil: "#b48a62",
  bath: ["#e0f1f7", "#cfe6ef"],
  floors: ["#e9cb9e", "#eec4bd", "#c9e5d2", "#c6dcf2", "#dccfee", "#f1e0a8", "#e8d3be", "#d3e8b8"],
  walls: ["#fff4e8", "#fdeef2", "#eef8f1", "#edf4fd", "#f4effc", "#fff8e2"],
  trims: ["#f0a47a", "#e888a3", "#78c495", "#7aa9e0", "#b298e0", "#e6c05c", "#d69c77", "#98c86a"],
  leaves: ["#5db45e", "#4fa654", "#6cc064", "#7bc96c"],
  flowers: ["#ff8fb1", "#ffd166", "#ffffff", "#c49cf2", "#ff9f6e"],
};

interface ResidentRig {
  fig: Figure;
  target: THREE.Vector3;
  facing: number;
  moving: number;
  sleeping: boolean;
  partner: string | null;
  phase: number;
}

export class TownScene {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly camera: THREE.OrthographicCamera;
  private map: TownMap;
  private info: Info;
  private catalog: Map<string, CatalogItem>;
  private reduced: boolean;
  private raf = 0;
  private timer = new THREE.Timer();
  private target = new THREE.Vector3();
  private targetGoal = new THREE.Vector3();
  private azimuth = 0;
  private azimuthGoal = 0;
  private zoomGoal = 1.4;
  private follow: string | null = null;
  private residents = new Map<string, ResidentRig>();
  private items = new Map<string, { group: THREE.Group; sig: string }>();
  private sparkles = new Map<string, THREE.Group>();
  private objects: THREE.Group[] = [];
  private ghost = new THREE.Group();
  private marks = new THREE.Group();
  private selectRing: THREE.Mesh;
  private selected: string | null = null;
  private sun: THREE.DirectionalLight;
  private hemi: THREE.HemisphereLight;
  private floorMat: THREE.MeshToonMaterial;
  private raycaster = new THREE.Raycaster();
  private ground = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  private labels: { key: string; text: string; pos: THREE.Vector3 }[] = [];
  private onFrame: (pts: Record<string, OverlayPoint>, labels: OverlayLabel[]) => void;
  private size = { w: 1, h: 1 };
  private daylight = 1;

  constructor(canvas: HTMLCanvasElement, map: TownMap, info: Info, opts: { reducedMotion: boolean; onFrame: TownScene["onFrame"] }) {
    this.map = map;
    this.info = info;
    this.catalog = new Map(info.content.items.map((i) => [i.id, i]));
    this.reduced = opts.reducedMotion;
    this.onFrame = opts.onFrame;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.camera = new THREE.OrthographicCamera(-10, 10, 10, -10, -200, 400);
    this.camera.zoom = this.zoomGoal;

    this.hemi = new THREE.HemisphereLight("#dff2ff", "#8fb26a", 1.6);
    this.scene.add(this.hemi, new THREE.AmbientLight("#ffffff", 0.35));
    this.sun = new THREE.DirectionalLight("#fff3dc", 2.4);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    const sc = this.sun.shadow.camera;
    sc.left = -26;
    sc.right = 26;
    sc.top = 26;
    sc.bottom = -26;
    sc.near = 1;
    sc.far = 120;
    this.sun.shadow.bias = -0.0006;
    this.sun.shadow.normalBias = 0.03;
    this.scene.add(this.sun, this.sun.target);

    this.floorMat = new THREE.MeshToonMaterial({ vertexColors: true, gradientMap: (vertexToon as THREE.MeshToonMaterial).gradientMap });
    this.floorMat.emissive = new THREE.Color("#ffcf87");
    this.floorMat.emissiveIntensity = 0;

    this.buildBase();
    this.buildGround();
    this.buildWallsAndNature();
    this.buildFlowers();
    this.buildObjects();
    this.buildLabels();

    this.selectRing = new THREE.Mesh(new THREE.RingGeometry(0.42, 0.56, 40), new THREE.MeshBasicMaterial({ color: "#f2792b", transparent: true, opacity: 0.9 }));
    this.selectRing.rotation.x = -Math.PI / 2;
    this.selectRing.position.y = 0.03;
    this.selectRing.visible = false;
    this.scene.add(this.selectRing, this.ghost, this.marks);

    for (const r of info.residents) {
      const fig = buildResident(r.look, r.id);
      fig.root.visible = false;
      this.scene.add(fig.root);
      this.residents.set(r.id, { fig, target: new THREE.Vector3(), facing: 0, moving: 0, sleeping: false, partner: null, phase: Math.random() * 6 });
    }
    const start = map.buildings.get(map.plazaSector) ?? [...map.buildings.values()][0];
    if (start) this.targetGoal.set((start.x0 + start.x1) / 2 + 0.5, 0, (start.y0 + start.y1) / 2 + 0.5);
    this.target.copy(this.targetGoal);
    this.setHour(9);
    this.loop = this.loop.bind(this);
    this.raf = requestAnimationFrame(this.loop);
  }

  // ================================================================== build the town
  private buildBase() {
    const { width: W, height: H } = this.map;
    const slab = new THREE.Mesh(new THREE.BoxGeometry(W + 2, 3, H + 2), [
      toon("#9b7452"),
      toon("#9b7452"),
      toon("#a6dc7a"),
      toon("#6f5038"),
      toon("#8e6a4a"),
      toon("#8e6a4a"),
    ]);
    slab.position.set(W / 2, -1.53, H / 2);
    slab.receiveShadow = true;
    this.scene.add(slab);
  }

  private floorColor(sector: number): string {
    return COLORS.floors[sector % COLORS.floors.length];
  }

  private buildGround() {
    const m = this.map;
    const out: number[] = [];
    const outC: number[] = [];
    const ins: number[] = [];
    const insC: number[] = [];
    const c = new THREE.Color();
    for (let y = 0; y < m.height; y++) {
      for (let x = 0; x < m.width; x++) {
        const i = y * m.width + x;
        const k = m.kind[i];
        const h = tileHash(x, y);
        const checker = (x + y) % 2;
        let hex: string;
        let indoor = false;
        switch (k) {
          case KIND.ROAD:
            hex = COLORS.road[h > 0.5 ? 0 : 1];
            break;
          case KIND.PLAZA:
            hex = COLORS.plaza[checker];
            break;
          case KIND.LAWN:
            hex = COLORS.lawn[h > 0.5 ? 0 : 1];
            break;
          case KIND.BED:
            hex = COLORS.soil;
            break;
          case KIND.BATH:
            hex = COLORS.bath[checker];
            indoor = true;
            break;
          case KIND.FLOOR:
          case KIND.WALL:
            hex = this.floorColor(m.sector[i]);
            indoor = true;
            break;
          default:
            hex = COLORS.grass[h < 0.45 ? 0 : h < 0.9 ? 1 : 2];
        }
        c.set(hex);
        if (k === KIND.FLOOR) c.offsetHSL(0, 0, checker ? 0.025 : -0.01);
        c.offsetHSL(0, 0, (tileHash(x, y, 7) - 0.5) * 0.03);
        const pos = indoor ? ins : out;
        const col = indoor ? insC : outC;
        pos.push(x, 0, y, x, 0, y + 1, x + 1, 0, y, x + 1, 0, y, x, 0, y + 1, x + 1, 0, y + 1);
        for (let v = 0; v < 6; v++) col.push(c.r, c.g, c.b);
      }
    }
    const mk = (pos: number[], col: number[], mat: THREE.Material) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
      g.computeVertexNormals();
      const mesh = new THREE.Mesh(g, mat);
      mesh.receiveShadow = true;
      this.scene.add(mesh);
    };
    mk(out, outC, vertexToon);
    mk(ins, insC, this.floorMat);
  }

  private buildWallsAndNature() {
    const m = this.map;
    const walls: number[] = [];
    const nature: number[] = [];
    for (let i = 0; i < m.width * m.height; i++) {
      if (m.kind[i] === KIND.WALL) walls.push(i);
      else if (m.kind[i] === KIND.NATURE) nature.push(i);
    }
    const mat4 = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const s = new THREE.Vector3();
    const p = new THREE.Vector3();
    const col = new THREE.Color();
    const wallH = 0.62;
    const wallMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, wallH, 1), instanceToon(), walls.length);
    const trimMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1.04, 0.12, 1.04), instanceToon(), walls.length);
    walls.forEach((i, n) => {
      const x = i % m.width;
      const y = (i / m.width) | 0;
      const sec = m.sector[i];
      mat4.compose(p.set(x + 0.5, wallH / 2, y + 0.5), q, s.set(1, 1, 1));
      wallMesh.setMatrixAt(n, mat4);
      wallMesh.setColorAt(n, col.set(COLORS.walls[sec % COLORS.walls.length]));
      mat4.compose(p.set(x + 0.5, wallH + 0.06, y + 0.5), q, s.set(1, 1, 1));
      trimMesh.setMatrixAt(n, mat4);
      trimMesh.setColorAt(n, col.set(COLORS.trims[sec % COLORS.trims.length]));
    });
    for (const im of [wallMesh, trimMesh]) {
      im.castShadow = true;
      im.receiveShadow = true;
      this.scene.add(im);
    }
    // nature: lollipop trees, bushes and rocks on the obstacles outside buildings
    const trees = nature.filter((i) => tileHash(i % m.width, (i / m.width) | 0, 3) < 0.55);
    const bushes = nature.filter((i) => {
      const h = tileHash(i % m.width, (i / m.width) | 0, 3);
      return h >= 0.55 && h < 0.92;
    });
    const rocks = nature.filter((i) => tileHash(i % m.width, (i / m.width) | 0, 3) >= 0.92);
    const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.09, 0.12, 0.55, 8), instanceToon(), trees.length);
    const canopy = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(0.46, 1), instanceToon(), trees.length);
    const bush = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(0.34, 1), instanceToon(), bushes.length);
    const rock = new THREE.InstancedMesh(new THREE.DodecahedronGeometry(0.28, 0), instanceToon(), rocks.length);
    trees.forEach((i, n) => {
      const x = i % m.width;
      const y = (i / m.width) | 0;
      const sc = 0.85 + tileHash(x, y, 4) * 0.4;
      mat4.compose(p.set(x + 0.5, 0.27, y + 0.5), q, s.set(1, 1, 1));
      trunk.setMatrixAt(n, mat4);
      trunk.setColorAt(n, col.set("#8a5a3c"));
      mat4.compose(p.set(x + 0.5, 0.78 * sc + 0.1, y + 0.5), q, s.set(sc, sc * 1.05, sc));
      canopy.setMatrixAt(n, mat4);
      canopy.setColorAt(n, col.set(COLORS.leaves[Math.floor(tileHash(x, y, 5) * COLORS.leaves.length)]));
    });
    bushes.forEach((i, n) => {
      const x = i % m.width;
      const y = (i / m.width) | 0;
      const sc = 0.9 + tileHash(x, y, 6) * 0.35;
      mat4.compose(p.set(x + 0.5, 0.26 * sc, y + 0.5), q, s.set(sc * 1.2, sc, sc * 1.2));
      bush.setMatrixAt(n, mat4);
      bush.setColorAt(n, col.set(COLORS.leaves[Math.floor(tileHash(x, y, 8) * COLORS.leaves.length)]).offsetHSL(0, 0, -0.04));
    });
    rocks.forEach((i, n) => {
      const x = i % m.width;
      const y = (i / m.width) | 0;
      mat4.compose(p.set(x + 0.5, 0.12, y + 0.5), q.setFromEuler(new THREE.Euler(0, tileHash(x, y, 9) * 3, 0)), s.set(1.1, 0.6, 1));
      rock.setMatrixAt(n, mat4);
      rock.setColorAt(n, col.set("#bdb6aa"));
    });
    q.identity();
    for (const im of [trunk, canopy, bush, rock]) {
      im.castShadow = true;
      im.receiveShadow = true;
      this.scene.add(im);
    }
  }

  private buildFlowers() {
    const m = this.map;
    const beds: number[] = [];
    for (let i = 0; i < m.width * m.height; i++) if (m.kind[i] === KIND.BED) beds.push(i);
    const per = 3;
    const heads = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(0.09, 0), instanceToon(), beds.length * per);
    const leaves = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(0.16, 0), instanceToon(), beds.length);
    const mat4 = new THREE.Matrix4();
    const col = new THREE.Color();
    beds.forEach((i, n) => {
      const x = i % m.width;
      const y = (i / m.width) | 0;
      leaves.setMatrixAt(n, mat4.makeTranslation(x + 0.5, 0.1, y + 0.5));
      leaves.setColorAt(n, col.set("#5aa857"));
      for (let k = 0; k < per; k++) {
        const ox = (tileHash(x, y, 20 + k) - 0.5) * 0.7;
        const oz = (tileHash(x, y, 30 + k) - 0.5) * 0.7;
        heads.setMatrixAt(n * per + k, mat4.makeTranslation(x + 0.5 + ox, 0.22, y + 0.5 + oz));
        heads.setColorAt(n * per + k, col.set(COLORS.flowers[Math.floor(tileHash(x, y, 40 + k) * COLORS.flowers.length)]));
      }
    });
    this.scene.add(leaves, heads);
  }

  private buildObjects() {
    const m = this.map;
    for (const [address, tiles] of m.objects) {
      if (m.groundObjects.has(address)) continue;
      const xs = tiles.map((t) => t[0]);
      const ys = tiles.map((t) => t[1]);
      const x0 = Math.min(...xs);
      const x1 = Math.max(...xs);
      const y0 = Math.min(...ys);
      const y1 = Math.max(...ys);
      const name = address.split(":").pop() ?? "";
      const sector = m.sector[y0 * m.width + x0];
      const g = buildMapObject(name, x1 - x0 + 1, y1 - y0 + 1, COLORS.trims[(sector + 3) % COLORS.trims.length]);
      g.position.set((x0 + x1 + 1) / 2, 0, (y0 + y1 + 1) / 2);
      g.userData.address = address;
      this.objects.push(g);
      this.scene.add(g);
    }
  }

  private buildLabels() {
    for (const b of this.map.buildings.values()) {
      if (b.tiles < 30) continue;
      const tile = b.entrance ?? [Math.round((b.x0 + b.x1) / 2), b.y1];
      this.labels.push({ key: `b${b.index}`, text: b.name, pos: new THREE.Vector3(tile[0] + 0.5, 1.3, tile[1] + 0.5) });
    }
  }

  // ================================================================== updates from the game
  updateFrame(frame: Frame | null) {
    if (!frame) return;
    for (const [id, a] of Object.entries(frame.agents)) {
      const rig = this.residents.get(id);
      if (!rig) continue;
      if (a.x === null || a.y === null) {
        rig.fig.root.visible = false;
        continue;
      }
      const wasHidden = !rig.fig.root.visible;
      rig.target.set(a.x + 0.5, 0, a.y + 0.5);
      if (wasHidden || this.reduced) rig.fig.root.position.copy(rig.target);
      rig.fig.root.visible = true;
      rig.sleeping = a.sleeping;
      rig.partner = a.partner ? (this.info.residents.find((r) => r.name === a.partner)?.id ?? null) : null;
    }
  }

  setItems(items: ShownItem[], paints: Map<string, string>) {
    const seen = new Set<string>();
    for (const it of items) {
      const cat = this.catalog.get(it.catalog_id);
      if (!cat) continue;
      seen.add(it.key);
      const color = (it.paint && paints.get(it.paint)) || paints.get(`theme:${cat.theme}`) || "#e9c46a";
      const sig = `${it.catalog_id}|${it.x}|${it.y}|${it.rot}|${color}|${it.draft}`;
      const cur = this.items.get(it.key);
      if (cur && cur.sig === sig) continue;
      if (cur) this.scene.remove(cur.group);
      const [w, h] = cat.footprint;
      const g = new THREE.Group();
      const body = buildItem(cat.shape, w, h, color);
      body.rotation.y = -(it.rot % 4) * (Math.PI / 2);
      g.add(body);
      const [rw, rh] = it.rot % 2 ? [h, w] : [w, h];
      g.position.set(it.x + rw / 2, 0, it.y + rh / 2);
      if (it.draft) {
        const mark = new THREE.Mesh(draftRing(Math.max(rw, rh)), flat("#ffffff", 0.85));
        mark.rotation.x = -Math.PI / 2;
        mark.rotation.z = Math.PI / 4;
        mark.position.y = 0.02;
        g.add(mark);
      }
      g.userData.itemKey = it.key;
      this.items.set(it.key, { group: g, sig });
      this.scene.add(g);
    }
    for (const [key, cur] of this.items) {
      if (!seen.has(key)) {
        this.scene.remove(cur.group);
        this.items.delete(key);
      }
    }
  }

  setSparkles(list: Sparkle[], themeColor: (t: string) => string) {
    const seen = new Set(list.map((s) => s.id));
    for (const s of list) {
      if (this.sparkles.has(s.id) || !s.tile) continue;
      const g = buildSparkle(themeColor(s.theme));
      g.position.set(s.tile[0] + 0.5, 0.9, s.tile[1] + 0.5);
      g.userData.sparkle = s.id;
      this.sparkles.set(s.id, g);
      this.scene.add(g);
    }
    for (const [id, g] of this.sparkles) {
      if (!seen.has(id)) {
        this.scene.remove(g);
        this.sparkles.delete(id);
      }
    }
  }

  setGhost(parts: GhostPart[], paints: Map<string, string>, marked: Tile[] = []) {
    this.ghost.clear();
    this.marks.clear();
    for (const [x, y] of marked) this.marks.add(tileMark(x, y, "#f2792b", 0.5));
    for (const part of parts) {
      const cat = this.catalog.get(part.catalogId);
      if (!cat) continue;
      const [w, h] = cat.footprint;
      const [rw, rh] = part.rot % 2 ? [h, w] : [w, h];
      const color = (part.paint && paints.get(part.paint)) || paints.get(`theme:${cat.theme}`) || "#e9c46a";
      const body = buildItem(cat.shape, w, h, color);
      body.rotation.y = -(part.rot % 4) * (Math.PI / 2);
      const tint = part.ok ? "#6fd38a" : "#f06a6a";
      const ghostMat = toon(tint, { transparent: 0.55 });
      body.traverse((o) => {
        if ((o as THREE.Mesh).isMesh) {
          (o as THREE.Mesh).material = ghostMat;
          o.castShadow = false;
        }
      });
      const g = new THREE.Group();
      g.add(body);
      g.position.set(part.x + rw / 2, 0, part.y + rh / 2);
      this.ghost.add(g);
      for (let dy = 0; dy < rh; dy++) {
        for (let dx = 0; dx < rw; dx++) this.marks.add(tileMark(part.x + dx, part.y + dy, tint, 0.45));
      }
    }
  }

  select(id: string | null) {
    this.selected = id;
    this.selectRing.visible = !!id;
  }

  setFollow(id: string | null) {
    this.follow = id;
  }

  // ================================================================== camera
  focus(tile: Tile) {
    this.targetGoal.set(tile[0] + 0.5, 0, tile[1] + 0.5);
    this.follow = null;
    if (this.reduced) this.target.copy(this.targetGoal);
  }

  /** The tile at the middle of the view. */
  viewCenter(): Tile {
    return [Math.floor(this.target.x), Math.floor(this.target.z)];
  }

  rotate(dir: 1 | -1) {
    this.azimuthGoal += dir;
    if (this.reduced) this.azimuth = this.azimuthGoal;
  }

  zoomBy(f: number) {
    this.zoomGoal = THREE.MathUtils.clamp(this.zoomGoal * f, 0.32, 3.2);
    if (this.reduced) this.camera.zoom = this.zoomGoal;
  }

  get zoom() {
    return this.zoomGoal;
  }

  /** Move the view by screen pixels. */
  panPixels(dx: number, dy: number) {
    const a = this.tileAt(this.size.w / 2, this.size.h / 2, true);
    const b = this.tileAt(this.size.w / 2 - dx, this.size.h / 2 - dy, true);
    if (!a || !b) return;
    this.targetGoal.x = THREE.MathUtils.clamp(this.targetGoal.x + (b[0] - a[0]), 0, this.map.width);
    this.targetGoal.z = THREE.MathUtils.clamp(this.targetGoal.z + (b[1] - a[1]), 0, this.map.height);
    this.follow = null;
    if (this.reduced) this.target.copy(this.targetGoal);
  }

  private viewDir(): THREE.Vector3 {
    const a = Math.PI / 4 + this.azimuth * (Math.PI / 2);
    const el = THREE.MathUtils.degToRad(38);
    return new THREE.Vector3(Math.sin(a) * Math.cos(el), Math.sin(el), Math.cos(a) * Math.cos(el));
  }

  resize(w: number, h: number) {
    this.size = { w: Math.max(1, w), h: Math.max(1, h) };
    this.renderer.setSize(this.size.w, this.size.h, false);
    const half = 12;
    const aspect = this.size.w / this.size.h;
    this.camera.left = -half * aspect;
    this.camera.right = half * aspect;
    this.camera.top = half;
    this.camera.bottom = -half;
    this.camera.updateProjectionMatrix();
  }

  // ================================================================== picking
  private ndc(x: number, y: number) {
    return new THREE.Vector2((x / this.size.w) * 2 - 1, -(y / this.size.h) * 2 + 1);
  }

  tileAt(x: number, y: number, unclamped = false): Tile | null {
    this.raycaster.setFromCamera(this.ndc(x, y), this.camera);
    const hit = new THREE.Vector3();
    if (!this.raycaster.ray.intersectPlane(this.ground, hit)) return null;
    const t: Tile = [Math.floor(hit.x), Math.floor(hit.z)];
    if (unclamped) return [hit.x, hit.z];
    if (t[0] < 0 || t[1] < 0 || t[0] >= this.map.width || t[1] >= this.map.height) return null;
    return t;
  }

  pick(x: number, y: number, opts: { residents?: boolean; things?: boolean } = {}): ScenePick {
    this.raycaster.setFromCamera(this.ndc(x, y), this.camera);
    const targets: THREE.Object3D[] = [];
    if (opts.residents !== false) for (const r of this.residents.values()) if (r.fig.root.visible) targets.push(r.fig.hit);
    if (opts.things !== false) {
      targets.push(...this.sparkles.values());
      for (const it of this.items.values()) targets.push(it.group);
      targets.push(...this.objects);
    }
    for (const hit of this.raycaster.intersectObjects(targets, true)) {
      let o: THREE.Object3D | null = hit.object;
      while (o) {
        if (o.userData.resident) return { kind: "resident", id: o.userData.resident };
        if (o.userData.sparkle) return { kind: "sparkle", id: o.userData.sparkle };
        if (o.userData.itemKey) return { kind: "item", key: o.userData.itemKey };
        if (o.userData.address) return { kind: "object", address: o.userData.address };
        o = o.parent;
      }
    }
    const t = this.tileAt(x, y);
    return t ? { kind: "tile", tile: t } : null;
  }

  addressOf(tile: Tile): string | null {
    return addressAt(this.map, tile[0], tile[1]);
  }

  // ================================================================== time of day
  setHour(hour: number) {
    const day = Math.max(0, Math.min(1, Math.sin(((hour - 6) / 13) * Math.PI)));
    this.daylight = day;
    const warm = Math.max(0, 1 - Math.abs(hour - 7) / 1.6) + Math.max(0, 1 - Math.abs(hour - 18.5) / 1.6);
    const sunColor = new THREE.Color("#fff3dc").lerp(new THREE.Color("#ffb37a"), Math.min(1, warm));
    const night = new THREE.Color("#8ea6ff");
    this.sun.color.copy(day > 0.05 ? sunColor : night);
    this.sun.intensity = 0.55 + 2.2 * day;
    this.hemi.color.copy(new THREE.Color("#33457a").lerp(new THREE.Color("#e2f3ff"), day));
    this.hemi.groundColor.copy(new THREE.Color("#2b3348").lerp(new THREE.Color("#93b56c"), day));
    this.hemi.intensity = 1.0 + 0.7 * day;
    this.floorMat.emissiveIntensity = day < 0.25 ? 0.28 * (1 - day / 0.25) : 0;
    for (const m of glowMaterials()) m.emissiveIntensity = day < 0.3 ? 1.1 : 0.15;
  }

  // ================================================================== frame loop
  private loop(now?: number) {
    this.raf = requestAnimationFrame(this.loop);
    this.timer.update(now);
    const dt = Math.min(0.1, this.timer.getDelta());
    const t = this.timer.getElapsed();
    const k = this.reduced ? 1 : 1 - Math.exp(-dt * 7);
    // residents
    for (const [id, r] of this.residents) {
      const root = r.fig.root;
      if (!root.visible) continue;
      const dx = r.target.x - root.position.x;
      const dz = r.target.z - root.position.z;
      const dist = Math.hypot(dx, dz);
      if (dist > 6) root.position.copy(r.target);
      else if (!this.reduced) root.position.lerp(r.target, 1 - Math.exp(-dt * 10));
      else root.position.copy(r.target);
      r.moving = THREE.MathUtils.lerp(r.moving, dist > 0.05 ? 1 : 0, 1 - Math.exp(-dt * 12));
      let face = r.facing;
      if (dist > 0.05) face = Math.atan2(dx, dz);
      else if (r.partner) {
        const p = this.residents.get(r.partner);
        if (p) face = Math.atan2(p.fig.root.position.x - root.position.x, p.fig.root.position.z - root.position.z);
      }
      let diff = face - r.facing;
      diff = Math.atan2(Math.sin(diff), Math.cos(diff));
      r.facing += this.reduced ? diff : diff * (1 - Math.exp(-dt * 10));
      root.rotation.y = r.facing;
      if (!this.reduced) {
        r.phase += dt * (6 + 6 * r.moving);
        const swing = Math.sin(r.phase) * 0.6 * r.moving;
        r.fig.legL.rotation.x = swing;
        r.fig.legR.rotation.x = -swing;
        r.fig.body.position.y = Math.abs(Math.sin(r.phase)) * 0.06 * r.moving + (r.sleeping ? 0 : Math.sin(t * 2 + r.phase) * 0.008);
        r.fig.head.rotation.x = r.sleeping ? 0.35 : Math.sin(t * 1.3 + r.phase) * 0.04;
        r.fig.head.rotation.z = r.partner ? Math.sin(t * 3 + r.phase) * 0.06 : 0;
      }
      if (id === this.selected) {
        this.selectRing.position.x = root.position.x;
        this.selectRing.position.z = root.position.z;
        this.selectRing.rotation.z += dt * 0.8;
      }
    }
    if (this.follow) {
      const r = this.residents.get(this.follow);
      if (r) this.targetGoal.copy(r.fig.root.position);
    }
    // sparkles
    for (const g of this.sparkles.values()) {
      g.rotation.y += this.reduced ? 0 : dt * 1.6;
      g.position.y = 0.9 + (this.reduced ? 0 : Math.sin(t * 2.4 + g.position.x) * 0.1);
    }
    // camera
    this.target.lerp(this.targetGoal, k);
    this.azimuth += (this.azimuthGoal - this.azimuth) * k;
    this.camera.zoom += (this.zoomGoal - this.camera.zoom) * k;
    this.camera.updateProjectionMatrix();
    const dir = this.viewDir();
    this.camera.position.copy(this.target).addScaledVector(dir, 80);
    this.camera.lookAt(this.target);
    this.sun.position.copy(this.target).add(new THREE.Vector3(-18, 34, 14));
    this.sun.target.position.copy(this.target);
    this.renderer.render(this.scene, this.camera);
    this.emitOverlay();
  }

  private project(v: THREE.Vector3): OverlayPoint {
    const p = v.clone().project(this.camera);
    return { x: ((p.x + 1) / 2) * this.size.w, y: ((1 - p.y) / 2) * this.size.h, visible: p.z < 1 && Math.abs(p.x) < 1.15 && Math.abs(p.y) < 1.15 };
  }

  private emitOverlay() {
    const pts: Record<string, OverlayPoint> = {};
    const head = new THREE.Vector3();
    for (const [id, r] of this.residents) {
      if (!r.fig.root.visible) {
        pts[id] = { x: 0, y: 0, visible: false };
        continue;
      }
      head.copy(r.fig.root.position);
      head.y = 1.62;
      pts[id] = this.project(head);
    }
    const labels: OverlayLabel[] = [];
    if (this.camera.zoom > 0.9) {
      for (const l of this.labels) {
        const p = this.project(l.pos);
        if (p.visible) labels.push({ key: l.key, text: l.text, x: p.x, y: p.y });
      }
    }
    this.onFrame(pts, labels);
  }

  /** Screen position of a tile's center (used by tests and tooltips). */
  projectTile(x: number, y: number): OverlayPoint {
    return this.project(new THREE.Vector3(x + 0.5, 0, y + 0.5));
  }

  residentPosition(id: string): Tile | null {
    const r = this.residents.get(id);
    return r && r.fig.root.visible ? [Math.floor(r.target.x), Math.floor(r.target.z)] : null;
  }

  get isNight() {
    return this.daylight < 0.25;
  }

  dispose() {
    cancelAnimationFrame(this.raf);
    this.renderer.dispose();
    this.scene.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.geometry) m.geometry.dispose();
    });
  }
}

// shared flat materials and geometry for tile marks, so hovering never allocates GPU resources
const flats = new Map<string, THREE.MeshBasicMaterial>();
function flat(color: string, opacity: number): THREE.MeshBasicMaterial {
  const key = `${color}|${opacity}`;
  let m = flats.get(key);
  if (!m) {
    m = new THREE.MeshBasicMaterial({ color, transparent: true, opacity, depthWrite: false });
    flats.set(key, m);
  }
  return m;
}
const tilePlane = new THREE.PlaneGeometry(0.94, 0.94);
function tileMark(x: number, y: number, color: string, opacity: number): THREE.Mesh {
  const q = new THREE.Mesh(tilePlane, flat(color, opacity));
  q.rotation.x = -Math.PI / 2;
  q.position.set(x + 0.5, 0.025, y + 0.5);
  return q;
}
const rings = new Map<number, THREE.RingGeometry>();
function draftRing(size: number): THREE.RingGeometry {
  let g = rings.get(size);
  if (!g) {
    g = new THREE.RingGeometry(0.5 * size - 0.08, 0.5 * size, 4, 1);
    rings.set(size, g);
  }
  return g;
}

export function themePaints(info: Info): Map<string, string> {
  const paints = new Map<string, string>();
  for (const p of info.content.paints) {
    paints.set(p.id, p.hex);
    if (p.theme && !paints.has(`theme:${p.theme}`)) paints.set(`theme:${p.theme}`, p.hex);
  }
  for (const t of info.content.themes) if (!paints.has(`theme:${t.id}`)) paints.set(`theme:${t.id}`, shade(t.color, 0.12));
  return paints;
}
