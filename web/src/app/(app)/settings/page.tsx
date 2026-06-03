import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { createClient } from "@/lib/supabase/server";
import { AppearanceControls, ReadingControls } from "@/components/settings/SettingsControls";
import SignOutMenuItem from "@/components/settings/SignOutMenuItem";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <main className="min-h-screen bg-parchment text-ink">
      <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6 space-y-8">
        {/* Header */}
        <div className="space-y-4">
          <Link
            href="/dashboard"
            className="flex items-center gap-0.5 text-sm text-ink/60 hover:text-ink transition-colors rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/25 w-fit"
          >
            <ChevronLeft size={16} />
            Dashboard
          </Link>
          <h1 className="font-serif text-4xl text-ink">Settings</h1>
        </div>

        {/* Appearance section */}
        <section>
          <h2 className="font-serif text-2xl text-ink mb-4">Appearance</h2>
          <div className="bg-parchment-warm rounded-2xl border border-ink/8 p-6">
            <AppearanceControls />
          </div>
        </section>

        {/* Reading section */}
        <section>
          <h2 className="font-serif text-2xl text-ink mb-4">Reading</h2>
          <div className="bg-parchment-warm rounded-2xl border border-ink/8 p-6">
            <ReadingControls />
          </div>
        </section>

        {/* Account section */}
        <section>
          <h2 className="font-serif text-2xl text-ink mb-4">Account</h2>
          <div className="bg-parchment-warm rounded-2xl border border-ink/8 p-6 space-y-4">
            <div>
              <p className="text-[11px] tracking-wider uppercase text-ink/50 mb-1">
                Signed in as
              </p>
              <p className="text-sm text-ink/70">{user?.email}</p>
            </div>
            <div className="border-t border-ink/8 pt-4">
              <SignOutMenuItem />
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
