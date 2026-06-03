import { LoginForm } from "./LoginForm";
import { safeRedirect } from "@/lib/proxy-paths";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ redirectTo?: string }>;
}) {
  const { redirectTo } = await searchParams;

  return (
    <main className="min-h-screen flex items-center justify-center px-4">
      <LoginForm redirectTo={safeRedirect(redirectTo)} />
    </main>
  );
}
