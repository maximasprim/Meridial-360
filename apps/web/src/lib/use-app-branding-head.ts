"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { API_BASE } from "@/lib/api";

interface Options {
  /** Only true when the farm's branding is switched on for the staff app. */
  active: boolean;
  slug: string | null | undefined;
  name: string | null | undefined;
  hasIcon: boolean | undefined;
  version: string | null | undefined;
}

function ensureLink(rel: string): { el: HTMLLinkElement; created: boolean } {
  const existing = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`);
  if (existing) return { el: existing, created: false };
  const el = document.createElement("link");
  el.rel = rel;
  document.head.appendChild(el);
  return { el, created: true };
}

/**
 * Makes the page present itself as the farm's own app: the web-app manifest (installed app name + icon), the tab and
 * home-screen icon, and the iOS home-screen title. Browsers read these when the person installs the app, so when it
 * is active the install prompt / "Add to Home Screen" offers the farm's name and logo. Everything is put back when
 * the page unmounts or branding turns off, so nothing leaks into another session.
 */
export function useAppBrandingHead({ active, slug, name, hasIcon, version }: Options) {
  const pathname = usePathname(); // re-applied after navigation in case the framework refreshed the head tags

  useEffect(() => {
    if (!active || !slug || !name) return;
    const restores: Array<() => void> = [];

    const manifest = ensureLink("manifest");
    const previousManifest = manifest.el.getAttribute("href");
    manifest.el.setAttribute("href", `/app-manifest/staff/${encodeURIComponent(slug)}`);
    restores.push(() => {
      if (manifest.created) manifest.el.remove();
      else if (previousManifest !== null) manifest.el.setAttribute("href", previousManifest);
    });

    if (hasIcon) {
      const base = `${API_BASE}/api/v1/public/${encodeURIComponent(slug)}/app-icon`;
      const v = version ? `?v=${version}` : "";
      const icons: Array<[string, string]> = [
        ["icon", `${base}/favicon-32.png${v}`], // browser tab
        ["apple-touch-icon", `${base}/apple-180.png${v}`], // iOS "Add to Home Screen"
      ];
      for (const [rel, href] of icons) {
        const link = ensureLink(rel);
        const previous = link.el.getAttribute("href");
        link.el.setAttribute("href", href);
        restores.push(() => {
          if (link.created) link.el.remove();
          else if (previous !== null) link.el.setAttribute("href", previous);
        });
      }
    }

    let title = document.head.querySelector<HTMLMetaElement>('meta[name="apple-mobile-web-app-title"]');
    const createdTitle = !title;
    const previousTitle = title?.getAttribute("content") ?? null;
    if (!title) {
      title = document.createElement("meta");
      title.name = "apple-mobile-web-app-title";
      document.head.appendChild(title);
    }
    title.setAttribute("content", name);
    restores.push(() => {
      if (createdTitle) title?.remove();
      else if (previousTitle !== null) title?.setAttribute("content", previousTitle);
    });

    return () => restores.forEach((restore) => restore());
  }, [active, slug, name, hasIcon, version, pathname]);
}
