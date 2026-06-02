import type React from "react";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, CalendarDays, FolderKanban, LogOut, Sheet, Target } from "lucide-react";
import { api } from "./lib/api";
import { addDays, isoDate, weekStart } from "./lib/dates";
import { AttendanceView } from "./components/AttendanceView";
import { GoalsView } from "./components/GoalsView";
import { LoginPanel } from "./components/LoginPanel";
import { OverviewView } from "./components/OverviewView";
import { ProjectConditionView } from "./components/ProjectConditionView";
import { ReportsView } from "./components/ReportsView";
import { SheetsView } from "./components/SheetsView";
import { EmptyState } from "./components/EmptyState";

type Tab = "overview" | "attendance" | "reports" | "goals" | "projects" | "sheets";

const tabs: Array<{ id: Tab; label: string; icon: React.ReactNode }> = [
  { id: "overview", label: "Overview", icon: <Activity size={18} /> },
  { id: "attendance", label: "Attendance", icon: <CalendarDays size={18} /> },
  { id: "reports", label: "Reports", icon: <BarChart3 size={18} /> },
  { id: "goals", label: "Goals", icon: <Target size={18} /> },
  { id: "projects", label: "Projects", icon: <FolderKanban size={18} /> },
  { id: "sheets", label: "Sheets", icon: <Sheet size={18} /> }
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

  return <AuthenticatedDashboard token={token} logout={logout} />;
}

function AuthenticatedDashboard({ token, logout }: { token: string; logout: () => void }) {
  const [active, setActive] = useState<Tab>("overview");
  const [selectedDate, setSelectedDate] = useState(isoDate());
  const startOfWeek = useMemo(() => weekStart(selectedDate), [selectedDate]);
  const historyStart = useMemo(() => addDays(selectedDate, -6), [selectedDate]);

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
  const performance = useQuery({
    queryKey: ["performance", startOfWeek, selectedDate],
    queryFn: () => api.performance(token, startOfWeek, selectedDate)
  });
  const goals = useQuery({
    queryKey: ["goals"],
    queryFn: () => api.goals(token)
  });
  const projects = useQuery({
    queryKey: ["project-conditions"],
    queryFn: () => api.projectConditions(token)
  });

  const hasError = [overview, today, history, weekly, reports, performance, goals, projects].find((query) => query.error);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <span className="eyebrow">Viper operations</span>
          <h1>Sigma Dashboard</h1>
        </div>
        <nav aria-label="Dashboard views">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={active === tab.id ? "active" : ""}
              onClick={() => setActive(tab.id)}
              title={tab.label}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </nav>
        <div className="topbar-actions">
          <input
            type="date"
            value={selectedDate}
            onChange={(event) => setSelectedDate(event.target.value)}
            aria-label="Dashboard date"
          />
          <button className="icon-button" onClick={logout} title="Sign out" aria-label="Sign out">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <main className="content">
        {hasError ? (
          <EmptyState title={hasError.error instanceof Error ? hasError.error.message : "Unable to load dashboard"} />
        ) : null}
        {!hasError && active === "overview" && overview.data ? <OverviewView overview={overview.data} /> : null}
        {!hasError && active === "attendance" && today.data && history.data && weekly.data ? (
          <AttendanceView
            token={token}
            shiftDate={selectedDate}
            today={today.data}
            history={history.data}
            weekly={weekly.data}
          />
        ) : null}
        {!hasError && active === "reports" && reports.data && performance.data ? (
          <ReportsView reports={reports.data} performance={performance.data} />
        ) : null}
        {!hasError && active === "goals" && goals.data ? <GoalsView goals={goals.data} /> : null}
        {!hasError && active === "projects" && projects.data ? (
          <ProjectConditionView conditions={projects.data} />
        ) : null}
        {active === "sheets" ? <SheetsView token={token} /> : null}
      </main>
    </div>
  );
}
