"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, Button, Input, ErrorState } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";
import type { PublicStoreStatus } from "@/lib/platform-types";

type Mode = PublicStoreStatus["mode"];

const CHOICES: { mode: Mode; label: string }[] = [
  { mode: "package", label: "Follow package" },
  { mode: "on", label: "Force on" },
  { mode: "off", label: "Force off" },
];

/**
 * One organization's public store switch (superadmin). Only the public storefront is affected - the organization's own
 * system keeps working. "Follow package" hands the decision back to the billing package it is on.
 */
export function PublicStoreCard({ orgId, canWrite }: { orgId: string; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const key = ["platform-public-store", orgId];
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const statusQuery = useQuery<PublicStoreStatus>({
    queryKey: key,
    queryFn: () => platformApiFetch<PublicStoreStatus>(`/api/v1/platform/organizations/${orgId}/public-store`),
  });

  const save = useMutation({
    mutationFn: (mode: Mode) =>
      platformApiFetch<PublicStoreStatus>(`/api/v1/platform/organizations/${orgId}/public-store`, {
        method: "PATCH",
        body: JSON.stringify({ mode, reason: reason.trim() || null }),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(key, data);
      setReason("");
      setError(null);
    },
    onError: (err) => setError(err instanceof PlatformApiError ? err.message : "Failed to update the public store"),
  });

  const s = statusQuery.data;
  const source = !s
    ? ""
    : s.mode === "on"
      ? "Forced on by a superadmin, whatever the package says."
      : s.mode === "off"
        ? "Forced off by a superadmin, whatever the package says."
        : `Following the ${s.package_name ?? "current"} package, which ${s.package_allows ? "includes" : "does not include"} the public store.`;

  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-muted">Public store</p>
          {statusQuery.error ? (
            <p className="text-sm text-clay">Could not load the public store status.</p>
          ) : (
            <>
              <p className={s?.enabled ? "font-display text-2xl text-moss" : "font-display text-2xl text-clay"}>
                {s ? (s.enabled ? "Active" : "Deactivated") : "…"}
              </p>
              <p className="text-sm text-muted">{source}</p>
            </>
          )}
        </div>
        {canWrite && s && (
          <div className="flex flex-wrap justify-end gap-2">
            {CHOICES.map((c) => (
              <Button
                key={c.mode}
                variant={s.mode === c.mode ? "primary" : "ghost"}
                disabled={save.isPending || s.mode === c.mode}
                onClick={() => save.mutate(c.mode)}
              >
                {c.label}
              </Button>
            ))}
          </div>
        )}
      </div>
      {canWrite && s && (
        <div className="mt-3 max-w-md">
          <Input label="Reason (optional, kept in the audit log)" value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
      )}
      {error && <div className="mt-3"><ErrorState message={error} /></div>}
      <p className="mt-3 text-xs text-muted">
        When deactivated, the shop pages, listings, orders, reviews, contact form and customer sign-up on this organization&apos;s public
        site stop working. Its staff, data and admin system are not affected.
      </p>
    </Card>
  );
}
