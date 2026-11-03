import { useState, useMemo, useEffect } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  LayoutDashboard, Building2, Landmark, CalendarClock, AlertTriangle,
  Upload, HandCoins, ScrollText, CheckCircle2, AlertCircle, Info,
  Search, RefreshCw, X, ShieldAlert, Check, ChevronRight, ExternalLink,
  Users, UserPlus, UserRound, KeyRound, WalletCards, FileCheck2, Clock3,
  AlertOctagon, BadgeCheck, Eye, EyeOff, ArrowUpRight, CircleDollarSign,
  Activity, FileClock, ShieldCheck, Bell
} from "lucide-react";
import { api, useFetch, getRole, getUser } from "./api";

// Currency formatter
const inr = (n, c = "INR") => {
  const numeric = Number(n);
  if (!Number.isFinite(numeric)) return "—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: c || "INR", maximumFractionDigits: 0 }).format(numeric);
};

const dateLabel = (value) => {
  if (!value) return "—";
  const text = String(value);
  const parsed = /^\d{4}-\d{2}-\d{2}$/.test(text)
    ? new Date(`${text}T00:00:00`)
    : new Date(text.endsWith("Z") ? text : `${text}Z`);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(parsed);
};

const dateTimeLabel = (value) => {
  if (!value) return "—";
  const text = String(value);
  const parsed = new Date(text.endsWith("Z") ? text : `${text}Z`);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(parsed);
};

const daysLabel = (value, pastLabel = "expired") => {
  const days = Number(value);
  if (!Number.isFinite(days)) return "—";
  return days < 0 ? `${Math.abs(days)}d ${pastLabel}` : `${days}d left`;
};

const MATURITY_LABELS = {
  active: "Active",
  due_within_30_days: "Due within 30 days",
  due_within_15_days: "Due within 15 days",
  due_within_7_days: "Due within 7 days",
  due_tomorrow: "Due tomorrow",
  matured_today: "Matured today",
  overdue: "Overdue",
};

// Status Badge
export const Badge = ({ v }) => {
  if (!v) return null;
  const raw = typeof v === "object" ? (v.label || v.name || "") : String(v);
  if (!raw) return null;
  const val = raw.toLowerCase().replace(/[^a-z0-9_-]/g, "_");
  const label = MATURITY_LABELS[val] || raw.replace(/_/g, " ");
  return <span className={"badge " + val}>{label}</span>;
};

// Empty State Component
export const Empty = ({ icon: Icon = Info, title = "No records found", children, action }) => (
  <div className="empty">
    <Icon size={32} className="empty-icon" />
    <div style={{ fontWeight: 600, color: "var(--navy)" }}>{title}</div>
    {children && <div style={{ fontSize: "13px", maxWidth: 440 }}>{children}</div>}
    {action && <div style={{ marginTop: 10 }}>{action}</div>}
  </div>
);

// Alert Notification
export const Msg = ({ m, onClose }) => {
  if (!m) return null;
  const isErr = m.err;
  const isInfo = m.info;
  const Icon = isErr ? AlertCircle : isInfo ? Info : CheckCircle2;
  const cls = isErr ? "err" : isInfo ? "info" : "ok";
  return (
    <div className={"msg " + cls} role="alert">
      <div className="msg-body">
        <Icon size={18} />
        <span>{m.text}</span>
      </div>
      {onClose && (
        <button type="button" className="msg-close" onClick={onClose} aria-label="Dismiss">
          &times;
        </button>
      )}
    </div>
  );
};

// Data Loader Container
export function Load({ r, children, emptyMessage = "No records found." }) {
  if (r.loading && !r.data) {
    return (
      <div className="empty">
        <RefreshCw size={28} className="empty-icon" style={{ animation: "spin 1s linear infinite" }} />
        <div>Loading records from database…</div>
      </div>
    );
  }
  if (r.error) {
    return (
      <div className="msg err">
        <div className="msg-body">
          <AlertCircle size={18} />
          <span>Could not load data: {r.error}</span>
        </div>
        <button type="button" className="sec sm" onClick={r.reload}>
          Retry
        </button>
      </div>
    );
  }
  return children(r.data);
}

// Page Header
export const Head = ({ t, s, badge, action }) => (
  <div className="page-head">
    <div>
      <div className="page-head-title">
        <h1>{t}</h1>
        {badge}
      </div>
      {s && <p className="lead">{s}</p>}
    </div>
    {action && <div className="page-head-action">{action}</div>}
  </div>
);

// Reusable Modal Component
export function Modal({ title, isOpen, onClose, children }) {
  if (!isOpen) return null;
  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button type="button" className="msg-close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div>{children}</div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// 1. DASHBOARD
// --------------------------------------------------------------------------
function MetricCard({ icon: Icon, label, value, note, tone = "neutral" }) {
  const displayValue = typeof value === "number" && !Number.isFinite(value) ? "—" : value;
  return (
    <div className={`metric-card ${tone}`}>
      <div className="metric-topline"><span className="metric-icon"><Icon size={17} /></span><span className="metric-label">{label}</span></div>
      <strong className="metric-value">{displayValue === undefined || displayValue === null ? "—" : displayValue}</strong>
      {note && <span className="metric-note">{note}</span>}
    </div>
  );
}

function StatusDistribution({ items, total }) {
  const safeTotal = Math.max(0, Number(total) || 0);
  return (
    <div className="status-distribution">
      <div className="status-track" aria-label="Maturity status distribution">
        {items.map((item) => (
          <span key={item.label} className={`status-segment ${item.tone}`} style={{ width: `${safeTotal ? (item.value / safeTotal) * 100 : 0}%` }} title={`${item.label}: ${item.value}`} />
        ))}
      </div>
      <div className="status-legend">
        {items.map((item) => (
          <div className="status-legend-item" key={item.label}>
            <span className={`legend-dot ${item.tone}`} />
            <span>{item.label}</span>
            <b>{item.value}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Dashboard() {
  const r = useFetch("/dashboard/summary");
  const pending = useFetch("/fdrs?review_status=pending&sort=created_at&desc=true");
  const portfolio = useFetch("/fdrs?sort=maturity_date");
  const role = getRole();

  return (
    <>
      <Head
        t="Operations overview"
        s="A focused view of the institutions, deposit instruments, and actions that need attention."
        action={<Link to="/fdrs" className="btn"><Landmark size={15} /> Open FDR records <ArrowUpRight size={15} /></Link>}
      />
      <Load r={r}>
        {(d) => (
          <>
            {(() => {
              const rows = portfolio.data || [];
              const totalValue = rows.reduce((sum, row) => sum + (Number(row.amount) || 0), 0);
              const upcomingCount = rows.filter((row) => Number(row.days_to_maturity) > 0 && Number(row.days_to_maturity) <= Number(d.warning_days || 60)).length;
              const dueSoon = (Number(d.due_within_30_days) || 0) + (Number(d.due_within_15_days) || 0) + (Number(d.due_within_7_days) || 0) + (Number(d.due_tomorrow) || 0);
              const active = Math.max(0, (Number(d.fdrs) || 0) - dueSoon - (Number(d.matured_today) || 0) - (Number(d.overdue) || 0));
              const statusItems = [
                { label: "Active", value: active, tone: "active" },
                { label: "Due soon", value: dueSoon, tone: "soon" },
                { label: "Matured today", value: Number(d.matured_today) || 0, tone: "today" },
                { label: "Overdue", value: Number(d.overdue) || 0, tone: "overdue" },
              ];
              return (
                <>
                  <section className="dashboard-hero">
                    <div><span className="eyebrow">Portfolio control room</span><h2>Keep every deposit obligation in view.</h2><p>Review exposure, maturity pressure, and the records requiring action from one calm workspace.</p></div>
                    <div className="hero-aside"><span className="status-dot ok" /><span><b>Workspace active</b><small>{role === "admin" ? "Full portfolio scope" : "Authorized institution scope"}</small></span></div>
                  </section>

                  <div className="metric-grid">
                    <MetricCard icon={Building2} label="Institutions" value={d.institutions} note="In authorized registry" tone="teal" />
                    <MetricCard icon={WalletCards} label="FDR records" value={d.fdrs} note="Registered instruments" tone="navy" />
                    <MetricCard icon={CircleDollarSign} label="Total deposit value" value={portfolio.loading && !portfolio.data ? "—" : inr(totalValue)} note="Across visible records" tone="teal" />
                    <MetricCard icon={Clock3} label="Upcoming maturities" value={portfolio.loading && !portfolio.data ? "—" : upcomingCount} note={`Within ${d.warning_days || 60} days`} tone="amber" />
                    <MetricCard icon={AlertOctagon} label="Overdue records" value={d.overdue} note="Require attention" tone="red" />
                    <MetricCard icon={FileCheck2} label="Pending reviews" value={pending.loading && !pending.data ? "—" : pending.data?.length || 0} note="Awaiting decision" tone="navy" />
                  </div>

                  <div className="dashboard-grid dashboard-grid-main">
                    <section className="card status-card">
                      <div className="section-head"><div><span className="eyebrow">Maturity overview</span><h2><Activity size={17} /> Portfolio status distribution</h2></div><Link to="/maturity" className="text-link">Open monitor <ArrowUpRight size={14} /></Link></div>
                      <StatusDistribution items={statusItems} total={d.fdrs} />
                      <div className="status-footnote"><span><BadgeCheck size={15} /> Based on stored maturity dates</span><span>{d.fdrs} total instruments</span></div>
                    </section>
                    <section className="card notification-summary">
                      <div className="section-head"><div><span className="eyebrow">Attention required</span><h2><Bell size={17} /> Maturity reminders</h2></div><Link to="/notifications" className="text-link">View all <ArrowUpRight size={14} /></Link></div>
                      <div className="notification-summary-value">{d.unread_maturity_reminders || 0}<span>unread</span></div>
                      <p>{d.unread_maturity_reminders ? "Authorized records have reached a configured reminder threshold." : "No unread maturity reminders in your authorized scope."}</p>
                      <Link to="/notifications" className="btn sec full-width"><Bell size={15} /> Open notifications</Link>
                    </section>
                  </div>

                  <section className="card dashboard-queue">
                    <div className="section-head"><div><span className="eyebrow">Work queue</span><h2><ShieldAlert size={17} /> Pending review queue</h2><p className="lead">FDR submissions awaiting an administrative review decision.</p></div><Link to="/fdrs?review_status=pending" className="btn sec sm">Open queue <ArrowUpRight size={14} /></Link></div>
                    <Load r={pending} emptyMessage="No FDR records are awaiting review.">
                      {(rowsInQueue) => rowsInQueue.length === 0 ? <Empty title="Review queue is clear" icon={CheckCircle2}>There are no pending FDR submissions in your authorized scope.</Empty> : (
                        <div className="table-wrap"><table><thead><tr><th>Instrument</th><th>Institution</th><th>Amount</th><th>Source</th></tr></thead><tbody>
                          {rowsInQueue.slice(0, 6).map((f) => <tr key={f.id}><td><Link to={`/fdrs/${f.id}`} className="table-primary">{f.reference_no}</Link></td><td>{f.institution_name}</td><td className="amount-cell">{inr(f.amount, f.currency)}</td><td><Badge v={f.source} /></td></tr>)}
                        </tbody></table></div>
                      )}
                    </Load>
                  </section>

                  <div className="dashboard-grid dashboard-grid-wide">
                    <section className="card"><div className="section-head"><div><span className="eyebrow">Calendar watch</span><h2><CalendarClock size={17} /> Upcoming maturities</h2></div><Link to="/maturity" className="text-link">View monitor <ArrowUpRight size={14} /></Link></div>
                      {(!d.upcoming || d.upcoming.length === 0) ? <Empty title="No upcoming maturities" icon={CalendarClock}>All registered instruments are outside the warning window.</Empty> : <div className="table-wrap"><table><thead><tr><th>Instrument</th><th>Institution</th><th>Maturity</th><th>Status</th></tr></thead><tbody>{d.upcoming.map((f) => <tr key={f.id}><td><Link to={`/fdrs/${f.id}`} className="table-primary">{f.reference_no}</Link></td><td>{f.institution_name}</td><td>{dateLabel(f.maturity_date)}</td><td><Badge v={f.maturity_category} /></td></tr>)}</tbody></table></div>}
                    </section>
                    <section className="card"><div className="section-head"><div><span className="eyebrow">Traceability</span><h2><ScrollText size={17} /> Recent audit activity</h2></div>{(role === "admin" || role === "officer") && <Link to="/audit" className="text-link">Full audit trail <ArrowUpRight size={14} /></Link>}</div>
                      {(!d.recent_audit || d.recent_audit.length === 0) ? <Empty title="No audit events logged" icon={ScrollText}>Audit activity will appear here as operations are performed.</Empty> : <div className="audit-feed">{d.recent_audit.map((a) => <div className="audit-feed-item" key={a.id}><span className="audit-feed-icon"><FileClock size={15} /></span><div><b>{a.action}</b><small>{a.actor_username || "Historical actor unavailable"} · {dateTimeLabel(a.at)}</small></div><Badge v={a.actor_role} /></div>)}</div>}
                    </section>
                  </div>

                  <section className="adapter-strip"><div className="adapter-copy"><span className="adapter-icon"><Building2 size={17} /></span><div><span className="eyebrow">Data source</span><b>AICTE integration adapter</b><small>{d.aicte?.note || "No integration note available."}</small></div></div><div className="adapter-actions"><span className="pill warn">{d.aicte?.state || "Adapter status unavailable"}</span>{role === "admin" && <Link to="/integration" className="btn sec sm">Manage data <ArrowUpRight size={14} /></Link>}</div></section>
                </>
              );
            })()}
          </>
        )}
      </Load>
    </>
  );
}

// --------------------------------------------------------------------------
// 2. INSTITUTIONS
// --------------------------------------------------------------------------
export function Institutions() {
  const [q, setQ] = useState("");
  const r = useFetch("/institutions?q=" + encodeURIComponent(q));
  const [f, setF] = useState({ name: "", aicte_id: "", city: "", state: "", source: "manual", source_details: "" });
  const [m, setM] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [lookupQ, setLookupQ] = useState("");
  const [lookupResult, setLookupResult] = useState(null);
  const [lookingUp, setLookingUp] = useState(false);
  const role = getRole();
  const isOfficerOrAdmin = role === "admin" || role === "officer";

  const handleLookup = async (e) => {
    e.preventDefault();
    if (!lookupQ.trim()) return;
    setLookingUp(true);
    try {
      const res = await api(`/institutions/lookup?q=${encodeURIComponent(lookupQ.trim())}`);
      setLookupResult(res);
    } catch (err) {
      setLookupResult({
        available: false,
        message: "Lookup service error: " + err.message,
        suggestions: []
      });
    } finally {
      setLookingUp(false);
    }
  };

  const applySuggestion = (sug) => {
    setF({
      name: sug.name || "",
      aicte_id: sug.aicte_id || "",
      city: sug.city || "",
      state: sug.state || "",
      source: "manual",
      source_details: ""
    });
    setM({
      info: 1,
      text: "Form pre-filled from suggestion. Review all fields carefully before submitting. All user-submitted registrations are recorded with 'manual' provenance and are not official AICTE verification."
    });
  };

  const resetForm = () => {
    setF({ name: "", aicte_id: "", city: "", state: "", source: "manual", source_details: "" });
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!f.name.trim() || f.name.trim().length < 2) {
      setM({ err: 1, text: "Institution name must be at least 2 characters long." });
      return;
    }
    setSubmitting(true);
    setM(null);
    try {
      await api("/institutions", {
        method: "POST",
        body: {
          name: f.name.trim(),
          aicte_id: f.aicte_id ? f.aicte_id.trim() : null,
          city: f.city.trim(),
          state: f.state.trim(),
          source: "manual"
        }
      });
      const addedName = f.name;
      resetForm();
      setLookupResult(null);
      setM({
        text: `Institution "${addedName}" registered successfully (Provenance: Manual Entry).`
      });
      r.reload();
    } catch (x) {
      setM({ err: 1, text: x.message });
    } finally {
      setSubmitting(false);
    }
  };

  const provenanceLabel = (src) => {
    switch (src) {
      case "manual": return "Manual Entry (Unverified)";
      case "directory-suggested": return "Directory Suggestion (Unverified)";
      case "imported": return "Imported File (Unverified)";
      case "official-source": return "Official Source Sync";
      case "dev-seed": return "Dev Seed";
      default: return String(src || "unverified");
    }
  };

  return (
    <>
      <Head
        t="Institutions"
        s="Registry of colleges and universities. Provenance is strictly tracked to distinguish manual, suggested, and official records."
      />

      <Msg m={m} onClose={() => setM(null)} />

      {/* Role notice for institution users */}
      {!isOfficerOrAdmin && (
        <div className="msg info">
          <div className="msg-body">
            <Info size={18} />
            <span>
              Institution User access is limited to assigned records. Institution registration is managed by an administrator.
            </span>
          </div>
        </div>
      )}

      {/* Add Institution & External Lookup Section */}
      {isOfficerOrAdmin && (
        <div className="card" style={{ marginBottom: 18 }}>
          <h2>
            <Building2 size={18} />
            Register Institution
          </h2>

          {/* Directory Lookup Tool */}
          <div style={{ background: "var(--bg)", border: "1px solid var(--bd)", borderRadius: "var(--radius-sm)", padding: 14, marginBottom: 16 }}>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4, display: "flex", alignItems: "center", gap: 6 }}>
              <Search size={14} /> Look up in External AICTE Directory (Optional)
            </div>
            <div style={{ fontSize: 12, color: "var(--tx-muted)", marginBottom: 10 }}>
              Query the external directory for pre-fill suggestions. Third-party suggestions require manual review before saving and are <b>never</b> treated as official AICTE verification.
            </div>
            <form onSubmit={handleLookup} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <input
                type="search"
                style={{ flex: 1, minWidth: 240, maxWidth: 450 }}
                placeholder="Search external directory by institution name or AICTE ID…"
                value={lookupQ}
                onChange={(e) => setLookupQ(e.target.value)}
              />
              <button type="submit" className="sec sm" disabled={!lookupQ.trim() || lookingUp}>
                {lookingUp ? "Searching…" : "Search Directory"}
              </button>
              {lookupResult && (
                <button type="button" className="sec sm" onClick={() => { setLookupResult(null); setLookupQ(""); }}>
                  Clear Lookup
                </button>
              )}
            </form>

            {/* Lookup Result Notice */}
            {lookupResult && (
              <div style={{ marginTop: 12 }}>
                {!lookupResult.available ? (
                  <div className="msg info" style={{ marginBottom: 0, fontSize: 12.5 }}>
                    <div className="msg-body">
                      <Info size={16} />
                      <span>{lookupResult.message}</span>
                    </div>
                  </div>
                ) : lookupResult.suggestions.length === 0 ? (
                  <div style={{ fontSize: 12.5, color: "var(--tx-muted)", marginTop: 6 }}>
                    No matching institutions found in external directory.
                  </div>
                ) : (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--navy)", marginBottom: 6 }}>
                      Suggestions Found (Review before saving):
                    </div>
                    {lookupResult.suggestions.map((sug, idx) => (
                      <div
                        key={idx}
                        style={{
                          background: "#fff",
                          border: "1px solid var(--bd)",
                          borderRadius: 6,
                          padding: "8px 12px",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          marginBottom: 6,
                          flexWrap: "wrap",
                          gap: 8
                        }}
                      >
                        <div>
                          <b>{sug.name}</b> {sug.aicte_id && <code>({sug.aicte_id})</code>}
                          <div style={{ fontSize: 12, color: "var(--tx-muted)" }}>
                            {[sug.city, sug.state].filter(Boolean).join(", ")} &bull; Source: {sug.source_name || "Directory"}
                          </div>
                        </div>
                        <button type="button" className="sec sm" onClick={() => applySuggestion(sug)}>
                          Review & Pre-fill Form
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Form */}
          {f.source === "directory-suggested" && (
            <div className="msg info" style={{ marginBottom: 12, fontSize: 12.5 }}>
              <div className="msg-body">
                <Info size={16} />
                <span>
                  <b>Directory Suggestion Active:</b> Review and adjust the pre-filled fields below. Submitting will register this record with <code>directory-suggested</code> provenance.
                </span>
              </div>
              <button type="button" className="sec sm" onClick={resetForm}>
                Switch to Manual
              </button>
            </div>
          )}

          <form className="f" onSubmit={submit}>
            <label>
              Institution Name <span className="req">*</span>
              <input
                value={f.name}
                onChange={(e) => setF({ ...f, name: e.target.value })}
                placeholder="e.g. National Institute of Engineering"
                required
              />
              <span className="form-hint">Official registered name</span>
            </label>
            <label>
              AICTE Permanent ID
              <input
                value={f.aicte_id}
                onChange={(e) => setF({ ...f, aicte_id: e.target.value })}
                placeholder="e.g. 1-10928371"
              />
              <span className="form-hint">Unique AICTE identifier if available</span>
            </label>
            <label>
              City
              <input
                value={f.city}
                onChange={(e) => setF({ ...f, city: e.target.value })}
                placeholder="e.g. Pune"
              />
            </label>
            <label>
              State
              <input
                value={f.state}
                onChange={(e) => setF({ ...f, state: e.target.value })}
                placeholder="e.g. Maharashtra"
              />
            </label>
            <div className="field-actions">
              <button type="submit" disabled={submitting}>
                {submitting ? "Registering…" : "Register Institution"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Search and Filters */}
      <div className="bar">
        <div className="search-wrap">
          <Search size={16} className="search-icon" />
          <input
            type="search"
            placeholder="Search by institution name, AICTE ID, or city…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search institutions"
          />
        </div>
        {q && (
          <button type="button" className="sec sm" onClick={() => setQ("")}>
            Clear Search
          </button>
        )}
      </div>

      {/* Table */}
      <div className="card">
        <Load r={r}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty
                title={q ? "No matching institutions found" : "No institutions in registry"}
                icon={Building2}
                action={
                  q ? (
                    <button type="button" className="sec sm" onClick={() => setQ("")}>
                      Reset search
                    </button>
                  ) : null
                }
              >
                {q
                  ? `No institutions matched "${q}". Check the spelling or try a broader term.`
                  : "Register an institution above or import an official CSV/XLSX file on the Data & Import page."}
              </Empty>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Institution Name</th>
                      <th>AICTE ID</th>
                      <th>Location</th>
                      <th>Data Provenance & Status</th>
                      <th>Linked FDRs</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((i) => (
                      <tr key={i.id}>
                        <td>
                          <b>{i.name}</b>
                        </td>
                        <td>
                          {i.aicte_id ? <code>{i.aicte_id}</code> : <span style={{ color: "var(--tx-subtle)" }}>—</span>}
                        </td>
                        <td>
                          {[i.city, i.state].filter(Boolean).join(", ") || (
                            <span style={{ color: "var(--tx-subtle)" }}>—</span>
                          )}
                        </td>
                        <td>
                          <Badge v={i.source} />
                          <small style={{ display: "block", color: "var(--tx-muted)", fontSize: 11, marginTop: 2 }}>
                            {provenanceLabel(i.source)}
                          </small>
                        </td>
                        <td>
                          <b>{i.fdr_count}</b> instrument(s)
                        </td>
                        <td>
                          <Link to={`/fdrs?q=${encodeURIComponent(i.name)}`} className="btn sec sm">
                            View FDRs
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        </Load>
      </div>
    </>
  );
}

// --------------------------------------------------------------------------
// 3. FDR RECORDS & TABLE
// --------------------------------------------------------------------------
const blankFdr = {
  institution_id: "",
  bank_name: "",
  branch: "",
  reference_no: "",
  amount: "",
  currency: "INR",
  issue_date: "",
  maturity_date: "",
  remarks: "",
};

export function FDRs() {
  const [searchParams] = useSearchParams();
  const [q, setQ] = useState(() => searchParams.get("q") || "");
  const [status, setStatus] = useState("");
  const [reviewStatus, setReviewStatus] = useState(() => searchParams.get("review_status") || "");
  const [sort, setSort] = useState("maturity_date");
  const r = useFetch(`/fdrs?q=${encodeURIComponent(q)}&status=${status}&review_status=${reviewStatus}&sort=${sort}`);
  const inst = useFetch("/institutions");
  const [f, setF] = useState(blankFdr);
  const [m, setM] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const role = getRole();
  const canSubmit = role === "admin" || role === "institution";
  const canExport = role === "admin" || role === "officer";

  useEffect(() => {
    setQ(searchParams.get("q") || "");
    setReviewStatus(searchParams.get("review_status") || "");
  }, [searchParams]);

  const setField = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    if (!f.institution_id) {
      setM({ err: 1, text: "Please select an institution." });
      return;
    }
    if (f.maturity_date <= f.issue_date) {
      setM({ err: 1, text: "Maturity date must be strictly after the issue date." });
      return;
    }
    if (+f.amount <= 0) {
      setM({ err: 1, text: "Deposit amount must be greater than zero." });
      return;
    }

    setSubmitting(true);
    setM(null);
    try {
      await api("/fdrs", {
        method: "POST",
        body: { ...f, institution_id: +f.institution_id, amount: +f.amount },
      });
      setF(blankFdr);
      setM({ text: "FDR submitted for administrative review." });
      r.reload();
    } catch (x) {
      setM({ err: 1, text: x.message });
    } finally {
      setSubmitting(false);
    }
  };

  const handleExport = async (e) => {
    e.preventDefault();
    setExporting(true);
    try {
      const res = await fetch("/api/fdrs/export.csv" + (status ? "?status=" + status : ""), {
        credentials: "include",
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || res.statusText);
      }
      const blob = await res.blob();
      const u = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = u;
      a.download = `fdr_export_${status || "all"}.csv`;
      a.click();
      URL.revokeObjectURL(u);
    } catch (err) {
      setM({ err: 1, text: "Export failed: " + err.message });
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <Head
        t="Fixed Deposit Receipts"
        s="Central repository of security deposit instruments. All submissions start as pending/unverified."
      />

      <Msg m={m} onClose={() => setM(null)} />

      {/* Submit FDR Card */}
      {canSubmit && <div className="card" style={{ marginBottom: 18 }}>
        <h2>
          <Landmark size={18} />
          Submit Security Deposit / FDR
        </h2>
        <form className="f" onSubmit={submit}>
          <label>
            Institution <span className="req">*</span>
            <select value={f.institution_id} onChange={setField("institution_id")} required>
              <option value="">Select Institution…</option>
              {(inst.data || []).map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name} {i.aicte_id ? `(${i.aicte_id})` : ""}
                </option>
              ))}
            </select>
            <span className="form-hint">Institution holding the deposit</span>
          </label>
          <label>
            Bank Name <span className="req">*</span>
            <input
              value={f.bank_name}
              onChange={setField("bank_name")}
              placeholder="e.g. State Bank of India"
              required
            />
          </label>
          <label>
            Branch
            <input
              value={f.branch}
              onChange={setField("branch")}
              placeholder="e.g. Connaught Place"
            />
          </label>
          <label>
            FDR Reference Number <span className="req">*</span>
            <input
              value={f.reference_no}
              onChange={setField("reference_no")}
              placeholder="e.g. FDR-893274"
              required
            />
            <span className="form-hint">Instrument number printed on receipt</span>
          </label>
          <label>
            Amount (INR) <span className="req">*</span>
            <input
              type="number"
              min="1"
              step="any"
              value={f.amount}
              onChange={setField("amount")}
              placeholder="e.g. 500000"
              required
            />
          </label>
          <label>
            Issue Date <span className="req">*</span>
            <input
              type="date"
              value={f.issue_date}
              onChange={setField("issue_date")}
              required
            />
          </label>
          <label>
            Maturity Date <span className="req">*</span>
            <input
              type="date"
              value={f.maturity_date}
              onChange={setField("maturity_date")}
              required
            />
            <span className="form-hint">Must be after issue date</span>
          </label>
          <div className="field-actions">
            <button type="submit" disabled={submitting}>
              {submitting ? "Submitting…" : "Submit for Review"}
            </button>
          </div>
        </form>
      </div>}

      {/* Filter and Export Bar */}
      <div className="bar">
        <div className="search-wrap">
          <Search size={16} className="search-icon" />
          <input
            type="search"
            placeholder="Search by reference, bank, or institution…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search FDRs"
          />
        </div>

        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by maturity">
          <option value="">All Maturity Statuses</option>
          <option value="active">Active</option>
          <option value="due_within_30_days">Due within 30 days</option>
          <option value="due_within_15_days">Due within 15 days</option>
          <option value="due_within_7_days">Due within 7 days</option>
          <option value="due_tomorrow">Due tomorrow</option>
          <option value="matured_today">Matured today</option>
          <option value="overdue">Overdue</option>
        </select>

        <select value={reviewStatus} onChange={(e) => setReviewStatus(e.target.value)} aria-label="Filter by review status">
          <option value="">All review states</option>
          <option value="pending">Pending review</option>
          <option value="approved">Approved</option>
          <option value="changes_requested">Changes requested</option>
          <option value="rejected">Rejected</option>
        </select>

        <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort FDRs">
          <option value="maturity_date">Sort by: Maturity Date</option>
          <option value="amount">Sort by: Amount</option>
          <option value="created_at">Sort by: Newest Submitted</option>
          <option value="issue_date">Sort by: Issue Date</option>
        </select>

        {(q || status || reviewStatus) && (
          <button
            type="button"
            className="sec sm"
            onClick={() => {
              setQ("");
              setStatus("");
              setReviewStatus("");
            }}
          >
            Clear Filters
          </button>
        )}

        {canExport && <button type="button" className="sec" onClick={handleExport} disabled={exporting}>
          <Upload size={14} style={{ transform: "rotate(180deg)" }} />
          {exporting ? "Exporting…" : "Export CSV"}
        </button>}
      </div>

      {/* FDR Table Card */}
      <div className="card">
        <Load r={r}>
          {(rows) => <FdrTable rows={rows} emptyMessage="No FDR records match the current search or filters." />}
        </Load>
      </div>
    </>
  );
}

export function FdrTable({ rows, emptyMessage = "No FDR records available." }) {
  if (!rows || rows.length === 0) {
    return <Empty title="No FDR records" icon={Landmark}>{emptyMessage}</Empty>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Reference No</th>
            <th>Institution</th>
            <th>Bank & Branch</th>
            <th>Amount (INR)</th>
            <th>Maturity Date</th>
            <th>Maturity</th>
            <th>Review</th>
            <th>Verification</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((f) => (
            <tr key={f.id}>
              <td>
                <Link to={"/fdrs/" + f.id} style={{ fontWeight: 600 }}>
                  {f.reference_no}
                </Link>
              </td>
              <td>{f.institution_name}</td>
              <td>
                <b>{f.bank_name}</b>
                {f.branch && <span style={{ color: "var(--tx-muted)" }}> ({f.branch})</span>}
              </td>
              <td style={{ fontWeight: 600 }}>{inr(f.amount, f.currency)}</td>
              <td>
                    {dateLabel(f.maturity_date)}
                {Number.isFinite(Number(f.days_to_maturity)) && (
                  <div style={{ fontSize: 11.5, color: "var(--tx-muted)" }}>
                    {daysLabel(f.days_to_maturity, "ago")}
                  </div>
                )}
              </td>
              <td>
                <Badge v={f.maturity_category || f.maturity_status} />
              </td>
              <td>
                <Badge v={f.review_status} />
              </td>
              <td>
                <Badge v={f.verification_status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --------------------------------------------------------------------------
// 4. FDR DETAIL & REVIEW
// --------------------------------------------------------------------------
export function FDRDetail() {
  const { id } = useParams();
  const r = useFetch("/fdrs/" + id);
  const [m, setM] = useState(null);
  const [reason, setReason] = useState("");
  const [submittingRelease, setSubmittingRelease] = useState(false);
  const [reviewRemarks, setReviewRemarks] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const role = getRole();
  const isOfficerOrAdmin = role === "admin" || role === "officer";
  const canRequestRelease = role === "admin" || role === "institution";

  const patch = async (body, successMsg) => {
    setReviewing(true);
    setM(null);
    try {
      const payload = { ...body };
      if (reviewRemarks.trim()) {
        payload.remarks = reviewRemarks.trim();
      }
      await api("/fdrs/" + id, { method: "PATCH", body: payload });
      setM({ text: successMsg });
      setReviewRemarks("");
      r.reload();
    } catch (x) {
      setM({ err: 1, text: x.message });
    } finally {
      setReviewing(false);
    }
  };

  const submitRelease = async (e) => {
    e.preventDefault();
    if (reason.trim().length < 5) {
      setM({ err: 1, text: "Release reason must be at least 5 characters long." });
      return;
    }
    setSubmittingRelease(true);
    setM(null);
    try {
      await api("/release-requests", { method: "POST", body: { fdr_id: +id, reason: reason.trim() } });
      setM({ text: "Release request submitted successfully. It is now pending administrative review." });
      setReason("");
      r.reload();
    } catch (x) {
      setM({ err: 1, text: x.message });
    } finally {
      setSubmittingRelease(false);
    }
  };

  return (
    <>
      <Head
        t="FDR Record Details"
        s="Financial instrument particulars, review state, verification status, and audit history."
        action={
          <Link to="/fdrs" className="btn sec sm">
            &larr; Back to all FDRs
          </Link>
        }
      />

      <Msg m={m} onClose={() => setM(null)} />

      <Load r={r}>
        {(f) => (
          <>
            {/* Instrument Summary Card */}
            <div className="card" style={{ marginBottom: 18 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
                <div>
                  <h2 style={{ marginBottom: 4 }}>
                    <Landmark size={20} />
                    {f.bank_name} — {f.reference_no}
                  </h2>
                  <div style={{ color: "var(--tx-muted)", fontSize: 14 }}>
                    Institution: <b>{f.institution_name}</b>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <div>
                    <span style={{ fontSize: 11, color: "var(--tx-muted)", display: "block" }}>Maturity</span>
                    <Badge v={f.maturity_category || f.maturity_status} />
                  </div>
                  <div>
                    <span style={{ fontSize: 11, color: "var(--tx-muted)", display: "block" }}>Review</span>
                    <Badge v={f.review_status} />
                  </div>
                  <div>
                    <span style={{ fontSize: 11, color: "var(--tx-muted)", display: "block" }}>Verification</span>
                    <Badge v={f.verification_status} />
                  </div>
                </div>
              </div>

              <div className="grid" style={{ marginBottom: 0 }}>
                <div>
                  <div className="l">Deposit Amount</div>
                  <b style={{ fontSize: 18, color: "var(--navy)" }}>{inr(f.amount, f.currency)}</b>
                </div>
                <div>
                  <div className="l">Branch</div>
                  <b>{f.branch || "—"}</b>
                </div>
                <div>
                  <div className="l">Issue Date</div>
                    <b>{dateLabel(f.issue_date)}</b>
                </div>
                <div>
                  <div className="l">Maturity Date</div>
                  <b>
                    {dateLabel(f.maturity_date)} {Number.isFinite(Number(f.days_to_maturity)) ? `(${daysLabel(f.days_to_maturity)})` : ""}
                  </b>
                </div>
                <div>
                  <div className="l">Document Reference</div>
                  <b>{f.document_ref || "None specified"}</b>
                </div>
                <div>
                  <div className="l">Data Source</div>
                  <Badge v={f.source} />
                </div>
              </div>
            </div>

            {/* Officer Review Panel (Role protected) */}
            {isOfficerOrAdmin && (
              <div className="card" style={{ marginBottom: 18 }}>
                <h2>
                  <ShieldAlert size={18} />
                  Administrative Review Panel
                </h2>
                <p className="lead" style={{ fontSize: 13, marginBottom: 12 }}>
                  Financial fields are strictly read-only. Review status updates are logged permanently in the audit trail.
                </p>

                <div style={{ marginBottom: 12 }}>
                  <label style={{ display: "block", fontSize: 12.5, fontWeight: 500, marginBottom: 4 }}>
                    Reviewer Notes / Remarks (Optional)
                  </label>
                  <input
                    style={{ width: "100%", maxWidth: 600 }}
                    value={reviewRemarks}
                    onChange={(e) => setReviewRemarks(e.target.value)}
                    placeholder="Enter reason for decision or requested changes…"
                  />
                </div>

                <div className="bar" style={{ marginBottom: 0 }}>
                  <button
                    type="button"
                    className="success sm"
                    disabled={reviewing || f.review_status === "approved"}
                    onClick={() => patch({ review_status: "approved" }, "Review status updated to Approved.")}
                  >
                    <Check size={14} /> Approve Instrument
                  </button>
                  <button
                    type="button"
                    className="sec sm"
                    disabled={reviewing || f.review_status === "changes_requested"}
                    onClick={() => patch({ review_status: "changes_requested" }, "Changes requested from institution.")}
                  >
                    Request Changes
                  </button>
                  <button
                    type="button"
                    className="danger sm"
                    disabled={reviewing || f.review_status === "rejected"}
                    onClick={() => patch({ review_status: "rejected" }, "Review status updated to Rejected.")}
                  >
                    Reject Instrument
                  </button>
                  <button
                    type="button"
                    className="sec sm"
                    disabled={reviewing || f.verification_status === "under_review"}
                    onClick={() => patch({ verification_status: "under_review" }, "Verification status set to Under Review.")}
                  >
                    Mark Under Review
                  </button>
                  <button
                    type="button"
                    className="sec sm"
                    disabled={reviewing || f.renewal_status === "submitted"}
                    onClick={() => patch({ renewal_status: "submitted" }, "Renewal status marked as Submitted.")}
                  >
                    Mark Renewal Submitted
                  </button>
                </div>
              </div>
            )}

            {/* Two Columns: Release Request & Discrepancies */}
            <div className={canRequestRelease ? "two" : ""} style={{ marginBottom: 18 }}>
              {/* Release Request Form */}
              {canRequestRelease && <div className="card">
                <h2>
                  <HandCoins size={18} />
                  Request Release / Refund
                </h2>
                <p className="lead" style={{ fontSize: 13, marginBottom: 12 }}>
                  Institutions may request release upon course closure or council approval. An officer must formally authorize release.
                </p>
                <form onSubmit={submitRelease}>
                  <label style={{ display: "block", marginBottom: 10 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 500 }}>
                      Justification / Reason <span className="req">*</span>
                    </span>
                    <textarea
                      style={{ width: "100%", marginTop: 4 }}
                      rows={3}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="e.g. Approved closure of Pharmacy programme vide AICTE letter dated 2026-04-10 (minimum 5 characters)…"
                      required
                    />
                  </label>
                  <button type="submit" disabled={submittingRelease}>
                    {submittingRelease ? "Submitting Request…" : "Submit Release Request"}
                  </button>
                </form>
              </div>}

              {/* Potential Discrepancies */}
              <div className="card">
                <h2>
                  <AlertTriangle size={18} />
                  Flagged Discrepancies
                </h2>
                {f.discrepancies.length === 0 ? (
                  <Empty title="No discrepancies detected" icon={CheckCircle2}>
                    No rule-based anomalies flagged for this instrument.
                  </Empty>
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Severity</th>
                          <th>Finding</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {f.discrepancies.map((d) => (
                          <tr key={d.id}>
                            <td>
                              <Badge v={d.severity} />
                            </td>
                            <td>
                              <b>{d.rule}</b>
                              <div style={{ fontSize: 12, color: "var(--tx-muted)" }}>{d.reason}</div>
                            </td>
                            <td>
                              <Badge v={d.status} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>

            {/* Instrument Audit History */}
            <div className="card">
              <h2>
                <ScrollText size={18} />
                Instrument Status & Audit History
              </h2>
              {f.history.length === 0 ? (
                <Empty title="No history recorded yet" icon={ScrollText}>
                  Lifecycle operations on this instrument will be recorded here.
                </Empty>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Action</th>
                        <th>Actor Role</th>
                        <th>Details</th>
                        <th>Timestamp</th>
                      </tr>
                    </thead>
                    <tbody>
                      {f.history.map((a) => (
                        <tr key={a.id}>
                          <td>
                            <b>{a.action}</b>
                          </td>
                            <td>
                              <Badge v={a.actor_role} />
                              <small style={{ display: "block", marginTop: 2 }}>{a.actor_username || "Historical actor unavailable"}</small>
                            </td>
                          <td>{a.detail || "—"}</td>
                          <td style={{ fontSize: 12, color: "var(--tx-muted)" }}>
                            {dateTimeLabel(a.at)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </Load>
    </>
  );
}

// --------------------------------------------------------------------------
// 5. MATURITY MONITORING
// --------------------------------------------------------------------------
export function Maturity() {
  const [days, setDays] = useState(60);
  const [status, setStatus] = useState("");
  const r = useFetch(`/maturities?days=${days}&status=${status}`);

  return (
    <>
      <Head
        t="Maturity Monitoring"
        s="Tracks approaching and overdue deposit maturities based strictly on recorded instrument dates."
      />

      {/* Preset Windows Bar */}
      <div className="bar">
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 500 }}>
          Warning Window:
          <input
            type="number"
            min="1"
            value={days}
            onChange={(e) => setDays(+e.target.value || 60)}
            style={{ width: 85 }}
            aria-label="Warning window in days"
          />
          days
        </label>

        <div style={{ display: "flex", gap: 6 }}>
          {[30, 60, 90, 180, 365].map((preset) => (
            <button
              key={preset}
              type="button"
              className={days === preset ? "sm" : "sec sm"}
              onClick={() => setDays(preset)}
            >
              {preset}d
            </button>
          ))}
        </div>

        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter status">
          <option value="">All Instruments in Window</option>
          <option value="due_within_30_days">Due within 30 days</option>
          <option value="due_within_15_days">Due within 15 days</option>
          <option value="due_within_7_days">Due within 7 days</option>
          <option value="due_tomorrow">Due tomorrow</option>
          <option value="matured_today">Matured today</option>
          <option value="overdue">Overdue</option>
          <option value="active">Active</option>
        </select>
      </div>

      <div className="card">
        <Load r={r}>
          {(rows) => (
            <FdrTable
              rows={rows}
              emptyMessage={`No instruments are expiring within the next ${days} days or match the selected filter.`}
            />
          )}
        </Load>
      </div>
    </>
  );
}

// --------------------------------------------------------------------------
// 6. DISCREPANCIES
// --------------------------------------------------------------------------
export function Discrepancies() {
  const r = useFetch("/discrepancies");
  const [m, setM] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [filterStatus, setFilterStatus] = useState("all");
  const [selectedDiscrepancy, setSelectedDiscrepancy] = useState(null);
  const [resolutionStatus, setResolutionStatus] = useState("resolved");
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [updating, setUpdating] = useState(false);
  const canScan = getRole() === "admin";

  const scan = async () => {
    setScanning(true);
    setM(null);
    try {
      const x = await api("/discrepancies/scan", { method: "POST" });
      setM({
        text: `Rule scan completed. ${x.new_findings} new potential finding(s) detected.`,
      });
      r.reload();
    } catch (e) {
      setM({ err: 1, text: e.message });
    } finally {
      setScanning(false);
    }
  };

  const openResolution = (d, newStatus) => {
    setSelectedDiscrepancy(d);
    setResolutionStatus(newStatus);
    setResolutionNotes(d.notes || "");
  };

  const confirmResolution = async () => {
    if (!selectedDiscrepancy) return;
    setUpdating(true);
    try {
      await api("/discrepancies/" + selectedDiscrepancy.id, {
        method: "PATCH",
        body: { status: resolutionStatus, notes: resolutionNotes.trim() || "Reviewed in UI" },
      });
      setSelectedDiscrepancy(null);
      setM({ text: `Discrepancy marked as ${resolutionStatus}.` });
      r.reload();
    } catch (e) {
      setM({ err: 1, text: e.message });
    } finally {
      setUpdating(false);
    }
  };

  return (
    <>
      <Head
        t="Verification & Discrepancies"
        s="Automated rule-based checks identify potential anomalies for manual human review (not confirmed fraud)."
        action={
          canScan ? (
            <button type="button" onClick={scan} disabled={scanning}>
              <RefreshCw size={14} style={{ animation: scanning ? "spin 1s linear infinite" : "none" }} />
              {scanning ? "Running Checks…" : "Run Discrepancy Checks"}
            </button>
          ) : null
        }
      />

      <Msg m={m} onClose={() => setM(null)} />

      {/* Filter Bar */}
      <div className="bar">
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 500 }}>
          Filter Status:
          <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="all">All Findings</option>
            <option value="open">Open Only</option>
            <option value="resolved">Resolved</option>
            <option value="dismissed">Dismissed</option>
          </select>
        </label>
      </div>

      <div className="card">
        <Load r={r}>
          {(allRows) => {
            const rows = filterStatus === "all" ? allRows : allRows.filter((d) => d.status === filterStatus);
            if (rows.length === 0) {
              return (
                <Empty title="No discrepancies found" icon={CheckCircle2}>
                  {filterStatus === "all"
                    ? "No potential discrepancies have been flagged. Run checks to analyze instruments."
                    : `No discrepancies with status '${filterStatus}'.`}
                </Empty>
              );
            }
            return (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Record</th>
                      <th>Institution</th>
                      <th>Finding / Reason</th>
                      <th>Severity</th>
                      <th>Detected</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((d) => (
                      <tr key={d.id}>
                        <td>
                          <Link to={"/fdrs/" + d.fdr_id} style={{ fontWeight: 600 }}>
                            {d.reference_no}
                          </Link>
                        </td>
                        <td>{d.institution_name}</td>
                        <td>
                          <b>{d.rule}</b>
                          <div style={{ fontSize: 12, color: "var(--tx-muted)" }}>{d.reason}</div>
                          {d.notes && (
                            <div style={{ fontSize: 11.5, color: "var(--indigo)", marginTop: 2 }}>
                              Notes: {d.notes}
                            </div>
                          )}
                        </td>
                        <td>
                          <Badge v={d.severity} />
                        </td>
                        <td style={{ fontSize: 12, color: "var(--tx-muted)" }}>
                          {dateLabel(d.detected_at)}
                        </td>
                        <td>
                          <Badge v={d.status} />
                        </td>
                        <td>
                          {d.status === "open" && (
                            <div style={{ display: "flex", gap: 6 }}>
                              <button
                                type="button"
                                className="sec sm"
                                onClick={() => openResolution(d, "resolved")}
                              >
                                Resolve
                              </button>
                              <button
                                type="button"
                                className="sec sm"
                                onClick={() => openResolution(d, "dismissed")}
                              >
                                Dismiss
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          }}
        </Load>
      </div>

      {/* Discrepancy Resolution Modal */}
      <Modal
        title={`Review Finding: ${resolutionStatus === "resolved" ? "Resolve" : "Dismiss"}`}
        isOpen={Boolean(selectedDiscrepancy)}
        onClose={() => setSelectedDiscrepancy(null)}
      >
        {selectedDiscrepancy && (
          <div>
            <p style={{ margin: "0 0 12px", fontSize: 13.5 }}>
              Updating finding on instrument <b>{selectedDiscrepancy.reference_no}</b> (
              {selectedDiscrepancy.institution_name}).
            </p>
            <div style={{ background: "var(--bg)", padding: 10, borderRadius: 6, marginBottom: 12, fontSize: 12.5 }}>
              <b>{selectedDiscrepancy.rule}</b>: {selectedDiscrepancy.reason}
            </div>
            <label style={{ display: "block", marginBottom: 16 }}>
              <span style={{ fontSize: 12.5, fontWeight: 500 }}>Reviewer Remarks / Resolution Notes:</span>
              <textarea
                style={{ width: "100%", marginTop: 4 }}
                rows={3}
                value={resolutionNotes}
                onChange={(e) => setResolutionNotes(e.target.value)}
                placeholder="Explain why this finding is being resolved or dismissed…"
              />
            </label>
            <div className="modal-actions">
              <button type="button" className="sec sm" onClick={() => setSelectedDiscrepancy(null)}>
                Cancel
              </button>
              <button
                type="button"
                className={resolutionStatus === "resolved" ? "success sm" : "danger sm"}
                onClick={confirmResolution}
                disabled={updating}
              >
                {updating ? "Saving…" : `Confirm ${resolutionStatus === "resolved" ? "Resolution" : "Dismissal"}`}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}

// --------------------------------------------------------------------------
// 7. RELEASE REQUESTS
// --------------------------------------------------------------------------
export function Releases() {
  const r = useFetch("/release-requests");
  const [m, setM] = useState(null);
  const [activeDecision, setActiveDecision] = useState(null); // { id, status: 'approved'|'rejected', reference_no }
  const [remarks, setRemarks] = useState("");
  const [deciding, setDeciding] = useState(false);
  const canDecide = getRole() === "admin" || getRole() === "officer";

  const startDecision = (req, status) => {
    setActiveDecision({ req, status });
    setRemarks("");
  };

  const confirmDecision = async () => {
    if (!activeDecision) return;
    if (remarks.trim().length < 3) {
      setM({ err: 1, text: "Reviewer remarks are required (minimum 3 characters)." });
      return;
    }
    setDeciding(true);
    setM(null);
    try {
      await api("/release-requests/" + activeDecision.req.id, {
        method: "PATCH",
        body: { status: activeDecision.status, reviewer_remarks: remarks.trim() },
      });
      setActiveDecision(null);
      setM({ text: `Release request marked as ${activeDecision.status}.` });
      r.reload();
    } catch (e) {
      setM({ err: 1, text: e.message });
    } finally {
      setDeciding(false);
    }
  };

  return (
    <>
      <Head
        t="Release & Refund Requests"
        s="Formal release requests for FDR deposit instruments. An authorized reviewer must approve or reject."
      />

      <Msg m={m} onClose={() => setM(null)} />

      <div className="card">
        <Load r={r}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty title="No release requests" icon={HandCoins}>
                No release requests have been submitted yet. To submit a request, open an instrument's detail page.
              </Empty>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>FDR Instrument</th>
                      <th>Institution</th>
                      <th>Request Reason</th>
                      <th>Status</th>
                      <th>Reviewer Remarks</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((x) => (
                      <tr key={x.id}>
                        <td>
                          <Link to={"/fdrs/" + x.fdr_id} style={{ fontWeight: 600 }}>
                            {x.reference_no}
                          </Link>
                        </td>
                        <td>{x.institution_name}</td>
                        <td style={{ maxWidth: 280 }}>{x.reason}</td>
                        <td>
                          <Badge v={x.status} />
                        </td>
                        <td>{x.reviewer_remarks || <span style={{ color: "var(--tx-subtle)" }}>—</span>}</td>
                        <td>
                          {x.status === "pending" && canDecide ? (
                            <div style={{ display: "flex", gap: 6 }}>
                              <button
                                type="button"
                                className="success sm"
                                onClick={() => startDecision(x, "approved")}
                              >
                                Approve
                              </button>
                              <button
                                type="button"
                                className="danger sm"
                                onClick={() => startDecision(x, "rejected")}
                              >
                                Reject
                              </button>
                            </div>
                          ) : x.status === "pending" ? (
                            <span style={{ fontSize: 12, color: "var(--tx-muted)" }}>Awaiting reviewer</span>
                          ) : (
                            <span style={{ fontSize: 12, color: "var(--tx-muted)" }}>Finalized</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        </Load>
      </div>

      {/* Decision Confirmation Modal (replaces window.prompt) */}
      <Modal
        title={activeDecision?.status === "approved" ? "Approve Deposit Release" : "Reject Deposit Release"}
        isOpen={Boolean(activeDecision)}
        onClose={() => setActiveDecision(null)}
      >
        {activeDecision && (
          <div>
            <p style={{ margin: "0 0 10px", fontSize: 13.5 }}>
              You are about to <b>{activeDecision.status.toUpperCase()}</b> the release request for instrument{" "}
              <b>{activeDecision.req.reference_no}</b> ({activeDecision.req.institution_name}).
            </p>
            <div style={{ background: "var(--bg)", padding: 10, borderRadius: 6, marginBottom: 12, fontSize: 12.5 }}>
              <b>Institution Reason:</b> {activeDecision.req.reason}
            </div>
            <label style={{ display: "block", marginBottom: 16 }}>
              <span style={{ fontSize: 12.5, fontWeight: 500 }}>
                Reviewer Remarks (Required, min 3 chars): <span className="req">*</span>
              </span>
              <textarea
                style={{ width: "100%", marginTop: 4 }}
                rows={3}
                value={remarks}
                onChange={(e) => setRemarks(e.target.value)}
                placeholder="State basis for decision (e.g. Verified university programme closure order dated 2026-03-15)…"
                required
              />
            </label>
            <div className="modal-actions">
              <button type="button" className="sec sm" onClick={() => setActiveDecision(null)}>
                Cancel
              </button>
              <button
                type="button"
                className={activeDecision.status === "approved" ? "success sm" : "danger sm"}
                onClick={confirmDecision}
                disabled={deciding}
              >
                {deciding ? "Submitting…" : `Confirm ${activeDecision.status === "approved" ? "Approval" : "Rejection"}`}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}

// --------------------------------------------------------------------------
// 8. DATA & IMPORT
// --------------------------------------------------------------------------
export function Integration() {
  const src = useFetch("/data-sources");
  const jobs = useFetch("/imports");
  const [kind, setKind] = useState("institutions");
  const [file, setFile] = useState(null);
  const [mapping, setMapping] = useState({});
  const [preview, setPreview] = useState(null);
  const [m, setM] = useState(null);
  const [res, setRes] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [importing, setImporting] = useState(false);
  const role = getRole();
  const canImport = role === "admin" || role === "officer";

  const sameMapping = (left, right) => JSON.stringify(left || {}) === JSON.stringify(right || {});

  const resetFile = (clearResult = true) => {
    setFile(null);
    setMapping({});
    setPreview(null);
    if (clearResult) setRes(null);
    const fileInput = document.getElementById("importFileInput");
    if (fileInput) fileInput.value = "";
  };

  const selectKind = (e) => {
    setKind(e.target.value);
    resetFile();
  };

  const requestPreview = async (e, requestedMapping = mapping) => {
    if (e) e.preventDefault();
    if (!file || !canImport) return;
    setPreviewing(true);
    setM(null);
    setRes(null);
    const fd = new FormData();
    fd.append("kind", kind);
    fd.append("file", file);
    fd.append("mapping", JSON.stringify(requestedMapping || {}));
    try {
      const p = await api("/imports/preview", { method: "POST", body: fd });
      setPreview(p);
      setMapping(p.mapped_fields);
      setM({ info: 1, text: "Preview generated. Review the mapping and row-level findings before committing records." });
    } catch (x) {
      setPreview(null);
      setM({ err: 1, text: x.message });
    } finally {
      setPreviewing(false);
    }
  };

  const commit = async () => {
    if (!file || !preview || !sameMapping(mapping, preview.mapped_fields) || !canImport) return;
    setImporting(true);
    setM(null);
    const fd = new FormData();
    fd.append("kind", kind);
    fd.append("file", file);
    fd.append("mapping", JSON.stringify(mapping));
    fd.append("preview_token", preview.preview_token);
    try {
      const j = await api("/imports", { method: "POST", body: fd });
      setM(j.status === "completed"
        ? { text: `Import completed: ${j.imported} row(s) imported.` }
        : { info: 1, text: `Import finished with issues: ${j.imported} imported, ${j.rejected} rejected, ${j.duplicates} duplicate, ${j.skipped} skipped.` });
      resetFile(false);
      setRes(j);
      jobs.reload();
      src.reload();
    } catch (x) {
      setM({ err: 1, text: x.message });
    } finally {
      setImporting(false);
    }
  };

  return (
    <>
      <Head
        t="Data Sources & File Import"
        s="Connect authorized directories or import validated CSV/XLSX files into FDR Nexus."
      />

      <Msg m={m} onClose={() => setM(null)} />

      {!canImport && (
        <div className="msg info">
          <div className="msg-body">
            <Info size={18} />
            <span>Imports are restricted to Administrator and Verification Officer roles. The server enforces this restriction.</span>
          </div>
        </div>
      )}

      {/* AICTE Adapter Status */}
      <Load r={src}>
        {(d) =>
          d.map((s) => (
            <div className="card" style={{ marginBottom: 18 }} key={s.name}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 10 }}>
                <div>
                  <h2>
                    <Building2 size={18} />
                    {s.name}
                  </h2>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                    <span className="pill warn">{s.state}</span>
                    <span style={{ fontSize: 13, color: "var(--tx-muted)" }}>Source Type: {s.type}</span>
                  </div>
                </div>
                <div style={{ fontSize: 12, color: "var(--tx-muted)" }}>
                  Last sync: <b>{s.last_sync || "Never (Manual Import Only)"}</b>
                </div>
              </div>
              <p className="lead" style={{ fontSize: 13, margin: "12px 0 6px" }}>
                {s.note}
              </p>
              <div style={{ fontSize: 12, color: "var(--tx-muted)", background: "var(--bg)", padding: 10, borderRadius: 6 }}>
                <b>Access Notice:</b> Live sync requires official AICTE API authorization and API credentials (configured in <code>.env</code> via <code>AICTE_API_BASE</code> and <code>AICTE_API_KEY</code>). To prevent fraud, this prototype never fakes connectivity or fabricates official AICTE data.
              </div>
            </div>
          ))
        }
      </Load>

      {/* File Import Card */}
      <div className="card" style={{ marginBottom: 18 }}>
        <h2>
          <Upload size={18} />
          Import Records from Spreadsheet
        </h2>
        <div style={{ fontSize: 13, color: "var(--tx-muted)", marginBottom: 14 }}>
          {kind === "institutions" ? (
            <>
              Required field: <code>name</code>. Optional: <code>aicte_id, city, state</code>. Known aliases are shown in the mapping step.
            </>
          ) : (
            <>
              Required fields: <code>aicte_id, bank_name, reference_no, amount, issue_date, maturity_date</code>. Optional: <code>branch, currency, document_ref, remarks</code>.
            </>
          )}
        </div>

        <form className="f" onSubmit={requestPreview}>
          <label>
            Record Type <span className="req">*</span>
            <select value={kind} onChange={selectKind} disabled={previewing || importing}>
              <option value="institutions">Institutions Directory</option>
              <option value="fdrs">Fixed Deposit Receipts (FDRs)</option>
            </select>
          </label>
          <label>
            File (.csv or .xlsx) <span className="req">*</span>
            <input
              id="importFileInput"
              type="file"
              accept=".csv,.xlsx"
              onChange={(e) => { setFile(e.target.files[0] || null); setPreview(null); setRes(null); setM(null); }}
              required
              disabled={!canImport || previewing || importing}
            />
            <span className="form-hint">CSV or XLSX only; the backend checks the actual content and enforces the configured size limit.</span>
          </label>
          <div className="field-actions">
            <button type="submit" disabled={!file || !canImport || previewing || importing}>
              {previewing ? "Generating Preview…" : "Preview & Validate"}
            </button>
            {file && <button type="button" className="sec" onClick={resetFile} disabled={previewing || importing}>Clear File</button>}
          </div>
        </form>

        {preview && (
          <div style={{ marginTop: 18, borderTop: "1px solid var(--bd)", paddingTop: 14 }}>
            <h3>Import Preview</h3>
            <div style={{ fontSize: 12.5, color: "var(--tx-muted)", marginBottom: 10 }}>
              File: <b>{preview.filename}</b> · Detected columns: {preview.detected_columns.join(", ")}
              {preview.unmapped_columns.length > 0 && <span> · Unmapped: {preview.unmapped_columns.join(", ")}</span>}
            </div>

            <div style={{ marginBottom: 14 }}>
              <b>Column mapping</b>
              <div className="table-wrap" style={{ marginTop: 6 }}>
                <table>
                  <thead><tr><th>Application field</th><th>Incoming column</th></tr></thead>
                  <tbody>
                    {preview.supported_fields.map((field) => (
                      <tr key={field}>
                        <td>{field} {preview.required_fields.includes(field) && <span className="req">*</span>}</td>
                        <td>
                          <select
                            value={mapping[field] || ""}
                            onChange={(e) => setMapping({ ...mapping, [field]: e.target.value || undefined })}
                            aria-label={`Map ${field}`}
                          >
                            <option value="">Not mapped</option>
                            {preview.detected_columns.map((column) => <option key={column} value={column}>{column}</option>)}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!sameMapping(mapping, preview.mapped_fields) && (
                <button type="button" className="sec sm" onClick={() => requestPreview(null, mapping)} disabled={previewing}>
                  {previewing ? "Revalidating…" : "Apply Mapping & Revalidate"}
                </button>
              )}
            </div>

            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 12 }}>
              <span>Total Rows: <b>{preview.summary.total}</b></span>
              <span style={{ color: "var(--green)" }}>Valid: <b>{preview.summary.valid}</b></span>
              <span style={{ color: "var(--red)" }}>Invalid: <b>{preview.summary.invalid}</b></span>
              <span style={{ color: "var(--amb)" }}>Potential duplicates: <b>{preview.summary.duplicates}</b></span>
              <span>Skipped: <b>{preview.summary.skipped}</b></span>
            </div>

            {preview.rows.length > 0 && (
              <div className="table-wrap" style={{ marginBottom: 12 }}>
                <table>
                  <thead><tr><th>Row</th><th>Preview status</th><th>Values / finding</th></tr></thead>
                  <tbody>
                    {preview.rows.map((row) => (
                      <tr key={row.row}>
                        <td><code>Row {row.row}</code></td>
                        <td><Badge v={row.status} /></td>
                        <td>
                          {row.problem && <span style={{ color: "var(--red)" }}>{row.problem}</span>}
                          {!row.problem && Object.entries(row.values).map(([key, value]) => `${key}: ${value}`).join(" · ")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <button type="button" onClick={commit} disabled={importing || previewing || !sameMapping(mapping, preview.mapped_fields)}>
              {importing ? "Committing Import…" : "Commit Import"}
            </button>
            {!sameMapping(mapping, preview.mapped_fields) && <span className="form-hint" style={{ marginLeft: 10 }}>Revalidate after changing the mapping.</span>}
          </div>
        )}

        {/* Import Results & Error Breakdown */}
        {res && (
          <div style={{ marginTop: 18, borderTop: "1px solid var(--bd)", paddingTop: 14 }}>
            <h3>Import Results Summary</h3>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 12 }}>
              <span>Total Rows: <b>{res.total}</b></span>
              <span style={{ color: "var(--green)" }}>Imported: <b>{res.imported}</b></span>
              <span style={{ color: "var(--red)" }}>Rejected: <b>{res.rejected}</b></span>
              <span style={{ color: "var(--amb)" }}>Duplicates (Skipped): <b>{res.duplicates}</b></span>
              <span>Skipped: <b>{res.skipped}</b></span>
              <span>Status: <b>{res.replayed ? "Already processed" : res.status}</b></span>
            </div>

            {res.errors.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: "var(--red)", marginBottom: 6 }}>
                  Row-Level Findings ({res.errors.length} shown):
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th style={{ width: 80 }}>Row #</th>
                        <th>Problem / Validation Failure</th>
                      </tr>
                    </thead>
                    <tbody>
                      {res.errors.map((e, idx) => (
                        <tr key={idx}>
                          <td>
                            <code>Row {e.row}</code>
                          </td>
                          <td style={{ color: "var(--red)" }}>{e.problem}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Import History Table */}
      <div className="card">
        <h2>
          <ScrollText size={18} />
          Past Import History
        </h2>
        <Load r={jobs}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty title="No past imports recorded" icon={Upload}>
                Files imported through this page will appear in this audit log.
              </Empty>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>File Name</th>
                      <th>Type</th>
                      <th>Imported</th>
                      <th>Rejected</th>
                      <th>Duplicates</th>
                      <th>Skipped</th>
                      <th>Status</th>
                      <th>Processed When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((j) => (
                      <tr key={j.id}>
                        <td>
                          <b>{j.filename}</b>
                        </td>
                        <td>
                          <Badge v={j.kind} />
                        </td>
                        <td style={{ color: "var(--green)", fontWeight: 600 }}>{j.imported}</td>
                        <td style={{ color: j.rejected > 0 ? "var(--red)" : "inherit" }}>{j.rejected}</td>
                        <td style={{ color: j.duplicates > 0 ? "var(--amb)" : "inherit" }}>{j.duplicates}</td>
                        <td>{j.skipped || 0}</td>
                        <td><Badge v={j.status || "completed"} /></td>
                        <td style={{ fontSize: 12, color: "var(--tx-muted)" }}>
                          {dateTimeLabel(j.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        </Load>
      </div>
    </>
  );
}

// --------------------------------------------------------------------------
// 9. AUDIT LOG (NEW VIEW)
// --------------------------------------------------------------------------
export function AuditLogPage() {
  const r = useFetch("/audit");
  const [q, setQ] = useState("");
  const role = getRole();
  const isOfficerOrAdmin = role === "admin" || role === "officer";

  return (
    <>
      <Head
        t="System Audit Log"
        s="Immutable chronicle of all administrative actions, submissions, and status changes across FDR Nexus."
      />

      {!isOfficerOrAdmin ? (
        <div className="msg err">
          <div className="msg-body">
            <ShieldAlert size={18} />
            <span>
              Role '{role}' is not permitted to view system audit logs.
            </span>
          </div>
        </div>
      ) : (
        <>
          <div className="bar">
            <div className="search-wrap">
              <Search size={16} className="search-icon" />
              <input
                type="search"
                placeholder="Search audit actions, entities, or details…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                aria-label="Search audit log"
              />
            </div>
            {q && (
              <button type="button" className="sec sm" onClick={() => setQ("")}>
                Clear
              </button>
            )}
          </div>

          <div className="card">
            <Load r={r}>
              {(rows) => {
                const filtered = q
                  ? rows.filter(
                      (a) =>
                        (a.action || "").toLowerCase().includes(q.toLowerCase()) ||
                        (a.detail || "").toLowerCase().includes(q.toLowerCase()) ||
                        (a.entity || "").toLowerCase().includes(q.toLowerCase()) ||
                        (a.actor_role || "").toLowerCase().includes(q.toLowerCase())
                    )
                  : rows;

                if (filtered.length === 0) {
                  return (
                    <Empty title="No matching audit logs" icon={ScrollText}>
                      {q ? `No logs matched "${q}".` : "No audit logs have been recorded yet."}
                    </Empty>
                  );
                }

                return (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Timestamp</th>
                          <th>Action</th>
                          <th>Actor Role</th>
                          <th>Target Entity</th>
                          <th>Details</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((a) => (
                          <tr key={a.id}>
                            <td style={{ fontSize: 12, color: "var(--tx-muted)", whiteSpace: "nowrap" }}>
                              {dateTimeLabel(a.at)}
                            </td>
                            <td>
                              <code>{a.action}</code>
                            </td>
                            <td>
                              <Badge v={a.actor_role} />
                              <small style={{ display: "block", marginTop: 2 }}>{a.actor_username || "Historical actor unavailable"}</small>
                            </td>
                            <td>{a.entity}</td>
                            <td style={{ maxWidth: 360, wordBreak: "break-word" }}>{a.detail || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              }}
            </Load>
          </div>
        </>
      )}
    </>
  );
}

// --------------------------------------------------------------------------
// 10. USER MANAGEMENT
// --------------------------------------------------------------------------
const roleLabels = {
  admin: "Administrator",
  officer: "Reviewing Officer",
  institution: "Institution User",
};

const blankUser = {
  username: "",
  password: "",
  role: "institution",
  institution_ids: [],
  is_active: true,
};

function AssignmentPicker({ institutions, selected, onChange, disabled = false }) {
  const toggle = (id) => {
    if (selected.includes(id)) onChange(selected.filter((item) => item !== id));
    else onChange([...selected, id]);
  };

  if (institutions.length === 0) {
    return <div className="form-hint">No institutions are available for assignment.</div>;
  }

  return (
    <div className="assignment-grid">
      {institutions.map((institution) => (
        <label className="assignment-item" key={institution.id}>
          <input
            type="checkbox"
            checked={selected.includes(institution.id)}
            onChange={() => toggle(institution.id)}
            disabled={disabled}
          />
          <span>
            <b>{institution.name}</b>
            <small>{[institution.city, institution.state].filter(Boolean).join(", ") || "Location not recorded"}</small>
          </span>
        </label>
      ))}
    </div>
  );
}

export function UsersPage() {
  const users = useFetch("/users");
  const institutions = useFetch("/institutions");
  const [form, setForm] = useState(blankUser);
  const [editing, setEditing] = useState(null);
  const [message, setMessage] = useState(null);
  const [saving, setSaving] = useState(false);
  const me = getUser();

  const institutionMap = useMemo(
    () => Object.fromEntries((institutions.data || []).map((item) => [item.id, item])),
    [institutions.data]
  );

  const assignmentSummary = (ids) => {
    const names = (ids || []).map((id) => institutionMap[id]?.name).filter(Boolean);
    if (names.length === 0) return "Global scope";
    if (names.length <= 2) return names.join(", ");
    return `${names.slice(0, 2).join(", ")} + ${names.length - 2} more`;
  };

  const setCreateField = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  const create = async (event) => {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      await api("/users", {
        method: "POST",
        body: {
          username: form.username.trim(),
          password: form.password,
          role: form.role,
          institution_ids: form.role === "admin" ? [] : form.institution_ids,
          is_active: form.is_active,
        },
      });
      setForm(blankUser);
      setMessage({ text: "User account created successfully." });
      users.reload();
    } catch (error) {
      setMessage({ err: 1, text: error.message });
    } finally {
      setSaving(false);
    }
  };

  const openEdit = (user) => {
    setEditing({
      ...user,
      institution_ids: [...(user.institution_ids || [])],
      password: "",
    });
    setMessage(null);
  };

  const saveEdit = async () => {
    if (!editing) return;
    setSaving(true);
    setMessage(null);
    const body = { institution_ids: editing.institution_ids };
    if (editing.id !== me?.id) {
      body.role = editing.role;
      body.is_active = editing.is_active;
    }
    if (editing.password.trim()) body.password = editing.password;
    try {
      await api(`/users/${editing.id}`, { method: "PATCH", body });
      setEditing(null);
      setMessage({ text: "User account updated successfully." });
      users.reload();
    } catch (error) {
      setMessage({ err: 1, text: error.message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Head
        t="User Management"
        s="Create and maintain authorized accounts. Roles and institution assignments are enforced by the server."
        badge={<Badge v="admin only" />}
      />
      <Msg m={message} onClose={() => setMessage(null)} />

      <div className="card" style={{ marginBottom: 18 }}>
        <h2><UserPlus size={18} /> Create User Account</h2>
        <p className="lead" style={{ marginBottom: 14 }}>
          Passwords are accepted only for account creation or reset and are never displayed after submission.
        </p>
        <form className="f" onSubmit={create}>
          <label>
            Username <span className="req">*</span>
            <input value={form.username} onChange={setCreateField("username")} autoComplete="off" required />
          </label>
          <label>
            Temporary password <span className="req">*</span>
            <input type="password" value={form.password} onChange={setCreateField("password")} autoComplete="new-password" minLength={12} required />
            <span className="form-hint">Minimum 12 characters. Share securely and ask the user to change it.</span>
          </label>
          <label>
            Role <span className="req">*</span>
            <select value={form.role} onChange={setCreateField("role")}>
              <option value="institution">Institution User</option>
              <option value="officer">Reviewing Officer</option>
              <option value="admin">Administrator</option>
            </select>
          </label>
          <label className="inline-check">
            <input type="checkbox" checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} />
            Active account
          </label>
          {form.role !== "admin" && (
            <div className="assignment-field">
              <div className="field-label">Authorized institutions <span className="req">*</span></div>
              <AssignmentPicker
                institutions={institutions.data || []}
                selected={form.institution_ids}
                onChange={(institution_ids) => setForm({ ...form, institution_ids })}
              />
              <span className="form-hint">Select at least one institution for this role.</span>
            </div>
          )}
          <div className="field-actions">
            <button type="submit" disabled={saving}>{saving ? "Creating…" : "Create User"}</button>
          </div>
        </form>
      </div>

      <div className="card">
        <div className="section-head">
          <div>
            <h2><Users size={18} /> Authorized Accounts</h2>
            <p className="lead">Existing accounts and their current access scope.</p>
          </div>
          <Badge v={`${(users.data || []).length} accounts`} />
        </div>
        <Load r={users}>
          {(rows) => rows.length === 0 ? (
            <Empty title="No user accounts" icon={Users}>Create the first authorized account above.</Empty>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>User</th><th>Role</th><th>Access scope</th><th>Status</th><th>Actions</th></tr>
                </thead>
                <tbody>
                  {rows.map((user) => (
                    <tr key={user.id}>
                      <td><b>{user.username}</b>{user.id === me?.id && <small className="table-subtle">Current account</small>}</td>
                      <td><Badge v={roleLabels[user.role] || user.role} /></td>
                      <td className="scope-cell">{user.role === "admin" ? "All institutions" : assignmentSummary(user.institution_ids)}</td>
                      <td><Badge v={user.is_active ? "active" : "inactive"} /></td>
                      <td><button type="button" className="sec sm" onClick={() => openEdit(user)}><UserRound size={14} /> Edit</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Load>
      </div>

      <Modal title={`Edit ${editing?.username || "user"}`} isOpen={Boolean(editing)} onClose={() => !saving && setEditing(null)}>
        {editing && (
          <div>
            <div className="edit-user-summary">
              <UserRound size={18} />
              <div><b>{editing.username}</b><span>{editing.id === me?.id ? "Current administrator account" : "Account settings"}</span></div>
            </div>
            <div className="f edit-user-form">
              <label>
                Role
                <select value={editing.role} disabled={editing.id === me?.id} onChange={(event) => setEditing({ ...editing, role: event.target.value })}>
                  <option value="institution">Institution User</option>
                  <option value="officer">Reviewing Officer</option>
                  <option value="admin">Administrator</option>
                </select>
              </label>
              <label>
                Reset password <span className="form-hint">Optional, minimum 12 characters</span>
                <input type="password" value={editing.password} onChange={(event) => setEditing({ ...editing, password: event.target.value })} autoComplete="new-password" minLength={12} placeholder="Leave blank to keep current password" />
              </label>
              <label className="inline-check">
                <input type="checkbox" checked={editing.is_active} disabled={editing.id === me?.id} onChange={(event) => setEditing({ ...editing, is_active: event.target.checked })} />
                Active account
              </label>
              {editing.role !== "admin" && (
                <div className="assignment-field">
                  <div className="field-label">Authorized institutions <span className="req">*</span></div>
                  <AssignmentPicker
                    institutions={institutions.data || []}
                    selected={editing.institution_ids}
                    onChange={(institution_ids) => setEditing({ ...editing, institution_ids })}
                  />
                </div>
              )}
            </div>
            <div className="modal-actions">
              <button type="button" className="sec sm" onClick={() => setEditing(null)} disabled={saving}>Cancel</button>
              <button type="button" className="sm" onClick={saveEdit} disabled={saving}><KeyRound size={14} />{saving ? "Saving…" : "Save changes"}</button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}

// --------------------------------------------------------------------------
// 11. MATURITY NOTIFICATIONS
// --------------------------------------------------------------------------
export function NotificationsPage() {
  const r = useFetch("/notifications");
  const [message, setMessage] = useState(null);

  const markRead = async (id) => {
    try {
      await api(`/notifications/${id}/read`, { method: "PATCH" });
      window.dispatchEvent(new CustomEvent("fdr_notifications_changed"));
      r.reload();
    } catch (error) {
      setMessage({ err: 1, text: error.message });
    }
  };

  return (
    <>
      <Head
        t="Maturity Notifications"
        s="In-app reminders for authorized FDR records approaching or passing maturity."
        badge={<Badge v="in-app" />}
      />
      <Msg m={message} onClose={() => setMessage(null)} />
      <div className="card">
        <Load r={r}>
          {(rows) => rows.length === 0 ? (
            <Empty title="No maturity reminders" icon={CalendarClock}>
              New reminders will appear when an authorized FDR reaches a configured maturity threshold.
            </Empty>
          ) : (
            <div className="notification-list">
              {rows.map((notification) => (
                <div className={`notification-item ${notification.is_read ? "read" : "unread"}`} key={notification.id}>
                  <div className="notification-icon"><CalendarClock size={18} /></div>
                  <div className="notification-body">
                    <div className="notification-title-row">
                      <Link to={`/fdrs/${notification.fdr_id}`} onClick={() => { if (!notification.is_read) markRead(notification.id); }}>
                        {notification.reference_no}
                      </Link>
                      <Badge v={notification.category} />
                    </div>
                    <div className="notification-meta">
                      {notification.institution_name} · Maturity {dateLabel(notification.maturity_date)}
                    </div>
                    <div className="notification-meta">Generated {dateTimeLabel(notification.generated_at)}</div>
                  </div>
                  <div className="notification-action">
                    {notification.is_read ? (
                      <span className="table-subtle">Read</span>
                    ) : (
                      <button type="button" className="sec sm" onClick={() => markRead(notification.id)}>Mark read</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Load>
      </div>
    </>
  );
}
