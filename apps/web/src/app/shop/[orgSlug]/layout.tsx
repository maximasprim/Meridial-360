import type { Metadata } from "next";
import type { ReactNode } from "react";
import { HydrationBoundary, QueryClient, dehydrate } from "@tanstack/react-query";
import { ShopFooter } from "@/components/shop-footer";
import type { PublicFarmProfile } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Fetched on the server. Cached for 60s, so edits show within a minute. Falls back to null (the page then
 * loads the profile in the browser exactly as it does today) if the API is slow or down. */
async function getProfile(orgSlug: string): Promise<PublicFarmProfile | null> {
  try {
    const res = await fetch(`${API}/api/v1/public/${orgSlug}/profile`, {
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(4000),
    });
    return res.ok ? ((await res.json()) as PublicFarmProfile) : null;
  } catch {
    return null;
  }
}

/** Puts the farm's name in the tab title and description in the HTML itself, from the first paint. */
export async function generateMetadata({ params }: { params: { orgSlug: string } }): Promise<Metadata> {
  const profile = await getProfile(params.orgSlug);
  if (!profile) return {};
  return {
    title: { default: profile.farm_name, template: `%s | ${profile.farm_name}` },
    description: profile.tagline ?? undefined,
  };
}

export default async function ShopLayout({ children, params }: { children: ReactNode; params: { orgSlug: string } }) {
  const profile = await getProfile(params.orgSlug);

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