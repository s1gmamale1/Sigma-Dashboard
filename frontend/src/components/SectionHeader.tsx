import type { ReactNode } from "react";

export function SectionHeader({
  title,
  eyebrow,
  actions
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="section-header">
      <div>
        {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
        <h2 className="h2">{title}</h2>
      </div>
      {actions ? <div className="section-header__actions">{actions}</div> : null}
    </header>
  );
}
