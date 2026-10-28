import type { SnapshotStatus } from "./api";

// Spec §5.2: real counts, not a progress bar. The slow stages report what they have done so
// far (pipeline.py): parse counts files, embed counts chunks; the others are quick.
const STAGE_UNITS: Record<string, [string, string]> = {
  parse: ["file", "files"],
  embed: ["chunk", "chunks"],
};
const count = new Intl.NumberFormat("en-US");

export function stageProgress(status: Pick<SnapshotStatus, "stage" | "progress">): string | null {
  const unit = STAGE_UNITS[status.stage];
  if (!unit || !status.progress) return null;
  const { done, total } = status.progress;
  return `${count.format(done)} / ${count.format(total)} ${total === 1 ? unit[0] : unit[1]}`;
}
