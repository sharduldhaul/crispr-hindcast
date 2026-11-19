import { loadDiagram } from "@/lib/repo";

// Serves the rendered diagrams in diagrams/ to the docs pages, so a figure
// loads from this site rather than from GitHub.
export const runtime = "nodejs";

export async function GET(_request: Request, { params }: { params: Promise<{ file: string }> }) {
  const { file } = await params;
  const image = loadDiagram(file);
  if (!image) return new Response("Not found", { status: 404 });
  return new Response(new Uint8Array(image), {
    headers: { "Content-Type": "image/png", "Cache-Control": "public, max-age=3600" },
  });
}
