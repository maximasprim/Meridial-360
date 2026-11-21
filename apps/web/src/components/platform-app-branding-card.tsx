"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Card, Button, ErrorState } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";
import type { AppBrandingStatus } from "@/lib/platform-types";

type Surface = "staff" | "shop";

const ROWS: { surface: Surface; title: string; text: string }[] = [
  {
    surface: "staff",
    title: "Staff app and sign-in page",
    text: "The app staff install on their phone or computer, and the page they sign in on.",
  },
  {
    surface: "shop",
    title: "Public shop app",
    text: "The app a customer can install from this farm's public shop.",
  },
];

/**
 * One organization's app branding (superadmin). For each surface, separately: show the PLATFORM's name and logo
 * (the default) or the FARM's own. Only the name and icon of the installed app, and the sign-in page for staff,
 * change - nothing else about the organization is affected.
 */
export function PlatformAppBrandingCard({ orgId, canWrite }: { orgId: string; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const key = ["platform-app-branding", orgId];
  const url = `/api/v1/platform/organizations/${orgId}/app-branding`;
  const [error, setError] = useState<string | null>(null);

  const statusQuery = useQuery<AppBrandingStatus>({ queryKey: key, queryFn: () => platformApiFetch<AppBrandingStatus>(url) });

  const save = useMutation({
    mutationFn: (body: Partial<Record<Surface, boolean>>) =>
      platformApiFetch<AppBrandingStatus>(url, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: (data) => {
      queryClient.setQueryData(key, data);
      setError(null);
    },
    onError: (err) => setError(err instanceof PlatformApiError ? err.message : "Failed to update the branding"),
  });

  const s = statusQuery.data;
  const isTenant = (surface: Surface) => (s ? (surface === "staff" ? s.staff_tenant_branding : s.shop_tenant_branding) : false);

  return (
    <Card>
      <p className="text-xs font-medium uppercase tracking-wider text-muted">App branding</p>
      {statusQuery.error && <p className="mt-1 text-sm text-clay">Could not load the app branding.</p>}
      {s && (
        <>
          <p className="mt-1 text-sm text-muted">
            Choose whether each installed app shows the platform&apos;s name and logo, or {s.farm_name ? `“${s.farm_name}”` : "the farm"}&apos;s own.
          </p>
          <div className="mt-4 space-y-4">
            {ROWS.map((row) => (
              <div key={row.surface} className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink">{row.title}</p>
                  <p className="text-xs text-muted">{row.text}</p>
                  <p className={isTenant(row.surface) ? "mt-1 text-xs font-medium text-moss" : "mt-1 text-xs font-medium text-muted"}>
                    Showing: {isTenant(row.surface) ? "the farm's own name and logo" : "the platform's name and logo"}
                  </p>
                </div>
                {canWrite && (
                  <div className="flex gap-2">
                    <Button
                      variant={!isTenant(row.surface) ? "primary" : "ghost"}
                      disabled={save.isPending || !isTenant(row.surface)}
                      onClick={() => save.mutate({ [row.surface]: false })}
                    >
                      Platform
                    </Button>
                    <Button
                      variant={isTenant(row.surface) ? "primary" : "ghost"}
                      disabled={save.isPending || isTenant(row.surface)}
                      onClick={() => save.mutate({ [row.surface]: true })}
                    >
                      Farm&apos;s own
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
          {!s.has_icon && (
            <p className="mt-4 text-xs text-muted">
              {s.has_logo
                ? "This farm's logo is a pasted web address, so installed-app icons can't be made from it - the farm's name is used with the platform icon. Uploading the logo from a device in Site content fixes that."
                : "This farm hasn't uploaded a logo yet, so its name is used with the platform icon until it does."}
            </p>
          )}
          {error && <div className="mt-3"><ErrorState message={error} /></div>}
          <p className="mt-4 text-xs text-muted">
            Devices that already installed an app may keep the old name and icon until it is reinstalled. On the sign-in page, staff see the
            farm&apos;s name once the device has signed in before, or via a link ending in <span className="font-mono">/login?org={"{farm-slug}"}</span>.
          </p>
        </>
      )}
    </Card>
  );
}
