import { Inbox } from "lucide-react";

export function EmptyState({ title }: { title: string }) {
  return (
    <div className="empty-state">
      <Inbox aria-hidden="true" size={22} />
      <p>{title}</p>
    </div>
  );
}

