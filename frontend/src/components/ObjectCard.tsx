import { Hammer, MagnifyingGlass, PencilSimple, X } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { iconByName } from "../lib/icons";
import { formatTime, isBefore } from "../lib/time";
import { useTown } from "../store";
import { Button, IconButton, ThemeChip } from "./ui";
import { objectName, placeOfAddress } from "../lib/places";
import { failureBody } from "../lib/text";

const SUGGESTIONS: [RegExp, string[]][] = [
  [/cooking|stove|oven|toaster/i, ["burning", "turned off", "messy"]],
  [/refrigerator/i, ["empty", "full of snacks"]],
  [/shower|toilet|sink/i, ["broken", "out of order", "clean"]],
  [/bed/i, ["unmade", "freshly made"]],
  [/piano|guitar|harp/i, ["out of tune", "freshly tuned"]],
  [/garden/i, ["blooming", "needs watering"]],
];

export function ObjectCard({ address, itemId }: { address?: string; itemId?: string }) {
  const info = useTown((s) => s.info)!;
  const poll = useTown((s) => s.poll);
  const select = useTown((s) => s.select);
  const setMode = useTown((s) => s.setMode);
  const setBuild = useTown((s) => s.setBuild);
  const toast = useTown((s) => s.toast);
  const addPending = useTown((s) => s.addPending);
  const pending = useTown((s) => s.pending);
  const reduce = useReducedMotion();
  const cardRef = useRef<HTMLElement>(null);
  const [sending, setSending] = useState(false);
  useEffect(() => {
    cardRef.current?.focus({ preventScroll: true });
  }, []);
  const [hint, setHint] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const item = itemId ? poll?.game?.items.find((i) => i.id === itemId) : undefined;
  const addr = item?.address ?? address ?? "";
  const cat = item ? info.content.items.find((c) => c.id === item.catalog_id) : undefined;
  const name = objectName(addr);
  const where = placeOfAddress(addr);
  const state = poll?.objects?.[addr];
  const cooldown = poll?.game?.cooldowns[addr];
  const now = poll?.clock?.time;
  const cooling = cooldown && now ? isBefore(now, cooldown) : false;
  const replay = !!poll?.replay;
  const themes = info.content.themes;

  useEffect(() => {
    let alive = true;
    if (item || !addr) return;
    api
      .object(addr)
      .then((o) => alive && setHint(o.search_theme))
      .catch(() => alive && setHint(null));
    return () => {
      alive = false;
    };
  }, [addr, item]);

  const act = async (kind: string, payload: Record<string, unknown>) => {
    setSending(true);
    try {
      const ack = await api.action(kind, payload);
      addPending(ack.seq, kind);
    } catch (e) {
      toast({ tone: "warn", title: kind === "search" ? "Could not search it" : "Could not change it", body: failureBody(e) });
    } finally {
      setSending(false);
    }
  };
  const searching = sending || Object.values(pending).some((p) => p.kind === "search");

  const suggestions = SUGGESTIONS.find(([re]) => re.test(name))?.[1] ?? ["broken", "messy", "brand new"];
  const theme = themes.find((t) => t.id === (cat?.theme ?? hint));
  const ThemeIcon = iconByName(theme?.icon);

  return (
    <motion.section
      ref={cardRef}
      tabIndex={-1}
      initial={reduce ? false : { y: 24, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 30 }}
      className="pointer-events-auto panel absolute bottom-3 left-1/2 w-[min(94vw,480px)] -translate-x-1/2 p-4 sm:bottom-4"
      aria-label={name}
    >
      <div className="flex items-start gap-3">
        <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl" style={{ background: `color-mix(in srgb, ${theme?.color ?? "#9aa3b5"} 22%, var(--panel))` }}>
          <ThemeIcon size={26} weight="fill" color={theme?.color ?? "#7d859a"} aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-xl font-bold capitalize">{name}</h2>
          <p className="truncate text-sm text-[var(--muted)]">{where}</p>
          <p className="mt-1 text-sm font-semibold">
            {state?.in_use_by ? `In use by ${info.residents.find((r) => r.id === state.in_use_by)?.first_name ?? "someone"}` : `It is ${state?.lasting ?? "idle"}`}
          </p>
        </div>
        <IconButton label="Close (Esc)" icon={X} onClick={() => select(null)} />
      </div>
      {item && cat ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <ThemeChip theme={themes.find((t) => t.id === cat.theme)} />
          <span className="text-sm text-[var(--muted)]">Placed by you{item.placed_at ? ` at ${formatTime(item.placed_at)}` : ""}</span>
          {replay ? null : (
            <Button
              icon={Hammer}
              className="ml-auto"
              onClick={() => {
                setMode("build");
                setBuild({ picked: item.id, tool: "select" });
              }}
            >
              Edit in Build Mode
            </Button>
          )}
        </div>
      ) : replay ? null : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button tone="primary" icon={MagnifyingGlass} disabled={!!cooling || searching} onClick={() => act("search", { address: addr })}>
            {searching ? "Searching…" : cooling && cooldown ? `Search Again at ${formatTime(cooldown)}` : "Search for Motifs"}
          </Button>
          {theme && !item ? <span className="text-sm text-[var(--muted)]">Might hold {theme.name} motifs</span> : null}
          <Button tone="ghost" icon={PencilSimple} onClick={() => setEditing(editing === null ? "" : null)} aria-expanded={editing !== null} title="Research: change the object’s state, as in the paper (§3.1)">
            Change State
          </Button>
        </div>
      )}
      {editing !== null ? (
        <form
          className="mt-3 space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!editing.trim()) return;
            void act("object_state", { address: addr, state: editing.trim() });
            setEditing(null);
          }}
        >
          <p className="text-sm text-[var(--muted)]">Residents who see it will notice. Suggestions:</p>
          <div className="flex flex-wrap gap-1.5">
            {suggestions.map((s) => (
              <button key={s} type="button" onClick={() => setEditing(s)} className="rounded-full bg-[var(--panel-2)] px-3 py-1 text-sm font-semibold transition-colors hover:bg-[var(--panel-hover)]">
                {s}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <label htmlFor="object-state" className="sr-only">
              New state
            </label>
            <input
              id="object-state"
              name="state"
              autoComplete="off"
              maxLength={60}
              value={editing}
              onChange={(e) => setEditing(e.target.value)}
              placeholder="burning…"
              className="min-h-10 min-w-0 flex-1 rounded-2xl border-2 border-[var(--line)] bg-[var(--panel)] px-3 text-[15px] placeholder:text-[var(--muted)]"
            />
            <Button type="submit" tone="primary">
              Set State
            </Button>
          </div>
        </form>
      ) : null}
    </motion.section>
  );
}
