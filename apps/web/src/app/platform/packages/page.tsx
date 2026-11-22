"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PlatformShell } from "@/components/platform-shell";
import { Button, Input, Modal, ErrorState, EmptyState } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";
import { usePlatformMe } from "@/lib/use-platform-auth";
import type { PlatformPackage } from "@/lib/platform-types";

type Form = {
  name: string;
  slug: string;
  price: string;
  maxUsers: string;
  maxAnimals: string;
  maxCrops: string;
  isActive: boolean;
  storeIncluded: boolean;
  staffBranding: boolean;
  shopBranding: boolean;
};

const EMPTY: Form = { name: "", slug: "", price: "0", maxUsers: "", maxAnimals: "", maxCrops: "", isActive: true, storeIncluded: true, staffBranding: false, shopBranding: false };

const show = (n: number | null) => (n === null ? "Unlimited" : n.toLocaleString());
const fromLimit = (n: number | null) => (n === null ? "" : String(n));

/** "" -> null (unlimited); otherwise a whole number >= 1, or undefined when the text is not valid. */
function parseLimit(text: string): number | null | undefined {
  if (text.trim() === "") return null;
  const n = Number(text);
  return Number.isInteger(n) && n >= 1 ? n : undefined;
}

function toForm(p: PlatformPackage): Form {
  return {
    name: p.name,
    slug: p.slug,
    price: String(p.monthly_price_kes),
    maxUsers: fromLimit(p.max_users),
    maxAnimals: fromLimit(p.max_animals),
    maxCrops: fromLimit(p.max_crop_plantings),
    isActive: p.is_active,
    storeIncluded: p.public_store_included,
    staffBranding: p.staff_branding_included,
    shopBranding: p.shop_branding_included,
  };
}

export default function PlatformPackagesPage() {
  const queryClient = useQueryClient();
  const { data: me } = usePlatformMe();
  const canWrite = me?.role === "superadmin";

  const [editing, setEditing] = useState<PlatformPackage | "new" | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  const packagesQuery = useQuery<PlatformPackage[]>({
    queryKey: ["platform-packages"],
    queryFn: () => platformApiFetch<PlatformPackage[]>("/api/v1/platform/billing/packages"),
  });

  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      editing === "new" || editing === null
        ? platformApiFetch("/api/v1/platform/billing/packages", { method: "POST", body: JSON.stringify(body) })
        : platformApiFetch(`/api/v1/platform/billing/packages/${editing.id}`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform-packages"] });
      queryClient.invalidateQueries({ queryKey: ["platform-plans"] }); // the 'Change plan' list on an organization page
      setEditing(null);
      setError(null);
    },
    onError: (err) => setError(err instanceof PlatformApiError ? err.message : "Failed to save the package"),
  });

  function openNew() {
    setForm(EMPTY);
    setError(null);
    setEditing("new");
  }

  function openEdit(p: PlatformPackage) {
    setForm(toForm(p));
    setError(null);
    setEditing(p);
  }

  function submit() {
    const price = Number(form.price);
    const maxUsers = parseLimit(form.maxUsers);
    const maxAnimals = parseLimit(form.maxAnimals);
    const maxCrops = parseLimit(form.maxCrops);
    if (!form.name.trim()) return setError("Give the package a name.");
    if (editing === "new" && !/^[a-zA-Z0-9][a-zA-Z0-9-]+$/.test(form.slug.trim())) {
      return setError("The identifier needs at least 2 characters: letters, numbers and dashes only.");
    }
    if (form.price.trim() === "" || !Number.isFinite(price) || price < 0) return setError("The monthly price must be 0 or more.");
    if (maxUsers === undefined || maxAnimals === undefined || maxCrops === undefined) {
      return setError("Limits must be whole numbers of 1 or more, or left empty for unlimited.");
    }
    setError(null);
    save.mutate({
      name: form.name.trim(),
      ...(editing === "new" ? { slug: form.slug.trim().toLowerCase() } : {}),
      monthly_price_kes: price,
      max_users: maxUsers,
      max_animals: maxAnimals,
      max_crop_plantings: maxCrops,
      is_active: form.isActive,
      public_store_included: form.storeIncluded,
      staff_branding_included: form.staffBranding,
      shop_branding_included: form.shopBranding,
    });
  }

  const isFree = editing !== null && editing !== "new" && editing.slug === "free";
  const set = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }));

  return (
    <PlatformShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Billing packages</h1>
          <p className="text-sm text-muted">The plans organizations can be on: price, limits, and whether the public store is included.</p>
        </div>
        {canWrite && <Button onClick={openNew}>+ New package</Button>}
      </div>

      {packagesQuery.error && (
        <ErrorState message={packagesQuery.error instanceof PlatformApiError ? packagesQuery.error.message : "Failed to load packages"} />
      )}
      {packagesQuery.data && packagesQuery.data.length === 0 && <EmptyState title="No packages" body="Create the first package." />}
      {packagesQuery.data && packagesQuery.data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-hairline">
          <table className="w-full text-left text-sm">
            <thead className="bg-ink text-paper">
              <tr>
                <th className="px-4 py-3 font-medium">Package</th>
                <th className="px-4 py-3 font-medium">Price / month</th>
                <th className="px-4 py-3 font-medium">Users</th>
                <th className="px-4 py-3 font-medium">Animals</th>
                <th className="px-4 py-3 font-medium">Crop plantings</th>
                <th className="px-4 py-3 font-medium">Public store</th>
                <th className="px-4 py-3 font-medium">Own branding</th>
                <th className="px-4 py-3 font-medium">Organizations</th>
                <th className="px-4 py-3 font-medium">Status</th>
                {canWrite && <th className="px-4 py-3" />}
              </tr>
            </thead>
            <tbody>
              {packagesQuery.data.map((p) => (
                <tr key={p.id} className="border-t border-hairline bg-white/60">
                  <td className="px-4 py-3">
                    <p className="font-medium text-ink">{p.name}</p>
                    <p className="font-mono text-xs text-muted">{p.slug}</p>
                  </td>
                  <td className="px-4 py-3">{p.monthly_price_kes > 0 ? `KES ${p.monthly_price_kes.toLocaleString()}` : "Free"}</td>
                  <td className="px-4 py-3">{show(p.max_users)}</td>
                  <td className="px-4 py-3">{show(p.max_animals)}</td>
                  <td className="px-4 py-3">{show(p.max_crop_plantings)}</td>
                  <td className="px-4 py-3">
                    <span className={p.public_store_included ? "text-moss" : "text-clay"}>{p.public_store_included ? "Included" : "Not included"}</span>
                  </td>
                  <td className="px-4 py-3">
                    {p.staff_branding_included || p.shop_branding_included ? (
                      <span className="text-moss">
                        {p.staff_branding_included && p.shop_branding_included ? "Staff app + shop" : p.staff_branding_included ? "Staff app" : "Shop"}
                      </span>
                    ) : (
                      <span className="text-clay">Not included</span>
                    )}
                  </td>
                  <td className="px-4 py-3">{p.organization_count}</td>
                  <td className="px-4 py-3">
                    <span className={p.is_active ? "text-moss" : "text-muted"}>{p.is_active ? "Offered" : "Switched off"}</span>
                  </td>
                  {canWrite && (
                    <td className="px-4 py-3 text-right">
                      <Button variant="ghost" onClick={() => openEdit(p)}>Edit</Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-xs text-muted">
        Lowering a limit never removes anything an organization already has - it only stops them adding more. A price change applies to
        payments made from then on. A switched-off package is no longer offered, but organizations already on it keep working. A single
        organization&apos;s public store can still be forced on or off from its own page.
      </p>

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "New package" : `Edit ${form.name || "package"}`}>
        <div className="space-y-4">
          {error && <ErrorState message={error} />}
          <Input label="Name" value={form.name} onChange={(e) => set({ name: e.target.value })} />
          {editing === "new" ? (
            <Input
              label="Identifier (cannot be changed later)"
              value={form.slug}
              placeholder="e.g. growth"
              onChange={(e) => set({ slug: e.target.value })}
            />
          ) : (
            <p className="text-xs text-muted">
              Identifier: <span className="font-mono">{form.slug}</span>
            </p>
          )}
          <Input
            label="Price per month (KES)"
            type="number"
            min={0}
            value={form.price}
            disabled={isFree}
            onChange={(e) => set({ price: e.target.value })}
          />
          {isFree && <p className="-mt-2 text-xs text-muted">The Free package stays at 0 - every new organization starts on it.</p>}
          <div className="grid grid-cols-3 gap-3">
            <Input label="Max users" type="number" min={1} placeholder="Unlimited" value={form.maxUsers} onChange={(e) => set({ maxUsers: e.target.value })} />
            <Input label="Max animals" type="number" min={1} placeholder="Unlimited" value={form.maxAnimals} onChange={(e) => set({ maxAnimals: e.target.value })} />
            <Input label="Max plantings" type="number" min={1} placeholder="Unlimited" value={form.maxCrops} onChange={(e) => set({ maxCrops: e.target.value })} />
          </div>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={form.storeIncluded} onChange={(e) => set({ storeIncluded: e.target.checked })} />
            <span>
              <span className="font-medium text-ink">Includes the public store</span>
              <span className="block text-xs text-muted">
                Off = organizations on this package have their system but no public storefront (unless forced on for one organization).
              </span>
            </span>
          </label>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={form.staffBranding} onChange={(e) => set({ staffBranding: e.target.checked })} />
            <span>
              <span className="font-medium text-ink">Includes own branding for the staff app</span>
              <span className="block text-xs text-muted">
                On = the installed staff app and the sign-in page show the farm&apos;s own name and logo instead of the platform&apos;s.
              </span>
            </span>
          </label>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={form.shopBranding} onChange={(e) => set({ shopBranding: e.target.checked })} />
            <span>
              <span className="font-medium text-ink">Includes own branding for the public shop</span>
              <span className="block text-xs text-muted">
                On = the installed shop app shows the farm&apos;s own name and logo. Needs the public store to be included to be useful.
              </span>
            </span>
          </label>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={form.isActive} disabled={isFree} onChange={(e) => set({ isActive: e.target.checked })} />
            <span>
              <span className="font-medium text-ink">Offered to organizations</span>
              <span className="block text-xs text-muted">Off = hidden from the plan list; those already on it are not affected.</span>
            </span>
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
            <Button disabled={save.isPending} onClick={submit}>{save.isPending ? "Saving…" : "Save package"}</Button>
          </div>
        </div>
      </Modal>
    </PlatformShell>
  );
}
