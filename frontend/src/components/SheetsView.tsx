import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import type { GoogleSheetTabPreview } from "../lib/types";
import { Card } from "./Card";
import { SectionHeader } from "./SectionHeader";
import { SkeletonText } from "./Skeleton";
import { EmptyState } from "./EmptyState";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function TabPreview({ tab }: { tab: GoogleSheetTabPreview }) {
  if (!tab.values.length) {
    return <EmptyState title="This tab has no visible values in the sampled range" />;
  }
  const columnCount = tab.values.reduce((max, row) => Math.max(max, row.length), 0);
  return (
    <div className="matrix-wrap">
      <table className="sheet-preview">
        <tbody>
          {tab.values.map((row, rowIndex) => (
            <tr key={`${tab.title}-${rowIndex}`}>
              {Array.from({ length: columnCount }).map((_, cellIndex) => (
                <td key={cellIndex}>{row[cellIndex] ?? ""}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

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

  if (preview.isLoading) {
    return (
      <section className="view-grid">
        <Card wide>
          <SkeletonText lines={4} />
        </Card>
      </section>
    );
  }

  if (preview.error) {
    return (
      <section className="view-grid">
        <Card wide>
          <SectionHeader title="Google Sheet" />
          <EmptyState title={errorMessage(preview.error, "Unable to read Google Sheet")} />
        </Card>
      </section>
    );
  }

  if (!preview.data) return <EmptyState title="No Google Sheet data" />;

  return (
    <section className="view-grid">
      <Card wide>
        <SectionHeader
          title={preview.data.spreadsheet_title}
          eyebrow={`Configured as ${preview.data.configured_name}`}
          actions={
            <button
              className="primary-button compact"
              onClick={() => importer.mutate()}
              disabled={importer.isPending}
            >
              <RefreshCw size={16} aria-hidden="true" />
              {importer.isPending ? "Importing" : "Import recognized tabs"}
            </button>
          }
        />
        {importer.data ? (
          <div className="import-result">
            <Database size={18} aria-hidden="true" />
            <span>
              Imported{" "}
              {Object.entries(importer.data.imported)
                .map(([key, value]) => `${value} ${key}`)
                .join(", ")}
              .
            </span>
          </div>
        ) : null}
        {importer.error ? (
          <p className="form-error">{errorMessage(importer.error, "Import failed")}</p>
        ) : null}
      </Card>

      {preview.data.tabs.map((tab) => (
        <Card wide key={tab.title}>
          <SectionHeader
            title={tab.title}
            eyebrow={`${tab.row_count} rows · ${tab.column_count} columns · ${tab.sample_range}`}
          />
          <TabPreview tab={tab} />
        </Card>
      ))}
    </section>
  );
}
