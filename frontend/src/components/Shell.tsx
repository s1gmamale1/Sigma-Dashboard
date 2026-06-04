import { useEffect, useRef, useState, type ReactNode } from "react";
import { LogOut, ChevronLeft, ChevronRight } from "lucide-react";
import { SegmentedControl, type Segment } from "./SegmentedControl";
import { addDays, isoDate } from "../lib/dates";

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
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [collapsed, setCollapsed] = useState(false);

  // iOS-style large-title collapse: when the big title scrolls under the bar,
  // crossfade the app name to the active view title in the topbar.
  useEffect(() => {
    const el = titleRef.current;
    if (!el || typeof IntersectionObserver !== "function") return;
    const io = new IntersectionObserver(([entry]) => setCollapsed(!entry.isIntersecting), {
      rootMargin: "-72px 0px 0px 0px",
      threshold: 0
    });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div className="app-shell">
      <header className={`topbar glass${collapsed ? " is-collapsed" : ""}`}>
        <div className="topbar__brand">
          <span className="brand-default">
            <span className="eyebrow">Viper operations</span>
            <strong>Sigma Dashboard</strong>
          </span>
          <strong className="brand-collapsed" aria-hidden="true">
            {title}
          </strong>
        </div>
        <div className="topbar__nav">
          <SegmentedControl items={tabs} value={active} onChange={onActive} ariaLabel="Dashboard views" panelId="view-panel" />
        </div>
        <div className="topbar__actions">
          <button className="today-button" onClick={() => onDate(isoDate())}>
            Today
          </button>
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
        <h1 className="title view-title" ref={titleRef}>
          {title}
        </h1>
        <div
          id="view-panel"
          role="tabpanel"
          aria-labelledby={`tab-${active}`}
          tabIndex={0}
          key={active}
          className="view-enter"
        >
          {children}
        </div>
      </main>
    </div>
  );
}
