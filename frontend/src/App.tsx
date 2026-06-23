import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CalendarDays,
  FolderKanban,
  Gauge,
  LayoutGrid,
  RefreshCw,
  Sheet,
  Target,
  Users
} from "lucide-react";
import { api } from "./lib/api";
import { addDays, isoDate, monSatWeek, monthRange, weekStart } from "./lib/dates";
import { AttendanceView } from "./components/AttendanceView";
import { GoalsView } from "./components/GoalsView";
import { LoginPanel } from "./components/LoginPanel";
import { ChangePasswordPanel } from "./components/ChangePasswordPanel";
import { OverviewView } from "./components/OverviewView";
import { PerformanceView, type PerformancePeriod } from "./components/PerformanceView";
import { ProjectConditionView } from "./components/ProjectConditionView";
import { ReportsView } from "./components/ReportsView";
import { SheetsView } from "./components/SheetsView";
import { UsersView } from "./components/UsersView";
import { EmptyState } from "./components/EmptyState";
import { ViewSkeleton } from "./components/ViewSkeleton";
import { Shell } from "./components/Shell";
import { HQPage } from "./components/hq/HQPage";
import { AssistantDock } from "./components/AssistantDock";
import type { Segment } from "./components/SegmentedControl";
import type { Me } from "./lib/types";

type Tab = "overview" | "hq" | "attendance" | "reports" | "performance" | "goals" | "projects" | "sheets" | "users";

// Each tab maps to a permission area; a tab shows only when the role can read that
// area. `overview` is the shared home (any signed-in user); `users` is admin-only.
// `hq` (read-only control plane) is visible to any signed-in user.
const TAB_AREA: Record<Tab, string | null> = {
  overview: null,
  hq: null,
  attendance: "attendance",
  reports: "reports",
  performance: "performance",
  goals: "goals",
  projects: "projects",
  sheets: "sheets",
  users: "users"
};

const allTabs: Segment[] = [
  { id: "overview", label: "Overview", icon: <Activity size={18} /> },
  { id: "hq", label: "HQ", icon: <LayoutGrid size={18} /> },
  { id: "attendance", label: "Attendance", icon: <CalendarDays size={18} /> },
  { id: "reports", label: "Reports", icon: <BarChart3 size={18} /> },
  { id: "performance", label: "Performance", icon: <Gauge size={18} /> },
  { id: "goals", label: "Goals", icon: <Target size={18} /> },
  { id: "projects", label: "Projects", icon: <FolderKanban size={18} /> },
  { id: "sheets", label: "Sheets", icon: <Sheet size={18} /> },
  { id: "users", label: "Users", icon: <Users size={18} /> }
];

export function App() {
  const [token, setToken] = useState(() => localStorage.getItem("sigma-token"));

  function storeToken(next: string) {
    localStorage.setItem("sigma-token", next);
    setToken(next);
  }

  function logout() {
    localStorage.removeItem("sigma-token");
    setToken(null);
  }

  if (!token) return <LoginPanel onLogin={storeToken} />;

  return <AuthenticatedApp token={token} logout={logout} />;
}

// Resolves the signed-in user (role + permissions), forces a password change when the
// account is on a temp password, then hands off to the dashboard.
function AuthenticatedApp({ token, logout }: { token: string; logout: () => void }) {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api.me(token), retry: false });

  useEffect(() => {
    // A bad/expired token surfaces as a failed /me — drop it and show the login.
    if (me.error) logout();
  }, [me.error, logout]);

  if (me.isLoading) {
    return (
      <main className="login-shell">
        <ViewSkeleton />
      </main>
    );
  }
  if (!me.data) return <LoginPanel onLogin={() => queryClient.invalidateQueries({ queryKey: ["me"] })} />;

  if (me.data.must_change_password) {
    return (
      <ChangePasswordPanel
        token={token}
        displayName={me.data.display_name}
        onChanged={() => queryClient.invalidateQueries({ queryKey: ["me"] })}
        onLogout={logout}
      />
    );
  }

  return <AuthenticatedDashboard token={token} logout={logout} me={me.data} />;
}

function AuthenticatedDashboard({ token, logout, me }: { token: string; logout: () => void; me: Me }) {
  const tabs = useMemo(
    () => allTabs.filter((tab) => {
      const area = TAB_AREA[tab.id as Tab];
      return area === null || area in me.permissions;
    }),
    [me.permissions]
  );
  const [active, setActive] = useState<Tab>("overview");
  const [selectedDate, setSelectedDate] = useState(isoDate());
  const [showArchivedProjects, setShowArchivedProjects] = useState(false);
  const [perfPeriod, setPerfPeriod] = useState<PerformancePeriod>(() => ({
    kind: "week",
    ...monSatWeek(isoDate())
  }));
  const queryClient = useQueryClient();
  const startOfWeek = useMemo(() => weekStart(selectedDate), [selectedDate]);
  const historyStart = useMemo(() => addDays(selectedDate, -6), [selectedDate]);

  // Week/Month presets track the selected date; Custom keeps its own from/to.
  useEffect(() => {
    setPerfPeriod((prev) => {
      if (prev.kind === "week") return { kind: "week", ...monSatWeek(selectedDate) };
      if (prev.kind === "month") return { kind: "month", ...monthRange(selectedDate) };
      return prev;
    });
  }, [selectedDate]);

  function onPerfPeriod(next: PerformancePeriod) {
    if (next.kind === "week") setPerfPeriod({ kind: "week", ...monSatWeek(selectedDate) });
    else if (next.kind === "month") setPerfPeriod({ kind: "month", ...monthRange(selectedDate) });
    else setPerfPeriod(next);
  }

  const overview = useQuery({
    queryKey: ["overview", selectedDate],
    queryFn: () => api.overview(token, selectedDate)
  });
  const today = useQuery({
    queryKey: ["today", selectedDate],
    queryFn: () => api.today(token, selectedDate)
  });
  const history = useQuery({
    queryKey: ["history", historyStart, selectedDate],
    queryFn: () => api.history(token, historyStart, selectedDate)
  });
  const weekly = useQuery({
    queryKey: ["weekly", startOfWeek],
    queryFn: () => api.weekly(token, startOfWeek)
  });
  const reports = useQuery({
    queryKey: ["reports", selectedDate],
    queryFn: () => api.reports(token, selectedDate)
  });
  // Graceful fallback: if the selected date has no reports but an earlier date does,
  // fetch that earlier date's reports too — without mutating the global selectedDate.
  const latestReportDate = reports.data?.latestReportDate ?? null;
  const needsFallback =
    !!reports.data &&
    reports.data.reports.length === 0 &&
    latestReportDate !== null &&
    latestReportDate !== selectedDate;
  const fallbackReports = useQuery({
    queryKey: ["reports", latestReportDate],
    queryFn: () => api.reports(token, latestReportDate as string),
    enabled: needsFallback
  });
  const performance = useQuery({
    queryKey: ["performance", perfPeriod.from, perfPeriod.to],
    queryFn: () => api.performance(token, perfPeriod.from, perfPeriod.to)
  });
  const evaluations = useQuery({
    queryKey: ["evaluations", perfPeriod.from, perfPeriod.to],
    queryFn: () => api.evaluations(token, perfPeriod.from, perfPeriod.to)
  });
  const feedback = useQuery({
    queryKey: ["feedback", perfPeriod.from, perfPeriod.to],
    queryFn: () => api.feedback(token, perfPeriod.from, perfPeriod.to)
  });
  const goals = useQuery({
    queryKey: ["goals"],
    queryFn: () => api.goals(token)
  });
  const projects = useQuery({
    queryKey: ["project-conditions", showArchivedProjects],
    queryFn: () => api.projectConditions(token, showArchivedProjects)
  });

  const activeQueries = {
    overview: [overview],
    hq: [],
    attendance: [today, history, weekly],
    reports: needsFallback ? [reports, fallbackReports] : [reports],
    performance: [performance, evaluations, feedback],
    goals: [goals],
    projects: [projects],
    sheets: [],
    users: []
  }[active];
  const errorQuery = activeQueries.find((query) => query.error);
  const isLoading = activeQueries.some((query) => query.isLoading);
  const title = tabs.find((tab) => tab.id === active)?.label ?? "Sigma Dashboard";

  let body: ReactNode;
  if (errorQuery) {
    const message = errorQuery.error instanceof Error ? errorQuery.error.message : "Unable to load dashboard";
    body = (
      <EmptyState
        title={message}
        icon={<AlertTriangle aria-hidden="true" size={22} />}
        action={
          <button className="primary-button compact" onClick={() => queryClient.invalidateQueries()}>
            <RefreshCw size={16} aria-hidden="true" /> Retry
          </button>
        }
      />
    );
  } else if (isLoading) {
    body = <ViewSkeleton />;
  } else {
    body = (
      <>
        {active === "overview" && overview.data ? <OverviewView overview={overview.data} /> : null}
        {active === "hq" ? <HQPage token={token} /> : null}
        {active === "attendance" && today.data && history.data && weekly.data ? (
          <AttendanceView
            token={token}
            shiftDate={selectedDate}
            today={today.data}
            history={history.data}
            weekly={weekly.data}
          />
        ) : null}
        {active === "reports" && reports.data
          ? (() => {
              const showFallback = needsFallback && !!fallbackReports.data;
              const shown = showFallback ? fallbackReports.data! : reports.data;
              return (
                <ReportsView
                  reports={shown.reports}
                  requestedDate={selectedDate}
                  fallbackDate={showFallback ? latestReportDate : null}
                />
              );
            })()
          : null}
        {active === "performance" && performance.data && evaluations.data && feedback.data ? (
          <PerformanceView
            token={token}
            performance={performance.data}
            evaluations={evaluations.data}
            feedback={feedback.data}
            period={perfPeriod}
            onPeriod={onPerfPeriod}
          />
        ) : null}
        {active === "goals" && goals.data ? <GoalsView goals={goals.data} /> : null}
        {active === "projects" && projects.data ? (
          <ProjectConditionView
            token={token}
            conditions={projects.data}
            showArchived={showArchivedProjects}
            onShowArchived={setShowArchivedProjects}
          />
        ) : null}
        {active === "sheets" ? <SheetsView token={token} /> : null}
        {active === "users" ? <UsersView token={token} currentUsername={me.username} /> : null}
      </>
    );
  }

  return (
    <>
      <Shell
        tabs={tabs}
        active={active}
        onActive={(id) => setActive(id as Tab)}
        title={title}
        date={selectedDate}
        onDate={setSelectedDate}
        onLogout={logout}
      >
        {body}
      </Shell>
      {["admin", "manager"].includes(me.role) && <AssistantDock token={token} />}
    </>
  );
}
