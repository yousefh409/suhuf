"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

type Mode = "login" | "signup";
type Step = "credentials" | "verify";

export function LoginForm({ redirectTo }: { redirectTo: string }) {
  const router = useRouter();
  const [step, setStep] = useState<Step>("credentials");
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function done() {
    router.push(redirectTo);
    router.refresh();
  }

  async function onSubmitCredentials(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setPending(true);
    const supabase = createClient();
    if (mode === "login") {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      setPending(false);
      if (error) return setError(error.message);
      done();
      return;
    }
    // signup
    const { data, error } = await supabase.auth.signUp({ email, password });
    setPending(false);
    if (error) return setError(error.message);
    if (data.session) {
      // Confirmation disabled — session issued immediately.
      done();
      return;
    }
    // Confirmation required — move to code entry.
    setStep("verify");
    setInfo(`We emailed a 6-digit code to ${email}.`);
  }

  async function onVerify(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setPending(true);
    const supabase = createClient();
    const { error } = await supabase.auth.verifyOtp({
      email,
      token: code.trim(),
      type: "email",
    });
    setPending(false);
    if (error) return setError(error.message);
    done();
  }

  async function onResend() {
    setError(null);
    setInfo(null);
    setPending(true);
    const supabase = createClient();
    const { error } = await supabase.auth.resend({ type: "signup", email });
    setPending(false);
    if (error) return setError(error.message);
    setInfo("Code sent. Check your email.");
  }

  if (step === "verify") {
    return (
      <div className="w-full max-w-sm rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
        <h1 className="mb-1 text-base font-semibold">Enter your code</h1>
        <p className="mb-4 text-sm text-zinc-500">
          We emailed a 6-digit code to {email}.
        </p>
        <form onSubmit={onVerify} className="space-y-3">
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            placeholder="123456"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="w-full rounded border border-zinc-300 px-3 py-2 text-sm tracking-widest"
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          {info && <p className="text-sm text-emerald-600">{info}</p>}
          <button
            type="submit"
            disabled={pending}
            className="w-full rounded bg-zinc-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {pending ? "…" : "Verify"}
          </button>
        </form>
        <div className="mt-3 flex items-center justify-between text-xs">
          <button
            type="button"
            onClick={onResend}
            disabled={pending}
            className="text-zinc-600 underline hover:text-zinc-900 disabled:opacity-50"
          >
            Resend code
          </button>
          <button
            type="button"
            onClick={() => {
              setStep("credentials");
              setError(null);
              setInfo(null);
              setCode("");
            }}
            className="text-zinc-600 underline hover:text-zinc-900"
          >
            Back
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-sm rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex gap-1 text-sm font-medium">
        <button
          type="button"
          onClick={() => {
            setMode("login");
            setError(null);
          }}
          className={`flex-1 rounded px-3 py-1.5 ${mode === "login" ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-600"}`}
        >
          Log in
        </button>
        <button
          type="button"
          onClick={() => {
            setMode("signup");
            setError(null);
          }}
          className={`flex-1 rounded px-3 py-1.5 ${mode === "signup" ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-600"}`}
        >
          Sign up
        </button>
      </div>

      <form onSubmit={onSubmitCredentials} className="space-y-3">
        <input
          type="email"
          required
          autoComplete="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded border border-zinc-300 px-3 py-2 text-sm"
        />
        <input
          type="password"
          required
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded border border-zinc-300 px-3 py-2 text-sm"
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={pending}
          className="w-full rounded bg-zinc-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {pending ? "…" : mode === "login" ? "Log in" : "Sign up"}
        </button>
      </form>
    </div>
  );
}
