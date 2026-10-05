import { create } from "zustand";
import { emptyDraft, type Draft } from "./lib/build";
import type { TownMap } from "./lib/map";
import type { BuildCheck, ConversationLine, FeedEvent, Frame, Info, Poll, Tile } from "./types";
import { sentence } from "./lib/text";

export type Selection = { kind: "resident"; id: string } | { kind: "object"; address: string } | { kind: "item"; id: string } | null;
export type NotebookTab = "requests" | "collections" | "residents" | "town";
export type BuildTool = "select" | "place" | "template";

export interface Toast {
  id: number;
  tone: "info" | "good" | "warn" | "level";
  title: string;
  body?: string;
  theme?: string;
  until: number; // Date.now() when it hides by itself (paused while hovered or focused)
}

export interface Bubble {
  text: string;
  mood?: string;
  until: number;
}

export interface ConversationShown {
  id: string;
  participants: string[];
  lines: ConversationLine[];
  startedAt: string;
  endedAt: string;
}

interface TownState {
  info: Info | null;
  map: TownMap | null;
  bootError: string | null;
  poll: Poll | null;
  frame: Frame | null;
  epoch: number;
  sinceStep: number;
  sinceFeed: number;
  feed: FeedEvent[];
  conversations: ConversationShown[];
  bubbles: Record<string, Bubble>;
  pending: Record<number, { kind: string; agent?: string }>;
  selection: Selection;
  mode: "play" | "build";
  notebook: { open: boolean; tab: NotebookTab };
  chatWith: string | null;
  toasts: Toast[];
  focus: { tile: Tile; at: number } | null;
  follow: string | null;
  look: boolean; // the "Look Around" list of nearby things
  // build mode
  draft: Draft;
  tool: BuildTool;
  catalogId: string | null;
  templateId: string | null;
  rot: number;
  paint: string | null;
  hover: Tile | null;
  check: BuildCheck | null;
  picked: string | null;

  boot: (info: Info, map: TownMap) => void;
  bootFailed: (msg: string) => void;
  ingest: (p: Poll) => void;
  select: (s: Selection) => void;
  setMode: (m: "play" | "build") => void;
  openNotebook: (tab?: NotebookTab) => void;
  closeNotebook: () => void;
  setChat: (id: string | null) => void;
  toast: (t: Omit<Toast, "id" | "until">) => void;
  dismiss: (id: number) => void;
  addPending: (seq: number, kind: string, agent?: string) => void;
  focusOn: (tile: Tile) => void;
  setFollow: (id: string | null) => void;
  setLook: (open: boolean) => void;
  setBuild: (patch: Partial<Pick<TownState, "draft" | "tool" | "catalogId" | "templateId" | "rot" | "paint" | "hover" | "check" | "picked">>) => void;
  resetBuild: () => void;
}

let toastId = 0;
const BUBBLE_MS = 7000;

function nameOf(info: Info | null, id: string | null | undefined): string {
  return info?.residents.find((r) => r.id === id)?.first_name ?? "Someone";
}

export const useTown = create<TownState>((set, get) => ({
  info: null,
  map: null,
  bootError: null,
  poll: null,
  frame: null,
  epoch: 0,
  sinceStep: -2,
  sinceFeed: 0,
  feed: [],
  conversations: [],
  bubbles: {},
  pending: {},
  selection: null,
  mode: "play",
  notebook: { open: false, tab: "requests" },
  chatWith: null,
  toasts: [],
  focus: null,
  follow: null,
  look: false,
  draft: emptyDraft(),
  tool: "select",
  catalogId: null,
  templateId: null,
  rot: 0,
  paint: null,
  hover: null,
  check: null,
  picked: null,

  boot: (info, map) => set({ info, map, bootError: null }),
  bootFailed: (msg) => set({ bootError: msg }),

  ingest: (p) => {
    const s = get();
    const reset = p.epoch !== s.epoch;
    const last = p.frames.length ? p.frames[p.frames.length - 1] : null;
    const bubbles = { ...s.bubbles };
    const pending = { ...s.pending };
    const conversations = reset ? [] : [...s.conversations];
    const toasts: Omit<Toast, "id" | "until">[] = [];
    const now = performance.now();
    const content = s.info?.content;
    const motifName = (id: unknown) => content?.motifs.find((m) => m.id === id)?.name ?? "a motif";
    // The first poll replays the session's recent history: keep conversations for Town Talk,
    // but do not pop toasts or speech bubbles for things that happened before the page opened.
    const catchingUp = s.poll === null;
    for (const ev of p.feed) {
      if (typeof ev.action_seq === "number") delete pending[ev.action_seq];
      if (catchingUp && ev.kind !== "conversation") continue;
      const who = nameOf(s.info, ev.agent_id as string | undefined);
      switch (ev.kind) {
        case "conversation":
          conversations.push({
            id: String(ev.conversation_id),
            participants: (ev.participants as string[]) ?? [],
            lines: (ev.lines as ConversationLine[]) ?? [],
            startedAt: String(ev.started_at),
            endedAt: String(ev.ended_at ?? ev.started_at),
          });
          break;
        case "chat":
          bubbles[String(ev.agent_id)] = { text: String(ev.reply ?? ""), mood: ev.mood as string, until: now + BUBBLE_MS };
          break;
        case "gift":
          bubbles[String(ev.agent_id)] = { text: String(ev.reply ?? ""), mood: ev.mood as string, until: now + BUBBLE_MS };
          toasts.push({ tone: "good", title: ev.loved ? `${who} loved it!` : `${who} thanked you`, body: `Friendship +${ev.friendship ?? 0}` });
          break;
        case "request":
          bubbles[String(ev.agent_id)] = { text: String(ev.reply ?? ""), until: now + BUBBLE_MS * 1.5 };
          toasts.push({ tone: "info", title: `${who} has a request`, body: String((ev.request as { wish?: string })?.wish ?? ""), theme: (ev.request as { theme?: string })?.theme });
          break;
        case "request_ready":
          toasts.push({ tone: "good", title: "Ready to deliver", body: `Talk to ${who} to hand it over.` });
          break;
        case "delivered":
          bubbles[String(ev.agent_id)] = { text: String(ev.reply ?? ""), mood: ev.mood as string, until: now + BUBBLE_MS };
          toasts.push({ tone: "good", title: "Request complete", body: `+${ev.pulse ?? 0} Town Pulse, and ${motifName(ev.reward)}` });
          break;
        case "motif":
          toasts.push({ tone: "good", title: `Found ${motifName(ev.motif)}`, body: ev.source === "conversation" ? "Left behind by a friendly chat" : `In the ${ev.object ?? "town"}`, theme: ev.theme as string });
          break;
        case "search_empty":
          toasts.push({ tone: "info", title: "Nothing here", body: `The ${ev.object ?? "object"} has nothing hidden right now.` });
          break;
        case "level_up":
          toasts.push({ tone: "level", title: `Town Pulse ${ev.level}: ${ev.name}`, body: "New things to build are unlocked." });
          break;
        case "build": {
          const n = (ev.placed as unknown[])?.length ?? 0;
          toasts.push({ tone: "good", title: n ? `Placed ${n} ${n === 1 ? "item" : "items"}` : "Changes saved" });
          break;
        }
        case "build_rejected":
          toasts.push({ tone: "warn", title: "Could not build that", body: sentence(((ev.problems as string[]) ?? [])[0] ?? "check the red tiles") });
          break;
        case "rejected":
          toasts.push({ tone: "warn", title: "Not right now", body: sentence(String(ev.reason ?? "")) });
          break;
        case "failed":
          toasts.push({ tone: "warn", title: "The model could not answer", body: "Nothing was invented; try again." });
          break;
        case "welcome":
          toasts.push({ tone: "info", title: "Welcome to town", body: "You start with a few motifs of every kind." });
          break;
        case "whisper":
          toasts.push({ tone: "info", title: `Whispered to ${who}`, body: "Stored as an inner voice memory." });
          break;
        case "object_state":
          toasts.push({ tone: "info", title: "Object changed", body: `${String(ev.address ?? "").split(":").pop()} is now ${ev.state}` });
          break;
        case "stopped":
          toasts.push({ tone: "warn", title: "The town stopped", body: String(ev.detail ?? "").split("\n")[0] });
          break;
      }
    }
    for (const [k, b] of Object.entries(bubbles)) if (b.until < now) delete bubbles[k];
    const feed = [...s.feed, ...p.feed].slice(-200);
    set({
      poll: p,
      epoch: p.epoch,
      frame: last ?? (reset ? null : s.frame),
      sinceStep: last ? last.step : reset ? -2 : s.sinceStep,
      sinceFeed: p.feed_seq,
      feed,
      conversations: conversations.slice(-24),
      bubbles,
      pending,
    });
    for (const t of toasts) get().toast(t);
  },

  select: (selection) => set({ selection, chatWith: selection?.kind === "resident" ? get().chatWith : null }),
  setMode: (mode) => set({ mode, selection: null, chatWith: null, look: false, notebook: { ...get().notebook, open: false } }),
  openNotebook: (tab) => set({ notebook: { open: true, tab: tab ?? get().notebook.tab } }),
  closeNotebook: () => set({ notebook: { ...get().notebook, open: false } }),
  setChat: (chatWith) => set({ chatWith }),
  toast: (t) => {
    const id = ++toastId;
    const ttl = t.tone === "warn" ? 9000 : t.tone === "level" ? 6500 : 4500;
    set({ toasts: [...get().toasts, { ...t, id, until: Date.now() + ttl }].slice(-4) });
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
  addPending: (seq, kind, agent) => set({ pending: { ...get().pending, [seq]: { kind, agent } } }),
  focusOn: (tile) => set({ focus: { tile, at: performance.now() } }),
  setFollow: (follow) => set({ follow }),
  setLook: (look) => set({ look }),
  setBuild: (patch) => set(patch),
  resetBuild: () => set({ draft: emptyDraft(), tool: "select", catalogId: null, templateId: null, rot: 0, paint: null, hover: null, check: null, picked: null }),
}));
