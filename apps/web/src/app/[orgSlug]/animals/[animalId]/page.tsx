import { redirect } from "next/navigation";

/**
 * Animal tags printed before the tag page existed point at /{farm}/animals/{animal}. They now land on the real page.
 */
export default function LegacyAnimalTagRedirect({ params }: { params: { orgSlug: string; animalId: string } }) {
  redirect(`/tag/${encodeURIComponent(params.orgSlug)}/${encodeURIComponent(params.animalId)}`);
}
