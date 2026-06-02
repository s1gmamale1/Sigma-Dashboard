import { Inbox } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({
  title,
  icon,
  action
}: {
  title: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      {icon ?? <Inbox aria-hidden="true" size={22} />}
      <p>{title}</p>
      {action}
    </div>
  );
}
