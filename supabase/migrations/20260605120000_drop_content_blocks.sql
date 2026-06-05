-- Drop the legacy per-page content_blocks column now that the flow format is the
-- only path: pages carry `tagged` + `open_tags`, and structure lives in the
-- `annotations` table. The reader and uploader no longer read or write
-- content_blocks. content_plain stays (page plain text / search).
--
-- Destructive: removes the old block JSON. Superseded by `tagged`; the only book
-- that had it (Nawawi) has been re-uploaded in the flow shape.

ALTER TABLE pages DROP COLUMN IF EXISTS content_blocks;
