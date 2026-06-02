import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { shortDate, shortTime } from "../lib/dates";
import type { Attendance, AttendanceHistoryRow, ChaseState, WeeklySummaryRow } from "../lib/types";
import { EmptyState } from "./EmptyState";
import { StatusPill } from "./StatusPill";

interface AttendanceViewProps {
  token: string;
  shiftDate: string;
  today: Attendance[];
  history: AttendanceHistoryRow[];
  weekly: WeeklySummaryRow[];
}

export function AttendanceView({ token, shiftDate, today, history, weekly }: AttendanceViewProps) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ id, state }: { id: number; state: ChaseState }) => api.patchChase(token, id, state),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["today", shiftDate] });
      void queryClient.invalidateQueries({ queryKey: ["overview", shiftDate] });
    }
  });

  const chartData = weekly.map((row) => ({
    name: row.person.display_name,
    lates: row.lates,
    charged: row.charged_count
  }));

  return (
    <section className="view-grid">
      <section className="panel wide">
        <header className="panel-header">
          <h2>Today</h2>
        </header>
        {today.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Person</th>
                  <th>Status</th>
                  <th>Check-in</th>
                  <th>Check-out</th>
                  <th>Late</th>
                  <th>Charge</th>
                  <th>Chase</th>
                </tr>
              </thead>
              <tbody>
                {today.map((record) => (
                  <tr key={record.id}>
                    <td>{record.person.display_name}</td>
                    <td><StatusPill value={record.status} /></td>
                    <td>{shortTime(record.check_in_at)}</td>
                    <td>{shortTime(record.check_out_at)}</td>
                    <td>{record.minutes_late}m</td>
                    <td>{record.charge_amount_uzs.toLocaleString()} UZS</td>
                    <td>
                      <select
                        value={record.chase_state}
                        onChange={(event) =>
                          mutation.mutate({ id: record.id, state: event.target.value as ChaseState })
                        }
                      >
                        <option value="none">None</option>
                        <option value="needs_chase">Needs chase</option>
                        <option value="chased">Chased</option>
                        <option value="resolved">Resolved</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No attendance records" />
        )}
      </section>

      <section className="panel wide">
        <header className="panel-header">
          <h2>History</h2>
        </header>
        {history.length ? (
          <div className="matrix-wrap">
            <table className="matrix">
              <thead>
                <tr>
                  <th>Person</th>
                  {history[0]?.cells.map((cell) => <th key={cell.date}>{shortDate(cell.date)}</th>)}
                </tr>
              </thead>
              <tbody>
                {history.map((row) => (
                  <tr key={row.person.id}>
                    <td>{row.person.display_name}</td>
                    {row.cells.map((cell) => (
                      <td key={cell.date}>
                        <StatusPill value={cell.status} />
                        <small>{shortTime(cell.check_in_at)}</small>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No history range data" />
        )}
      </section>

      <section className="panel">
        <header className="panel-header">
          <h2>Weekly lates</h2>
        </header>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData}>
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
            <Tooltip />
            <Bar dataKey="lates" fill="var(--accent)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="charged" fill="var(--danger)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </section>

      <section className="panel">
        <header className="panel-header">
          <h2>Weekly totals</h2>
        </header>
        <div className="stack">
          {weekly.map((row) => (
            <article className="list-item" key={row.person.id}>
              <strong>{row.person.display_name}</strong>
              <span>{row.lates} late · {row.charged_count} charged</span>
              <b>{row.total_charge_uzs.toLocaleString()} UZS</b>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}

