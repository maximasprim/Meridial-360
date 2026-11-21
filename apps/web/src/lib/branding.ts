import { useQuery } from "@tanstack/react-query";
import { API_BASE } from "@/lib/api";
import { LAST_ORG_COOKIE, isOwnAppHost } from "@/lib/branding-shared";

/** What GET /api/v1/public/{slug}/branding returns. farm_name / logo_url are only present when a superadmin switched
 * tenant branding on for this farm (staff app and/or public shop). */
export interface Branding {
  staff_branding: boolean;
  shop_branding: boolean;
  farm_name: string | null;
  logo_url: string | null;
  has_icon: boolean;
  icon_version: string | null;
}

/** The sign-in page is branded on the SERVER from a cookie naming the last farm that signed in on this device (never for a
 * superadmin's workspace session), so the farm's name is already in the page when it arrives - for example after an
 * idle sign-out. A link like /login?org=farm-slug does the same for a first visit. */
export function rememberOrg(slug: string): void {
  try {
    const secure = window.location.protocol === "https:" ? "; Secure" : "";
    document.cookie = `${LAST_ORG_COOKIE}=${encodeURIComponent(slug)}; Path=/; Max-Age=31536000; SameSite=Lax${secure}`;
  } catch {
    /* cookies unavailable: the page simply shows the platform branding */
  }
}

const onFarmDomain = () => typeof window !== "undefined" && !isOwnAppHost(window.location.host);

/** On a farm's own domain the browser may not be allowed to call the API directly (the API's CORS list is fixed), so
 * the lookup goes through this app's own /api/branding route, which asks the API from the server. */
async function loadBranding(slug: string): Promise<Branding | null> {
  if (onFarmDomain()) {
    const res = await fetch(`/api/branding?slug=${encodeURIComponent(slug)}`);
    return res.ok ? (((await res.json()) as { branding: Branding | null }).branding ?? null) : null;
  }
  const res = await fetch(`${API_BASE}/api/v1/public/${encodeURIComponent(slug)}/branding`);
  return res.ok ? ((await res.json()) as Branding) : null;
}

/** Public, unauthenticated, cheap. Any failure means "no tenant branding" so nothing ever breaks the page. */
export function useBranding(slug: string | null | undefined) {
  return useQuery<Branding | null>({
    queryKey: ["branding", slug],
    enabled: !!slug,
    staleTime: 60_000,
    retry: 0,
    queryFn: async () => {
      try {
        return await loadBranding(slug as string);
      } catch {
        return null;
      }
    },
  });
}
