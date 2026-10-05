import { ChatCircleDots, Crosshair, Gift as GiftIcon, PaperPlaneRight, Question, SealCheck, Wind, X } from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { activityIcon, activityLabel, iconByName } from "../lib/icons";
import { formatTime, hourOf } from "../lib/time";
import { useTown } from "../store";
import type { ResidentDetail } from "../types";
import { Button, Hearts, IconButton, Portrait, ThemeChip } from "./ui";
import { placeOfAddress, placeOfLabel } from "../lib/places";

async function send(kind: string, payload: Record<string, unknown>, agent?: string) {
  const st = useTown.getState();
  try {
    const ack = await api.action(kind, payload);
    st.addPending(ack.seq, kind, agent);
  } catch (e) {
    st.toast({ tone: "warn", title: "That did not work", body: (e as Error).message });
  }
}

export function ResidentCard({ id }: { id: string }) {
  const info = useTown((s) => s.info)!;
  const poll = useTown((s) => s.poll);
  const frame = useTown((s) => s.frame);
  const pending = useTown((s) => s.pending);
  const select = useTown((s) => s.select);
  const setChat = useTown((s) => s.setChat);
  const chatWith = useTown((s) => s.chatWith);
  const setFollow = useTown((s) => s.setFollow);
  const follow = useTown((s) => s.follow);
  const focusOn = useTown((s) => s.focusOn);
  const reduce = useReducedMotion();
  const [giftOpen, setGiftOpen] = useState(false);
  const [whisper, setWhisper] = useState<string | null>(null);
  const r = info.residents.find((x) => x.id === id);
  if (!r) return null;
  const a = frame?.agents[id];
  const game = poll?.game;
  const friendship = game?.friendship[id] ?? 0;
  const themes = info.content.themes;
  const req = game?.requests.find((q) => q.agent_id === id && q.status !== "fulfilled");
  const schedule = poll?.schedules?.[id];
  const now = poll?.clock?.time;
  const busy = Object.values(pending).some((p) => p.agent === id);
  const thinking = !!poll?.thinking[id];
  const replay = !!poll?.replay;
  const unavailable = a?.sleeping ? `${r.first_name} is asleep` : a?.partner ? `${r.first_name} is talking with ${a.partner}` : null;
  const Act = activityIcon(a?.activity ?? "");
  const place = placeOfAddress(a?.address);

  return (
    <motion.section
      key={id}
      initial={reduce ? false : { y: 24, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={reduce ? undefined : { y: 24, opacity: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 30 }}
      className="pointer-events-auto panel absolute bottom-3 left-1/2 w-[min(94vw,720px)] -translate-x-1/2 p-4 sm:bottom-4"
      aria-label={`${r.name}, resident`}
    >
      <div className="flex items-start gap-3">
        <Portrait look={r.look} size={56} ring={themes.find((t) => t.id === r.loves[0])?.color} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h2 className="font-display text-xl font-bold">{r.name}</h2>
            <span className="text-sm font-bold text-[var(--muted)]">{r.age}</span>
            <Hearts value={friendship} />
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            {r.loves.length ? r.loves.map((t) => <ThemeChip key={t} theme={themes.find((x) => x.id === t)} size="sm" />) : <span className="text-xs text-[var(--muted)]">No strong favorites yet</span>}
          </div>
          <p className="mt-2 flex items-center gap-1.5 text-[15px] font-semibold">
            <Act size={18} weight="fill" aria-hidden="true" />
            <span className="min-w-0 truncate">{thinking ? `${r.first_name} is thinking…` : a?.sleeping ? "Sleeping" : activityLabel(a?.activity ?? "")}</span>
          </p>
          {place ? <p className="truncate text-sm text-[var(--muted)]">{place}</p> : null}
        </div>
        <IconButton label="Close" icon={X} onClick={() => select(null)} />
      </div>

      {schedule?.blocks.length ? (
        <div className="scroll-thin mt-3 flex gap-1 overflow-x-auto pb-1" aria-label={`${r.first_name}'s plan for today`}>
          {schedule.blocks.map((b) => {
            const start = hourOf(b.start);
            const nowH = now ? hourOf(now) : 0;
            const current = nowH >= start && nowH < start + b.minutes / 60;
            return (
              <div key={b.start} className={`min-w-[96px] shrink-0 rounded-2xl px-2.5 py-1.5 text-xs ${current ? "bg-sun text-[#2a2838]" : "bg-[var(--panel-2)]"}`}>
                <div className="font-display font-bold tabular">{formatTime(b.start)}</div>
                <div className="line-clamp-2 font-semibold">{activityLabel(b.description)}</div>
              </div>
            );
          })}
        </div>
      ) : null}

      {req ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-2xl bg-[var(--panel-2)] px-3 py-2">
          {req.status === "ready" ? <SealCheck size={20} weight="fill" color="#3f9a50" aria-hidden="true" /> : <Question size={20} weight="fill" color="#f2792b" aria-hidden="true" />}
          <p className="min-w-0 flex-1 text-sm">
            <span className="font-bold">Wishes for {req.wish}</span> <span className="text-[var(--muted)]">at {placeOfLabel(req.place_label)}</span>
          </p>
          <ThemeChip theme={themes.find((t) => t.id === req.theme)} size="sm" />
          {req.status === "ready" && !replay ? (
            <Button tone="primary" disabled={!!unavailable || busy} onClick={() => send("deliver", { request: req.id }, id)}>
              Deliver
            </Button>
          ) : null}
        </div>
      ) : null}

      {replay ? null : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button tone="primary" icon={ChatCircleDots} onClick={() => setChat(chatWith === id ? null : id)} disabled={!!unavailable} aria-expanded={chatWith === id} data-chat-button="">
            Chat
          </Button>
          <Button icon={GiftIcon} onClick={() => setGiftOpen((v) => !v)} disabled={!!unavailable || busy} aria-expanded={giftOpen}>
            Give a Gift
          </Button>
          {!req ? (
            <Button icon={Question} onClick={() => send("ask_request", { agent: id }, id)} disabled={!!unavailable || busy}>
              Ask for a Wish
            </Button>
          ) : null}
          <Button
            tone="ghost"
            icon={Crosshair}
            aria-pressed={follow === id}
            onClick={() => {
              if (follow === id) setFollow(null);
              else {
                setFollow(id);
                if (a && a.x !== null && a.y !== null) focusOn([a.x, a.y]);
              }
            }}
          >
            {follow === id ? "Following" : "Follow"}
          </Button>
          <Button tone="ghost" icon={Wind} onClick={() => setWhisper(whisper === null ? "" : null)} aria-expanded={whisper !== null} title="Research: add an inner-voice memory (paper §3.1)">
            Whisper
          </Button>
          {unavailable ? <span className="text-sm font-semibold text-[var(--muted)]">{unavailable}</span> : null}
        </div>
      )}

      <AnimatePresence>
        {giftOpen ? (
          <motion.div initial={reduce ? false : { height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={reduce ? undefined : { height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {info.content.gifts.map((g) => {
                const theme = themes.find((t) => t.id === g.theme)!;
                const have = game?.theme_counts[g.theme] ?? 0;
                const Icon = iconByName(g.icon);
                const loved = r.loves.includes(g.theme);
                return (
                  <button
                    key={g.id}
                    type="button"
                    disabled={have < g.cost}
                    onClick={() => {
                      setGiftOpen(false);
                      void send("gift", { agent: id, gift: g.id }, id);
                    }}
                    className="flex items-center gap-2 rounded-2xl bg-[var(--panel-2)] px-3 py-2 text-left transition-colors hover:bg-[var(--panel-3)] disabled:opacity-45"
                  >
                    <Icon size={22} weight="fill" color={theme.color} aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-bold capitalize">{g.name}</span>
                      <span className="block text-xs text-[var(--muted)]">
                        1 {theme.name} motif{loved ? `, ${r.first_name} loves ${theme.name}` : ""}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {whisper !== null ? (
        <form
          className="mt-3 flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!whisper.trim()) return;
            void send("whisper", { agent: id, text: whisper.trim() }, id);
            setWhisper(null);
          }}
        >
          <label htmlFor="whisper" className="sr-only">
            Inner voice for {r.first_name}
          </label>
          <input
            id="whisper"
            name="whisper"
            autoComplete="off"
            value={whisper}
            onChange={(e) => setWhisper(e.target.value)}
            placeholder={`You want to visit the library tomorrow…`}
            className="min-h-10 flex-1 rounded-2xl border-2 border-[var(--line)] bg-[var(--panel)] px-3 text-[15px] placeholder:text-[var(--muted)]"
          />
          <Button type="submit" tone="soft">
            Whisper
          </Button>
        </form>
      ) : null}
    </motion.section>
  );
}

export function ChatSheet({ id }: { id: string }) {
  const info = useTown((s) => s.info)!;
  const pending = useTown((s) => s.pending);
  const feed = useTown((s) => s.feed);
  const setChat = useTown((s) => s.setChat);
  const reduce = useReducedMotion();
  const [detail, setDetail] = useState<ResidentDetail | null>(null);
  const [text, setText] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const r = info.residents.find((x) => x.id === id)!;
  const waiting = Object.values(pending).some((p) => p.agent === id);

  useEffect(() => {
    let alive = true;
    api
      .resident(id)
      .then((d) => alive && setDetail(d))
      .catch(() => alive && setDetail({ id, exchanges: [], conversations: [] }));
    return () => {
      alive = false;
    };
  }, [id]);

  const lines = useMemo(() => {
    const out: { who: "you" | "them"; text: string; key: string }[] = [];
    const seen = new Set<number>();
    for (const ex of detail?.exchanges ?? []) {
      seen.add(ex.id);
      if (ex.builder_line) out.push({ who: "you", text: ex.builder_line, key: `d${ex.id}a` });
      if (ex.reply) out.push({ who: "them", text: ex.reply, key: `d${ex.id}b` });
      if (ex.kind === "rejected" && ex.reason) out.push({ who: "them", text: `(${ex.reason})`, key: `d${ex.id}c` });
    }
    for (const ev of feed) {
      if (ev.agent_id !== id || !["chat", "gift", "delivered", "request"].includes(ev.kind)) continue;
      if (typeof ev.id === "number" && seen.has(ev.id as number)) continue;
      if (ev.builder_line) out.push({ who: "you", text: String(ev.builder_line), key: `f${ev.seq}a` });
      if (ev.reply) out.push({ who: "them", text: String(ev.reply), key: `f${ev.seq}b` });
    }
    return out;
  }, [detail, feed, id]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: reduce ? "auto" : "smooth" });
  }, [lines.length, waiting, reduce]);

  return (
    <motion.aside
      initial={reduce ? false : { x: 40, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={reduce ? undefined : { x: 40, opacity: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="pointer-events-auto panel absolute inset-x-3 bottom-3 flex max-h-[70dvh] flex-col overflow-hidden sm:inset-x-auto sm:bottom-auto sm:right-4 sm:top-24 sm:max-h-[calc(100dvh-12rem)] sm:w-[360px]"
      aria-label={`Chat with ${r.first_name}`}
      onKeyDown={(e) => {
        if (e.key !== "Escape") return;
        e.stopPropagation();
        setChat(null);
        document.querySelector<HTMLButtonElement>("[data-chat-button]")?.focus();
      }}
    >
      <div className="flex items-center gap-2 border-b-2 border-[var(--line)] px-3 py-2">
        <Portrait look={r.look} size={32} />
        <h2 className="flex-1 font-display text-lg font-bold">Chat with {r.first_name}</h2>
        <IconButton label="Close chat" icon={X} onClick={() => setChat(null)} />
      </div>
      <div ref={listRef} className="scroll-thin flex-1 space-y-2 overflow-y-auto overscroll-contain p-3" aria-live="polite">
        {!lines.length && !waiting ? <p className="text-sm text-[var(--muted)]">Say hello. {r.first_name} remembers what you talk about.</p> : null}
        {lines.map((l) => (
          <p key={l.key} className={`max-w-[85%] break-words rounded-2xl px-3 py-2 text-[15px] ${l.who === "you" ? "ml-auto bg-sun/25" : "bg-[var(--panel-2)]"}`}>
            {l.text}
          </p>
        ))}
        {waiting ? <p className="w-fit rounded-2xl bg-[var(--panel-2)] px-3 py-2 text-[15px] text-[var(--muted)]">{r.first_name} is thinking…</p> : null}
      </div>
      <form
        className="flex items-center gap-2 border-t-2 border-[var(--line)] p-2"
        onSubmit={(e) => {
          e.preventDefault();
          const msg = text.trim();
          if (!msg) return;
          setText("");
          void send("chat", { agent: id, text: msg }, id);
        }}
      >
        <label htmlFor="chat-input" className="sr-only">
          Message to {r.first_name}
        </label>
        <input
          id="chat-input"
          name="message"
          autoComplete="off"
          maxLength={400}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={`Ask ${r.first_name} about their day…`}
          className="min-h-11 min-w-0 flex-1 rounded-2xl border-2 border-[var(--line)] bg-[var(--panel)] px-3 text-[15px] placeholder:text-[var(--muted)]"
        />
        <button type="submit" disabled={!text.trim()} aria-label="Send" className="inline-flex size-11 items-center justify-center rounded-full bg-sun text-[#2a2838] transition-transform active:scale-95 disabled:opacity-40">
          <PaperPlaneRight size={20} weight="fill" aria-hidden="true" />
        </button>
      </form>
    </motion.aside>
  );
}
