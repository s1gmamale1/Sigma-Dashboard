import type { ElementType, ReactNode } from "react";

export function Card({
  children,
  wide,
  className = "",
  as: Tag = "section"
}: {
  children: ReactNode;
  wide?: boolean;
  className?: string;
  as?: ElementType;
}) {
  return <Tag className={`card${wide ? " card--wide" : ""} ${className}`.trim()}>{children}</Tag>;
}
