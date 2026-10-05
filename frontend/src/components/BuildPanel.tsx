import { ArrowClockwise, ArrowCounterClockwise, ArrowsClockwise, Check, Copy, Cursor, FloppyDisk, Lock, PaintBucket, Stack, Trash, X } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { draftCost, dropPlacement, push, redo, replace, shownItems, undo } from "../lib/build";
import { iconByName } from "../lib/icons";
import { useTown } from "../store";
import type { CatalogItem } from "../types";
import { Button, IconButton, Kbd, ThemeChip } from "./ui";
import { sentence } from "../lib/text";

const CATEGORIES = [
  { id: "all", label: "All" },
  { id: "furniture", label: "Furniture" },
  { id: "decor", label: "Decor" },
  { id: "garden", label: "Garden" },
  { id: "structure", label: "Structures" },
  { id: "templates", label: "Templates" },
] as const;

export function BuildPanel() {
  const info = useTown((s) => s.info)!;
  const game = useTown((s) => s.poll?.game);
  const st = useTown();
  const reduce = useReducedMotion();
  const [cat, setCat] = useState<(typeof CATEGORIES)[number]["id"]>("all");
  const [paintOpen, setPaintOpen] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const level = game?.pulse.level ?? 1;
  const themes = info.content.themes;
  const catalog = useMemo(() => new Map(info.content.items.map((i) => [i.id, i])), [info]);
  const cost = draftCost(st.draft.ops, catalog);
  const check = st.check;
  const lastVerdict = check?.verdicts.length ? check.verdicts[check.verdicts.length - 1] : null;
  const lastFeedback = check?.feedback.length ? check.feedback[check.feedback.length - 1] : null;
  const shown = shownItems(game?.items ?? [], st.draft.ops);
  const picked = shown.find((i) => i.key === st.picked) ?? null;
  const templates = [...info.content.templates, ...(game?.user_templates ?? [])];
  const items = info.content.items.filter((i) => cat === "all" || i.category === cat);

  const choose = (item: CatalogItem) => {
    if (item.unlock > level) return;
    st.setBuild({ tool: "place", catalogId: item.id, templateId: null, picked: null, paint: st.paint });
  };

  const rotate = () => {
    if (picked) {
      const rot = (picked.rot + 1) % 4;
      if (picked.committedId) st.setBuild({ draft: push(st.draft, [{ op: "move", item_id: picked.committedId, x: picked.x, y: picked.y, rot }]) });
      else if (picked.opIndex !== null) st.setBuild({ draft: replace(st.draft, st.draft.ops.map((op, i) => (i === picked.opIndex ? { ...op, rot } : op))) });
    } else st.setBuild({ rot: (st.rot + 1) % 4 });
  };

  const remove = () => {
    if (!picked) return;
    if (picked.committedId) st.setBuild({ draft: push(st.draft, [{ op: "remove", item_id: picked.committedId }]), picked: null });
    else if (picked.opIndex !== null) st.setBuild({ draft: replace(st.draft, dropPlacement(st.draft.ops, picked.opIndex)), picked: null });
  };

  const duplicate = () => {
    if (!picked) return;
    st.setBuild({ tool: "place", catalogId: picked.catalog_id, rot: picked.rot, paint: picked.paint, picked: null });
  };

  const applyPaint = (paint: string) => {
    setPaintOpen(false);
    if (picked) {
      if (picked.committedId) st.setBuild({ draft: push(st.draft, [{ op: "paint", item_id: picked.committedId, paint }]) });
      else if (picked.opIndex !== null) st.setBuild({ draft: replace(st.draft, st.draft.ops.map((op, i) => (i === picked.opIndex ? { ...op, paint } : op))) });
    } else st.setBuild({ paint });
  };

  const done = async () => {
    if (!st.draft.ops.length) {
      st.resetBuild();
      st.setMode("play");
      return;
    }
    setBusy(true);
    try {
      const pre = await api.validateBuild(st.draft.ops);
      if (!pre.ok) {
        st.setBuild({ check: pre });
        st.toast({ tone: "warn", title: "Some pieces do not fit", body: sentence(pre.problems[0] ?? pre.verdicts.find((v) => !v.ok)?.reasons[0] ?? "check the red tiles") });
        return;
      }
      const ack = await api.action("build", { ops: st.draft.ops });
      st.addPending(ack.seq, "build");
      st.resetBuild();
      st.setMode("play");
    } catch (e) {
      st.toast({ tone: "warn", title: "Could not save the build", body: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const saveTemplate = async () => {
    const name = (saving ?? "").trim();
    const placed = shown.filter((i) => i.draft || i.key === st.picked);
    if (!name || !placed.length) return;
    const x0 = Math.min(...placed.map((p) => p.x));
    const y0 = Math.min(...placed.map((p) => p.y));
    try {
      const ack = await api.action("save_template", { name, parts: placed.map((p) => ({ item: p.catalog_id, dx: p.x - x0, dy: p.y - y0, rot: p.rot, paint: p.paint })) });
      st.addPending(ack.seq, "save_template");
      st.toast({ tone: "good", title: `Saved “${name}”`, body: "Find it under Templates." });
      setSaving(null);
    } catch (e) {
      st.toast({ tone: "warn", title: "Could not save the template", body: (e as Error).message });
    }
  };

  // keyboard shortcuts while building
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea")) return;
      const k = e.key.toLowerCase();
      if ((e.metaKey || e.ctrlKey) && k === "z") {
        e.preventDefault();
        st.setBuild({ draft: e.shiftKey ? redo(st.draft) : undo(st.draft) });
      } else if ((e.metaKey || e.ctrlKey) && k === "y") {
        e.preventDefault();
        st.setBuild({ draft: redo(st.draft) });
      } else if (k === "r") rotate();
      else if (k === "delete" || k === "backspace") remove();
      else if (k === "d") duplicate();
      else if (k === "escape") st.setBuild({ tool: "select", catalogId: null, templateId: null, picked: null });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const status = (() => {
    if (!check) return null;
    if (check.problems.length) return { ok: false, text: sentence(check.problems[0]) };
    if (lastVerdict && !lastVerdict.ok) return { ok: false, text: sentence(lastVerdict.reasons[0] ?? "does not fit here") };
    if (st.hover && lastFeedback) {
      const bits: string[] = [];
      if (lastFeedback.fulfils?.length) bits.push("Fulfils a request here!");
      const lovers = (lastFeedback.loved_by ?? []).map((id) => info.residents.find((r) => r.id === id)?.first_name).filter(Boolean);
      if (lovers.length) bits.push(`${lovers.join(" and ")} ${lovers.length > 1 ? "love" : "loves"} ${themes.find((t) => t.id === lastFeedback.theme)?.name}.`);
      if (lastFeedback.harmony) bits.push("The colors match.");
      if (lastFeedback.room_theme) bits.push(`This place feels ${themes.find((t) => t.id === lastFeedback.room_theme)?.name}.`);
      return { ok: true, text: bits.join(" ") || "Fits here." };
    }
    return null;
  })();

  return (
    <>
      {/* top bar */}
      <motion.div
        initial={reduce ? false : { y: -16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="pointer-events-auto panel absolute left-1/2 top-3 flex w-[min(96vw,720px)] -translate-x-1/2 flex-wrap items-center gap-2 px-3 py-2 sm:top-4"
      >
        <p className="font-display text-lg font-bold">Build and Decorate</p>
        <span className="text-sm text-[var(--muted)] tabular">
          {st.draft.ops.length ? `${st.draft.ops.length} ${st.draft.ops.length === 1 ? "change" : "changes"}` : "Pick something below"}
          {Object.keys(cost).length ? ", costs " : ""}
        </span>
        {Object.entries(cost).map(([t, n]) => (
          <ThemeChip key={t} theme={themes.find((x) => x.id === t)} size="sm">{`${n} ${themes.find((x) => x.id === t)?.name}`}</ThemeChip>
        ))}
        <div className="ml-auto flex gap-2">
          <Button
            tone="ghost"
            icon={X}
            onClick={() => {
              st.resetBuild();
              st.setMode("play");
            }}
          >
            Cancel
          </Button>
          <Button tone="primary" icon={Check} onClick={done} disabled={busy}>
            {busy ? "Saving…" : "Done"}
          </Button>
        </div>
      </motion.div>

      {/* tool rail */}
      <div className="pointer-events-auto panel absolute left-3 top-1/2 flex -translate-y-1/2 flex-col gap-1.5 p-1.5 sm:left-4" role="toolbar" aria-label="Build tools">
        <IconButton label="Select and move (Esc)" icon={Cursor} active={st.tool === "select"} onClick={() => st.setBuild({ tool: "select", catalogId: null, templateId: null })} />
        <IconButton label="Rotate (R)" icon={ArrowsClockwise} onClick={rotate} />
        <IconButton label="Paint" icon={PaintBucket} active={paintOpen} onClick={() => setPaintOpen((v) => !v)} />
        <IconButton label="Duplicate (D)" icon={Copy} onClick={duplicate} disabled={!picked} />
        <IconButton label="Remove (Delete)" icon={Trash} onClick={remove} disabled={!picked} />
        <span className="my-1 h-px bg-[var(--line)]" />
        <IconButton label="Undo (Ctrl+Z)" icon={ArrowCounterClockwise} onClick={() => st.setBuild({ draft: undo(st.draft) })} disabled={!st.draft.undo.length} />
        <IconButton label="Redo (Ctrl+Shift+Z)" icon={ArrowClockwise} onClick={() => st.setBuild({ draft: redo(st.draft) })} disabled={!st.draft.redo.length} />
        <IconButton label="Save as template" icon={FloppyDisk} onClick={() => setSaving(saving === null ? "" : null)} disabled={!st.draft.ops.some((o) => o.op === "place")} />
      </div>

      {paintOpen ? (
        <div className="pointer-events-auto panel absolute left-20 top-1/2 grid -translate-y-1/2 grid-cols-3 gap-2 p-3 sm:left-[76px]" role="group" aria-label="Paints">
          {info.content.paints.map((p) => (
            <button key={p.id} type="button" onClick={() => applyPaint(p.id)} className="flex flex-col items-center gap-1 rounded-2xl p-1.5 hover:bg-[var(--panel-2)]" aria-pressed={st.paint === p.id}>
              <span className="size-8 rounded-full ring-2 ring-[var(--line)]" style={{ background: p.hex }} aria-hidden="true" />
              <span className="text-[11px] font-bold">{p.name}</span>
            </button>
          ))}
        </div>
      ) : null}

      {saving !== null ? (
        <form
          className="pointer-events-auto panel absolute left-20 top-[calc(50%+140px)] flex gap-2 p-2 sm:left-[76px]"
          onSubmit={(e) => {
            e.preventDefault();
            void saveTemplate();
          }}
        >
          <label htmlFor="template-name" className="sr-only">
            Template name
          </label>
          <input
            id="template-name"
            name="template"
            autoComplete="off"
            maxLength={40}
            value={saving}
            onChange={(e) => setSaving(e.target.value)}
            placeholder="Cozy corner…"
            className="min-h-10 w-44 rounded-2xl border-2 border-[var(--line)] bg-[var(--panel)] px-3 text-[15px] placeholder:text-[var(--muted)]"
          />
          <Button type="submit" tone="primary">
            Save
          </Button>
        </form>
      ) : null}

      {/* verdict */}
      {status ? (
        <div className="pointer-events-none absolute left-1/2 top-[88px] -translate-x-1/2 sm:top-[92px]" aria-live="polite">
          <span className={`rounded-full px-4 py-1.5 font-display text-sm font-semibold shadow ${status.ok ? "bg-[#e3f5e6] text-[#1f5a2b] dark:bg-[#21402a] dark:text-[#cdeed5]" : "bg-[#ffe3e0] text-[#8a1f17] dark:bg-[#4a2a2e] dark:text-[#ffd6d2]"}`}>
            {status.text}
          </span>
        </div>
      ) : null}

      {/* catalog tray */}
      <motion.div initial={reduce ? false : { y: 24, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="pointer-events-auto panel absolute bottom-3 left-1/2 w-[min(96vw,1040px)] -translate-x-1/2 p-3 sm:bottom-4">
        <div className="mb-2 flex items-center gap-1 overflow-x-auto" role="tablist" aria-label="Catalog">
          {CATEGORIES.map((c) => (
            <button
              key={c.id}
              type="button"
              role="tab"
              aria-selected={cat === c.id}
              onClick={() => setCat(c.id)}
              className={`whitespace-nowrap rounded-full px-3 py-1 font-display text-sm font-semibold ${cat === c.id ? "bg-sun text-[#2a2838]" : "hover:bg-[var(--panel-2)]"}`}
            >
              {c.label}
            </button>
          ))}
          <span className="ml-auto hidden gap-2 text-xs text-[var(--muted)] lg:flex">
            <span>
              <Kbd>R</Kbd> rotate
            </span>
            <span>
              <Kbd>D</Kbd> duplicate
            </span>
            <span>
              <Kbd>Ctrl Z</Kbd> undo
            </span>
          </span>
        </div>
        <div className="scroll-thin flex gap-2 overflow-x-auto pb-1">
          {cat === "templates"
            ? templates.map((t) => {
                const locked = (t.unlock ?? 1) > level;
                return (
                  <button
                    key={t.id}
                    type="button"
                    disabled={locked}
                    onClick={() => st.setBuild({ tool: "template", templateId: t.id, catalogId: null, picked: null })}
                    aria-pressed={st.templateId === t.id}
                    title={locked ? `Unlocks at Town Pulse level ${t.unlock}` : undefined}
                    className={`flex w-40 shrink-0 flex-col gap-1 rounded-3xl p-3 text-left transition-colors ${st.templateId === t.id ? "bg-sun/30 ring-2 ring-sun" : "bg-[var(--panel-2)] hover:bg-[var(--panel-3)]"} disabled:opacity-50`}
                  >
                    <span className="flex items-center gap-1.5 font-display font-bold">
                      <Stack size={18} weight="fill" aria-hidden="true" /> {t.name}
                    </span>
                    <span className="text-xs text-[var(--muted)]">{t.parts.length} pieces</span>
                    {locked ? (
                      <span className="flex items-center gap-1 text-xs font-bold text-[var(--muted)]">
                        <Lock size={12} weight="bold" aria-hidden="true" /> Level {t.unlock}
                      </span>
                    ) : null}
                  </button>
                );
              })
            : items.map((it) => {
                const theme = themes.find((t) => t.id === it.theme)!;
                const Icon = iconByName(theme.icon);
                const locked = it.unlock > level;
                return (
                  <button
                    key={it.id}
                    type="button"
                    disabled={locked}
                    onClick={() => choose(it)}
                    aria-pressed={st.catalogId === it.id}
                    aria-label={`${it.name}, ${it.footprint[0]} by ${it.footprint[1]}, costs ${Object.entries(it.cost)
                      .map(([t, n]) => `${n} ${themes.find((x) => x.id === t)?.name}`)
                      .join(" and ")}, ${it.placement === "any" ? "anywhere" : it.placement}${locked ? `, unlocks at Town Pulse level ${it.unlock}` : ""}`}
                    title={locked ? `Unlocks at Town Pulse level ${it.unlock}` : undefined}
                    className={`flex w-36 shrink-0 flex-col gap-1 rounded-3xl p-3 text-left transition-colors ${st.catalogId === it.id ? "bg-sun/30 ring-2 ring-sun" : "bg-[var(--panel-2)] hover:bg-[var(--panel-3)]"} disabled:opacity-50`}
                  >
                    <span className="flex items-center justify-between">
                      <Icon size={22} weight="fill" color={theme.color} aria-hidden="true" />
                      {locked ? (
                        <span className="flex items-center gap-0.5 text-[11px] font-bold text-[var(--muted)]">
                          <Lock size={12} weight="bold" aria-hidden="true" /> {it.unlock}
                        </span>
                      ) : (
                        <span className="text-[11px] font-bold text-[var(--muted)]">
                          {it.footprint[0]}×{it.footprint[1]}
                        </span>
                      )}
                    </span>
                    <span className="truncate font-display text-[15px] font-bold capitalize">{it.name}</span>
                    <span className="flex flex-wrap gap-1">
                      {Object.entries(it.cost).map(([t, n]) => (
                        <span key={t} className="rounded-full px-1.5 text-[11px] font-bold" style={{ background: `color-mix(in srgb, ${themes.find((x) => x.id === t)?.color} 22%, var(--panel))` }}>
                          {n} {themes.find((x) => x.id === t)?.name}
                        </span>
                      ))}
                    </span>
                    <span className="text-[11px] text-[var(--muted)]">{it.placement === "any" ? "anywhere" : it.placement}</span>
                  </button>
                );
              })}
        </div>
      </motion.div>
    </>
  );
}
