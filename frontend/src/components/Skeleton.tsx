export function Skeleton({
  w = "100%",
  h = 16,
  r = 8,
  className = ""
}: {
  w?: string | number;
  h?: string | number;
  r?: number;
  className?: string;
}) {
  return (
    <span
      className={`skeleton ${className}`.trim()}
      aria-hidden="true"
      style={{ width: w, height: h, borderRadius: r }}
    />
  );
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <span className="skeleton-text">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} w={i === lines - 1 ? "60%" : "100%"} h={12} />
      ))}
    </span>
  );
}
