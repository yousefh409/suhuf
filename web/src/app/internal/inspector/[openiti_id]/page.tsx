import { redirect, notFound } from "next/navigation";
import { getBook, getEffectiveChapters } from "@/lib/reader/queries";

export default async function InspectorRedirect({
  params,
}: {
  params: Promise<{ openiti_id: string }>;
}) {
  const { openiti_id } = await params;
  const decoded = decodeURIComponent(openiti_id);
  const result = await getBook(decoded);
  if (!result) notFound();
  const chapters = await getEffectiveChapters(result.book.id);
  if (chapters.length === 0) notFound();
  redirect(`/internal/inspector/${openiti_id}/${chapters[0].sort_order}`);
}
