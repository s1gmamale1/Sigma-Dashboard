import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import { EmptyState } from "./EmptyState";

export function SheetsView({ token }: { token: string }) {
  const queryClient = useQueryClient();
  const preview = useQuery({
    queryKey: ["google-sheet-preview"],
    queryFn: () => api.googleSheetPreview(token),
    retry: 0
  });
  const importer = useMutation({
    mutationFn: () => api.googleSheetImport(token),
    onSuccess: () => {
      void queryClient.invalidateQueries();
    }
  });

  if (preview.isLoading) return <EmptyState title="Loading Google Sheet" />;
  if (preview.error) {
    return (
      <section className="panel wide">
        <header className="panel-header">
          <h2>Google Sheet</h2>
        </header>
        <EmptyState title={preview.error instanceof Error ? preview.error.message : "Unable to read Google Sheet"} />
      </section>
    );
  }
  if (!preview.data) return <EmptyState title="No Google Sheet data" />;

  return (
    <section className="view-grid">
      <section className="panel wide">
        <header className="panel-header">
          <div>
            <h2>{preview.data.spreadsheet_title}</h2>
            <span>Configured as {preview.data.configured_name}</span>
          </div>
          <button className="primary-button compact" onClick={() => importer.mutate()} disabled={importer.isPending}>
            <RefreshCw size={16} aria-hidden="true" />
            {importer.isPending ? "Importing" : "Import recognized tabs"}
          </button>
        </header>
        {importer.data ? (
          <div className="import-result">
            <Database size={18} aria-hidden="true" />
            <span>
              Imported {Object.entries(importer.data.imported).map(([key, value]) => `${value} ${key}`).join(", ")}.
            </span>
          </div>
        ) : null}
        {importer.error ? (
          <p className="form-error">{importer.error instanceof Error ? importer.error.message : "Import failed"}</p>
        ) : null}
      </section>

      {preview.data.tabs.map((tab) => (
        <section className="panel wide" key={tab.title}>
          <header className="panel-header">
            <div>
              <h2>{tab.title}</h2>
              <span>{tab.row_count} rows · {tab.column_count} columns · {tab.sample_range}</span>
            </div>
          </header>
          {tab.values.length ? (
            <div className="matrix-wrap">
              <table className="sheet-preview">
                <tbody>
                  {tab.values.map((row, rowIndex) => (
                    <tr key={`${tab.title}-${rowIndex}`}>
                      {Array.from({ length: Math.max(...tab.values.map((valueRow) => valueRow.length)) }).map((_, cellIndex) => (
                        <td key={cellIndex}>{row[cellIndex] ?? ""}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="This tab has no visible values in the sampled range" />
          )}
        </section>
      ))}
    </section>
  );
}
