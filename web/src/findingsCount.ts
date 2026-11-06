/** The number beside the Findings heading: "(60)", or "(48 of 60)" when a filter hides some. */
export function findingsCountLabel(matching: number, total: number): string {
  return matching === total ? `(${total})` : `(${matching} of ${total})`;
}
