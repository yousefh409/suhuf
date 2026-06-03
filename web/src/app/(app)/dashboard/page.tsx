import { createClient } from "@/lib/supabase/server";
import { getStats, getContinueReading, getRecommended } from "@/lib/dashboard/data";
import DashboardHeader from "@/components/dashboard/DashboardHeader";
import StatsBar from "@/components/dashboard/StatsBar";
import ContinueReading from "@/components/dashboard/ContinueReading";
import LibraryShelf from "@/components/dashboard/LibraryShelf";
import RecommendedGrid from "@/components/dashboard/RecommendedGrid";

export const dynamic = "force-dynamic";

function initialsFromEmail(email: string | undefined): string {
  if (!email) return "YH";
  return email.slice(0, 2).toUpperCase();
}

function nameFromEmail(email: string | undefined): string {
  if (!email) return "Reader";
  const local = email.split("@")[0].replace(/[._-]+/g, " ").trim();
  if (!local) return "Reader";
  return local.charAt(0).toUpperCase() + local.slice(1);
}

export default async function DashboardPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [stats, continueReading, recommended] = await Promise.all([
    getStats(),
    getContinueReading(),
    getRecommended(),
  ]);

  return (
    <main className="min-h-screen bg-parchment text-ink">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8 space-y-10">
      <DashboardHeader
        name={nameFromEmail(user?.email)}
        userInitials={initialsFromEmail(user?.email)}
      />
      <StatsBar stats={stats} />
      <ContinueReading items={continueReading} />
      <LibraryShelf />
      <RecommendedGrid books={recommended} />
      </div>
    </main>
  );
}
