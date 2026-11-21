"use client";

import { useEffect } from "react";
import { useMe } from "@/lib/use-auth";
import { getWorkspaceSession } from "@/lib/impersonation";
import { rememberOrg, useBranding } from "@/lib/branding";
import { useAppBrandingHead } from "@/lib/use-app-branding-head";

/** Mounted once in the admin layout (renders nothing). Does two things for the signed-in farm:
 *  1. remembers it on this device so the sign-in page can show its branding next time;
 *  2. when a superadmin switched staff branding on, makes the installed app / home-screen entry use the farm's own
 *     name and logo instead of the platform's.
 * Skipped while a superadmin is working inside a farm's workspace, so the platform console never takes on a farm's identity. */
export function StaffBranding() {
  const slug = useMe().data?.organization.slug ?? null;
  const impersonating = typeof window !== "undefined" && !!getWorkspaceSession();

  useEffect(() => {
    if (slug && !getWorkspaceSession()) rememberOrg(slug);
  }, [slug]);

  const branding = useBranding(impersonating ? null : slug).data;
  useAppBrandingHead({
    active: !!branding?.staff_branding && !impersonating,
    slug,
    name: branding?.farm_name,
    hasIcon: branding?.has_icon,
    version: branding?.icon_version,
  });
  return null;
}
