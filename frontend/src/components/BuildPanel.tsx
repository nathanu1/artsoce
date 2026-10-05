import { ArrowClockwise, ArrowCounterClockwise, ArrowsClockwise, Check, Copy, Cursor, FloppyDisk, Lock, PaintBucket, Stack, Trash, X } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { draftCost, dropPlacement, push, redo, replace, shownItems, templateOps, undo } from "../lib/build";
import { iconByName } from "../lib/icons";
import { failureBody, listOf, MOD, plural, sentence } from "../lib/text";
import { useTown } from "../store";
import type { CatalogItem, Tile } from "../types";
import { Button, IconButton, Kbd, ThemeChip } from "./ui";

const CATEGORIES = [
  { id: "all", label: "All" },
  { id: "furniture", label: "Furniture" },
  { id: "decor", label: "Decor" },
  { id: "garden", label: "Garden" },
  { id: "structure", label: "Structures" },
  { id: "templates", label: "Templates" },
] as const;

type SceneLike = { viewCenter: () => Tile; focus: (t: Tile) => void };
const scene = () => (window as unknown as { __town?: SceneLike }).__town;

export function BuildPanel() {
  const info = useTown((s) => s.info)!;
  const game = useTown((s) => s.poll?.game);
  const st = useTown();
  const reduce = useReducedMotion();
  const [cat, setCat] = useState<(typeof CATEGORIES)[number]["id"]>("all");
  const [paintOpen, setPaintOpen] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savingBusy, setSavingBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const paintBtn = useRef<HTMLButtonElement>(null);
  const level = game?.pulse.level ?? 1;
  const themes = info.content.themes;
  const catalog = useMemo(() => new Map(info.content.items.map((i) => [i.id, i])), [info]);
  const cost = draftCost(st.draft.ops, catalog);
  const check = st.check;
  const changes = st.draft.ops.length;
  const lastVerdict = check?.verdicts.length ? check.verdicts[check.verdicts.length - 1] : null;
  const lastFeedback = check?.feedback.length ? check.feedback[check.feedback.length - 1] : null;
  const shown = shownItems(game?.items ?? [], st.draft.ops);
  const picked = shown.find((i) => i.key === st.picked) ?? null;
  const templates = [...info.content.templates, ...(game?.user_templates ?? [])];
  const items = info.content.items.filter((i) => cat === "all" || i.category === cat);
  const placing = (st.tool === "place" && !!st.catalogId) || (st.tool === "template" && !!st.templateId);

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
    paintBtn.current?.focus();
    if (picked) {
      if (picked.committedId) st.setBuild({ draft: push(st.draft, [{ op: "paint", item_id: picked.committedId, paint }]) });
      else if (picked.opIndex !== null) st.setBuild({ draft: replace(st.draft, st.draft.ops.map((op, i) => (i === picked.opIndex ? { ...op, paint } : op))) });
    } else st.setBuild({ paint });
  };

  /** Place the current item or template at a tile (the keyboard twin of clicking the town). */
  const placeAt = (t: Tile) => {
    const s = useTown.getState();
    if (s.tool === "place" && s.catalogId) s.setBuild({ draft: push(s.draft, [{ op: "place", catalog_id: s.catalogId, x: t[0], y: t[1], rot: s.rot, paint: s.paint }]) });
    else if (s.tool === "template" && s.templateId) {
      const tpl = templates.find((q) => q.id === s.templateId);
      if (tpl) s.setBuild({ draft: push(s.draft, templateOps(tpl, t[0], t[1])) });
    }
  };

  const leave = () => {
    st.resetBuild();
    st.setMode("play");
  };

  const done = async () => {
    if (!changes) return leave();
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
      leave();
    } catch (e) {
      st.toast({ tone: "warn", title: "Could not save the build", body: failureBody(e) });
    } finally {
      setBusy(false);
    }
  };

  const saveTemplate = async () => {
    const name = (saving ?? "").trim();
    const placed = shown.filter((i) => i.draft || i.key === st.picked);
    if (!placed.length) return setSaveError("Place something first, then save it as a template.");
    if (!name) return setSaveError("Give the template a name.");
    setSaveError(null);
    setSavingBusy(true);
    const x0 = Math.min(...placed.map((p) => p.x));
    const y0 = Math.min(...placed.map((p) => p.y));
    try {
      const ack = await api.action("save_template", { name, parts: placed.map((p) => ({ item: p.catalog_id, dx: p.x - x0, dy: p.y - y0, rot: p.rot, paint: p.paint })) });
      st.addPending(ack.seq, "save_template");
      st.toast({ tone: "good", title: `Saved “${name}”`, body: "Find it under Templates." });
      setSaving(null);
    } catch (e) {
      setSaveError(failureBody(e));
    } finally {
      setSavingBusy(false);
    }
  };

  // an unsent draft lives only in this tab: warn before the page goes away
  useEffect(() => {
    if (!changes) return;
    const onUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onUnload);
    return () => window.removeEventListener("beforeunload", onUnload);
  }, [changes]);

  // keyboard: shortcuts, plus arrows to move the placement cursor and P (or Enter) to place
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target?.closest("input, textarea, select")) return;
      const k = e.key.toLowerCase();
      if ((e.metaKey || e.ctrlKey) && !e.altKey && k === "z") {
        e.preventDefault();
        st.setBuild({ draft: e.shiftKey ? redo(st.draft) : undo(st.draft) });
        return;
      }
      if ((e.metaKey || e.ctrlKey) && !e.altKey && k === "y") {
        e.preventDefault();
        st.setBuild({ draft: redo(st.draft) });
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return; // browser shortcuts (reload, bookmark) stay intact
      const onControl = !!target?.closest("button, a, [role=tab]");
      if (placing && k.startsWith("arrow") && !target?.closest("[role=tab]")) {
        e.preventDefault();
        const from: Tile = st.hover ?? scene()?.viewCenter() ?? [70, 50];
        const step: Record<string, Tile> = { arrowup: [0, -1], arrowdown: [0, 1], arrowleft: [-1, 0], arrowright: [1, 0] };
        const next: Tile = [from[0] + step[k][0], from[1] + step[k][1]];
        st.setBuild({ hover: next });
        const c = scene()?.viewCenter();
        if (c && Math.abs(c[0] - next[0]) + Math.abs(c[1] - next[1]) > 8) scene()?.focus(next);
        return;
      }
      if (placing && st.hover && (k === "p" || (k === "enter" && !onControl))) {
        e.preventDefault();
        placeAt(st.hover);
        return;
      }
      if (k === "r") rotate();
      else if (k === "delete" || k === "backspace") remove();
      else if (k === "d") duplicate();
      else if (k === "escape") {
        if (paintOpen) {
          setPaintOpen(false);
          paintBtn.current?.focus();
        } else if (confirmCancel) setConfirmCancel(false);
        else st.setBuild({ tool: "select", catalogId: null, templateId: null, picked: null });
      }
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
      const lovers = (lastFeedback.loved_by ?? []).map((id) => info.residents.find((r) => r.id === id)?.first_name).filter((n): n is string => !!n);
      if (lovers.length) bits.push(`${listOf(lovers)} ${lovers.length > 1 ? "love" : "loves"} ${themes.find((t) => t.id === lastFeedback.theme)?.name}.`);
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
        <h1 className="font-display text-lg font-bold">Build and Decorate</h1>
        {confirmCancel ? (
          <>
            <p className="text-sm font-semibold">Discard {plural(changes, "change")}?</p>
            <div className="ml-auto flex gap-2">
              <Button tone="ghost" onClick={() => setConfirmCancel(false)} autoFocus>
                Keep Building
              </Button>
              <Button tone="danger" icon={Trash} onClick={leave}>
                Discard
              </Button>
            </div>
          </>
        ) : (
          <>
            <span className="text-sm text-[var(--muted)] tabular">
              {changes ? plural(changes, "change") : "Pick something below"}
              {Object.keys(cost).length ? ", costs " : ""}
            </span>
            {Object.entries(cost).map(([t, n]) => (
              <ThemeChip key={t} theme={themes.find((x) => x.id === t)} size="sm">{`${n} ${themes.find((x) => x.id === t)?.name}`}</ThemeChip>
            ))}
            <div className="ml-auto flex gap-2">
              <Button tone="ghost" icon={X} onClick={() => (changes ? setConfirmCancel(true) : leave())}>
                Cancel
              </Button>
              <Button tone="primary" icon={Check} onClick={done} disabled={busy}>
                {busy ? "Building…" : changes ? "Build It" : "Done"}
              </Button>
            </div>
          </>
        )}
      </motion.div>

      {/* tool rail: a column on the left, a row under the top bar on phones */}
      <div
        className="pointer-events-auto panel absolute left-3 top-[124px] flex max-w-[calc(100vw-1.5rem)] gap-1.5 overflow-x-auto p-1.5 sm:left-4 sm:top-1/2 sm:-translate-y-1/2 sm:flex-col sm:overflow-visible"
        role="group"
        aria-label="Build tools"
      >
        <IconButton label="Select and Move (Esc)" icon={Cursor} pressed={st.tool === "select"} onClick={() => st.setBuild({ tool: "select", catalogId: null, templateId: null })} />
        <IconButton label="Rotate (R)" icon={ArrowsClockwise} onClick={rotate} />
        <IconButton ref={paintBtn} label="Paint" icon={PaintBucket} active={paintOpen} aria-expanded={paintOpen} aria-controls="paint-picker" onClick={() => setPaintOpen((v) => !v)} />
        <IconButton label="Duplicate (D)" icon={Copy} onClick={duplicate} disabled={!picked} />
        <IconButton label="Remove (Delete)" icon={Trash} onClick={remove} disabled={!picked} />
        <span className="mx-1 w-px shrink-0 bg-[var(--line)] sm:mx-0 sm:my-1 sm:h-px sm:w-auto" aria-hidden="true" />
        <IconButton label={`Undo (${MOD}+Z)`} icon={ArrowCounterClockwise} onClick={() => st.setBuild({ draft: undo(st.draft) })} disabled={!st.draft.undo.length} />
        <IconButton label={`Redo (${MOD}+Shift+Z)`} icon={ArrowClockwise} onClick={() => st.setBuild({ draft: redo(st.draft) })} disabled={!st.draft.redo.length} />
        <IconButton
          label="Save as Template"
          icon={FloppyDisk}
          active={saving !== null}
          aria-expanded={saving !== null}
          onClick={() => {
            setSaveError(null);
            setSaving(saving === null ? "" : null);
          }}
        />
      </div>

      {paintOpen ? (
        <div id="paint-picker" className="pointer-events-auto panel absolute left-3 top-[184px] grid grid-cols-3 gap-2 p-3 sm:left-[76px] sm:top-1/2 sm:-translate-y-1/2" role="group" aria-label="Paints">
          {info.content.paints.map((p) => (
            <button key={p.id} type="button" onClick={() => applyPaint(p.id)} className="flex flex-col items-center gap-1 rounded-2xl p-1.5 transition-colors hover:bg-[var(--panel-hover)]" aria-pressed={st.paint === p.id}>
              <span className="size-8 rounded-full ring-2 ring-[var(--line)]" style={{ background: p.hex }} aria-hidden="true" />
              <span className="text-[11px] font-bold">{p.name}</span>
            </button>
          ))}
        </div>
      ) : null}

      {saving !== null ? (
        <form
          className="pointer-events-auto panel absolute left-3 top-[184px] flex max-w-[min(92vw,360px)] flex-col gap-1.5 p-2 sm:left-[76px] sm:top-[calc(50%+40px)]"
          onSubmit={(e) => {
            e.preventDefault();
            void saveTemplate();
          }}
        >
          <div className="flex gap-2">
            <label htmlFor="template-name" className="sr-only">
              Template name
            </label>
            <input
              id="template-name"
              name="template"
              autoComplete="off"
              maxLength={40}
              value={saving}
              aria-invalid={!!saveError}
              aria-describedby={saveError ? "template-error" : undefined}
              onChange={(e) => setSaving(e.target.value)}
              placeholder="Cozy corner…"
              className="min-h-10 w-44 min-w-0 rounded-2xl border-2 border-[var(--line)] bg-[var(--panel)] px-3 text-[15px] placeholder:text-[var(--muted)]"
            />
            <Button type="submit" tone="primary" disabled={savingBusy}>
              {savingBusy ? "Saving…" : "Save Template"}
            </Button>
          </div>
          {saveError ? (
            <p id="template-error" className="px-1 text-sm font-semibold text-[#a3261c] dark:text-[#ffb4ab]">
              {saveError}
            </p>
          ) : null}
        </form>
      ) : null}

      {/* verdict for what is under the cursor */}
      <div className="pointer-events-none absolute left-1/2 top-[176px] w-[min(92vw,520px)] -translate-x-1/2 text-center sm:top-[92px]" aria-live="polite">
        {status ? (
          <p
            className={`mx-auto line-clamp-2 w-fit max-w-full rounded-2xl px-4 py-1.5 font-display text-sm font-semibold shadow ${status.ok ? "bg-[#e3f5e6] text-[#1f5a2b] dark:bg-[#21402a] dark:text-[#cdeed5]" : "bg-[#ffe3e0] text-[#8a1f17] dark:bg-[#4a2a2e] dark:text-[#ffd6d2]"}`}
          >
            {status.text}
          </p>
        ) : null}
      </div>

      {/* catalog tray */}
      <motion.div initial={reduce ? false : { y: 24, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="pointer-events-auto panel absolute bottom-3 left-1/2 w-[min(96vw,1040px)] -translate-x-1/2 p-3 sm:bottom-4">
        <div className="mb-1 flex items-center gap-1 overflow-x-auto px-0.5 py-1" role="group" aria-label="Catalog categories">
          {CATEGORIES.map((c) => (
            <button
              key={c.id}
              type="button"
              aria-pressed={cat === c.id}
              onClick={() => setCat(c.id)}
              className={`whitespace-nowrap rounded-full px-3 py-1 font-display text-sm font-semibold transition-colors ${cat === c.id ? "bg-sun text-[#2a2838]" : "hover:bg-[var(--panel-hover)]"}`}
            >
              {c.label}
            </button>
          ))}
          <span className="ml-auto hidden gap-2 whitespace-nowrap text-xs text-[var(--muted)] lg:flex">
            <span>
              <Kbd>R</Kbd> rotate
            </span>
            <span>
              <Kbd>D</Kbd> duplicate
            </span>
            <span>
              <Kbd>Arrows</Kbd> move, <Kbd>P</Kbd> place
            </span>
            <span>
              <Kbd>{`${MOD} Z`}</Kbd> undo
            </span>
          </span>
        </div>
        <div className="scroll-thin flex gap-2 overflow-x-auto px-0.5 pb-1 pt-1">
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
                    className={`flex w-40 shrink-0 flex-col gap-1 rounded-3xl p-3 text-left transition-colors ${st.templateId === t.id ? "bg-sun/30 ring-2 ring-sun" : "bg-[var(--panel-2)] hover:bg-[var(--panel-hover)]"} disabled:opacity-50`}
                  >
                    <span className="flex min-w-0 items-start gap-1.5 font-display font-bold">
                      <Stack size={18} weight="fill" aria-hidden="true" className="mt-0.5 shrink-0" />
                      <span className="line-clamp-2 break-words">{t.name}</span>
                    </span>
                    <span className="text-xs text-[var(--muted)]">{plural(t.parts.length, "piece")}</span>
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
                    aria-label={`${it.name}, ${it.footprint[0]} by ${it.footprint[1]}, costs ${listOf(Object.entries(it.cost).map(([t, n]) => `${n} ${themes.find((x) => x.id === t)?.name}`))}, ${it.placement === "any" ? "anywhere" : it.placement}${locked ? `, unlocks at Town Pulse level ${it.unlock}` : ""}`}
                    title={locked ? `Unlocks at Town Pulse level ${it.unlock}` : undefined}
                    className={`flex w-36 shrink-0 flex-col gap-1 rounded-3xl p-3 text-left transition-colors ${st.catalogId === it.id ? "bg-sun/30 ring-2 ring-sun" : "bg-[var(--panel-2)] hover:bg-[var(--panel-hover)]"} disabled:opacity-50`}
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
