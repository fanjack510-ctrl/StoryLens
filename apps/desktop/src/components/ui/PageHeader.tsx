import type { ReactNode } from "react";

export function PageHeader({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <header className={`sl-page-header page-title ${className}`.trim()}>{children}</header>;
}

export function PageTitle({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <h1 className={`sl-page-title ${className}`.trim()}>{children}</h1>;
}

export function PageSubtitle({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <p className={`sl-page-subtitle ${className}`.trim()}>{children}</p>;
}

export function SectionHeader({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <h2 className={`sl-section-title ${className}`.trim()}>{children}</h2>;
}
