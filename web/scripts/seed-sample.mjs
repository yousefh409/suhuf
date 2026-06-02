import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const src = path.join(dir, "..", "fixtures", "Sample.Taxonomy.enriched.json");
const destDir = path.join(dir, "..", "data");
await mkdir(destDir, { recursive: true });
await copyFile(src, path.join(destDir, "Sample.Taxonomy.enriched.json"));
console.log("seeded Sample.Taxonomy.enriched.json into web/data");
