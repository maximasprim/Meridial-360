import type { Branding } from "@/lib/branding";
import { isOwnAppHost, isValidSlug } from "@/lib/branding-shared";

/**
 * Server-side: whose sign-in page is this, and what is its branding? Used by /login so the page is sent with the
 * farm's name and logo already in it (no flash of the platform name, nothing popping in after the form).
 *
 * Order: a link like /login?org=farm-slug; the farm that owns the domain the page was opened on (a farm's own domain,
 * verified domains only); the last farm that signed in on this device (cookie). Both lookups are cached for a short
 * time and time out quickly, so a slow or unreachable API just means the platform's own sign-in page.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TIMEOUT_MS = 2500;

export type LoginBranding = { slug: string; branding: Branding } | null;

async function fetchJson<T>(url: string, revalidate: number): Promise<T | null> {
  try {
    const res = await fetch(url, { next: { revalidate }, signal: AbortSignal.timeout(TIMEOUT_MS) });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

export async function resolveLoginBranding(input: { org?: string; host: string; remembered?: string }): Promise<LoginBranding> {
  let slug: string | null = null;

  const fromLink = input.org?.trim().toLowerCase();
  if (fromLink && isValidSlug(fromLink)) {
    slug = fromLink;
  } else if (!isOwnAppHost(input.host)) {
    const found = await fetchJson<{ slug?: string } | null>(
      `${API}/api/v1/public/resolve-domain?host=${encodeURIComponent(input.host)}`,
      60,
    );
    if (found?.slug && isValidSlug(found.slug)) slug = found.slug;
  }
  if (!slug && input.remembered && isValidSlug(input.remembered)) slug = input.remembered;
  if (!slug) return null;

  const branding = await fetchJson<Branding>(`${API}/api/v1/public/${encodeURIComponent(slug)}/branding`, 15);
  return branding ? { slug, branding } : null;
}
