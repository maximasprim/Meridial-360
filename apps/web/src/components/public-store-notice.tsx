"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { PublicStoreNotice as PublicStoreNoticeData } from "@/lib/billing-types";

/** Tells an organization's admins when their public store is switched off, and why. Renders nothing when it is on
 * (or while loading / if the status can't be fetched), so it never gets in the way. */
export function PublicStoreNotice() {
  const statusQuery = useQuery<PublicStoreNoticeData>({
    queryKey: ["public-store-notice"],
    queryFn: () => apiFetch<PublicStoreNoticeData>("/api/v1/billing/public-store"),
  });

  const status = statusQuery.data;
  if (!status || status.enabled) return null;

  return (
    <div role="status" className="mb-6 rounded-lg border border-clay/30 bg-clay/5 px-4 py-3 text-sm text-red-600">
      <p className="font-bold">Your public store is switched off.</p>
      <p className="mt-1">
        {status.reason === "package"
          ? `Your ${status.package_name ?? "current"} plan does not include the public store. Customers can't see your shop until you move to a plan that includes it (see Billing).`
          : "It has been switched off by the platform administrator. Customers can't see your shop until it is switched back on - please contact support."}{" "}
        Your system, staff and data are not affected.
      </p>
    </div>
  );
}
