import { Crosshair, HandHeart, Lock, MapPin, Question, SealCheck, Star, X } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";
import { TabList, tabPanelProps } from "./Tabs";
import { activityIcon, activityLabel, iconByName } from "../lib/icons";
import { formatNumber, formatTime } from "../lib/time";
import { useTown, type NotebookTab } from "../store";
import type { Theme } from "../types";
import { Button, Hearts, IconButton, Portrait, ThemeChip } from "./ui";
import { placeOfAddress, placeOfLabel } from "../lib/places";

const TABS: { id: NotebookTab; label: string }[] = [
  { id: "requests", label: "Requests" },
  { id: "collections", label: "Collections" },
  { id: "residents", label: "Residents" },
  { id: "town", label: "Town" },
];

export function Notebook() {
  const nb = useTown((s) => s.notebook);
  const open = useTown((s) => s.openNotebook);
  const close = useTown((s) => s.closeNotebook);
  const reduce = useReducedMotion();
  const opener = useRef<Element | null>(null);

  // Esc closes; focus goes back where it came from (the rest of the page is inert meanwhile)
  useEffect(() => {
    opener.current = document.activeElement;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      const el = opener.current;
      if (el instanceof HTMLElement && el.isConnected) el.focus({ preventScroll: true });
    };
  }, [close]);

  return (
    <div className="pointer-events-auto fixed inset-0 z-30 flex items-center justify-center bg-[#1b2440]/35 p-3 backdrop-blur-[2px]" onClick={close} role="presentation">
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby="notebook-title"
        initial={reduce ? false : { scale: 0.94, y: 18, opacity: 0 }}
        animate={{ scale: 1, y: 0, opacity: 1 }}
        transition={{ type: "spring", stiffness: 280, damping: 26 }}
        onClick={(e) => e.stopPropagation()}
        className="relative flex h-[min(86dvh,720px)] w-[min(96vw,980px)] overflow-hidden rounded-[28px] bg-[var(--panel)] shadow-[var(--shadow)]"
      >
        {/* spiral binding */}
        <div className="hidden w-10 shrink-0 flex-col items-center justify-around bg-[var(--panel-2)] py-6 sm:flex" aria-hidden="true">
          {Array.from({ length: 12 }, (_, i) => (
            <span key={i} className="size-4 rounded-full border-[3px] border-[var(--muted)]/50 bg-[var(--panel)]" />
          ))}
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex flex-wrap items-center gap-2 border-b-2 border-[var(--line)] px-4 py-3">
            <h2 id="notebook-title" className="font-display text-2xl font-bold">
              Town Notebook
            </h2>
            <TabList
              items={TABS}
              value={nb.tab}
              onChange={(t) => open(t)}
              idPrefix="notebook"
              label="Notebook pages"
              focusOnMount
              className="order-last -mx-1 flex basis-full gap-1 overflow-x-auto px-1 py-1 sm:order-none sm:ml-2 sm:min-w-0 sm:flex-1 sm:basis-auto"
              tabClassName={(on) => `whitespace-nowrap rounded-full px-3.5 py-1.5 font-display text-sm font-semibold transition-colors ${on ? "bg-sun text-[#2a2838]" : "hover:bg-[var(--panel-hover)]"}`}
            />
            <IconButton label="Close Notebook (Esc)" icon={X} onClick={close} className="ml-auto" />
          </div>
          <div className="paper-lines scroll-thin flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6" {...tabPanelProps("notebook", nb.tab)}>
            {nb.tab === "requests" ? <RequestsPage /> : nb.tab === "collections" ? <CollectionsPage /> : nb.tab === "residents" ? <ResidentsPage /> : <TownPage />}
          </div>
        </div>
      </motion.div>
    </div>
  );
}

function useThemes(): Theme[] {
  return useTown((s) => s.info!.content.themes);
}

function RequestsPage() {
  const info = useTown((s) => s.info)!;
  const game = useTown((s) => s.poll?.game);
  const select = useTown((s) => s.select);
  const close = useTown((s) => s.closeNotebook);
  const focusOn = useTown((s) => s.focusOn);
  const map = useTown((s) => s.map)!;
  const themes = useThemes();
  const reqs = [...(game?.requests ?? [])].sort((a, b) => ["ready", "open", "fulfilled"].indexOf(a.status) - ["ready", "open", "fulfilled"].indexOf(b.status));
  if (!reqs.length) {
    return (
      <Empty icon={HandHeart} title="No requests yet">
        Residents ask for something once they are up and about, or when you ask what they wish for. Their wishes come from their own goals and memories.
      </Empty>
    );
  }
  const showPlace = (address: string) => {
    for (const [addr, tiles] of map.objects) if (addr.startsWith(address) && tiles.length) return focusOn(tiles[0]);
  };
  return (
    <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {reqs.map((q) => {
        const r = info.residents.find((x) => x.id === q.agent_id)!;
        return (
          <li key={q.id} className={`rounded-3xl bg-[var(--panel)] p-4 shadow-sm ring-2 ${q.status === "ready" ? "ring-[#58b368]" : "ring-[var(--line)]"} ${q.status === "fulfilled" ? "opacity-70" : ""}`}>
            <div className="flex items-center gap-3">
              <Portrait look={r.look} size={40} />
              <div className="min-w-0 flex-1">
                <p className="font-display text-lg font-bold">{r.first_name}</p>
                <p className="truncate text-sm text-[var(--muted)]">{placeOfLabel(q.place_label)}</p>
              </div>
              {q.status === "fulfilled" ? (
                <span className="flex items-center gap-1 font-display text-xs font-bold text-[#22612f] dark:text-[#bfe8c8]">
                  <SealCheck size={24} weight="fill" color="#3f9a50" aria-hidden="true" />
                  Fulfilled
                </span>
              ) : q.status === "ready" ? (
                <span className="rounded-full bg-[#dff3e2] px-2.5 py-1 font-display text-xs font-bold text-[#22612f]">Ready</span>
              ) : (
                <span className="rounded-full bg-sun/25 px-2.5 py-1 font-display text-xs font-bold">Open</span>
              )}
            </div>
            <p className="mt-2 text-[15px] font-semibold">“{q.request_line}”</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <ThemeChip theme={themes.find((t) => t.id === q.theme)} size="sm">
                Any {themes.find((t) => t.id === q.theme)?.name} item
              </ThemeChip>
              <span className="text-xs text-[var(--muted)]">{q.outdoor ? "outdoors" : "indoors"}</span>
              <div className="ml-auto flex gap-1.5">
                <Button tone="ghost" icon={MapPin} onClick={() => (showPlace(q.place_address), close())} aria-label={`Show ${r.first_name}’s place on the map`}>
                  Show on Map
                </Button>
                {q.status === "ready" ? (
                  <Button tone="primary" onClick={() => (select({ kind: "resident", id: q.agent_id }), close())} aria-label={`Deliver it to ${r.first_name}`}>
                    Deliver
                  </Button>
                ) : null}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function CollectionsPage() {
  const info = useTown((s) => s.info)!;
  const game = useTown((s) => s.poll?.game);
  const themes = useThemes();
  return (
    <div className="space-y-6">
      <section>
        <h3 className="mb-3 font-display text-xl font-bold">Motifs</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {themes.map((t) => (
            <div key={t.id} className="rounded-3xl p-3" style={{ background: `color-mix(in srgb, ${t.color} 13%, var(--panel))` }}>
              <ThemeChip theme={t} size="sm" />
              <p className="mt-1 text-xs text-[var(--muted)]">{t.description}</p>
              <ul className="mt-2 space-y-1.5">
                {info.content.motifs
                  .filter((m) => m.theme === t.id)
                  .map((m) => {
                    const n = game?.inventory[m.id] ?? 0;
                    const found = !!game?.found[m.id];
                    const Icon = iconByName(m.icon);
                    return (
                      <li key={m.id} className="flex items-center gap-2">
                        <span className="flex size-8 items-center justify-center rounded-full bg-[var(--panel)]" style={{ opacity: found ? 1 : 0.45 }}>
                          {found ? <Icon size={18} weight="fill" color={t.color} aria-hidden="true" /> : <Question size={16} weight="bold" aria-hidden="true" />}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className={`block truncate text-sm font-semibold ${found ? "" : "text-[var(--muted)]"}`}>{m.name}</span>
                          <span className="block truncate text-[11px] text-[var(--muted)]">
                            {m.source === "social" ? "From friendly chats" : `Search ${t.name.toLowerCase()} places`}
                            {found ? "" : ", not found yet"}
                          </span>
                        </span>
                        <span className="tabular text-sm font-bold">{n}</span>
                      </li>
                    );
                  })}
              </ul>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h3 className="mb-3 font-display text-xl font-bold">Gifts You Can Wrap</h3>
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {info.content.gifts.map((g) => {
            const t = themes.find((x) => x.id === g.theme)!;
            const Icon = iconByName(g.icon);
            return (
              <li key={g.id} className="flex items-center gap-2 rounded-2xl bg-[var(--panel)] px-3 py-2 shadow-sm">
                <Icon size={22} weight="fill" color={t.color} aria-hidden="true" />
                <span className="flex-1 text-sm font-bold capitalize">{g.name}</span>
                <span className="text-xs text-[var(--muted)]">1 {t.name}</span>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}

function ResidentsPage() {
  const info = useTown((s) => s.info)!;
  const poll = useTown((s) => s.poll);
  const frame = useTown((s) => s.frame);
  const select = useTown((s) => s.select);
  const close = useTown((s) => s.closeNotebook);
  const focusOn = useTown((s) => s.focusOn);
  const themes = useThemes();
  return (
    <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {info.residents.map((r) => {
        const a = frame?.agents[r.id];
        const Act = activityIcon(a?.activity ?? "");
        return (
          <li key={r.id} className="rounded-3xl bg-[var(--panel)] p-4 shadow-sm">
            <div className="flex items-center gap-3">
              <Portrait look={r.look} size={48} />
              <div className="min-w-0">
                <p className="font-display text-lg font-bold">{r.name}</p>
                <Hearts value={poll?.game?.friendship[r.id] ?? 0} />
              </div>
            </div>
            <p className="mt-2 line-clamp-3 text-sm text-[var(--muted)]">{r.learned}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {r.loves.map((t) => (
                <ThemeChip key={t} theme={themes.find((x) => x.id === t)} size="sm" />
              ))}
            </div>
            <p className="mt-2 flex items-center gap-1.5 text-sm font-semibold">
              <Act size={16} weight="fill" aria-hidden="true" />
              <span className="truncate">{a?.sleeping ? "Sleeping" : activityLabel(a?.activity ?? "")}</span>
            </p>
            <Button
              className="mt-3 w-full"
              icon={Crosshair}
              onClick={() => {
                select({ kind: "resident", id: r.id });
                if (a && a.x !== null && a.y !== null) focusOn([a.x, a.y]);
                close();
              }}
            >
              Visit {r.first_name}
            </Button>
          </li>
        );
      })}
    </ul>
  );
}

function TownPage() {
  const info = useTown((s) => s.info)!;
  const poll = useTown((s) => s.poll);
  const game = poll?.game;
  const themes = useThemes();
  const pulse = game?.pulse;
  const stats = game?.stats ?? {};
  const byTheme: Record<string, number> = {};
  for (const it of game?.items ?? []) {
    const t = info.content.items.find((c) => c.id === it.catalog_id)?.theme;
    if (t) byTheme[t] = (byTheme[t] ?? 0) + 1;
  }
  const STAT_LABELS: [string, string][] = [
    ["conversations", "Resident conversations"],
    ["chats", "Chats with you"],
    ["gifts", "Gifts given"],
    ["requests_fulfilled", "Requests fulfilled"],
    ["items_placed", "Items placed"],
    ["motifs_found", "Motifs found"],
  ];
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <section>
        <h3 className="mb-3 font-display text-xl font-bold">Town Pulse</h3>
        <ol className="space-y-2">
          {info.content.levels.map((l) => {
            const reached = (pulse?.level ?? 1) >= l.level;
            const current = pulse?.level === l.level;
            const unlocks = info.content.items.filter((i) => i.unlock === l.level).length;
            return (
              <li key={l.level} className={`flex items-center gap-3 rounded-3xl px-4 py-3 ${current ? "bg-sun/25 ring-2 ring-sun" : "bg-[var(--panel)]"}`}>
                <span className={`flex size-10 items-center justify-center rounded-full font-display text-lg font-bold ${reached ? "bg-sun text-[#2a2838]" : "bg-[var(--panel-2)] text-[var(--muted)]"}`}>
                  {reached ? (
                    l.level
                  ) : (
                    <>
                      <Lock size={18} weight="bold" aria-hidden="true" />
                      <span className="sr-only">Locked</span>
                    </>
                  )}
                </span>
                <div className="flex-1">
                  <p className="font-display text-lg font-bold">{l.name}</p>
                  <p className="text-xs text-[var(--muted)]">
                    From {formatNumber(l.points)} points · unlocks {unlocks} {unlocks === 1 ? "item" : "items"}
                  </p>
                </div>
                {current ? (
                  <>
                    <Star size={22} weight="fill" color="#f2a33a" aria-hidden="true" />
                    <span className="sr-only">The town is here</span>
                  </>
                ) : null}
              </li>
            );
          })}
        </ol>
        <p className="mt-3 text-sm text-[var(--muted)]">
          {formatNumber(pulse?.points ?? 0)} points{pulse?.next_at ? `, ${formatNumber(pulse.next_at - pulse.points)} to ${pulse.next_name}` : ", the town is at its liveliest"}.
        </p>
      </section>
      <section className="space-y-6">
        <div>
          <h3 className="mb-3 font-display text-xl font-bold">This Town So Far</h3>
          <dl className="grid grid-cols-2 gap-2">
            {STAT_LABELS.map(([k, label]) => (
              <div key={k} className="rounded-2xl bg-[var(--panel)] px-3 py-2 shadow-sm">
                <dt className="text-xs font-bold text-[var(--muted)]">{label}</dt>
                <dd className="font-display text-2xl font-bold tabular">{formatNumber(stats[k] ?? 0)}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div>
          <h3 className="mb-2 font-display text-xl font-bold">What You Have Built</h3>
          {game?.items.length ? (
            <>
              <div className="mb-2 flex flex-wrap gap-1">
                {themes.map((t) => (byTheme[t.id] ? <ThemeChip key={t.id} theme={t} size="sm">{`${t.name} ${byTheme[t.id]}`}</ThemeChip> : null))}
              </div>
              <ul className="space-y-1 text-sm">
                {game.items.slice(-8).map((it) => (
                  <li key={it.id} className="flex justify-between gap-2 rounded-xl bg-[var(--panel)] px-3 py-1.5">
                    <span className="font-semibold capitalize">{it.name}</span>
                    <span className="truncate text-[var(--muted)]">{placeOfAddress(it.address)}</span>
                    {it.placed_at ? <span className="shrink-0 text-[var(--muted)]">{formatTime(it.placed_at)}</span> : null}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-sm text-[var(--muted)]">Nothing yet. Press B to build and decorate; residents notice what you place.</p>
          )}
        </div>
      </section>
    </div>
  );
}

function Empty({ icon: Icon, title, children }: { icon: typeof Star; title: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-10 text-center">
      <span className="flex size-16 items-center justify-center rounded-full bg-sun/25">
        <Icon size={32} weight="fill" color="#c95d16" aria-hidden="true" />
      </span>
      <p className="mt-3 font-display text-xl font-bold">{title}</p>
      <p className="mt-1 text-[15px] text-[var(--muted)]">{children}</p>
    </div>
  );
}
