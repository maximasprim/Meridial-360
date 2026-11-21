import { cookies, headers } from "next/headers";
import { LAST_ORG_COOKIE, logoSrc } from "@/lib/branding-shared";
import { resolveLoginBranding } from "@/lib/login-branding";
import { LoginClient } from "./login-client";

// Branded per request (link, domain, cookie), so the farm's name and logo arrive inside the page itself.
export const dynamic = "force-dynamic";

export default async function LoginPage({ searchParams }: { searchParams: { org?: string | string[] } }) {
  const org = Array.isArray(searchParams.org) ? searchParams.org[0] : searchParams.org;
  const found = await resolveLoginBranding({
    org,
    host: headers().get("host") ?? "",
    remembered: cookies().get(LAST_ORG_COOKIE)?.value,
  });
  // Only a farm whose staff branding a superadmin switched on is shown; otherwise the platform's own sign-in page.
  const tenant = found && found.branding.staff_branding && found.branding.farm_name ? found : null;

  return (
    <>
      {tenant?.branding.logo_url && <link rel="preload" as="image" href={logoSrc(tenant.branding.logo_url)} />}
      <LoginClient initial={tenant} />
    </>
  );
}
