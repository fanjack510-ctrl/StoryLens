type Props = {
  bookId: number;
  onUpgrade: () => void;
};

/**
 * Book workspace entry for chapter-aggregate insights.
 * CHG-20260727-016: always hidden for 1.1.0 single-chapter release scope.
 * Direct route still shows a coming-soon page; do not delete this component.
 */
export function WholeBookInsightsEntry(_props: Props) {
  return null;
}
