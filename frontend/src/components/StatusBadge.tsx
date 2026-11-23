const LABELS: Record<string, string> = {
  approved: "Approved",
  needs_review: "Needs review",
  rejected: "Rejected",
  processing: "Processing",
};

export default function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${status}`}>{LABELS[status] ?? status}</span>;
}
