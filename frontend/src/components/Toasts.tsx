import { CaretDown, CaretUp, ChatsCircle, Info, Sparkle, Star, Warning, X } from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { formatTime } from "../lib/time";
import { useTown } from "../store";
import type { Theme } from "../types";

const NO_THEMES: Theme[] = [];

const TONE = {
  info: { icon: Info, color: "#4a82dd" },
  good: { icon: Sparkle, color: "#3f9a50" },
  warn: { icon: Warning, color: "#d9534f" },
  level: { icon: Star, color: "#f2a33a" },
};

export function Toasts() {
  const toasts = useTown((s) => s.toasts);
  const dismiss = useTown((s) => s.dismiss);
  const themes = useTown((s) => s.info?.content.themes ?? NO_THEMES);
  const reduce = useReducedMotion();
  return (
    <div className="pointer-events-none fixed right-3 top-[180px] z-20 flex w-[min(92vw,340px)] flex-col gap-2 sm:right-4 md:top-24" aria-live="polite" role="status">
      <AnimatePresence initial={false}>
        {toasts.map((t, i) => {
          const tone = TONE[t.tone];
          const color = t.theme ? (themes.find((x) => x.id === t.theme)?.color ?? tone.color) : tone.color;
          const Icon = tone.icon;
          return (
            <motion.div
              key={t.id}
              layout={!reduce}
              initial={reduce ? false : { x: 30, opacity: 0, scale: 0.96 }}
              animate={{ x: 0, opacity: 1, scale: 1 }}
              exit={reduce ? { opacity: 0 } : { x: 30, opacity: 0 }}
              transition={{ type: "spring", stiffness: 360, damping: 30 }}
              className={`pointer-events-auto panel items-start gap-2.5 px-3 py-2.5 ${i < toasts.length - 2 ? "hidden sm:flex" : "flex"} ${t.tone === "level" ? "border-[#f2a33a]" : ""}`}
            >
              <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full" style={{ background: `color-mix(in srgb, ${color} 20%, var(--panel))` }}>
                <Icon size={18} weight="fill" color={color} aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-display font-bold leading-snug">{t.title}</p>
                {t.body ? <p className="break-words text-sm text-[var(--muted)]">{t.body}</p> : null}
              </div>
              <button type="button" onClick={() => dismiss(t.id)} aria-label="Dismiss" className="rounded-full p-1 hover:bg-[var(--panel-2)]">
                <X size={14} weight="bold" aria-hidden="true" />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

export function TownTalk() {
  const conversations = useTown((s) => s.conversations);
  const info = useTown((s) => s.info)!;
  const [open, setOpen] = useState(false);
  const recent = conversations.slice(-6).reverse();
  if (!recent.length) return null;
  const name = (id: string) => info.residents.find((r) => r.id === id)?.first_name ?? id;
  const latest = recent[0];
  return (
    <div className="pointer-events-auto panel absolute bottom-3 right-16 hidden w-[320px] p-3 sm:bottom-4 sm:right-[76px] xl:block">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex w-full items-center gap-2 text-left">
        <ChatsCircle size={20} weight="fill" color="#2a9d96" aria-hidden="true" />
        <span className="flex-1 font-display font-bold">Town Talk</span>
        {open ? <CaretDown size={16} weight="bold" aria-hidden="true" /> : <CaretUp size={16} weight="bold" aria-hidden="true" />}
      </button>
      {!open ? (
        <p className="mt-1 line-clamp-2 text-sm text-[var(--muted)]">
          <span className="font-bold text-[var(--text)]">{latest.participants.map(name).join(" and ")}:</span> {latest.lines[0]?.text ?? "…"}
        </p>
      ) : (
        <ul className="scroll-thin mt-2 max-h-72 space-y-3 overflow-y-auto overscroll-contain">
          {recent.map((c) => (
            <li key={c.id}>
              <p className="text-xs font-bold text-[var(--muted)]">
                {c.participants.map(name).join(" and ")}, {formatTime(c.startedAt)}
              </p>
              <ul className="mt-1 space-y-1">
                {c.lines.slice(0, 6).map((l, i) => (
                  <li key={i} className="text-sm">
                    <span className="font-bold">{name(l.speaker)}:</span> {l.text}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
