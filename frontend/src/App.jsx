import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
const SUGGESTIONS = [
  "What projects does Dar Global have in Dubai?",
  "Find Wasalt apartments in Jeddah under SAR 400k",
  "Show me Wasalt listings in Riyadh",
  "Give me a description of Trump Tower Jeddah",
];

function parseProperties(md) {
  const lines = String(md || "").split(/\r?\n/);
  const intro = [];
  const props = [];
  let cur = null;
  for (const line of lines) {
    const heading = line.match(/^##\s+(.+)$/);
    if (heading) {
      cur = { title: heading[1].trim(), fields: {} };
      props.push(cur);
      continue;
    }
    if (!cur) { intro.push(line); continue; }
    const field = line.match(/^\s*[-*]?\s*\*\*(.+?):\*\*\s*(.*)$/);
    if (field) cur.fields[field[1].trim().toLowerCase()] = field[2].trim();
  }
  return { intro: intro.join("\n").trim(), props };
}

function badgeClass(status) {
  const s = (status || "").toLowerCase();
  if (s.includes("sold")) return "border-rose-200 bg-rose-50 text-rose-700";
  if (s.includes("under development") || s.includes("off") || s.includes("launch")) return "border-amber-200 bg-amber-50 text-amber-700";
  if (s.includes("completed") || s.includes("ready")) return "border-emerald-200 bg-emerald-50 text-emerald-700";
  return "border-slate-200 bg-slate-100 text-slate-600";
}

function hasValue(v) {
  return v && v.toLowerCase() !== "not stated";
}

function propertyKey(p) {
  return p.fields.source || p.title;
}

function PropertyCard({ p, selected, onToggleCompare }) {
  const f = p.fields;
  const facts = [["Price", f.price], ["Bedrooms", f.bedrooms], ["Area", f.area], ["Type", f.type]];
  const amenities = hasValue(f.amenities) ? f.amenities.split(",").map((a) => a.trim()).filter(Boolean) : [];
  const intro = [f.location, hasValue(f.developer) ? f.developer : null].filter(Boolean);
  return (
    <article className="mt-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold leading-snug text-slate-900">{p.title}</h3>
          {hasValue(f.status) && (
            <span className={`mt-1 inline-block rounded-full border px-2 py-0.5 text-[11px] font-medium ${badgeClass(f.status)}`}>{f.status}</span>
          )}
        </div>
        <button
          type="button"
          aria-pressed={selected}
          onClick={() => onToggleCompare(p)}
          className={`shrink-0 rounded-lg border px-2.5 py-1.5 text-xs font-medium ${
            selected
              ? "border-indigo-200 bg-indigo-50 text-indigo-700"
              : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          }`}
        >
          {selected ? "Added to compare" : "Add to compare"}
        </button>
      </div>
      {intro.length > 0 && <p className="mt-1 text-xs text-slate-500">{intro.join(" | ")}</p>}
      <div className="mt-3 grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-2 sm:grid-cols-4">
        {facts.map(([label, value]) => (
          <div key={label} className="px-1">
            <span className="block text-[10px] font-medium uppercase tracking-wide text-slate-400">{label}</span>
            <strong className={`text-xs ${label === "Price" && hasValue(value) ? "font-semibold text-indigo-700" : "font-medium text-slate-700"}`}>
              {hasValue(value) ? value : "Not stated"}
            </strong>
          </div>
        ))}
      </div>
      {amenities.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {amenities.map((a) => (
            <span key={a} className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] text-indigo-700">{a}</span>
          ))}
        </div>
      )}
      {hasValue(f.source) && (() => {
        let url = f.source;
        try { url = new URL(f.source).href; } catch (_) { return null; }
        return (
          <a href={url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs font-medium text-indigo-600 hover:underline">
            View source
          </a>
        );
      })()}
    </article>
  );
}

function Answer({ content, selectedProperties, onToggleCompare }) {
  const { intro, props } = parseProperties(content);
  if (!props.length) {
    return <div className="answer"><ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown></div>;
  }
  return (
    <div className="answer">
      {intro && <ReactMarkdown remarkPlugins={[remarkGfm]}>{intro}</ReactMarkdown>}
      {props.map((p, i) => (
        <PropertyCard
          key={`${p.title}-${i}`}
          p={p}
          selected={Boolean(selectedProperties[propertyKey(p)])}
          onToggleCompare={onToggleCompare}
        />
      ))}
    </div>
  );
}

const COMPARE_FIELDS = [
  ["Location", "location"],
  ["Type", "type"],
  ["Developer", "developer"],
  ["Bedrooms", "bedrooms"],
  ["Area", "area"],
  ["Price", "price"],
  ["Status", "status"],
  ["Amenities", "amenities"],
];

function ComparisonDialog({ properties, onClose, onRemove }) {
  return (
    <div
      className="fixed inset-0 z-20 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="compare-title"
        className="max-h-[90vh] w-full max-w-5xl overflow-hidden rounded-t-2xl bg-white shadow-xl sm:rounded-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b px-5 py-4">
          <div>
            <h2 id="compare-title" className="text-base font-semibold text-slate-900">Compare properties</h2>
            <p className="mt-1 text-xs text-slate-500">Unavailable details are shown as Not stated.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close comparison" className="rounded-lg px-2 py-1 text-lg text-slate-500 hover:bg-slate-100">
            ×
          </button>
        </div>
        {properties.length < 2 ? (
          <div className="px-5 py-8 text-center">
            <p className="text-sm font-medium text-slate-700">Select at least two properties to compare.</p>
            <p className="mt-1 text-xs text-slate-500">Use “Add to compare” on property cards in the chat.</p>
          </div>
        ) : (
          <div className="max-h-[calc(90vh-76px)] overflow-auto">
            <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
              <thead className="sticky top-0 z-10 bg-slate-50">
                <tr>
                  <th scope="col" className="sticky left-0 min-w-32 border-b border-r bg-slate-50 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Details
                  </th>
                  {properties.map((p) => (
                    <th key={propertyKey(p)} scope="col" className="min-w-52 border-b px-4 py-3 align-top">
                      <div className="flex items-start justify-between gap-2">
                        <span className="font-semibold text-slate-800">{p.title}</span>
                        <button
                          type="button"
                          aria-label={`Remove ${p.title} from comparison`}
                          onClick={() => onRemove(propertyKey(p))}
                          className="shrink-0 rounded px-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
                        >
                          ×
                        </button>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARE_FIELDS.map(([label, field]) => (
                  <tr key={field}>
                    <th scope="row" className="sticky left-0 border-b border-r bg-white px-4 py-3 text-xs font-medium text-slate-500">
                      {label}
                    </th>
                    {properties.map((p) => (
                      <td key={propertyKey(p)} className="max-w-80 border-b px-4 py-3 align-top text-slate-700">
                        {hasValue(p.fields[field]) ? p.fields[field] : "Not stated"}
                      </td>
                    ))}
                  </tr>
                ))}
                <tr>
                  <th scope="row" className="sticky left-0 border-b border-r bg-white px-4 py-3 text-xs font-medium text-slate-500">
                    Source
                  </th>
                  {properties.map((p) => {
                    try {
                      const url = new URL(p.fields.source);
                      if (!["http:", "https:"].includes(url.protocol)) return <td key={propertyKey(p)} className="border-b px-4 py-3">Not stated</td>;
                      return (
                        <td key={propertyKey(p)} className="border-b px-4 py-3">
                          <a href={url.href} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">View listing</a>
                        </td>
                      );
                    } catch (_) {
                      return <td key={propertyKey(p)} className="border-b px-4 py-3">Not stated</td>;
                    }
                  })}
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedProperties, setSelectedProperties] = useState({});
  const [compareOpen, setCompareOpen] = useState(false);
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);
  useEffect(() => {
    if (!compareOpen) return undefined;
    function closeOnEscape(event) {
      if (event.key === "Escape") setCompareOpen(false);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [compareOpen]);

  function toggleCompare(p) {
    const key = propertyKey(p);
    setSelectedProperties((current) => {
      const next = { ...current };
      if (next[key]) delete next[key];
      else next[key] = p;
      return next;
    });
  }

  function removeFromCompare(key) {
    setSelectedProperties((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
  }

  async function send(text) {
    const q = (text ?? input).trim();
    if (!q || loading) return;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((m) => [...m, { role: "user", content: q }]);
    setInput(""); setLoading(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q, history }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      const data = await res.json();
      setMessages((m) => [...m, { role: "assistant", content: data.answer, sources: data.sources }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: `Error: ${e.message}` }]);
    } finally { setLoading(false); }
  }
  const compareProperties = Object.values(selectedProperties);
  return (
    <div className="flex h-screen flex-col bg-slate-50">
      <header className="flex items-center justify-between gap-4 border-b bg-white px-4 py-3 sm:px-6 sm:py-4">
        <div>
          <h1 className="text-base font-semibold text-slate-800 sm:text-lg">Real Estate Assistant (DarGlobal & Wasalt)</h1>
          <p className="hidden text-sm text-slate-500 sm:block">Hybrid RAG with PostgreSQL + pgvector & Reciprocal Rank Fusion</p>
        </div>
        <button
          type="button"
          onClick={() => setCompareOpen(true)}
          className="shrink-0 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-100"
        >
          Compare <span className="ml-1 rounded-full bg-white px-1.5 py-0.5 text-xs">{compareProperties.length}</span>
        </button>
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 overflow-y-auto px-4 py-6">
        {messages.length === 0 && (
          <div className="mt-10 text-center">
            <p className="mb-4 text-slate-500">Suggested queries:</p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)} className="rounded-full border bg-white px-4 py-2 text-sm text-slate-700 hover:bg-slate-100">{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`mb-4 flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`rounded-2xl px-4 py-3 text-sm ${m.role === "user" ? "max-w-[85%] whitespace-pre-wrap bg-indigo-600 text-white" : "w-full border bg-white text-slate-800"}`}>
              {m.role === "user" ? m.content : (
                <Answer
                  content={m.content}
                  selectedProperties={selectedProperties}
                  onToggleCompare={toggleCompare}
                />
              )}
              {m.sources?.length > 0 && (
                <div className="mt-3 border-t pt-2 text-xs text-slate-500">
                  Sources:
                  <ul className="mt-1 space-y-1">
                    {m.sources.map((s) => (
                      <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{s.title || s.url}</a></li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && <div className="text-sm text-slate-400">Thinking…</div>}
        <div ref={endRef} />
      </main>
      <footer className="border-t bg-white p-4">
        <div className="mx-auto flex max-w-3xl gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder="Ask about properties, prices, or locations..." className="flex-1 rounded-lg border px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
          <button onClick={() => send()} disabled={loading} className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white disabled:opacity-50">Send</button>
        </div>
      </footer>
      {compareOpen && (
        <ComparisonDialog
          properties={compareProperties}
          onClose={() => setCompareOpen(false)}
          onRemove={removeFromCompare}
        />
      )}
    </div>
  );
}
