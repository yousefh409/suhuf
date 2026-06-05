import { describe, it, expect } from "vitest";
import { parseFlowPage, flowToNewBook, type FlowBook, type OpenTag } from "./flowFormat";

const HADITH_MATN: OpenTag[] = [
  { name: "hadith", id: "h2" },
  { name: "matn", id: null },
];

describe("parseFlowPage", () => {
  it("treats a continuation page (inside matn) as all-matn", () => {
    // page 49 of the Jibril hadith: bare text, inherited <hadith><matn>
    const { text, spans } = parseFlowPage("قال فأخبرني عن الساعة", HADITH_MATN);
    expect(text).toBe("قال فأخبرني عن الساعة");
    const matn = spans.filter((s) => s.label === "matn");
    expect(matn).toHaveLength(1);
    expect(matn[0]).toMatchObject({ start: 0, end: text.length });
    // the hadith container also spans the whole page, carrying its id
    const hadith = spans.filter((s) => s.label === "hadith");
    expect(hadith[0]).toMatchObject({ start: 0, end: text.length, id: "h2" });
  });

  it("closes the matn at the right place on the final page", () => {
    // page 50: closes matn + hadith, opens takhrij
    const tagged = "ثم انطلق فإنه جبريل</matn> <takhrij>رواه مسلم</takhrij></hadith>";
    const { text, spans } = parseFlowPage(tagged, HADITH_MATN);
    expect(text).toBe("ثم انطلق فإنه جبريل رواه مسلم");
    const matn = spans.find((s) => s.label === "matn")!;
    expect(text.slice(matn.start, matn.end)).toBe("ثم انطلق فإنه جبريل");
    const takhrij = spans.find((s) => s.label === "takhrij")!;
    expect(text.slice(takhrij.start, takhrij.end)).toBe("رواه مسلم");
  });

  it("parses a self-contained hadith with nested entity tags", () => {
    const tagged =
      '<hadith id="h1"><isnad>عن <person id="p1">عمر</person> قال</isnad> <matn>إنما الأعمال</matn></hadith>';
    const { text, spans } = parseFlowPage(tagged, []);
    expect(text).toBe("عن عمر قال إنما الأعمال");
    expect(spans.find((s) => s.label === "person")).toMatchObject({ id: "p1" });
    expect(text.slice(...spanRange(spans, "isnad"))).toBe("عن عمر قال");
    expect(text.slice(...spanRange(spans, "matn"))).toBe("إنما الأعمال");
  });
});

describe("flowToNewBook", () => {
  it("drops the hadith container span but keeps isnad/matn/person", () => {
    const book: FlowBook = {
      metadata: { openiti_id: "x", title_ar: "ت", author_openiti_id: "a" },
      chapters: [],
      annotations: [],
      pages: [
        {
          page_number: 1,
          volume: 1,
          tagged:
            '<hadith id="h1"><isnad>عن <person id="p1">عمر</person></isnad> <matn>الأعمال بالنيات</matn></hadith>',
          open_tags: [],
          text: "",
          start_offset: 0,
        },
      ],
    };
    const nb = flowToNewBook(book);
    const labels = (nb.pages[0].blocks[0].spans ?? []).map((s) => s.label);
    expect(labels).toContain("isnad");
    expect(labels).toContain("matn");
    expect(labels).toContain("person");
    expect(labels).not.toContain("hadith");
    expect(nb.pages[0].blocks[0].type).toBe("prose");
  });

  it("keeps the matn continuous across the three Jibril pages", () => {
    const book: FlowBook = {
      metadata: { openiti_id: "x", title_ar: "ت", author_openiti_id: "a" },
      chapters: [],
      annotations: [],
      pages: [
        { page_number: 47, volume: 1, start_offset: 0, text: "", open_tags: [],
          tagged: '<hadith id="h2"><isnad>عن عمر قال</isnad> <matn>بينما نحن جلوس' },
        { page_number: 49, volume: 1, start_offset: 0, text: "", open_tags: HADITH_MATN,
          tagged: "قال فأخبرني عن الساعة" },
        { page_number: 50, volume: 1, start_offset: 0, text: "", open_tags: HADITH_MATN,
          tagged: "فإنه جبريل</matn></hadith>" },
      ],
    };
    const nb = flowToNewBook(book);
    // every page carries a matn span -> the hadith body is styled continuously
    for (const page of nb.pages) {
      const labels = (page.blocks[0].spans ?? []).map((s) => s.label);
      expect(labels).toContain("matn");
    }
  });

  it("splits a page with a <heading> into a heading block + prose", () => {
    const book: FlowBook = {
      metadata: { openiti_id: "x", title_ar: "ت", author_openiti_id: "a" },
      chapters: [],
      annotations: [],
      pages: [
        {
          page_number: 47,
          volume: 1,
          start_offset: 0,
          text: "",
          open_tags: [],
          tagged:
            '<heading>الحديث الثاني</heading> <hadith id="h2"><isnad>عن عمر</isnad> <matn>إنما الأعمال</matn></hadith>',
        },
      ],
    };
    const blocks = flowToNewBook(book).pages[0].blocks;
    const heading = blocks.find((b) => b.type === "heading");
    expect(heading).toBeTruthy();
    expect(heading!.text).toBe("الحديث الثاني");
    // the hadith body still styles as matn, in a following prose block
    const matnBlock = blocks.find((b) => (b.spans ?? []).some((s) => s.label === "matn"));
    expect(matnBlock?.type).toBe("prose");
  });
});

function spanRange(
  spans: { start: number; end: number; label: string }[],
  label: string,
): [number, number] {
  const s = spans.find((x) => x.label === label)!;
  return [s.start, s.end];
}
