import { NextResponse } from "next/server";

/**
 * The installed-app manifest for one farm: GET /app-manifest/staff/{slug} or /app-manifest/shop/{slug}.
 *
 * When a superadmin switched tenant branding on for that surface, the app is named after the farm and (if the farm
 * uploaded a logo) uses icons made from it. Otherwise - branding off, unknown farm, API unreachable - it returns the
 * platform's own manifest, identical to the static /manifest.webmanifest, so a mistake or outage can never leave an app
 * without a name or icon.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const APP_HOSTS = new Set(
  (process.env.NEXT_PUBLIC_APP_HOSTS ?? "localhost:3000,localhost")
    .split(",")
    .map((h) => h.trim())
    .filter(Boolean),
);

function isOwnAppHost(host: string): boolean {
  return APP_HOSTS.has(host) || host.endsWith(".vercel.app");
}

const PLATFORM_ICONS = [
  { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
  { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
  { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
];

interface BrandingPayload {
  staff_branding: boolean;
  shop_branding: boolean;
  farm_name: string | null;
  has_icon: boolean;
  icon_version: string | null;
}

function shortName(name: string): string {
  if (name.length <= 12) return name;
  const first = name.split(/\s+/)[0];
  return (first.length >= 3 ? first : name).slice(0, 12);
}

function manifestResponse(body: Record<string, unknown>) {
  return new NextResponse(JSON.stringify(body), {
    headers: { "Content-Type": "application/manifest+json", "Cache-Control": "public, max-age=60" },
  });
}

export async function GET(request: Request, { params }: { params: { surface: string; orgSlug: string } }) {
  const { surface, orgSlug } = params;
  if (surface !== "staff" && surface !== "shop") return new NextResponse("Not found", { status: 404 });

  const onCustomDomain = !isOwnAppHost(request.headers.get("host") ?? "");
  const startUrl = surface === "staff" ? "/admin/feedlot#weigh" : onCustomDomain ? "/" : `/shop/${orgSlug}`;
  const scope = surface === "staff" ? "/" : onCustomDomain ? "/" : `/shop/${orgSlug}/`;

  let branding: BrandingPayload | null = null;
  try {
    const res = await fetch(`${API}/api/v1/public/${encodeURIComponent(orgSlug)}/branding`, {
      next: { revalidate: 30 },
      signal: AbortSignal.timeout(4000),
    });
    if (res.ok) branding = (await res.json()) as BrandingPayload;
  } catch {
    branding = null;
  }

  const branded = !!branding && !!branding.farm_name && (surface === "staff" ? branding.staff_branding : branding.shop_branding);

  const common = {
    start_url: startUrl,
    scope,
    display: "standalone",
    background_color: "#F7F3EA",
    theme_color: "#1F3A2E",
  };

  if (!branded || !branding || !branding.farm_name) {
    return manifestResponse({
      name: "Meridial 360",
      short_name: "Meridial",
      description: "Farm management: weigh animals, manage crop production, record flocks and sales, even with no signal.",
      ...common,
      icons: PLATFORM_ICONS,
    });
  }

  const farm = branding.farm_name;
  const version = branding.icon_version ? `?v=${branding.icon_version}` : "";
  const iconBase = `${API}/api/v1/public/${encodeURIComponent(orgSlug)}/app-icon`;
  const icons = branding.has_icon
    ? [
        ...[192, 256, 384, 512].map((px) => ({ src: `${iconBase}/${px}.png${version}`, sizes: `${px}x${px}`, type: "image/png", purpose: "any" })),
        ...[192, 512].map((px) => ({ src: `${iconBase}/maskable-${px}.png${version}`, sizes: `${px}x${px}`, type: "image/png", purpose: "maskable" })),
      ]
    : PLATFORM_ICONS;

  return manifestResponse({
    // A different id per farm and surface, so a device that uses two farms (or the staff app and a shop) keeps them as separate apps.
    id: surface === "staff" ? `/admin?tenant=${orgSlug}` : `/shop/${orgSlug}`,
    name: farm,
    short_name: shortName(farm),
    description: surface === "staff" ? `${farm} - farm management` : `Shop at ${farm}`,
    ...common,
    icons,
  });
}
