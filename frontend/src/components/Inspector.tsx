import { ArrowLeft, Flask, Warning, X } from "@phosphor-icons/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api";
import { formatDay, formatNumber, formatTime } from "../lib/time";
import { Button, IconButton } from "./ui";

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const TABS = ["memories", "retrieval", "plans", "reflections", "diffusion", "provenance"] as const;
type Tab = (typeof TABS)[number];

function useResearch<T>(path: string | null, deps: unknown[] = []): { data: T | null; error: string | null; loading: boolean } {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: !!path });
  useEffect(() => {
    if (!path) return;
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    api
      .research<T>(path)
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((e) => alive && setState({ data: null, error: (e as Error).message, loading: false }));
    return () => {
      alive = false;
    };
  }, [path, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  return state;
}

function readTab(): Tab {
  const t = new URLSearchParams(window.location.search).get("tab") as Tab | null;
  return t && TABS.includes(t) ? t : "memories";
}

export function Inspector() {
  const run = useResearch<Json>("run");
  const [agent, setAgent] = useState<string | null>(new URLSearchParams(window.location.search).get("agent"));
  const [tab, setTab] = useState<Tab>(readTab());
  const [refresh, setRefresh] = useState(0);
  const agents: Json[] = run.data?.agents ?? [];
  useEffect(() => {
    if (!agent && agents.length) setAgent(agents[0].id);
  }, [agent, agents]);
  useEffect(() => {
    const q = new URLSearchParams();
    q.set("tab", tab);
    if (agent) q.set("agent", agent);
    window.history.replaceState(null, "", `/inspector?${q.toString()}`);
  }, [tab, agent]);

  return (
    <div className="flex h-full flex-col bg-[var(--panel-2)] text-[var(--text)]">
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
          <a href="/" className="inline-flex min-h-10 items-center gap-2 rounded-full bg-sun px-4 font-display text-[15px] font-semibold text-[#2a2838]">
            <ArrowLeft size={18} weight="bold" aria-hidden="true" /> Back to Town
          </a>
        </div>
      </header>
      {run.error ? <p className="p-6 text-[#b3261e]">Could not read the run: {run.error}</p> : null}
      {run.data?.mock_llm || run.data?.mock_embeddings ? (
        <p className="flex items-center gap-2 border-b-2 border-[var(--line)] bg-[#fff4d6] px-4 py-2 text-sm text-[#5c4300] dark:bg-[#3a3220] dark:text-[#f3dfa6]" role="note">
          <Warning size={18} weight="fill" aria-hidden="true" />
          {run.data?.mock_llm ? "This run uses the mock model, so residents' words are placeholders. " : ""}
          {run.data?.mock_embeddings ? "Relevance comes from mock hash embeddings, a test fixture with no semantic meaning; do not report these retrieval scores as results." : ""}
        </p>
      ) : null}
      <div className="flex min-h-0 flex-1">
        <nav className="scroll-thin w-52 shrink-0 overflow-y-auto border-r-2 border-[var(--line)] bg-[var(--panel)] p-2" aria-label="Residents">
          {agents.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => setAgent(a.id)}
              aria-current={agent === a.id}
              className={`mb-1 flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-sm font-semibold ${agent === a.id ? "bg-sun text-[#2a2838]" : "hover:bg-[var(--panel-2)]"}`}
            >
              <span className="size-3 shrink-0 rounded-full" style={{ background: a.color }} aria-hidden="true" />
              <span className="truncate">{a.name}</span>
            </button>
          ))}
        </nav>
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex gap-1 overflow-x-auto border-b-2 border-[var(--line)] bg-[var(--panel)] px-3 py-2" role="tablist" aria-label="Inspector views">
            {TABS.map((t) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`rounded-full px-3.5 py-1.5 font-display text-sm font-semibold capitalize ${tab === t ? "bg-sun text-[#2a2838]" : "hover:bg-[var(--panel-2)]"}`}>
                {t}
              </button>
            ))}
          </div>
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-4" role="tabpanel">
            {agent || tab === "diffusion" || tab === "provenance" ? (
              tab === "memories" ? (
                <Memories agent={agent!} refresh={refresh} />
              ) : tab === "retrieval" ? (
                <Retrieval agent={agent!} refresh={refresh} mockEmbeddings={!!run.data?.mock_embeddings} />
              ) : tab === "plans" ? (
                <Plans agent={agent!} refresh={refresh} />
              ) : tab === "reflections" ? (
                <Reflections agent={agent!} refresh={refresh} />
              ) : tab === "diffusion" ? (
                <Diffusion agents={agents} refresh={refresh} />
              ) : (
                <Provenance agent={agent} refresh={refresh} />
              )
            ) : (
              <p className="text-[var(--muted)]">Loading residents…</p>
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
      <div className="mb-2 flex items-center gap-2">
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
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const path = `agent/${encodeURIComponent(agent)}/memories?limit=80${kind ? `&kind=${kind}` : ""}${query ? `&q=${encodeURIComponent(query)}` : ""}`;
  const { data, error, loading } = useResearch<Json[]>(path, [refresh]);
  return (
    <Card
      title="Memory Stream"
      aside={
        <form
          className="flex flex-wrap items-center gap-2"
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
          <input id="mem-q" name="q" autoComplete="off" value={q} onChange={(e) => setQ(e.target.value)} placeholder="party…" className="min-h-9 w-44 rounded-xl border-2 border-[var(--line)] bg-[var(--panel)] px-2 text-sm placeholder:text-[var(--muted)]" />
          <Button type="submit" tone="soft" className="min-h-9">
            Search
          </Button>
        </form>
      }
    >
      {error ? <p className="text-[#b3261e]">{error}</p> : null}
      {loading && !data ? <p className="text-[var(--muted)]">Loading…</p> : null}
      {data && !data.length ? <p className="text-[var(--muted)]">No memories match. Memories appear after the next save (about every five game minutes).</p> : null}
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
                  <td className={`${td} whitespace-nowrap tabular text-[var(--muted)]`}>
                    {formatDay(m.created_at).split(",")[0]} {formatTime(m.created_at)}
                  </td>
                  <td className={`${td} whitespace-nowrap`}>
                    {m.kind}
                    <span className="block text-xs text-[var(--muted)]">{m.origin}</span>
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
  const list = useResearch<Json[]>(`agent/${encodeURIComponent(agent)}/traces?limit=60`, [refresh]);
  const [id, setId] = useState<string | null>(null);
  const trace = useResearch<Json>(id ? `trace/${encodeURIComponent(id)}` : null);
  useEffect(() => setId(null), [agent]);
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
      <Card title="Retrievals">
        {list.data?.length ? (
          <ul className="space-y-1">
            {list.data.map((t) => (
              <li key={t.id}>
                <button type="button" onClick={() => setId(t.id)} className={`w-full rounded-xl px-3 py-2 text-left text-sm ${id === t.id ? "bg-sun/25" : "hover:bg-[var(--panel-2)]"}`}>
                  <span className="block text-xs text-[var(--muted)]">
                    {formatTime(t.sim_time)}, {t.purpose}, {t.delivered} of {t.candidates}
                  </span>
                  <span className="line-clamp-2 font-semibold">{t.query}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[var(--muted)]">{list.loading ? "Loading…" : "No retrievals recorded yet."}</p>
        )}
      </Card>
      <Card title="Why These Memories">
        {!id ? <p className="text-[var(--muted)]">Pick a retrieval to see recency, importance and relevance for each candidate, as in the paper (§4.1).</p> : null}
        {trace.data ? (
          <>
            <p className="mb-2 text-sm">
              <span className="font-bold">Query:</span> {trace.data.query}
            </p>
            {mockEmbeddings ? (
              <p className="mb-2 rounded-xl bg-[#fff4d6] px-3 py-2 text-xs font-semibold text-[#5c4300] dark:bg-[#3a3220] dark:text-[#f3dfa6]">Relevance below is from mock hash embeddings (a test fixture), not semantic similarity.</p>
            ) : null}
            <p className="mb-3 text-xs text-[var(--muted)]">
              Weights recency {trace.data.weights?.recency}, importance {trace.data.weights?.importance}, relevance {trace.data.weights?.relevance}. Components are min-max normalized over {trace.data.n_candidates ?? trace.data.candidates?.length} candidates.
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
                      <td className={`${td} tabular`}>{c.rank}</td>
                      <td className={`${td} break-words`}>{c.description}</td>
                      {(["recency", "importance", "relevance"] as const).map((k) => (
                        <td key={k} className={`${td} tabular`}>
                          <span className="block font-bold">{(c.normalized?.[k] ?? 0).toFixed(2)}</span>
                          <span className="block h-1 rounded-full" style={{ width: `${Math.round((c.normalized?.[k] ?? 0) * 44)}px`, background: k === "recency" ? "#4a82dd" : k === "importance" ? "#e2629b" : "#58b368" }} aria-hidden="true" />
                        </td>
                      ))}
                      <td className={`${td} tabular font-bold`}>{(c.score ?? 0).toFixed(2)}</td>
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
  const { data } = useResearch<Json>(`agent/${encodeURIComponent(agent)}`, [refresh]);
  if (!data) return <p className="text-[var(--muted)]">Loading…</p>;
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title={`Plan for ${data.day ?? "today"}`}>
        {data.day_plan ? <p className="mb-3 text-sm text-[var(--muted)]">{data.day_plan.description}</p> : null}
        <ol className="space-y-2">
          {(data.hours ?? []).map((h: Json) => (
            <li key={h.id} className="rounded-xl bg-[var(--panel-2)] p-2.5">
              <p className="text-sm font-bold">
                <span className="tabular">{formatTime(h.start)}</span> {h.description} <span className="font-normal text-[var(--muted)]">({h.duration_min} min, {h.status})</span>
              </p>
              {h.tasks?.length ? (
                <ul className="mt-1 space-y-0.5 pl-3 text-sm">
                  {h.tasks.map((t: Json) => (
                    <li key={t.id}>
                      <span className="tabular text-[var(--muted)]">{formatTime(t.start)}</span> {t.description} <span className="text-[var(--muted)]">({t.duration_min} min)</span>
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
              {Math.round(data.state?.reflection_accumulator ?? 0)} / {data.state?.reflection_threshold}
            </dd>
          </div>
        </dl>
        <h3 className="mt-4 font-display font-bold">Places {data.identity?.first_name} knows</h3>
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
  const { data } = useResearch<Json[]>(`agent/${encodeURIComponent(agent)}/reflections`, [refresh]);
  const [open, setOpen] = useState<string | null>(null);
  const tree = useResearch<Json>(open ? `evidence/${encodeURIComponent(open)}` : null);
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Reflections">
        {data?.length ? (
          <ul className="space-y-1">
            {data.map((r) => (
              <li key={r.id}>
                <button type="button" onClick={() => setOpen(r.id)} className={`w-full rounded-xl px-3 py-2 text-left text-sm ${open === r.id ? "bg-sun/25" : "hover:bg-[var(--panel-2)]"}`}>
                  <span className="block text-xs text-[var(--muted)]">
                    {formatTime(r.created_at)}, depth {r.depth}, {r.evidence.length} cited
                  </span>
                  <span className="font-semibold">{r.description}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[var(--muted)]">No reflections yet. They happen when the importance of new memories adds up past the threshold (§4.2).</p>
        )}
      </Card>
      <Card title="Evidence Tree">{tree.data ? <EvidenceNode node={tree.data} /> : <p className="text-[var(--muted)]">Pick a reflection to see what it cites.</p>}</Card>
    </div>
  );
}

function EvidenceNode({ node }: { node: Json }) {
  return (
    <div className="border-l-2 border-[var(--line)] pl-3">
      <p className="text-sm">
        <span className="font-bold">{node.kind}</span> <span className="text-[var(--muted)]">({node.origin}, importance {node.importance})</span>
      </p>
      <p className="mb-2 text-sm">{node.description}</p>
      {(node.evidence ?? []).map((e: Json) => (
        <EvidenceNode key={e.id} node={e} />
      ))}
    </div>
  );
}

function Diffusion({ agents, refresh }: { agents: Json[]; refresh: number }) {
  const { data, loading } = useResearch<Json>("diffusion", [refresh]);
  const name = (id: string) => agents.find((a) => a.id === id)?.name ?? id;
  if (!data) return <p className="text-[var(--muted)]">{loading ? "Reading memories…" : "No seeded events in this scenario."}</p>;
  return (
    <>
      {Object.entries(data).map(([key, ev]: [string, Json]) => (
        <Card key={key} title={ev.label}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className={th}>Resident</th>
                  <th className={th}>Knows</th>
                  <th className={th}>First heard</th>
                  <th className={th}>From</th>
                  <th className={`${th} tabular`}>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(ev.agents as Record<string, Json>).map(([aid, a]) => (
                  <tr key={aid} className="border-t border-[var(--line)]">
                    <td className={`${td} font-semibold`}>{name(aid)}</td>
                    <td className={td}>{a.seeded ? "Seeded" : a.aware ? "Yes" : "No"}</td>
                    <td className={`${td} tabular`}>{a.first ? `${formatDay(a.first.created_at).split(",")[0]} ${formatTime(a.first.created_at)}` : "-"}</td>
                    <td className={td}>{a.first?.speaker_id ? (a.first.speaker_id === "builder" ? "the town builder" : name(a.first.speaker_id)) : a.first ? a.first.origin : "-"}</td>
                    <td className={`${td} tabular`}>
                      {a.evidence}
                      {a.weak ? <span className="text-[var(--muted)]"> +{a.weak} weak</span> : null}
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
  const [mine, setMine] = useState(false);
  const calls = useResearch<Json[]>(`calls?limit=150${mine && agent ? `&agent=${encodeURIComponent(agent)}` : ""}`, [refresh, mine, agent]);
  const [open, setOpen] = useState<number | null>(null);
  const call = useResearch<Json>(open ? `call/${open}` : null);
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
        ) : (
          <p className="text-[var(--muted)]">The manifest is written when the run starts and stops.</p>
        )}
        {fidelity.length ? (
          <>
            <h3 className="mt-3 font-display font-bold">Settings That Are Not the Paper's</h3>
            <ul className="mt-1 grid gap-1 text-sm sm:grid-cols-2">
              {fidelity.map((f: Json) => (
                <li key={f.setting}>
                  <span className="rounded-md bg-[var(--panel-2)] px-1.5 font-bold">{f.class}</span> {f.setting} = {JSON.stringify(f.value)}
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
            <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} className="size-4 accent-[var(--color-sun)]" />
            Only the selected resident
          </label>
        }
      >
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
              {(calls.data ?? []).map((c) => (
                <tr key={c.id} className="cursor-pointer border-t border-[var(--line)] hover:bg-[var(--panel-2)]" onClick={() => setOpen(c.id)}>
                  <td className={`${td} whitespace-nowrap tabular`}>{c.sim_time ? formatTime(c.sim_time) : "-"}</td>
                  <td className={td}>
                    <button type="button" className="font-semibold underline-offset-2 hover:underline" onClick={() => setOpen(c.id)}>
                      {c.task}
                    </button>
                  </td>
                  <td className={td}>{c.agent_id ?? "-"}</td>
                  <td className={td}>{c.status}</td>
                  <td className={`${td} tabular`}>
                    {formatNumber(c.input_tokens)}/{formatNumber(c.output_tokens)}
                    {c.tokens_estimated ? "*" : ""}
                  </td>
                  <td className={`${td} tabular`}>{c.latency_ms ? Math.round(c.latency_ms) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-[var(--muted)]">* estimated (the provider did not report token counts).</p>
      </Card>
      {open && call.data ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-[#1b2440]/40 p-3" onClick={() => setOpen(null)}>
          <div role="dialog" aria-modal="true" aria-label={`Call ${open}`} className="scroll-thin max-h-[88dvh] w-[min(96vw,900px)] overflow-y-auto overscroll-contain rounded-3xl bg-[var(--panel)] p-5 shadow-[var(--shadow)]" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center gap-2">
              <h2 className="font-display text-xl font-bold">
                Call {open}: {call.data.task}
              </h2>
              <span className="text-sm text-[var(--muted)]">
                {call.data.model} {call.data.template_id}
              </span>
              <IconButton label="Close" icon={X} className="ml-auto" onClick={() => setOpen(null)} />
            </div>
            <Pre title="System">{call.data.system}</Pre>
            <Pre title="Prompt (exactly as sent)">{call.data.prompt}</Pre>
            <Pre title="Raw output">{call.data.raw_output ?? call.data.error ?? ""}</Pre>
            {call.data.validation_errors ? <Pre title="Validator">{JSON.stringify(call.data.validation_errors, null, 2)}</Pre> : null}
          </div>
        </div>
      ) : null}
    </>
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
      <pre className="whitespace-pre-wrap break-words rounded-2xl bg-[var(--panel-2)] p-3 font-mono text-[13px] leading-relaxed">{children}</pre>
    </section>
  );
}
