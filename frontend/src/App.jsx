import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Building2, Landmark, CalendarClock, AlertTriangle,
  Upload, HandCoins, ScrollText, Menu, X, Shield, LogOut, LockKeyhole, Users, Bell,
  Search, ChevronRight, Eye, EyeOff, ArrowUpRight, ShieldCheck
} from "lucide-react";
import { getRole, login, logout, useAuth, useFetch } from "./api";
import {
  Dashboard, Institutions, FDRs, FDRDetail, Maturity,
  Discrepancies, Releases, Integration, AuditLogPage, UsersPage, NotificationsPage
} from "./pages.jsx";

const navGroups = [
  {
    label: "Workspace",
    items: [
      ["/", "Dashboard", LayoutDashboard],
      ["/notifications", "Notifications", Bell],
    ],
  },
  {
    label: "Portfolio",
    items: [
      ["/institutions", "Institutions", Building2],
      ["/fdrs", "FDR Records", Landmark],
      ["/maturity", "Maturity monitor", CalendarClock],
    ],
  },
  {
    label: "Controls",
    items: [
      ["/discrepancies", "Discrepancies", AlertTriangle],
      ["/releases", "Release requests", HandCoins],
      ["/integration", "Data & import", Upload],
      ["/audit", "Audit log", ScrollText],
      ["/users", "User management", Users],
    ],
  },
];

const roleLabels = {
  admin: "Administrator",
  officer: "Reviewing Officer",
  institution: "Institution User",
};

const allNavItems = navGroups.flatMap((group) => group.items);

function AccessDenied() {
  return (
    <div className="msg err" role="alert">
      <Shield size={18} />
      <span>Your account is not authorized to access this area.</span>
    </div>
  );
}

function NotificationIndicator() {
  const unread = useFetch("/notifications/unread-count");
  useEffect(() => {
    const refresh = () => unread.reload();
    window.addEventListener("fdr_notifications_changed", refresh);
    return () => window.removeEventListener("fdr_notifications_changed", refresh);
  }, [unread.reload]);
  const count = Number(unread.data?.unread_count) || 0;
  return (
    <Link to="/notifications" className="notification-indicator" aria-label={count ? `${count} unread notifications` : "Notifications"}>
      <span className="notification-icon-button"><Bell size={17} /></span>
      {count > 0 && <span className="notification-count">{count > 99 ? "99+" : count}</span>}
    </Link>
  );
}

function LoginScreen({ onLoggedIn }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await login(username, password);
      onLoggedIn();
    } catch (err) {
      setError(err.message || "Unable to sign in");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-frame">
        <section className="auth-intro">
          <div className="auth-brand">
            <span className="brand-mark"><Landmark size={21} /></span>
            <span>FDR NEXUS</span>
          </div>
          <div className="auth-intro-copy">
            <span className="eyebrow">Financial operations platform</span>
            <h1>One clear view of every instrument.</h1>
            <p>Manage institutional security deposits, review FDR records, and keep maturity obligations visible.</p>
          </div>
          <div className="auth-trust">
            <div className="auth-trust-icon"><ShieldCheck size={18} /></div>
            <div><b>Controlled access</b><span>Role and institution scope are enforced by the server.</span></div>
          </div>
        </section>

        <section className="card auth-card">
          <div className="auth-card-heading">
            <div className="auth-lock"><LockKeyhole size={18} /></div>
            <div><span className="eyebrow">Secure workspace</span><h2>Welcome back</h2></div>
          </div>
          <p className="lead">Sign in to continue to your authorized workspace.</p>
          {error && <div className="msg err" role="alert"><span>{error}</span></div>}
          <form className="f auth-form" onSubmit={submit}>
            <label>
              Username
              <div className="input-with-icon"><LockKeyhole size={16} /><input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></div>
            </label>
            <label>
              Password
              <div className="input-with-action"><input type={showPassword ? "text" : "password"} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /><button type="button" className="input-action" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div>
            </label>
            <button type="submit" disabled={submitting}>{submitting ? "Signing in…" : "Sign in"}<ArrowUpRight size={16} /></button>
          </form>
          <p className="form-hint auth-note"><ShieldCheck size={14} /> Sessions are protected with server-side authentication and CSRF controls.</p>
        </section>
      </div>
    </div>
  );
}

function AuthenticatedApp({ user, onLoggedOut }) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [quickSearch, setQuickSearch] = useState("");
  const src = useFetch("/data-sources");
  const s = src.data?.[0];
  const role = getRole();
  const location = useLocation();
  const navigate = useNavigate();
  const visibleNavGroups = useMemo(() => navGroups.map((group) => ({
    ...group,
    items: group.items.filter(([to]) => {
      if (to === "/integration") return role === "admin";
      if (to === "/audit") return role === "admin" || role === "officer";
      if (to === "/users") return role === "admin";
      return true;
    }),
  })).filter((group) => group.items.length), [role]);
  const currentPage = allNavItems.find(([to]) => to === location.pathname || (to !== "/" && location.pathname.startsWith(to)));

  const submitQuickSearch = (event) => {
    event.preventDefault();
    if (!quickSearch.trim()) return;
    navigate(`/fdrs?q=${encodeURIComponent(quickSearch.trim())}`);
    setQuickSearch("");
  };

  return (
    <div className="shell">
      {/* Mobile Drawer Backdrop */}
      {mobileMenuOpen && (
        <div
          className="sidebar-backdrop"
          onClick={() => setMobileMenuOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside className={`sidebar ${mobileMenuOpen ? "open" : ""}`}>
        <div className="sidebar-inner">
        <div className="brand">
          <div className="logo">
            <span className="brand-mark"><Landmark size={21} /></span>
            <span>FDR NEXUS</span>
          </div>
          <div className="sub">Security deposit operations</div>
        </div>

        <nav className="nav-groups">
          {visibleNavGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <div className="nav-group-label">{group.label}</div>
              {group.items.map(([to, label, Icon]) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === "/"}
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) => "navlink" + (isActive ? " active" : "")}
                >
                  <Icon size={17} />
                  <span>{label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="sidebar-status">
            <span className={`status-dot ${s?.state === "Credentials required" ? "warn" : s ? "ok" : "muted"}`} />
            <span><b>Data source</b><small>{s?.state || "Checking adapter…"}</small></span>
          </div>
          <div className="tagline">Every instrument. One source of truth.</div>
        </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="main">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="mobile-toggle"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label="Toggle navigation menu"
            >
              {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
            <div className="breadcrumbs"><span>FDR Nexus</span><ChevronRight size={14} /><b>{currentPage?.[1] || "Workspace"}</b></div>
          </div>

          <div className="topbar-right">
            <form className="quick-search" onSubmit={submitQuickSearch} role="search">
              <Search size={15} />
              <input value={quickSearch} onChange={(event) => setQuickSearch(event.target.value)} placeholder="Search FDRs…" aria-label="Search FDR records" />
            </form>
            <NotificationIndicator />
            <div className="profile-chip">
              <span className="avatar">{(user.username || "U").slice(0, 1).toUpperCase()}</span>
              <span className="profile-copy"><b>{user.username}</b><small>{roleLabels[role] || role}</small></span>
            </div>
            <button type="button" className="sec sm signout" onClick={async () => { try { await logout(); onLoggedOut(); } catch {} }} aria-label="Sign out">
              <LogOut size={15} /><span>Sign out</span>
            </button>
          </div>
        </header>

        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/institutions" element={<Institutions />} />
            <Route path="/fdrs" element={<FDRs />} />
            <Route path="/fdrs/:id" element={<FDRDetail />} />
            <Route path="/maturity" element={<Maturity />} />
            <Route path="/discrepancies" element={<Discrepancies />} />
            <Route path="/releases" element={<Releases />} />
            <Route path="/integration" element={role === "admin" ? <Integration /> : <AccessDenied />} />
            <Route path="/audit" element={role === "admin" || role === "officer" ? <AuditLogPage /> : <AccessDenied />} />
            <Route path="/users" element={role === "admin" ? <UsersPage /> : <AccessDenied />} />
            <Route path="/notifications" element={<NotificationsPage />} />
          </Routes>

          <footer className="disclaimer">
            <span>FDR Nexus</span> · Independent project; not endorsed by AICTE. Access is controlled by server-side authentication and authorization.
          </footer>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const auth = useAuth();
  const [, rerender] = useState(0);
  useEffect(() => {
    const refresh = () => rerender((value) => value + 1);
    window.addEventListener("fdr_auth_changed", refresh);
    window.addEventListener("fdr_auth_expired", refresh);
    return () => {
      window.removeEventListener("fdr_auth_changed", refresh);
      window.removeEventListener("fdr_auth_expired", refresh);
    };
  }, []);

  if (auth.loading) {
    return <div className="auth-shell"><div className="card auth-card"><p>Checking session…</p></div></div>;
  }
  if (!auth.user) return <LoginScreen onLoggedIn={() => rerender((value) => value + 1)} />;
  return <AuthenticatedApp user={auth.user} onLoggedOut={() => rerender((value) => value + 1)} />;
}
