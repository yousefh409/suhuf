// TypeScript mirrors of the ingestion Pydantic models.
// Block is a discriminated union on `type`.

export type BlockType =
  | "prose"
  | "heading"
  | "poetry"
  | "isnad"
  | "matn"
  | "takhrij"
  | "quran";

export type SpanLabel =
  | "quran"
  | "person"
  | "place"
  | "book_ref"
  | "hadith_ref"
  | "date_hijri"
  | "footnote"
  | "isnad"
  | "matn"
  | "takhrij";

export type QualityFlag =
  | "parse_error"
  | "tashkeel_suspect"
  | "ocr_artifact";

export type Token = {
  id: string;
  text: string;
  text_raw?: string | null;
};

export type Span = {
  start_token_id: string;
  end_token_id: string;
  label: SpanLabel;
  sub_label?: string | null;
  ref?: string | null;
  confidence?: number | null;
};

type BlockBase = {
  key: string;
  metadata?: Record<string, unknown> | null;
  parser_type?: string | null;
  spans?: Span[];
  flags?: QualityFlag[];
  level?: number | null;
  number?: string | null;
};

export type ProseLikeBlock = BlockBase & {
  type: Exclude<BlockType, "poetry">;
  tokens: Token[];
};

export type PoetryBlock = BlockBase & {
  type: "poetry";
  hemistichs: Token[][][];
};

export type Block = ProseLikeBlock | PoetryBlock;

export type Footnote = {
  marker: string;
  tokens: Token[];
};

export type Page = {
  page_number: number;
  volume: number;
  content_blocks: Block[];
  footnotes?: Footnote[];
};

export type Chapter = {
  id?: string;
  title: string;
  level: number;
  page_number: number;
  volume: number;
  sort_order: number;
  synthesized?: boolean;
  // Index of the heading block within its page's content_blocks; lets the
  // reader split a single physical page that contains several chapter starts.
  block_index?: number | null;
};

export type Author = {
  id: string;
  openiti_id: string;
  full_name_ar?: string | null;
  shuhra_ar?: string | null;
  full_name_en?: string | null;
  bio_en?: string | null;
  birth_ah?: number | null;
  death_ah?: number | null;
  primary_fields?: string[] | null;
};

export type Book = {
  id: string;
  openiti_id: string;
  title_ar: string;
  title_lat?: string | null;
  title_en?: string | null;
  description?: string | null;
  genres?: string[] | null;
  composition_date_ah?: number | null;
  commentary_on?: string | null;
  abridgement_of?: string | null;
  total_pages?: number | null;
  total_volumes?: number | null;
  has_tashkeel?: boolean | null;
  language?: string | null;
  author_id: string;
};

export type BookListItem = Pick<
  Book,
  | "openiti_id"
  | "title_ar"
  | "title_lat"
  | "title_en"
  | "description"
  | "genres"
  | "total_pages"
  | "total_volumes"
  | "has_tashkeel"
> & {
  author_name_ar: string | null;
  author_name_en: string | null;
};

export type ReaderMode = "reader" | "inspector";
