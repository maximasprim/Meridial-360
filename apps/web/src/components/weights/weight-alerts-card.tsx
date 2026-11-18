"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useCan } from "@/lib/use-auth";
import { fullDate, kg, type WeightAlertList } from "@/lib/weights-types";

/** Dashboard follow-up list: animals whose daily gain between the last two weighings is above +2 or below -2 kg/day.
 *  Shows nothing when there are none (or when the person may not see weights). Marking one reviewed hides that reading. */
export function WeightAlertsCard() {
  const can = useCan();
  const qc = useQueryClient();
  const q = useQuery<WeightAlertList>({ queryKey: ["weights", "alerts"], queryFn: () => apiFetch<WeightAlertList>("/api/v1/weights/alerts"), retry: false });
  const review = useMutation({
    mutationFn: (v: { animal_id: string; alert_date: string }) => apiFetch(`/api/v1/weights/alerts/${v.animal_id}/review`, { method: "POST", body: JSON.stringify({ alert_date: v.alert_date }) }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["weights"] }); },
  });
  if (q.isError || !q.data || q.data.count === 0) return null;
  const { alerts, threshold, count } = q.data;
  return (
    <section role="alert" className="mt-6 rounded-lg border border-clay/30 bg-clay/5 px-4 py-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-medium text-clay">{count} weight{count === 1 ? "" : "s"} to follow up</h2>
        <Link href="/admin/weights" className="text-forest hover:underline">Open weights →</Link>
      </div>
      <p className="mb-2 text-xs text-muted">Daily gain between the last two weighings is above +{threshold} or below -{threshold} kg/day. One of the two weights may be a mistake.</p>
      <ul className="divide-y divide-clay/20">
        {alerts.map((a) => (
          <li key={`${a.animal_id}-${a.to_date}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5">
            <Link href={`/admin/livestock/${a.animal_id}`} className="font-medium text-ink hover:underline">{a.tag}</Link>
            {a.batch && <span className="text-xs text-muted">{a.batch}</span>}
            <span className="font-medium text-clay">{a.adg > 0 ? "+" : ""}{a.adg.toFixed(2)} kg/day</span>
            <span className="text-xs text-muted">{kg(a.from_kg)} on {fullDate(a.from_date)} → {kg(a.to_kg)} on {fullDate(a.to_date)} ({a.days} {a.days === 1 ? "day" : "days"})</span>
            {can("weights.targets") && (
              <Button variant="ghost" className="ml-auto" disabled={review.isPending} onClick={() => review.mutate({ animal_id: a.animal_id, alert_date: a.to_date })}>Mark reviewed</Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
