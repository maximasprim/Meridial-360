"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight, Menu, Phone, Search, ShoppingCart, Truck, User, X } from "lucide-react";
import { useCart } from "@/lib/cart";
import { shopPath, useShopProfile } from "@/lib/shop-utils";

/** Storefront header: announcement bar, brand + search + account/cart row,
 * and a category/navigation strip. Same `orgSlug` prop as before, so every
 * page that already renders <ShopHeader orgSlug=... /> gets the new look.
 *
 * `overlay` (off by default, so every existing page is unchanged): used by the home page's full-bleed hero. The header
 * then floats, transparent, over the hero image and turns into the normal solid header once the page is scrolled. */
export function ShopHeader({ orgSlug, overlay = false }: { orgSlug: string; overlay?: boolean }) {
  const { data } = useShopProfile(orgSlug);
  const router = useRouter();
  const cart = useCart(orgSlug);
  const cartCount = cart.length;
  const [q, setQ] = useState("");
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    if (!overlay) return;
    const on = () => setScrolled(window.scrollY > 24);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, [overlay]);
  const [menuOpen, setMenuOpen] = useState(false); // small screens: the hamburger menu
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);
  const floating = overlay && !scrolled && !menuOpen; // transparent, over the hero image

  const nav: { label: string; href: string }[] = [
    { label: "All products", href: shopPath(orgSlug, "/store") },
    { label: "Livestock", href: shopPath(orgSlug, "/store?kind=animal") },
    { label: "Fresh produce", href: shopPath(orgSlug, "/store?kind=crop_produce") },
    { label: "Featured deals", href: shopPath(orgSlug, "/store?featured=1") },
    { label: "About us", href: shopPath(orgSlug, "/about") },
    { label: "Blog", href: shopPath(orgSlug, "/blog") },
    { label: "FAQs", href: shopPath(orgSlug, "/faqs") },
    { label: "Contact", href: shopPath(orgSlug, "/contact") },
  ];

  return (
    <header className={overlay ? `fixed inset-x-0 top-0 z-40 ${floating ? "" : "shadow-sm"}` : "sticky top-0 z-40 shadow-sm"}>
      <div className={floating ? "bg-black/35 text-xs text-paper/90 backdrop-blur-sm transition-colors duration-300" : `bg-ink text-xs text-paper/80${overlay ? " transition-colors duration-300" : ""}`}>
        <div className="mx-auto flex max-w-8xl items-center justify-between gap-4 px-3 py-0.5">
          <p className="flex items-center gap-1.5">
            <Truck className="h-3.5 w-3.5" aria-hidden /> Farm pickup or delivery &middot; buy direct from {data?.farm_name ?? "our farm"}
          </p>
          {data?.phone && (
            <a href={`tel:${data.phone}`} className="hidden items-center gap-1.5 hover:text-paper sm:flex">
              <Phone className="h-3.5 w-3.5" aria-hidden /> {data.phone}
            </a>
          )}
        </div>
      </div>

      <div className={floating ? "bg-transparent text-paper transition-colors duration-300" : `bg-forest text-paper${overlay ? " transition-colors duration-300" : ""}`}>
        <div className="mx-auto flex max-w-8xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-2">
          <Link href={shopPath(orgSlug)} className="flex min-w-0 items-center gap-3">
            {data?.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element -- org-supplied CMS image URL
              <img src={data.logo_url} alt="" className="h-10 w-10 rounded-full border border-paper/20 bg-white object-cover" />
            ) : (
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-brass font-display text-lg text-ink">
                {(data?.farm_name ?? "F").charAt(0).toUpperCase()}
              </span>
            )}
            <span className="min-w-0">
              <span className="block truncate font-display text-xl italic leading-tight">{data?.farm_name ?? "Farm"}</span>
              {data?.tagline && <span className="hidden truncate text-xs text-brass/80 md:block">{data.tagline}</span>}
            </span>
          </Link>

          <form
            role="search"
            className="order-last flex w-full overflow-hidden rounded-full bg-white md:order-none md:w-auto md:flex-1"
            onSubmit={(e) => {
              e.preventDefault();
              const term = q.trim();
              router.push(shopPath(orgSlug, term ? `/store?q=${encodeURIComponent(term)}` : "/store"));
            }}
          >
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search animals, produce, breeds…"
              aria-label="Search the store"
              className="min-w-0 flex-1 px-4 py-2.5 text-sm text-ink outline-none placeholder:text-muted"
            />
            <button type="submit" className="flex items-center bg-brass px-4 text-ink hover:bg-brass/90" aria-label="Search">
              <Search className="h-5 w-5" aria-hidden />
            </button>
          </form>

          <div className="ml-auto flex items-center gap-5 text-sm md:ml-0">
            <Link href={shopPath(orgSlug, "/account")} className="flex items-center gap-1.5 text-paper/90 hover:text-paper">
              <User className="h-5 w-5" aria-hidden />
              <span className="hidden sm:inline">My account</span>
            </Link>
            <Link href={shopPath(orgSlug, "/cart")} className="relative flex items-center gap-1.5 text-paper/90 hover:text-paper">
              <ShoppingCart className="h-6 w-6" aria-hidden />
              <span className="hidden sm:inline">Cart</span>
              {cartCount > 0 && (
                <span className="absolute -right-2 -top-2 flex h-5 min-w-5 items-center justify-center rounded-full bg-brass px-1 text-[11px] font-bold text-ink">
                  {cartCount}
                </span>
              )}
            </Link>
            <button
              type="button"
              className="-mr-1 flex h-10 w-10 items-center justify-center rounded-md text-brass-light hover:bg-paper/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-paper md:hidden"
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              aria-controls="shop-mobile-menu"
              onClick={() => setMenuOpen((o) => !o)}
            >
              {menuOpen ? <X className="h-7 w-7" strokeWidth={2.5} aria-hidden /> : <Menu className="h-7 w-7" strokeWidth={2.5} aria-hidden />}
            </button>
          </div>
        </div>
      </div>

      <nav className={floating ? "hidden border-b border-paper/15 bg-black/25 backdrop-blur-sm transition-colors duration-300 md:flex" : overlay ? "hidden border-b border-hairline bg-white/90 backdrop-blur-sm transition-colors duration-300 md:flex" : "hidden border-b border-hairline bg-white/60 md:flex"} aria-label="Store sections">
        <ul className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 text-sm sm:px-6">
          {nav.map((item) => (
            <li key={item.label} className="shrink-0">
              <Link href={item.href} className={floating ? "block px-3 py-2 text-paper/90 hover:text-paper hover:underline hover:underline-offset-8" : "block px-3 py-2 text-ink/80 hover:text-forest hover:underline hover:underline-offset-8"}>
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      {menuOpen && (
        <nav id="shop-mobile-menu" aria-label="Menu" className="max-h-[calc(100dvh-9rem)] overflow-y-auto border-b border-paper/10 bg-forest-dark text-paper md:hidden">
          <ul className="mx-auto max-w-7xl px-4 py-1">
            {nav.map((item) => (
              <li key={item.label} className="border-b border-paper/10 last:border-b-0">
                <Link
                  href={item.href}
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center justify-between py-3.5 text-base text-paper/95 hover:text-brass-light"
                >
                  {item.label}
                  <ChevronRight className="h-4 w-4 text-brass-light" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </header>
  );
}