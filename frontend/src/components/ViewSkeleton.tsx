import { Skeleton } from "./Skeleton";

function SkeletonCard({ wide, chartHeight = 120 }: { wide?: boolean; chartHeight?: number }) {
  return (
    <div className={`card${wide ? " card--wide" : ""}`} style={{ display: "grid", gap: "var(--sp-3)" }}>
      <Skeleton w="38%" h={16} />
      <Skeleton h={chartHeight} r={12} />
    </div>
  );
}

export function ViewSkeleton() {
  return (
    <section className="view-grid" aria-busy="true" aria-label="Loading">
      <div className="metric-row">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card" style={{ display: "grid", gap: "var(--sp-2)" }}>
            <Skeleton w="55%" h={12} />
            <Skeleton w="40%" h={28} r={10} />
          </div>
        ))}
      </div>
      <SkeletonCard wide chartHeight={160} />
      <SkeletonCard />
      <SkeletonCard />
    </section>
  );
}
