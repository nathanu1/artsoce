// Shapes of the `ga play` HTTP API (src/generative_agents/game/api.py).

export type Tile = [number, number];

export interface Theme {
  id: string;
  name: string;
  color: string;
  icon: string;
  description: string;
  keywords: string[];
}

export interface Motif {
  id: string;
  name: string;
  theme: string;
  source: "environment" | "social";
  icon: string;
}

export interface Gift {
  id: string;
  name: string;
  theme: string;
  icon: string;
  cost: number;
}

export interface CatalogItem {
  id: string;
  name: string;
  theme: string;
  category: "furniture" | "decor" | "garden" | "structure";
  footprint: [number, number];
  placement: "indoor" | "outdoor" | "any";
  blocks: boolean;
  cost: Record<string, number>;
  unlock: number;
  shape: string;
}

export interface Paint {
  id: string;
  name: string;
  hex: string;
  theme: string | null;
}

export interface TemplatePart {
  item: string;
  dx: number;
  dy: number;
  rot?: number;
  paint?: string | null;
}

export interface Template {
  id: string;
  name: string;
  unlock?: number;
  parts: TemplatePart[];
}

export interface PulseLevel {
  level: number;
  name: string;
  points: number;
}

export interface Look {
  shirt: string;
  pants: string;
  hair: string;
  hair_style: "short" | "long" | "bun" | "curly" | "bob" | "spiky" | "bald";
  skin: string;
  accessory: "none" | "glasses" | "apron" | "beanie" | "scarf" | "bow" | "headphones" | "cap";
}

export interface Content {
  themes: Theme[];
  motifs: Motif[];
  gifts: Gift[];
  items: CatalogItem[];
  paints: Paint[];
  templates: Template[];
  levels: PulseLevel[];
  points: Record<string, number>;
  friendship: Record<string, number>;
  ground_min_tiles: number;
}

export interface Resident {
  id: string;
  name: string;
  first_name: string;
  age: number;
  innate: string;
  learned: string;
  currently: string;
  lifestyle: string;
  living_area: string;
  loves: string[];
  look: Look;
}

export interface Info {
  run_id: string;
  mode: "mock" | "live" | "replay";
  label: string;
  llm: { kind: string; model: string; local: boolean; describe: Record<string, unknown> };
  embeddings: { kind: string; model: string };
  builder: string;
  start: string;
  end: string;
  seconds_per_step: number;
  speeds: string[];
  residents: Resident[];
  content: Content;
  zones: Record<string, number>;
}

export interface MapPayload {
  world: string;
  width: number;
  height: number;
  legend: { sector: string[]; arena: string[]; object: string[] };
  layers: { collision: [number, number][]; sector: [number, number][]; arena: [number, number][]; object: [number, number][] };
  outdoor_arenas: string[];
  ground_objects: string[];
  objects: string[];
}

export interface AgentFrame {
  x: number | null;
  y: number | null;
  activity: string;
  kind: string;
  address: string | null;
  sleeping: boolean;
  conversation: string | null;
  partner: string | null;
  path_left: number;
}

export interface Frame {
  step: number;
  time: string;
  agents: Record<string, AgentFrame>;
}

export interface PlacedItem {
  id: string;
  catalog_id: string;
  name: string;
  x: number;
  y: number;
  rot: number;
  paint: string | null;
  address: string;
  tiles: Tile[];
  blocks: boolean;
  placed_at: string | null;
  step: number | null;
}

export interface TownRequest {
  id: string;
  agent_id: string;
  wish: string;
  theme: string;
  place_label: string;
  place_address: string;
  outdoor: boolean;
  reason: string;
  request_line: string;
  status: "open" | "ready" | "fulfilled";
  item_id: string | null;
  created_at: string;
  fulfilled_at?: string;
}

export interface Sparkle {
  id: string;
  conversation_id: string;
  participants: string[];
  tile: Tile;
  theme: string;
  motif: string;
  appears_at: string;
  expires_at: string;
}

export interface GameState {
  pulse: { points: number; level: number; name: string; next_at: number | null; next_name: string | null };
  inventory: Record<string, number>;
  found: Record<string, string>;
  theme_counts: Record<string, number>;
  friendship: Record<string, number>;
  residents: Record<string, { loves: string[] }>;
  requests: TownRequest[];
  items: PlacedItem[];
  sparkles: Sparkle[];
  cooldowns: Record<string, string>;
  user_templates: Template[];
  stats: Record<string, number>;
  applied_seq: number;
}

export interface ScheduleBlock {
  start: string;
  minutes: number;
  description: string;
}

export interface Schedule {
  day: string;
  blocks: ScheduleBlock[];
  task: ScheduleBlock | null;
}

export interface ConversationLine {
  speaker: string;
  text: string;
}

export interface FeedEvent {
  seq: number;
  kind: string;
  agent_id?: string | null;
  sim_time?: string;
  action_seq?: number | null;
  [key: string]: unknown;
}

export interface Poll {
  epoch: number;
  status: string;
  paused: boolean;
  speed: string;
  replay: boolean;
  error: string | null;
  thinking: Record<string, { task: string; since: number }>;
  clock: { step: number; time: string; end: string } | null;
  frames: Frame[];
  feed: FeedEvent[];
  feed_seq: number;
  game: GameState | null;
  schedules: Record<string, Schedule> | null;
  objects: Record<string, { lasting?: string; in_use?: string | null; in_use_by?: string | null }> | null;
  ledger: { calls: number; input_tokens: number; output_tokens: number } | null;
}

export interface BuildOp {
  op: "place" | "move" | "paint" | "remove";
  catalog_id?: string;
  item_id?: string;
  x?: number;
  y?: number;
  rot?: number;
  paint?: string | null;
}

export interface BuildVerdict {
  ok: boolean;
  reasons: string[];
  tiles: Tile[];
  arena: string | null;
  outdoor: boolean | null;
}

export interface BuildCheck {
  ok: boolean;
  problems: string[];
  verdicts: BuildVerdict[];
  cost: Record<string, number>;
  refund: Record<string, number>;
  feedback: { theme: string; arena: string | null; room_theme?: string | null; harmony?: boolean; loved_by?: string[]; fulfils?: string[] }[];
}

export interface ResidentDetail {
  id: string;
  exchanges: { id: number; time: string; kind: string; builder_line?: string; reply?: string; mood?: string; reason?: string; gift?: string; loved?: boolean }[];
  conversations: { id: string; started_at: string; participants: string[]; summary: string | null; lines: ConversationLine[] }[];
}
