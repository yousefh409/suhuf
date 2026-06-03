import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { coercePreferences } from "@/lib/preferences/serialize";
import { readUserPreferences, upsertUserPreferences } from "@/lib/preferences/server";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const prefs = await readUserPreferences();
  return NextResponse.json({ prefs });
}

export async function PUT(request: Request): Promise<Response> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const prefs = coercePreferences(body);
  await upsertUserPreferences(prefs);
  return NextResponse.json({ prefs });
}
