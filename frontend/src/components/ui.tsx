import { Heart, type Icon } from "@phosphor-icons/react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { iconByName } from "../lib/icons";
import type { Look, Theme } from "../types";

type Tone = "primary" | "soft" | "ghost" | "danger";

const TONES: Record<Tone, string> = {
  primary: "bg-sun text-[#2a2838] shadow-[0_4px_0_var(--color-sun-deep)] hover:brightness-105",
  soft: "bg-[var(--panel-2)] text-[var(--text)] hover:bg-[var(--panel-3)]",
  ghost: "bg-transparent text-[var(--text)] hover:bg-[var(--panel-2)]",
  danger: "bg-[#ffe1de] text-[#8a1f17] hover:bg-[#ffd2cd] dark:bg-[#4a2a2e] dark:text-[#ffd6d2]",
};

export function Button({ tone = "soft", icon: IconCmp, children, className = "", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone; icon?: Icon }) {
  return (
    <button
      type="button"
      className={`inline-flex min-h-10 items-center justify-center gap-2 whitespace-nowrap rounded-full px-4 font-display text-[15px] font-semibold transition-[transform,background-color,filter] duration-150 active:translate-y-px active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 ${TONES[tone]} ${className}`}
      {...rest}
    >
      {IconCmp ? <IconCmp size={18} weight="bold" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

export function IconButton({ label, icon: IconCmp, active = false, className = "", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; icon: Icon; active?: boolean }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active || undefined}
      className={`inline-flex size-11 shrink-0 items-center justify-center rounded-full transition-[transform,background-color] duration-150 active:scale-95 disabled:opacity-40 ${
        active ? "bg-sun text-[#2a2838]" : "bg-[var(--panel-2)] text-[var(--text)] hover:bg-[var(--panel-3)]"
      } ${className}`}
      {...rest}
    >
      <IconCmp size={21} weight={active ? "fill" : "bold"} aria-hidden="true" />
    </button>
  );
}

export function ThemeChip({ theme, children, size = "md" }: { theme: Theme | undefined; children?: ReactNode; size?: "sm" | "md" }) {
  if (!theme) return null;
  const Icon = iconByName(theme.icon);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-display font-semibold text-[var(--text)] ${size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm"}`}
      style={{ background: `color-mix(in srgb, ${theme.color} 20%, var(--panel))` }}
    >
      <Icon size={size === "sm" ? 13 : 15} weight="fill" color={theme.color} aria-hidden="true" />
      {children ?? theme.name}
    </span>
  );
}

export function MotifCount({ theme, count }: { theme: Theme; count: number }) {
  const Icon = iconByName(theme.icon);
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-2 py-1 font-display text-sm font-semibold tabular" style={{ background: `color-mix(in srgb, ${theme.color} 18%, var(--panel))` }}>
      <Icon size={16} weight="fill" color={theme.color} aria-hidden="true" />
      <span className="sr-only">{theme.name}</span>
      {count}
    </span>
  );
}

export function Hearts({ value, label }: { value: number; label?: string }) {
  const full = Math.floor(value / 20);
  return (
    <span className="inline-flex items-center gap-0.5" role="img" aria-label={label ?? `Friendship ${full} of 5`}>
      {[0, 1, 2, 3, 4].map((i) => (
        <Heart key={i} size={16} weight={i < full ? "fill" : "regular"} color={i < full ? "#e2629b" : "var(--muted)"} aria-hidden="true" />
      ))}
    </span>
  );
}

/** A small portrait drawn with CSS shapes from the resident's look. */
export function Portrait({ look, size = 44, ring }: { look: Look; size?: number; ring?: string }) {
  const hair = look.hair_style !== "bald";
  return (
    <span
      aria-hidden="true"
      className="relative inline-block shrink-0 overflow-hidden rounded-full"
      style={{ width: size, height: size, background: look.shirt, boxShadow: ring ? `0 0 0 3px ${ring}` : undefined }}
    >
      <span className="absolute rounded-full" style={{ left: "18%", right: "18%", top: "14%", bottom: "16%", background: look.skin }} />
      {hair ? <span className="absolute rounded-t-full" style={{ left: "15%", right: "15%", top: "8%", height: "30%", background: look.hair }} /> : null}
      {look.hair_style === "bun" ? <span className="absolute rounded-full" style={{ left: "40%", width: "20%", top: "0%", height: "18%", background: look.hair }} /> : null}
      {look.hair_style === "long" ? <span className="absolute" style={{ left: "13%", right: "13%", top: "30%", height: "38%", background: look.hair, opacity: 0.9, borderRadius: "0 0 40% 40%" }} /> : null}
      <span className="absolute rounded-full bg-[#2b2533]" style={{ left: "35%", top: "50%", width: "8%", height: "11%" }} />
      <span className="absolute rounded-full bg-[#2b2533]" style={{ right: "35%", top: "50%", width: "8%", height: "11%" }} />
      <span className="absolute rounded-full bg-[#f39a9a] opacity-80" style={{ left: "24%", top: "63%", width: "12%", height: "7%" }} />
      <span className="absolute rounded-full bg-[#f39a9a] opacity-80" style={{ right: "24%", top: "63%", width: "12%", height: "7%" }} />
      {look.accessory === "glasses" ? (
        <span className="absolute rounded-full border-2 border-[#3b3346]" style={{ left: "27%", right: "27%", top: "45%", height: "18%", borderRadius: "40%" }} />
      ) : null}
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded-md border border-[var(--line)] bg-[var(--panel-2)] px-1.5 py-0.5 font-sans text-xs font-bold">{children}</kbd>;
}
