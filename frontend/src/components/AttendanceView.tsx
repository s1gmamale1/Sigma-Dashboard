import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { shortDate, shortTime } from "../lib/dates";
import type { Attendance, AttendanceHistoryRow, ChaseState, WeeklySummaryRow } from "../lib/types";
import { Avatar } from "./Avatar";
import { BarChart } from "./BarChart";
import { Card } from "./Card";
import { ChaseControl } from "./ChaseControl";
import { EmptyState } from "./EmptyState";
import { SectionHeader } from "./SectionHeader";
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
    onMutate: async ({ id, state }: { id: number; state: ChaseState }) => {
      await queryClient.cancelQueries({ queryKey: ["today", shiftDate] });
      const prev = queryClient.getQueryData<Attendance[]>(["today", shiftDate]);
      queryClient.setQueryData<Attendance[]>(["today", shiftDate], (old) =>
        (old ?? []).map((row) => (row.id === id ? { ...row, chase_state: state } : row))
      );
      return { prev };
    },
    onError: (_error, _variables, context) => {
      if (context?.prev) {
        queryClient.setQueryData(["today", shiftDate], context.prev);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["today", shiftDate] });
      void queryClient.invalidateQueries({ queryKey: ["overview", shiftDate] });
    }
  });

  return (
    <section className="view-grid">
      <Card wide>
        <SectionHeader title="Today" />
        {today.length ? (
          <div className="att-rows">
            {today.map((record) => (
              <div className="att-row" key={record.id}>
                <Avatar name={record.person.display_name} />
                <div className="att-row__main">
                  <strong>{record.person.display_name}</strong>
                  <span className="muted num">
                    in {shortTime(record.check_in_at)} · out {shortTime(record.check_out_at)}
                    {record.minutes_late > 0 ? ` · ${record.minutes_late}m late` : ""}
                  </span>
                </div>
                <div className="att-row__status">
                  <StatusPill value={record.status} />
                </div>
                <ChaseControl
                  value={record.chase_state}
                  onChange={(state) => mutation.mutate({ id: record.id, state })}
                  disabled={mutation.isPending}
                />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No attendance records" />
        )}
      </Card>

      <Card wide>
        <SectionHeader title="History" />
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
                        {cell.check_in_at || cell.check_out_at ? (
                          <div className="cell-times">
                            <small className="muted num">in {shortTime(cell.check_in_at)}</small>
                            <small className="muted num">out {shortTime(cell.check_out_at)}</small>
                          </div>
                        ) : (
                          <small className="muted">—</small>
                        )}
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
      </Card>

      <Card>
        <SectionHeader title="Weekly lateness" />
        <BarChart
          data={weekly.map((row) => ({
            label: row.person.display_name,
            value: row.late,
            value2: row.late_15
          }))}
          ariaLabel="Weekly late and 15+ late counts per person"
          seriesLabels={["Late", "15+ Late"]}
        />
      </Card>

      <Card>
        <SectionHeader title="Weekly totals" />
        <div className="total-rows">
          {weekly.map((row) => (
            <div className="total-row" key={row.person.id}>
              <strong>{row.person.display_name}</strong>
              <span className="muted">
                {row.late} late · {row.late_15} × 15+ · {row.no_show} no-show
              </span>
            </div>
          ))}
        </div>
      </Card>
    </section>
  );
}
