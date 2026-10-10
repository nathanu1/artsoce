import { ArrowLeft, Flask, Warning, X } from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../api";
import { formatDayTime, formatDecimal, formatNumber, formatTime } from "../lib/time";
import { DEMO } from "../demo/flag";
import { replaceQuery, viewHref } from "../lib/route";
import { TabList, tabPanelProps } from "./Tabs";
import { Button, IconButton } from "./ui";

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const TABS = ["memories", "retrieval", "plans", "reflections", "diffusion", "provenance"] as const;
type Tab = (typeof TABS)[number];
const TAB_ITEMS = TABS.map((id) => ({ id, label: id.charAt(0).toUpperCase() + id.slice(1) }));
const NBSP = " ";
const errorText = "text-[#b3261e] dark:text-[#ffb4ab]";
const SERVER_HINT = "Check that “ga play” (or “ga serve”) is still running, then select Refresh.";

interface Loaded<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/** One research API read. Data from a previous path is never shown under a new one. */
function useResearch<T>(path: string | null, deps: unknown[] = []): Loaded<T> {
  const [state, setState] = useState<Loaded<T> & { path: string | null }>({ path, data: null, error: null, loading: !!path });
  useEffect(() => {
    if (!path) return;
    let alive = true;
    setState((s) => (s.path === path ? { ...s, loading: true } : { path, data: null, error: null, loading: true }));
    api
      .research<T>(path)
      .then((data) => alive && setState({ path, data, error: null, loading: false }))
      .catch((e) => alive && setState({ path, data: null, error: (e as Error).message, loading: false }));
    return () => {
      alive = false;
    };
  }, [path, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  if (state.path !== path) return { data: null, error: null, loading: !!path };
  return state;
}

/** Read and write one query parameter, so every view can be linked and reloaded. */
function useQueryParam(key: string, fallback = ""): [string, (v: string) => void] {
  const [value, setValue] = useState(() => new URLSearchParams(window.location.search).get(key) ?? fallback);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (value && value !== fallback) q.set(key, value);
    else q.delete(key);
    replaceQuery(q);
  }, [key, value, fallback]);
  return [value, setValue];
}

function Problem({ children }: { children: ReactNode }) {
  return <p className={`text-sm ${errorText}`}>{children}</p>;
}

export function Inspector() {
  const run = useResearch<Json>("run");
  const [agent, setAgent] = useQueryParam("agent");
  const [tabParam, setTab] = useQueryParam("tab", "memories");
  const tab: Tab = (TABS as readonly string[]).includes(tabParam) ? (tabParam as Tab) : "memories";
  const [refresh, setRefresh] = useState(0);
  const agents: Json[] = run.data?.agents ?? [];
  useEffect(() => {
    if (!agent && agents.length) setAgent(agents[0].id);
  }, [agent, agents, setAgent]);
  const link = (id: string) => {
    if (DEMO) return viewHref("inspector");
    const q = new URLSearchParams(window.location.search);
    q.set("agent", id);
    return `/inspector?${q.toString()}`;
  };

  return (
    <div className="flex h-full flex-col bg-[var(--panel-2)] text-[var(--text)]">
      <a href="#inspector-main" className="sr-only z-50 rounded-full bg-sun px-4 py-2 font-display font-semibold text-[#2a2838] focus:not-sr-only focus:absolute focus:left-3 focus:top-3">
        Skip to Content
      </a>
      <header className="flex flex-wrap items-center gap-3 border-b-2 border-[var(--line)] bg-[var(--panel)] px-4 py-3">
        <Flask size={24} weight="fill" color="#4a82dd" aria-hidden="true" />
        <h1 className="font-display text-xl font-bold">Research Inspector</h1>
        <span className="rounded-full bg-[var(--panel-2)] px-2.5 py-0.5 font-display text-xs font-bold uppercase">{run.data?.mode ?? "…"}</span>
        <span className="text-sm text-[var(--muted)]" translate="no">
          {run.data?.run_id}
        </span>
        <p className="text-sm text-[var(--muted)]">For the researcher only: nothing on this page is ever sent to residents.</p>
        <div className="ml-auto flex gap-2">
          <Button tone="soft" onClick={() => setRefresh((n) => n + 1)}>
            Refresh
          </Button>
          <a href={viewHref("town")} className="inline-flex min-h-10 items-center gap-2 rounded-full bg-sun px-4 font-display text-[15px] font-semibold text-[#2a2838] transition-[filter] hover:brightness-105">
            <ArrowLeft size={18} weight="bold" aria-hidden="true" /> Back to Town
          </a>
        </div>
      </header>
      {run.error ? (
        <p className={`p-6 ${errorText}`}>
          Could not read the run: {run.error}. {SERVER_HINT}
        </p>
      ) : null}
      {run.data?.mock_llm || run.data?.mock_embeddings ? (
        <p className="flex items-center gap-2 border-b-2 border-[var(--line)] bg-[#fff4d6] px-4 py-2 text-sm text-[#5c4300] dark:bg-[#3a3220] dark:text-[#f3dfa6]" role="note">
          <Warning size={18} weight="fill" aria-hidden="true" className="shrink-0" />
          <span>
            {run.data?.mock_llm ? "This run uses the mock model, so residents’ words are placeholders. " : ""}
            {run.data?.mock_embeddings ? "Relevance comes from mock hash embeddings, a test fixture with no semantic meaning; do not report these retrieval scores as results." : ""}
          </span>
        </p>
      ) : null}
      <div className="flex min-h-0 flex-1">
        <nav className="scroll-thin w-52 shrink-0 overflow-y-auto border-r-2 border-[var(--line)] bg-[var(--panel)] p-2 max-md:hidden" aria-label="Residents">
          {agents.map((a) => (
            <a
              key={a.id}
              href={link(a.id)}
              onClick={(e) => {
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return; // new tab or window
                e.preventDefault();
                setAgent(a.id);
              }}
              aria-current={agent === a.id ? "page" : undefined}
              className={`mb-1 flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-sm font-semibold transition-colors ${agent === a.id ? "bg-sun text-[#2a2838]" : "hover:bg-[var(--panel-hover)]"}`}
            >
              <span className="size-3 shrink-0 rounded-full" style={{ background: a.color }} aria-hidden="true" />
              <span className="truncate">{a.name}</span>
            </a>
          ))}
        </nav>
        <main id="inspector-main" tabIndex={-1} className="flex min-w-0 flex-1 flex-col">
          <div className="flex flex-wrap items-center gap-2 border-b-2 border-[var(--line)] bg-[var(--panel)] px-3 py-1">
            <TabList
              items={TAB_ITEMS}
              value={tab}
              onChange={setTab}
              idPrefix="inspector"
              label="Inspector views"
              className="flex gap-1 overflow-x-auto px-0.5 py-1"
              tabClassName={(on) => `whitespace-nowrap rounded-full px-3.5 py-1.5 font-display text-sm font-semibold transition-colors ${on ? "bg-sun text-[#2a2838]" : "hover:bg-[var(--panel-hover)]"}`}
            />
            {agents.length ? (
              <span className="ml-auto md:hidden">
                <label htmlFor="agent-pick" className="sr-only">
                  Resident
                </label>
                <select id="agent-pick" name="agent" value={agent} onChange={(e) => setAgent(e.target.value)} className="min-h-9 rounded-xl border-2 border-[var(--line)] bg-[var(--panel)] px-2 text-sm text-[var(--text)]">
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </span>
            ) : null}
          </div>
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-4" {...tabPanelProps("inspector", tab)}>
            {run.error ? null : !run.data ? (
              <p className="text-[var(--muted)]">Loading residents…</p>
            ) : !agents.length && tab !== "diffusion" && tab !== "provenance" ? (
              <p className="text-[var(--muted)]">This run has no residents yet.</p>
            ) : tab === "memories" ? (
              <Memories agent={agent} refresh={refresh} />
            ) : tab === "retrieval" ? (
              <Retrieval agent={agent} refresh={refresh} mockEmbeddings={!!run.data?.mock_embeddings} />
            ) : tab === "plans" ? (
              <Plans agent={agent} refresh={refresh} />
            ) : tab === "reflections" ? (
              <Reflections agent={agent} refresh={refresh} />
            ) : tab === "diffusion" ? (
              <Diffusion agents={agents} refresh={refresh} />
            ) : (
              <Provenance agent={agent || null} refresh={refresh} />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

function Card({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="mb-4 rounded-2xl bg-[var(--panel)] p-4 shadow-sm">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h2 className="font-display text-lg font-bold">{title}</h2>
        <div className="ml-auto">{aside}</div>
      </div>
      {children}
    </section>
  );
}

const th = "px-2 py-1.5 text-left text-xs font-bold uppercase tracking-wide text-[var(--muted)]";
const td = "px-2 py-1.5 align-top";

function Memories({ agent, refresh }: { agent: string; refresh: number }) {
  const [kind, setKind] = useQueryParam("kind");
  const [query, setQuery] = useQueryParam("q");
  const [q, setQ] = useState(query);
  const path = agent ? `agent/${encodeURIComponent(agent)}/memories?limit=80${kind ? `&kind=${kind}` : ""}${query ? `&q=${encodeURIComponent(query)}` : ""}` : null;
  const { data, error, loading } = useResearch<Json[]>(path, [refresh]);
  return (
    <Card
      title="Memory Stream"
      aside={
        <form
          className="flex flex-wrap items-center gap-2"
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(q.trim());
          }}
        >
          <label htmlFor="mem-kind" className="sr-only">
            Kind
          </label>
          <select id="mem-kind" name="kind" value={kind} onChange={(e) => setKind(e.target.value)} className="min-h-9 rounded-xl border-2 border-[var(--line)] bg-[var(--panel)] px-2 text-sm text-[var(--text)]">
            <option value="">All kinds</option>
            <option value="observation">Observations</option>
            <option value="reflection">Reflections</option>
            <option value="plan">Plans</option>
          </select>
          <label htmlFor="mem-q" className="sr-only">
            Search memories
          </label>
          <input
            id="mem-q"
            name="q"
            type="search"
            autoComplete="off"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="party…"
            className="min-h-9 w-44 rounded-xl border-2 border-[var(--line)] bg-[var(--panel)] px-2 text-sm placeholder:text-[var(--muted)]"
          />
          <Button type="submit" tone="soft" className="min-h-9">
            Search
          </Button>
        </form>
      }
    >
      {error ? <Problem>{`Could not load memories: ${error}. ${SERVER_HINT}`}</Problem> : null}
      {loading && !data ? <p className="text-[var(--muted)]">Loading…</p> : null}
      {data && !data.length ? <p className="text-[var(--muted)]">No memories match. New memories appear after the next save (about every 5 game minutes).</p> : null}
      {data?.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className={th}>Time</th>
                <th className={th}>Kind</th>
                <th className={`${th} tabular`}>Imp.</th>
                <th className={th}>Description</th>
              </tr>
            </thead>
            <tbody>
              {data.map((m) => (
                <tr key={m.id} className="border-t border-[var(--line)]">
                  <td className={`${td} whitespace-nowrap tabular text-[var(--muted)]`}>{formatDayTime(m.created_at)}</td>
                  <td className={`${td} whitespace-nowrap`}>
                    {m.kind}
                    <span className="block text-xs text-[var(--muted)]" translate="no">
                      {m.origin}
                    </span>
                  </td>
                  <td className={`${td} tabular font-bold`}>{m.importance}</td>
                  <td className={`${td} break-words`}>{m.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  );
}

function Retrieval({ agent, refresh, mockEmbeddings }: { agent: string; refresh: number; mockEmbeddings: boolean }) {
  const list = useResearch<Json[]>(agent ? `agent/${encodeURIComponent(agent)}/traces?limit=60` : null, [refresh]);
  const [id, setId] = useState<string | null>(null);
  const trace = useResearch<Json>(id ? `trace/${encodeURIComponent(id)}` : null);
  useEffect(() => setId(null), [agent]);
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
      <Card title="Retrievals">
        {list.error ? <Problem>{`Could not load retrievals: ${list.error}. ${SERVER_HINT}`}</Problem> : null}
        {list.data?.length ? (
          <ul className="space-y-1">
            {list.data.map((t) => (
              <li key={t.id} className="[contain-intrinsic-size:auto_64px] [content-visibility:auto]">
                <button
                  type="button"
                  aria-pressed={id === t.id}
                  onClick={() => setId(t.id)}
                  className={`w-full rounded-xl px-3 py-2 text-left text-sm transition-colors ${id === t.id ? "bg-sun/25" : "hover:bg-[var(--panel-hover)]"}`}
                >
                  <span className="block text-xs text-[var(--muted)]">
                    {formatTime(t.sim_time)}, <span translate="no">{t.purpose}</span>, {formatNumber(t.delivered)} of {formatNumber(t.candidates)}
                  </span>
                  <span className="line-clamp-2 font-semibold">{t.query}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : list.error ? null : (
          <p className="text-[var(--muted)]">{list.loading ? "Loading…" : "No retrievals recorded yet."}</p>
        )}
      </Card>
      <Card title="Why These Memories">
        {!id ? <p className="text-[var(--muted)]">Pick a retrieval to see recency, importance and relevance for each candidate, as in the paper (§4.1).</p> : null}
        {id && trace.loading ? <p className="text-[var(--muted)]">Loading…</p> : null}
        {id && trace.error ? <Problem>{`Could not load this retrieval: ${trace.error}. ${SERVER_HINT}`}</Problem> : null}
        {trace.data ? (
          <>
            {mockEmbeddings ? (
              <p className="mb-2 rounded-xl bg-[#fff4d6] px-3 py-2 text-xs font-semibold text-[#5c4300] dark:bg-[#3a3220] dark:text-[#f3dfa6]">Relevance below is from mock hash embeddings (a test fixture), not semantic similarity.</p>
            ) : null}
            <p className="mb-2 text-sm">
              <span className="font-bold">Query:</span> {trace.data.query}
            </p>
            <p className="mb-3 text-xs text-[var(--muted)]">
              Weights recency {trace.data.weights?.recency}, importance {trace.data.weights?.importance}, relevance {trace.data.weights?.relevance}. Components are min-max normalized over{" "}
              {formatNumber(trace.data.n_candidates ?? trace.data.candidates?.length ?? 0)} candidates. Faded rows were not delivered.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    <th className={th}>#</th>
                    <th className={th}>Memory</th>
                    <th className={`${th} tabular`}>Rec.</th>
                    <th className={`${th} tabular`}>Imp.</th>
                    <th className={`${th} tabular`}>Rel.</th>
                    <th className={`${th} tabular`}>Score</th>
                  </tr>
                </thead>
                <tbody>
                  {(trace.data.candidates ?? []).slice(0, 20).map((c: Json) => (
                    <tr key={c.id} className={`border-t border-[var(--line)] ${c.delivered ? "" : "opacity-55"}`}>
                      <td className={`${td} tabular`}>
                        {c.rank}
                        {c.delivered ? null : <span className="sr-only"> (not delivered)</span>}
                      </td>
                      <td className={`${td} break-words`}>{c.description}</td>
                      {(["recency", "importance", "relevance"] as const).map((k) => (
                        <td key={k} className={`${td} tabular`}>
                          <span className="block font-bold">{formatDecimal(c.normalized?.[k] ?? 0)}</span>
                          <span className="block h-1 rounded-full" style={{ width: `${Math.round((c.normalized?.[k] ?? 0) * 44)}px`, background: k === "recency" ? "#4a82dd" : k === "importance" ? "#e2629b" : "#58b368" }} aria-hidden="true" />
                        </td>
                      ))}
                      <td className={`${td} tabular font-bold`}>{formatDecimal(c.score ?? 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {trace.data.explain ? <p className="mt-3 rounded-xl bg-[var(--panel-2)] p-3 text-sm">{trace.data.explain}</p> : null}
          </>
        ) : null}
      </Card>
    </div>
  );
}

function Plans({ agent, refresh }: { agent: string; refresh: number }) {
  const { data, error } = useResearch<Json>(agent ? `agent/${encodeURIComponent(agent)}` : null, [refresh]);
  if (error) return <Problem>{`Could not load plans: ${error}. ${SERVER_HINT}`}</Problem>;
  if (!data) return <p className="text-[var(--muted)]">Loading…</p>;
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title={data.day ? `Plan for ${data.day}` : "Plan for Today"}>
        {data.day_plan ? <p className="mb-3 text-sm text-[var(--muted)]">{data.day_plan.description}</p> : null}
        {(data.hours ?? []).length ? null : <p className="text-sm text-[var(--muted)]">No plan yet. Residents plan their day when they wake up.</p>}
        <ol className="space-y-2">
          {(data.hours ?? []).map((h: Json) => (
            <li key={h.id} className="rounded-xl bg-[var(--panel-2)] p-2.5">
              <p className="text-sm font-bold">
                <span className="tabular">{formatTime(h.start)}</span> {h.description}{" "}
                <span className="font-normal text-[var(--muted)]">
                  ({formatNumber(h.duration_min)}
                  {NBSP}min, {h.status})
                </span>
              </p>
              {h.tasks?.length ? (
                <ul className="mt-1 space-y-0.5 pl-3 text-sm">
                  {h.tasks.map((t: Json) => (
                    <li key={t.id}>
                      <span className="tabular text-[var(--muted)]">{formatTime(t.start)}</span> {t.description}{" "}
                      <span className="text-[var(--muted)]">
                        ({formatNumber(t.duration_min)}
                        {NBSP}min)
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ol>
      </Card>
      <Card title="State">
        <dl className="grid grid-cols-2 gap-2 text-sm">
          {Object.entries(data.memory_counts ?? {}).map(([k, v]) => (
            <div key={k} className="rounded-xl bg-[var(--panel-2)] px-3 py-2">
              <dt className="text-xs font-bold text-[var(--muted)]">{k} memories</dt>
              <dd className="font-display text-xl font-bold tabular">{formatNumber(Number(v))}</dd>
            </div>
          ))}
          <div className="rounded-xl bg-[var(--panel-2)] px-3 py-2">
            <dt className="text-xs font-bold text-[var(--muted)]">Reflection trigger</dt>
            <dd className="font-display text-xl font-bold tabular">
              {formatNumber(Math.round(data.state?.reflection_accumulator ?? 0))} / {formatNumber(data.state?.reflection_threshold ?? 0)}
            </dd>
          </div>
        </dl>
        <h3 className="mt-4 font-display font-bold">Places {data.identity?.first_name} Knows</h3>
        <ul className="mt-1 space-y-1 text-sm">
          {(data.known_places ?? []).map((p: Json) => (
            <li key={p.sector}>
              <span className="font-semibold">{p.sector}</span> <span className="text-[var(--muted)]">{p.arenas.join(", ")}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function Reflections({ agent, refresh }: { agent: string; refresh: number }) {
  const { data, error, loading } = useResearch<Json[]>(agent ? `agent/${encodeURIComponent(agent)}/reflections` : null, [refresh]);
  const [open, setOpen] = useState<string | null>(null);
  const tree = useResearch<Json>(open ? `evidence/${encodeURIComponent(open)}` : null);
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Reflections">
        {error ? <Problem>{`Could not load reflections: ${error}. ${SERVER_HINT}`}</Problem> : null}
        {loading && !data ? <p className="text-[var(--muted)]">Loading…</p> : null}
        {data?.length ? (
          <ul className="space-y-1">
            {data.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  aria-pressed={open === r.id}
                  onClick={() => setOpen(r.id)}
                  className={`w-full rounded-xl px-3 py-2 text-left text-sm transition-colors ${open === r.id ? "bg-sun/25" : "hover:bg-[var(--panel-hover)]"}`}
                >
                  <span className="block text-xs text-[var(--muted)]">
                    {formatTime(r.created_at)}, depth {r.depth}, {formatNumber(r.evidence.length)} cited
                  </span>
                  <span className="font-semibold">{r.description}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : data ? (
          <p className="text-[var(--muted)]">No reflections yet. They happen when the importance of new memories adds up past the threshold (§4.2).</p>
        ) : null}
      </Card>
      <Card title="Evidence Tree">
        {tree.error ? <Problem>{`Could not load the evidence: ${tree.error}. ${SERVER_HINT}`}</Problem> : null}
        {tree.data ? <EvidenceNode node={tree.data} /> : open ? tree.error ? null : <p className="text-[var(--muted)]">Loading…</p> : <p className="text-[var(--muted)]">Pick a reflection to see what it cites.</p>}
      </Card>
    </div>
  );
}

function EvidenceNode({ node }: { node: Json }) {
  return (
    <div className="border-l-2 border-[var(--line)] pl-3">
      <p className="text-sm">
        <span className="font-bold">{node.kind}</span>{" "}
        <span className="text-[var(--muted)]">
          (<span translate="no">{node.origin}</span>, importance {node.importance})
        </span>
      </p>
      <p className="mb-2 text-sm">{node.description}</p>
      {(node.evidence ?? []).map((e: Json) => (
        <EvidenceNode key={e.id} node={e} />
      ))}
    </div>
  );
}

function Diffusion({ agents, refresh }: { agents: Json[]; refresh: number }) {
  const { data, error, loading } = useResearch<Json>("diffusion", [refresh]);
  const name = (id: string) => agents.find((a) => a.id === id)?.name ?? id;
  if (error) return <Problem>{`Could not read who knows what: ${error}. ${SERVER_HINT}`}</Problem>;
  if (!data) return <p className="text-[var(--muted)]">{loading ? "Reading memories…" : ""}</p>;
  const topics = Object.entries(data);
  if (!topics.length) return <p className="text-[var(--muted)]">This scenario seeds no events to follow.</p>;
  return (
    <>
      {topics.map(([key, ev]: [string, Json]) => (
        <Card key={key} title={ev.label}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className={th}>Resident</th>
                  <th className={th}>Knows</th>
                  <th className={th}>First Heard</th>
                  <th className={th}>From</th>
                  <th className={`${th} tabular`}>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(ev.agents as Record<string, Json>).map(([aid, a]) => (
                  <tr key={aid} className="border-t border-[var(--line)]">
                    <td className={`${td} font-semibold`}>{name(aid)}</td>
                    <td className={td}>{a.seeded ? "Seeded" : a.aware ? "Yes" : "No"}</td>
                    <td className={`${td} tabular`}>{a.first ? formatDayTime(a.first.created_at) : <span className="text-[var(--muted)]">Not yet</span>}</td>
                    <td className={td}>
                      {a.first?.speaker_id ? (
                        a.first.speaker_id === "builder" ? (
                          "the town builder"
                        ) : (
                          name(a.first.speaker_id)
                        )
                      ) : a.first ? (
                        <span translate="no">{a.first.origin}</span>
                      ) : (
                        <span className="text-[var(--muted)]">Not yet</span>
                      )}
                    </td>
                    <td className={`${td} tabular`}>
                      {formatNumber(a.evidence)}
                      {a.weak ? <span className="text-[var(--muted)]"> +{formatNumber(a.weak)} weak</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3 className="mt-3 font-display font-bold">Transmissions</h3>
          {ev.transmissions.length ? (
            <ul className="mt-1 space-y-1 text-sm">
              {ev.transmissions.slice(-20).map((t: Json, i: number) => (
                <li key={i}>
                  <span className="tabular text-[var(--muted)]">{formatTime(t.time)}</span> <span className="font-semibold">{name(t.sender)}</span> to <span className="font-semibold">{name(t.receiver)}</span>:{" "}
                  <span className="text-[var(--muted)]">{t.text}</span>
                  {t.invitation ? <span className="ml-1.5 rounded-full bg-sun/25 px-1.5 text-xs font-bold">invitation</span> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-[var(--muted)]">Nobody has passed this on in conversation yet.</p>
          )}
        </Card>
      ))}
    </>
  );
}

function Provenance({ agent, refresh }: { agent: string | null; refresh: number }) {
  const manifest = useResearch<Json>("manifest", [refresh]);
  const [mineParam, setMine] = useQueryParam("mine");
  const mine = mineParam === "1";
  const calls = useResearch<Json[]>(`calls?limit=150${mine && agent ? `&agent=${encodeURIComponent(agent)}` : ""}`, [refresh, mine, agent]);
  const [openParam, setOpenParam] = useQueryParam("call");
  const open = openParam ? Number(openParam) : null;
  const m = manifest.data;
  const fidelity = useMemo(() => (m?.fidelity ?? []).filter((f: Json) => f.class !== "P"), [m]);
  return (
    <>
      <Card title="This Run">
        {m ? (
          <dl className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Mode">{m.mode}</Field>
            <Field label="Language model">{`${m.llm?.provider ?? ""} ${m.llm?.model ?? ""}`}</Field>
            <Field label="Model digest">{m.llm?.digest ?? "not reported"}</Field>
            <Field label="Embeddings">{`${m.embeddings?.model ?? ""} (${m.embeddings?.dims ?? "?"} dims)`}</Field>
            <Field label="Calls">{`${formatNumber(m.ledger?.calls ?? 0)}, ${formatNumber(m.ledger?.input_tokens ?? 0)} tokens in`}</Field>
            <Field label="Code">{m.code?.git_commit?.slice(0, 10) ?? "unknown"}</Field>
          </dl>
        ) : manifest.error ? (
          <Problem>{`Could not read the manifest: ${manifest.error}. ${SERVER_HINT}`}</Problem>
        ) : (
          <p className="text-[var(--muted)]">{manifest.loading ? "Loading…" : "No manifest yet. The town writes one when it starts and when it stops."}</p>
        )}
        {fidelity.length ? (
          <>
            <h3 className="mt-3 font-display font-bold">Settings That Differ From the Paper</h3>
            <ul className="mt-1 grid gap-1 text-sm sm:grid-cols-2">
              {fidelity.map((f: Json) => (
                <li key={f.setting} className="min-w-0 break-all">
                  <span className="rounded-md bg-[var(--panel-2)] px-1.5 font-bold">{f.class}</span>{" "}
                  <span translate="no">
                    {f.setting} = {JSON.stringify(f.value)}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-xs text-[var(--muted)]">C: released code, E: engineering choice, X: extension (the town game is one).</p>
          </>
        ) : null}
      </Card>
      <Card
        title="Model Calls"
        aside={
          <label className="flex items-center gap-2 text-sm font-semibold">
            <input type="checkbox" name="mine" checked={mine} onChange={(e) => setMine(e.target.checked ? "1" : "")} className="size-4 accent-[var(--color-sun)]" />
            Only the selected resident
          </label>
        }
      >
        {calls.error ? <Problem>{`Could not load the calls: ${calls.error}. ${SERVER_HINT}`}</Problem> : null}
        {calls.loading && !calls.data ? <p className="text-[var(--muted)]">Loading…</p> : null}
        {calls.data && !calls.data.length ? <p className="text-[var(--muted)]">No model calls recorded yet.</p> : null}
        {calls.data?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className={th}>Time</th>
                  <th className={th}>Task</th>
                  <th className={th}>Resident</th>
                  <th className={th}>Status</th>
                  <th className={`${th} tabular`}>Tokens</th>
                  <th className={`${th} tabular`}>ms</th>
                </tr>
              </thead>
              <tbody>
                {calls.data.map((c) => (
                  <tr key={c.id} className="border-t border-[var(--line)]">
                    <td className={`${td} whitespace-nowrap tabular`}>{c.sim_time ? formatTime(c.sim_time) : "-"}</td>
                    <td className={td}>
                      <button type="button" className="font-semibold underline-offset-2 hover:underline" onClick={() => setOpenParam(String(c.id))} translate="no">
                        {c.task}
                      </button>
                    </td>
                    <td className={td} translate="no">
                      {c.agent_id ?? "-"}
                    </td>
                    <td className={td}>{c.status}</td>
                    <td className={`${td} tabular`}>
                      {formatNumber(c.input_tokens)}/{formatNumber(c.output_tokens)}
                      {c.tokens_estimated ? "*" : ""}
                    </td>
                    <td className={`${td} tabular`}>{c.latency_ms ? formatNumber(Math.round(c.latency_ms)) : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <p className="mt-2 text-xs text-[var(--muted)]">* estimated (the provider did not report token counts).</p>
      </Card>
      {open ? <CallDialog id={open} onClose={() => setOpenParam("")} /> : null}
    </>
  );
}

/** One model call, exactly as sent and received. A native modal dialog: Esc closes it and the page behind is inert. */
function CallDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const call = useResearch<Json>(`call/${id}`);
  useEffect(() => {
    const opener = document.activeElement;
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => {
      if (dialog?.open) dialog.close();
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby="call-title"
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className="m-auto max-h-[88dvh] w-[min(96vw,900px)] overflow-hidden rounded-3xl bg-[var(--panel)] p-0 text-[var(--text)] shadow-[var(--shadow)] backdrop:bg-[#1b2440]/40"
    >
      <div className="scroll-thin max-h-[88dvh] overflow-y-auto overscroll-contain p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h2 id="call-title" className="font-display text-xl font-bold">
            Call {id}
            {call.data ? (
              <>
                : <span translate="no">{call.data.task}</span>
              </>
            ) : null}
          </h2>
          {call.data ? (
            <span className="text-sm text-[var(--muted)]" translate="no">
              {call.data.model} {call.data.template_id}
            </span>
          ) : null}
          <IconButton label="Close (Esc)" icon={X} className="ml-auto" onClick={onClose} autoFocus />
        </div>
        {call.error ? <Problem>{`Could not load this call: ${call.error}. ${SERVER_HINT}`}</Problem> : null}
        {!call.data && !call.error ? <p className="text-[var(--muted)]">Loading…</p> : null}
        {call.data ? (
          <>
            <Pre title="System">{call.data.system}</Pre>
            <Pre title="Prompt (Exactly as Sent)">{call.data.prompt}</Pre>
            <Pre title="Raw Output">{call.data.raw_output ?? call.data.error ?? ""}</Pre>
            {call.data.validation_errors ? <Pre title="Validator">{JSON.stringify(call.data.validation_errors, null, 2)}</Pre> : null}
          </>
        ) : null}
      </div>
    </dialog>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-xl bg-[var(--panel-2)] px-3 py-2">
      <dt className="text-xs font-bold text-[var(--muted)]">{label}</dt>
      <dd className="break-words font-semibold" translate="no">
        {children}
      </dd>
    </div>
  );
}

function Pre({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-3">
      <h3 className="mb-1 text-xs font-bold uppercase tracking-wide text-[var(--muted)]">{title}</h3>
      <pre className="whitespace-pre-wrap break-words rounded-2xl bg-[var(--panel-2)] p-3 font-mono text-[13px] leading-relaxed" translate="no">
        {children}
      </pre>
    </section>
  );
}
