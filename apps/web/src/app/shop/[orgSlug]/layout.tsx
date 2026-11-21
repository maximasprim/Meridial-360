import type { Metadata } from "next";
import type { ReactNode } from "react";
import { HydrationBoundary, QueryClient, dehydrate } from "@tanstack/react-query";
import { ShopFooter } from "@/components/shop-footer";
import type { PublicFarmProfile } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type StoreStatus = {
  /** Is the public store switched on? */
  enabled: boolean;
  /** A superadmin chose the farm's own name + logo for the installed shop app. */
  shop_branding: boolean;
  /** An uploaded logo exists, so the API can serve installed-app icons made from it. */
  has_icon: boolean;
  icon_version: string | null;
};

const DEFAULT_STATUS: StoreStatus = { enabled: true, shop_branding: false, has_icon: false, icon_version: null };

type ProfileResult = {
  profile: PublicFarmProfile | null;
  /** True when this tenant's public store is switched off. */
  unavailable: boolean;
};

type LoadResult = ProfileResult & { status: StoreStatus };

/** One tiny endpoint that answers 200 either way, cached for 15s: Next.js only stores 200 responses, so asking the
 * profile endpoint (which answers 403 when the store is off) would keep serving a stale "store is on" copy. Anything
 * unexpected (unknown farm, API slow or down) counts as "on, platform branding" so the page behaves as before. */
async function getStoreStatus(orgSlug: string): Promise<StoreStatus> {
  try {
    const res = await fetch(`${API}/api/v1/public/${orgSlug}/store-status`, {
      next: { revalidate: 15 },
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) return DEFAULT_STATUS;
    const data = (await res.json()) as Partial<StoreStatus>;
    return {
      enabled: data.enabled !== false,
      shop_branding: data.shop_branding === true,
      has_icon: data.has_icon === true,
      icon_version: data.icon_version ?? null,
    };
  } catch {
    return DEFAULT_STATUS;
  }
}

/** Fetched on the server. Cached for 60s, so edits show within a minute. Falls back to null (the page then
 * loads the profile in the browser exactly as it does today) if the API is slow or down. A 403 here also means the
 * store is off (covers an older API without the status endpoint). */
async function getProfile(orgSlug: string): Promise<ProfileResult> {
  try {
    const res = await fetch(`${API}/api/v1/public/${orgSlug}/profile`, {
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(4000),
    });
    if (res.status === 403) return { profile: null, unavailable: true };
    return { profile: res.ok ? ((await res.json()) as PublicFarmProfile) : null, unavailable: false };
  } catch {
    return { profile: null, unavailable: false };
  }
}

async function load(orgSlug: string): Promise<LoadResult> {
  const status = await getStoreStatus(orgSlug);
  if (!status.enabled) return { profile: null, unavailable: true, status };
  return { ...(await getProfile(orgSlug)), status };
}

/** Puts the farm's name in the tab title and description in the HTML itself, from the first paint. When a superadmin
 * switched on the farm's own branding for the shop, it also points the page at the farm's installed-app manifest, icon
 * and home-screen title (otherwise the platform's, set in the root layout, are left alone). */
export async function generateMetadata({ params }: { params: { orgSlug: string } }): Promise<Metadata> {
  const { profile, unavailable, status } = await load(params.orgSlug);
  if (unavailable) return { title: "Store unavailable", robots: { index: false, follow: false } };
  if (!profile) return {};
  const iconBase = `${API}/api/v1/public/${params.orgSlug}/app-icon`;
  const v = status.icon_version ? `?v=${status.icon_version}` : "";
  return {
    title: { default: profile.farm_name, template: `%s | ${profile.farm_name}` },
    description: profile.tagline ?? undefined,
    ...(status.shop_branding
      ? {
          manifest: `/app-manifest/shop/${params.orgSlug}`,
          appleWebApp: { capable: true, title: profile.farm_name },
          ...(status.has_icon
            ? {
                icons: {
                  icon: [
                    { url: `${iconBase}/favicon-32.png${v}`, sizes: "32x32", type: "image/png" },
                    { url: `${iconBase}/192.png${v}`, sizes: "192x192", type: "image/png" },
                  ],
                  apple: [{ url: `${iconBase}/apple-180.png${v}`, sizes: "180x180", type: "image/png" }],
                },
              }
            : {}),
        }
      : {}),
  };
}

export default async function ShopLayout({ children, params }: { children: ReactNode; params: { orgSlug: string } }) {
  const { profile, unavailable } = await load(params.orgSlug);

  // A tenant whose public store is switched off (by its package or by a platform admin) shows a plain notice instead of
  // the shop. Its system and data are untouched - only this public front is closed.
  if (unavailable) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-paper px-6 text-center">
        <div className="max-w-md">
          <h1 className="font-display text-3xl text-forest">This store is currently unavailable</h1>
          <p className="mt-3 text-sm text-muted">Please check back later or contact the farm directly.</p>
        </div>
      </main>
    );
  }

  // Hand the profile to react-query under the SAME key the pages already use, so useShopProfile() finds the data
  // on its first render and there is no loading state.
  const queryClient = new QueryClient();
  if (profile) queryClient.setQueryData(["public-profile", params.orgSlug], profile);

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      {children}
      <ShopFooter orgSlug={params.orgSlug} />
    </HydrationBoundary>
  );
}
