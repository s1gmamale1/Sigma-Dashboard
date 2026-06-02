import type { ReactNode } from "react";
import { LogOut, ChevronLeft, ChevronRight } from "lucide-react";
import { SegmentedControl, type Segment } from "./SegmentedControl";
import { addDays } from "../lib/dates";

export function Shell({
  tabs,
  active,
  onActive,
  title,
  date,
  onDate,
  onLogout,
  children
}: {
  tabs: Segment[];
  active: string;
  onActive: (id: string) => void;
  title: string;
  date: string;
  onDate: (d: string) => void;
  onLogout: () => void;
  children: ReactNode;
}) {
  return (
    <div className="app-shell">
      <header className="topbar glass">
        <div className="topbar__brand">
          <span className="eyebrow">Viper operations</span>
          <strong>Sigma Dashboard</strong>
        </div>
        <SegmentedControl items={tabs} value={active} onChange={onActive} ariaLabel="Dashboard views" />
        <div className="topbar__actions">
          <div className="datestepper">
            <button className="icon-button" aria-label="Previous day" onClick={() => onDate(addDays(date, -1))}>
              <ChevronLeft size={18} />
            </button>
            <input type="date" value={date} onChange={(e) => onDate(e.target.value)} aria-label="Dashboard date" />
            <button className="icon-button" aria-label="Next day" onClick={() => onDate(addDays(date, 1))}>
              <ChevronRight size={18} />
            </button>
          </div>
          <button className="icon-button" onClick={onLogout} aria-label="Sign out">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <main className="content">
        <h1 className="title view-title">{title}</h1>
        <div key={active} className="view-enter">
          {children}
        </div>
      </main>
    </div>
  );
}
