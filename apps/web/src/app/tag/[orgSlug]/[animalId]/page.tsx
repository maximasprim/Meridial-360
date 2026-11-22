import type { Metadata } from "next";
import Link from "next/link";
import type { AnimalQRProfile } from "@/lib/types";
import { logoSrc } from "@/lib/branding-shared";

/**
 * Where a scanned animal tag lands: /tag/{farm}/{animal}. Public, read-only, and deliberately limited to what the API's QR
 * profile allows (species, breed, sex, coarse health status, availability) - never costs or internal notes. It sits outside
 * the shop layout on purpose, so a tag keeps working when the farm's public store is switched off.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Params = { params: { orgSlug: string; animalId: string } };

async function getProfile({ orgSlug, animalId }: Params["params"]): Promise<AnimalQRProfile | null> {
  try {
    const res = await fetch(
      `${API}/api/v1/public/${encodeURIComponent(orgSlug)}/animals/${encodeURIComponent(animalId)}/qr-profile`,
      { next: { revalidate: 30 }, signal: AbortSignal.timeout(4000) },
    );
    return res.ok ? ((await res.json()) as AnimalQRProfile) : null;
  } catch {
    return null;
  }
}

const label = (value: string) => {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
};

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const profile = await getProfile(params);
  const owner = profile?.organization_name ?? profile?.farm_name;
  return {
    title: profile ? `${profile.animal_number}${owner ? ` | ${owner}` : ""}` : "Animal tag",
    robots: { index: false, follow: false },
  };
}

export default async function AnimalTagPage({ params }: Params) {
  const profile = await getProfile(params);

  if (!profile) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-paper px-6 text-center">
        <div className="max-w-md">
          <h1 className="font-display text-3xl text-forest">We couldn&apos;t find this animal</h1>
          <p className="mt-3 text-sm text-muted">The tag may be out of date, or the animal is no longer on the farm&apos;s records.</p>
        </div>
      </main>
    );
  }

  const owner = profile.organization_name ?? profile.farm_name;
  const rows: [string, string][] = [
    ["Species", label(profile.species)],
    ["Breed", profile.breed ? label(profile.breed) : "-"],
    ["Sex", label(profile.sex)],
    ["Health", label(profile.health_status)],
  ];

  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          {profile.logo_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={logoSrc(profile.logo_url)}
              alt=""
              className="mx-auto mb-3 h-16 w-16 rounded-full border border-hairline bg-white object-cover"
            />
          )}
          <p className="font-display text-3xl italic text-forest">{owner}</p>
          {profile.farm_name !== owner && <p className="mt-1 text-sm text-muted">{profile.farm_name}</p>}
        </div>

        <div className="rounded-lg border border-hairline bg-white/70 p-6">
          <p className="text-xs font-medium uppercase tracking-wider text-muted">Animal</p>
          <p className="font-display text-2xl text-ink">{profile.animal_number}</p>

          <dl className="mt-4 divide-y divide-hairline text-sm">
            {rows.map(([name, value]) => (
              <div key={name} className="flex justify-between py-2">
                <dt className="text-muted">{name}</dt>
                <dd className="font-medium text-ink">{value}</dd>
              </div>
            ))}
          </dl>

          {profile.is_for_sale && (
            <p className="mt-4 rounded bg-brass/10 px-3 py-2 text-sm font-medium text-brass-dark">Available for sale</p>
          )}

          {profile.is_for_sale && profile.listing_slug && (
            <Link
              href={`/shop/${encodeURIComponent(params.orgSlug)}/listings/${encodeURIComponent(profile.listing_slug)}`}
              className="mt-4 block rounded bg-forest px-4 py-3 text-center text-sm font-medium text-paper hover:opacity-90"
            >
              View this animal in the shop
            </Link>
          )}
        </div>

        {profile.shop_enabled !== false && (
          <p className="mt-6 text-center text-sm">
            <Link href={`/shop/${encodeURIComponent(params.orgSlug)}`} className="text-forest hover:underline">
              Visit {owner}&apos;s shop
            </Link>
          </p>
        )}
      </div>
    </main>
  );
}
