import type { ProductEditionState } from "../../services/productEdition";

type Props = {
  edition: ProductEditionState;
  compact?: boolean;
};

/** Compact edition chip for the top bar — hidden until entitlement has loaded. */
export function ProductEditionBadge({ edition, compact = true }: Props) {
  if (!edition.loaded) return null;
  const pro = edition.is_pro;
  return (
    <span
      className={`product-edition-badge ${pro ? "product-edition-badge--pro" : "product-edition-badge--free"}`}
      data-testid="app-edition-badge"
      data-edition={edition.edition}
    >
      {compact ? (pro ? "Pro" : "免费版") : edition.edition_display_name}
    </span>
  );
}
