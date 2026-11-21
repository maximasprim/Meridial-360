import { NextResponse } from "next/server";

/**
 * Same-origin branding lookup for the browser: GET /api/branding?slug={farm}  or  GET /api/branding (the farm that owns
 * the domain this request came in on).
 *
 * Why it exists: a farm's own domain is a different origin from the API, and the API's CORS list is fixed, so the
 * browser may not be allowed to call the API from there. This route makes those calls on the server instead and hands
 * the answer back from the page's own address, so the sign-in page and the installed-app branding work on a farm's own
 * domain exactly as they do on the platform's. It only relays what the public branding endpoint already says (which
 * reveals a farm's name and logo only when a superadmin switched tenant branding on), and only looks up VERIFIED domains.
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

const json = (body: unknown) => NextResponse.json(body, { headers: { "Cache-Control": "no-store" } });

export async function GET(request: Request) {
  let slug = new URL(request.url).searchParams.get("slug")?.trim().toLowerCase() || null;

  if (!slug) {
    const host = request.headers.get("host") ?? "";
    if (isOwnAppHost(host)) return json({ slug: null, branding: null });
    try {
      const res = await fetch(`${API}/api/v1/public/resolve-domain?host=${encodeURIComponent(host)}`, {
        next: { revalidate: 60 },
        signal: AbortSignal.timeout(4000),
      });
      if (res.ok) slug = ((await res.json()) as { slug?: string } | null)?.slug ?? null;
    } catch {
      slug = null;
    }
  }
  if (!slug) return json({ slug: null, branding: null });

  try {
    const res = await fetch(`${API}/api/v1/public/${encodeURIComponent(slug)}/branding`, {
      next: { revalidate: 15 },
      signal: AbortSignal.timeout(4000),
    });
    return json({ slug, branding: res.ok ? await res.json() : null });
  } catch {
    return json({ slug, branding: null });
  }
}
