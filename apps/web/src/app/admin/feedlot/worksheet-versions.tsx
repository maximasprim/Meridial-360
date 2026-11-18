"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, ErrorState, Input } from "@/components/ui";
import { apiDownload, apiFetch, ApiError } from "@/lib/api";

interface Version {
  id: string; version_no: number; source: "upload" | "sync" | "restore" | "unpost"; filename: string | null; size_bytes: number;
  has_file: boolean; note: string | null; created_at: string; is_latest: boolean; restored_from_version_no: number | null;
  summary: { weights?: { appended: number; voided: number; restored: number; entry_weights: number }; conflicts?: number; warnings?: number } | null;
}
interface Change { tag: string; void: { date: string; kg: number }[]; append: { date: string; kg: number }[]; restore: { date: string; kg: number }[] }
interface Report {
  dry_run: boolean; ok: boolean; created: Record<string, number>; updated: Record<string, number>;
  weight_changes?: Change[]; weight_conflicts?: { tag: string; date: string; system_kg: number; sheet_kg: number }[];
  warnings: { code: string; message: string }[];
}

const when = (iso: string) => new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);
interface FinReport {
  dry_run: boolean; dating: string; animals_checked: number; animals_with_changes: number; entries: number; net_amount: number;
  by_month: Record<string, number>; purchases_not_booked_yet: number;
  items: { tag: string; batch: number; booked: number; expected: number; adjustments: { date: string; amount: number }[] }[];
}
const kes = (n: number) => `KES ${n.toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
const SOURCE: Record<Version["source"], string> = { upload: "Uploaded", sync: "Google Sheet", restore: "Restored", unpost: "Unposted" };

/** Every worksheet that was imported, with preview + restore, and an "unpost all imported weights" action. */
export function WorksheetVersions() {
  const qc = useQueryClient();
  const q = useQuery<Version[]>({ queryKey: ["feedlot", "worksheet-versions"], queryFn: () => apiFetch<Version[]>("/api/v1/feedlot/worksheet/versions") });
  const [shown, setShown] = useState<{ title: string; report: Report; apply: (() => void) | null } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [confirm, setConfirm] = useState("");
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["feedlot"] }); void qc.invalidateQueries({ queryKey: ["weights"] }); };

  const restore = useMutation({
    mutationFn: ({ id, dry }: { id: string; dry: boolean }) => apiFetch<Report>(`/api/v1/feedlot/worksheet/versions/${id}/restore?dry_run=${dry}`, { method: "POST" }),
    onError: (e) => setErr(errMsg(e, "Could not restore that version")),
  });
  const unpost = useMutation({
    mutationFn: ({ dry }: { dry: boolean }) => apiFetch<Report>(`/api/v1/feedlot/worksheet/unpost?dry_run=${dry}${dry ? "" : `&confirm=${encodeURIComponent(confirm)}`}`, { method: "POST" }),
    onError: (e) => setErr(errMsg(e, "Could not unpost")),
  });

  const preview = async (v: Version) => {
    setErr(null);
    const report = await restore.mutateAsync({ id: v.id, dry: true });
    setShown({ title: `Preview: restore version ${v.version_no}`, report, apply: async () => {
      const done = await restore.mutateAsync({ id: v.id, dry: false });
      setShown({ title: `Restored version ${v.version_no}`, report: done, apply: null }); refresh(); void q.refetch();
    } });
  };
  const previewUnpost = async () => {
    setErr(null);
    const report = await unpost.mutateAsync({ dry: true });
    setShown({ title: "Preview: unpost every imported weight", report, apply: null });
  };
  const doUnpost = async () => {
    setErr(null);
    const done = await unpost.mutateAsync({ dry: false });
    setShown({ title: "Unposted every imported weight", report: done, apply: null }); setConfirm(""); refresh(); void q.refetch();
  };
  const [dating, setDating] = useState<"original" | "today">("original");
  const [fin, setFin] = useState<FinReport | null>(null);
  const finRun = useMutation({
    mutationFn: ({ dry }: { dry: boolean }) => apiFetch<FinReport>(`/api/v1/feedlot/finance-align?dry_run=${dry}&dating=${dating}`, { method: "POST" }),
    onSuccess: (r) => { setFin(r); setErr(null); if (!r.dry_run) void qc.invalidateQueries({ queryKey: ["finance"] }); },
    onError: (e) => setErr(errMsg(e, "Could not align Finance")),
  });
  const busy = restore.isPending || unpost.isPending || finRun.isPending;
  const w = (r: Report) => ({ appended: r.created.weight_records ?? 0, voided: r.updated.weights_voided ?? 0, restored: r.updated.weights_restored ?? 0, entry: r.updated.entry_weights ?? 0 });

  return (
    <Card className="space-y-3">
      <h2 className="font-display text-lg text-forest">Worksheet versions</h2>
      <p className="text-sm text-muted">Every worksheet that is imported is kept here. Restoring a version puts the <b>weights</b> on existing animals back to what that worksheet said, and it is recorded as a new version, so it can be undone. It does not delete animals, sales or Finance entries.</p>
      {q.isError && <ErrorState message="Could not load the versions" />}
      {q.data && q.data.length === 0 && <p className="text-sm text-muted">Nothing has been imported since versions were switched on.</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-muted"><tr><th className="py-1 pr-3">Version</th><th className="pr-3">When</th><th className="pr-3">Source</th><th className="pr-3">What changed</th><th /></tr></thead>
          <tbody>
            {(q.data ?? []).map((v) => (
              <tr key={v.id} className="border-t border-hairline align-top">
                <td className="py-2 pr-3 font-medium">v{v.version_no}{v.is_latest && <span className="ml-1 text-xs text-forest">latest</span>}</td>
                <td className="pr-3">{when(v.created_at)}</td>
                <td className="pr-3">{SOURCE[v.source]}{v.filename ? ` · ${v.filename}` : ""}{v.restored_from_version_no ? ` (of v${v.restored_from_version_no})` : ""}</td>
                <td className="pr-3 text-xs text-muted">
                  {v.summary?.weights ? `${v.summary.weights.appended} added, ${v.summary.weights.voided} set aside, ${v.summary.weights.restored} brought back` : v.note ?? "–"}
                  {v.summary?.conflicts ? ` · ${v.summary.conflicts} need attention` : ""}
                </td>
                <td className="space-x-1 whitespace-nowrap text-right">
                  {v.has_file && <Button variant="ghost" disabled={busy} onClick={() => void apiDownload(`/api/v1/feedlot/worksheet/versions/${v.id}/download`, `Worksheet_version_${v.version_no}.xlsx`)}>Download</Button>}
                  {v.has_file && !v.is_latest && <Button variant="ghost" disabled={busy} onClick={() => void preview(v)}>Preview restore</Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {err && <ErrorState message={err} />}
      {shown && (
        <div className="space-y-2 rounded-md border border-hairline p-3 text-sm">
          <p className="font-medium">{shown.title}</p>
          <p>{w(shown.report).voided} weight(s) set aside · {w(shown.report).appended} added · {w(shown.report).restored} brought back · {w(shown.report).entry} entry weight(s) corrected</p>
          {(shown.report.weight_changes ?? []).slice(0, 12).map((c) => (
            <p key={c.tag} className="text-xs text-muted"><b>{c.tag}</b>
              {c.void.map((x) => ` · remove ${x.date} ${x.kg}kg`).join("")}{c.append.map((x) => ` · add ${x.date} ${x.kg}kg`).join("")}{c.restore.map((x) => ` · bring back ${x.date} ${x.kg}kg`).join("")}
            </p>
          ))}
          {(shown.report.weight_changes?.length ?? 0) > 12 && <p className="text-xs text-muted">…and {(shown.report.weight_changes?.length ?? 0) - 12} more animals</p>}
          {(shown.report.weight_conflicts ?? []).length > 0 && <p className="text-xs text-clay">{shown.report.weight_conflicts!.length} weight(s) entered by hand differ from the worksheet and were left as they are.</p>}
          {shown.report.warnings.filter((x) => x.code !== "date_unresolved").slice(0, 4).map((x, i) => <p key={i} className="text-xs text-clay">{x.message}</p>)}
          {shown.apply && <Button disabled={busy} onClick={shown.apply}>Restore this version</Button>}
        </div>
      )}
      <div className="space-y-2 border-t border-hairline pt-3">
        <p className="text-sm font-medium">Unpost everything the worksheet imported</p>
        <p className="text-xs text-muted">Sets aside every imported weight (weights entered by hand stay). Reversible: restore any version to bring them back. Animals, sales and Finance entries are not touched.</p>
        <div className="flex flex-wrap items-end gap-2">
          <Button variant="ghost" disabled={busy} onClick={() => void previewUnpost()}>Preview</Button>
          <Input label="Type UNPOST to apply" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          <Button disabled={busy || confirm !== "UNPOST"} onClick={() => void doUnpost()}>Unpost</Button>
        </div>
      </div>
      <div className="space-y-2 border-t border-hairline pt-3">
        <p className="text-sm font-medium">Align Finance purchases with the worksheet</p>
        <p className="text-xs text-muted">After animals were moved between batches, their purchase cost follows the new batch. This adds adjusting entries to the Finance ledger (nothing is edited or deleted) so the books match. Always preview first.</p>
        <select value={dating} onChange={(e) => setDating(e.target.value as "original" | "today")} className="rounded-md border border-hairline bg-white px-3 py-2 text-sm">
          <option value="original">Correct each month (use the original dates)</option>
          <option value="today">Leave past months as reported (one entry dated today)</option>
        </select>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" disabled={busy} onClick={() => finRun.mutate({ dry: true })}>Preview</Button>
          <Button disabled={busy || !fin || !fin.dry_run || fin.entries === 0} onClick={() => finRun.mutate({ dry: false })}>Post {fin?.entries ?? 0} adjusting entries</Button>
        </div>
        {fin && (
          <div className="space-y-1 text-sm">
            <p className="font-medium">{fin.dry_run ? "Preview" : "Posted"}: {fin.entries} entries for {fin.animals_with_changes} animals · net {kes(fin.net_amount)}</p>
            {Object.entries(fin.by_month).map(([m, v]) => <p key={m} className="text-xs text-muted">{m}: {kes(v)}</p>)}
            {fin.items.slice(0, 12).map((i) => (
              <p key={i.tag} className="text-xs text-muted"><b>{i.tag}</b> (batch {i.batch}) booked {kes(i.booked)}, should be {kes(i.expected)}</p>
            ))}
            {fin.purchases_not_booked_yet > 0 && <p className="text-xs text-clay">{fin.purchases_not_booked_yet} animal(s) have no purchase in Finance yet; the normal Finance sync books those.</p>}
          </div>
        )}
      </div>
    </Card>
  );
}
