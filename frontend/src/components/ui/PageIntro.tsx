import type { ReactNode } from 'react';

interface PageIntroProps {
  description: string;
  actions?: ReactNode;
}

/** One line of context under the page title, with optional page-level actions on the right. */
export default function PageIntro({ description, actions }: PageIntroProps) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <p className="max-w-2xl text-[13px] text-muted">{description}</p>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
