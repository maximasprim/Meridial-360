import type { Metadata } from "next";
import type { ReactNode } from "react";
import { HydrationBoundary, QueryClient, dehydrate } from "@tanstack/react-query";
import { ShopFooter } from "@/components/shop-footer";
import type { PublicFarmProfile } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ProfileResult = {
  profile: PublicFarmProfile | null;
  /** True when the API says this tenant's public store is switched off (HTTP 403). */
  unavailable: boolean;
};

/** Fetched on the server. Cached for 60s, so edits show within a minute. Falls back to null (the page then
 * loads the profile in the browser exactly as it does today) if the API is slow or down. */
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

/** Puts the farm's name in the tab title and description in the HTML itself, from the first paint. */
export async function generateMetadata({ params }: { params: { orgSlug: string } }): Promise<Metadata> {
  const { profile, unavailable } = await getProfile(params.orgSlug);
  if (unavailable) return { title: "Store unavailable", robots: { index: false, follow: false } };
  if (!profile) return {};
  return {
    title: { default: profile.farm_name, template: `%s | ${profile.farm_name}` },
    description: profile.tagline ?? undefined,
  };
}

export default async function ShopLayout({ children, params }: { children: ReactNode; params: { orgSlug: string } }) {
  const { profile, unavailable } = await getProfile(params.orgSlug);

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
