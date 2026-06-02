export function Avatar({ name }: { name: string }) {
  const initials = name
    .trim()
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <span className="avatar" aria-hidden="true">
      {initials || "?"}
    </span>
  );
}
