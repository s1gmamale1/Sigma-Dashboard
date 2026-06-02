import { useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, BarChart3, CalendarDays, FolderKanban, RefreshCw, Sheet, Target } from "lucide-react";
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
import { ViewSkeleton } from "./components/ViewSkeleton";
import { Shell } from "./components/Shell";
import type { Segment } from "./components/SegmentedControl";

type Tab = "overview" | "attendance" | "reports" | "goals" | "projects" | "sheets";

const tabs: Segment[] = [
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
  const queryClient = useQueryClient();
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

  const activeQueries = {
    overview: [overview],
    attendance: [today, history, weekly],
    reports: [reports, performance],
    goals: [goals],
    projects: [projects],
    sheets: []
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
        {active === "attendance" && today.data && history.data && weekly.data ? (
          <AttendanceView
            token={token}
            shiftDate={selectedDate}
            today={today.data}
            history={history.data}
            weekly={weekly.data}
          />
        ) : null}
        {active === "reports" && reports.data && performance.data ? (
          <ReportsView reports={reports.data} performance={performance.data} />
        ) : null}
        {active === "goals" && goals.data ? <GoalsView goals={goals.data} /> : null}
        {active === "projects" && projects.data ? <ProjectConditionView conditions={projects.data} /> : null}
        {active === "sheets" ? <SheetsView token={token} /> : null}
      </>
    );
  }

  return (
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
  );
}
