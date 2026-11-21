import { buildManifestResponse } from "@/lib/app-manifest";

export async function GET(request: Request, { params }: { params: { orgSlug: string } }) {
  return buildManifestResponse(request, "shop", params.orgSlug);
}
