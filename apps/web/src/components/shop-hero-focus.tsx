"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight, MapPin, MessageCircle, Phone, ShieldCheck, ShoppingCart, Sprout, Star, Truck } from "lucide-react";
import { shopPath, whatsappLink } from "@/lib/shop-utils";
import type { PublicBanner, PublicFarmProfile, PublicTestimonial } from "@/lib/types";

/** Storefront hero, "focus" layout: the tenant's banners run edge to edge across the whole page width - and behind the
 * (transparent, see ShopHeader's `overlay`) top bar and menu - while the farm's name is set large on the left, followed by real numbers (reviews, items in stock), the shop's trust points, contact buttons
 * and one clear call to action.
 *
 * Self-contained: it takes the same data the classic <Hero/> gets (plus testimonials and the listing count the page
 * already loads) and makes no requests of its own. Nothing here is invented - a block with no data behind it (no
 * reviews, no phone, no banners) simply isn't shown. */

type Props = {
  orgSlug: string;
  profile: PublicFarmProfile | undefined;
  banners: PublicBanner[];
  testimonials: PublicTestimonial[];
  listingCount: number;
};

/** "Sahara Oasis Farm" -> ["Sahara Oasis", "Farm"]. One word stays on one line. */
function splitName(name: string): [string, string] {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length < 2) return [words[0] ?? "", ""];
  const mid = Math.ceil(words.length / 2);
  return [words.slice(0, mid).join(" "), words.slice(mid).join(" ")];
}

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

const TRUST = [
  { Icon: Sprout, title: "Direct from the farm", text: "No middlemen - you buy from the grower" },
  { Icon: Truck, title: "Pickup or delivery", text: "Choose what suits you at checkout" },
  { Icon: ShieldCheck, title: "Simple online payment", text: "Order first, pay securely after" },
];

export function HeroFocus({ orgSlug, profile, banners, testimonials, listingCount }: Props) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const reduced = useReducedMotion();
  const count = banners.length;

  useEffect(() => {
    if (count < 2 || paused) return;
    const t = setInterval(() => setIndex((i) => (i + 1) % count), 4000);
    return () => clearInterval(t);
  }, [count, paused]);

  const active = count > 0 ? banners[index % count] : null;
  const farm = profile?.farm_name ?? "Our farm";
  const [line1, line2] = splitName(farm);
  const longest = Math.max(line1.length, line2.length);
  const headSize =
    longest > 18 ? "text-3xl sm:text-5xl lg:text-6xl" : longest > 12 ? "text-4xl sm:text-6xl lg:text-7xl" : "text-5xl sm:text-7xl lg:text-8xl";

  const ratings = testimonials.map((t) => t.rating).filter((r): r is number => typeof r === "number" && r > 0);
  const avg = ratings.length ? ratings.reduce((a, b) => a + b, 0) / ratings.length : null;

  const wa = whatsappLink(profile?.phone, `Hello ${profile?.farm_name ?? ""}, I'd like to enquire about your products.`);
  const circle =
    "flex h-10 w-10 items-center justify-center rounded-full bg-brass-light text-ink transition-colors hover:bg-brass-light/85 focus:outline-none focus-visible:ring-2 focus-visible:ring-paper";

  return (
    <section
      className="relative isolate overflow-hidden bg-forest-dark text-paper"
    // onMouseEnter={() => setPaused(true)}
    // onMouseLeave={() => setPaused(false)}
    >
      {/* Backdrop: the banner spans the full width of the page and runs under the floating header. */}
      <div className="absolute inset-0 overflow-hidden">
        {banners.map((b, i) => (
          // eslint-disable-next-line @next/next/no-img-element -- org-supplied CMS image URL
          <img
            key={`${b.image_url}-${i}`}
            src={b.image_url}
            alt=""
            loading={i === 0 ? "eager" : "lazy"}
            className="absolute inset-0 h-full w-full object-cover"
            style={{
              opacity: i === index % count ? 1 : 0,
              transform: !reduced && i === index % count ? "scale(1.06)" : "scale(1)",
              transition: reduced ? "none" : "opacity 1200ms ease, transform 9000ms ease-out",
            }}
          />
        ))}
        {count === 0 && (
          <div className="absolute inset-0 bg-[radial-gradient(55%_60%_at_75%_45%,rgba(217,168,76,0.22),transparent_70%)]" />
        )}
        {/* Darkens the text side; stronger at the bottom on phones where the text covers the whole picture. */}
        {/* <div className="absolute inset-0 bg-gradient-to-t from-forest-dark via-forest-dark/70 to-forest-dark/40 lg:bg-gradient-to-r lg:from-forest-dark/95 lg:via-forest-dark/55 lg:to-forest-dark/5" /> */}
        <div className="absolute inset-0 bg-gradient-to-t from-forest-dark/90 via-forest-dark/50 to-forest-dark/20 lg:bg-gradient-to-r lg:from-forest-dark/95 lg:via-forest-dark/40 lg:to-transparent" />
        {/* Keeps the floating top bar and menu readable over any photo. */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-56 bg-gradient-to-b from-black/60 to-transparent" />
        {/* Extra weight at the bottom so the buttons stay readable. */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-2/5 bg-gradient-to-t from-forest-dark/80 to-transparent" />
        {/* Melts the bottom edge into the page background (bg-paper) so the hero flows into the sections below it. */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-[linear-gradient(to_top,rgb(247_243_234)_0%,rgb(247_243_234/0.8)_28%,rgb(247_243_234/0.35)_60%,rgb(247_243_234/0)_100%)] sm:h-56" />
      </div>

      {/* pt-* clears the floating header (top bar + brand row + menu). */}
      <div className="relative z-10 mx-auto flex min-h-[40rem] max-w-7xl flex-col justify-between gap-8 px-4 pb-44 pt-52 sm:px-6 sm:pb-56 sm:pt-44 lg:min-h-[48rem] lg:pt-48">
        <div>
          <p className="flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.2em] text-brass-light sm:text-sm">
            <span className="h-px w-6 bg-brass-light" aria-hidden />
            {profile?.county ? `Farm-fresh from ${profile.county}` : "Fresh and direct"}
            <span className="h-px w-6 bg-brass-light" aria-hidden />
          </p>

          <h1 className={`mt-4 max-w-3xl font-body font-black uppercase leading-[0.95] tracking-tight ${headSize}`}>
            <span className="block text-paper">{line1}</span>
            {line2 && <span className="block text-brass-light">{line2}</span>}
          </h1>

          <p className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-paper/90 sm:text-base">
            <span>Direct from the farm</span>
            <span className="h-1.5 w-1.5 rounded-full bg-brass-light" aria-hidden />
            <span>Pickup or delivery</span>
            <span className="h-1.5 w-1.5 rounded-full bg-brass-light" aria-hidden />
            <span>Pay securely online</span>
          </p>
          {/* {profile?.tagline && <p className="mt-3 max-w-md text-sm text-paper/75">{profile.tagline}</p>} */}
        </div>

        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-6 sm:gap-8">
            {avg !== null ? (
              <div>
                <p className="text-3xl font-semibold leading-none">{avg.toFixed(1)}</p>
                <div className="mt-1.5 flex gap-0.5 text-brass-light" aria-label={`${avg.toFixed(1)} out of 5`}>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <Star key={n} className={`h-4 w-4 ${n <= Math.round(avg) ? "fill-current" : "opacity-30"}`} aria-hidden />
                  ))}
                </div>
                <p className="mt-1 text-xs text-paper/75">
                  Customer rating ({ratings.length} {ratings.length === 1 ? "review" : "reviews"})
                </p>
              </div>
            ) : (
              /* No reviews yet: an honest placeholder in the same slot. It becomes the real score with the first review. */
              <div>
                <p className="text-lg font-semibold leading-none">New shop</p>
                <div className="mt-1.5 flex gap-0.5 text-brass-light" aria-label="No reviews yet">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <Star key={n} className="h-4 w-4" aria-hidden />
                  ))}
                </div>
                <p className="mt-1 text-xs text-paper/75">No reviews yet</p>
              </div>
            )}
            {listingCount > 0 && <div className="hidden h-12 w-px bg-paper/20 sm:block" aria-hidden />}
            {listingCount > 0 && (
              <div>
                <p className="text-3xl font-semibold leading-none">{listingCount}</p>
                <p className="mt-2 text-xs text-paper/75">{listingCount === 1 ? "Item" : "Items"} available now</p>
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-3">
            {TRUST.map(({ Icon, title, text }) => (
              <div
                key={title}
                className="flex items-center gap-3 rounded-full border border-paper/10 bg-black/20 px-3 py-2 backdrop-blur-xs sm:px-4 sm:py-2"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 border-brass-light text-brass-light sm:h-11 sm:w-11">
                  <Icon className="h-5 w-5" aria-hidden />
                </span>
                <div>
                  <p className="text-sm font-semibold leading-tight">{title}</p>
                  <p className="hidden text-xs text-paper/70 sm:block">{text}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="text-sm text-paper/90">Get in touch:</span>
              <Link href={shopPath(orgSlug, "/contact")} aria-label="Contact and location" className={circle}>
                <MapPin className="h-5 w-5" aria-hidden />
              </Link>
              {profile?.phone && (
                <a href={`tel:${profile.phone.replace(/\s+/g, "")}`} aria-label="Call the farm" className={circle}>
                  <Phone className="h-5 w-5" aria-hidden />
                </a>
              )}
              {wa && (
                <a href={wa} target="_blank" rel="noreferrer" aria-label="Message on WhatsApp" className={circle}>
                  <MessageCircle className="h-5 w-5" aria-hidden />
                </a>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Link
                href={shopPath(orgSlug, "/about")}
                className="inline-flex items-center rounded-full border border-paper/40 bg-paper/10 px-5 py-3 text-sm font-semibold text-paper backdrop-blur-sm transition-colors hover:bg-paper/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-paper"
              >
                Our story
              </Link>
              <Link
                href={shopPath(orgSlug, "/store")}
                className="inline-flex items-center gap-2 rounded-full bg-brass-light px-6 py-3 text-sm font-semibold text-ink shadow-lg transition-colors hover:bg-brass-light/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-paper"
              >
                Shop now
                <ShoppingCart className="h-4 w-4" aria-hidden />
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Banner caption and controls, bottom centre, just above the fade (the top of the picture belongs to the menu). */}
      {count > 0 && (active?.title || active?.link_url || count > 1) && (
        <div className="pointer-events-none absolute inset-x-0 bottom-[7.75rem] z-20 flex justify-center px-4 sm:bottom-[10.75rem]">
          <div
            className="pointer-events-auto flex items-center gap-2"
            onPointerEnter={(e) => e.pointerType === "mouse" && setPaused(true)}
            onPointerLeave={() => setPaused(false)}
          >
            {active?.link_url ? (
              <a
                href={active.link_url}
                target="_blank"
                rel="noreferrer"
                className="hidden max-w-[16rem] truncate rounded-full border border-paper/25 bg-forest-dark/50 px-4 py-1.5 text-xs backdrop-blur-sm hover:bg-forest-dark/70 sm:block"
              >
                {active.title || "Learn more"} &#8599;
              </a>
            ) : (
              active?.title && (
                <span className="hidden max-w-[16rem] truncate rounded-full border border-paper/25 bg-forest-dark/50 px-4 py-1.5 text-xs backdrop-blur-sm sm:block">
                  {active.title}
                </span>
              )
            )}
            {count > 1 && (
              <>
                <button
                  type="button"
                  aria-label="Previous slide"
                  onClick={() => setIndex((i) => (i - 1 + count) % count)}
                  className="rounded-full bg-forest-dark/50 p-1.5 backdrop-blur-sm hover:bg-forest-dark/70"
                >
                  <ChevronLeft className="h-4 w-4" aria-hidden />
                </button>
                <div className="flex items-center gap-1.5 px-1">
                  {banners.map((_, i) => (
                    <button
                      key={i}
                      type="button"
                      aria-label={`Go to slide ${i + 1}`}
                      onClick={() => setIndex(i)}
                      className={`h-2 rounded-full transition-all ${i === index % count ? "w-6 bg-brass-light" : "w-2 bg-paper/60"}`}
                    />
                  ))}
                </div>
                <button
                  type="button"
                  aria-label="Next slide"
                  onClick={() => setIndex((i) => (i + 1) % count)}
                  className="rounded-full bg-forest-dark/50 p-1.5 backdrop-blur-sm hover:bg-forest-dark/70"
                >
                  <ChevronRight className="h-4 w-4" aria-hidden />
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}