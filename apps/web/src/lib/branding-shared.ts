/** Small, dependency-free helpers shared by server code (the sign-in page, route handlers) and the browser. */

/** Cookie holding the last farm that signed in on this device, so the SERVER can brand the sign-in page before it is
 * sent (a browser-only memory would make the farm's name pop in after the page has already shown). */
export const LAST_ORG_COOKIE = "m360_org";

const APP_HOSTS = new Set(
  (process.env.NEXT_PUBLIC_APP_HOSTS ?? "localhost:3000,localhost")
    .split(",")
    .map((h) => h.trim())
    .filter(Boolean),
);

/** The platform's own web address (as opposed to a farm's own domain). Same rule the middleware uses. */
export function isOwnAppHost(host: string): boolean {
  return APP_HOSTS.has(host) || host.endsWith(".vercel.app");
}

/** A farm slug as the platform issues them; anything else is ignored rather than put into a request. */
export function isValidSlug(value: string): boolean {
  return /^[a-z0-9][a-z0-9-]{0,62}$/.test(value);
}

/** An uploaded logo is stored with its full address; tolerate a relative one too. */
export function logoSrc(url: string): string {
  return url.startsWith("/") ? `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}${url}` : url;
}
