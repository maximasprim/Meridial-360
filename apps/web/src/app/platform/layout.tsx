import type { Metadata } from "next";
import { PlatformShellLayout } from "@/components/platform-shell";

/**
 * The platform console is its own installable app: "Meridial 360 Console", opening at the console dashboard and limited to
 * /platform, so it installs separately from the staff app (which keeps its own manifest from the root layout).
 */
export const metadata: Metadata = {
  manifest: "/platform.webmanifest",
  appleWebApp: { capable: true, title: "Meridial 360 Console" },
};

/**
 * One persistent shell for the signed-in /platform console (the login and reset-password pages are
 * left bare by PlatformShellLayout). Pages still wrap themselves in <PlatformShell>; inside this
 * layout that is a no-op.
 */
export default function PlatformLayout({ children }: { children: React.ReactNode }) {
  return <PlatformShellLayout>{children}</PlatformShellLayout>;
}
