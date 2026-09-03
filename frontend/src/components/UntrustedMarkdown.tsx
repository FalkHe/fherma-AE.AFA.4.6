import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import type { SxProps, Theme } from "@mui/material/styles";
import type { ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * The one markdown renderer for retrieved/LLM-generated content, inert by
 * construction: GFM only, raw HTML **off**. Never add `rehype-raw`; no
 * plugin props are exposed here, so no call site can ever turn raw HTML on.
 *
 * `children` is always server/retrieved content, never user-typed text —
 * user input keeps rendering as plain pre-wrapped text at its call sites.
 */

/** Links inside untrusted Markdown never navigate the application. */
function ExternalLink({ href, children }: { href?: string; children?: ReactNode }) {
  return (
    <Link href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </Link>
  );
}

const REMARK_PLUGINS = [remarkGfm];

/**
 * The exact intersection of the three landed `MARKDOWN_SX` configurations
 * (`MessageBubble`, `CatalogueModelRoute`, `ModelDocumentsPanel`) — every
 * site-specific delta (bubble margins, prose images, heading demotion) stays
 * module-local at its call site. Palette tokens only.
 */
const BASE_MARKDOWN_SX = {
  "& table": { borderCollapse: "collapse", my: 2 },
  "& th, & td": {
    border: 1,
    borderColor: "divider",
    px: 1,
    py: 0.5,
    textAlign: "left",
  },
  "& pre": { overflowX: "auto" },
  "& a": { wordBreak: "break-word" },
} as const;

export function UntrustedMarkdown({
  children,
  components,
  sx,
}: {
  /** The markdown string — always server/retrieved content, never user-typed. */
  children: string;
  /** Site overrides merged over the base `{ a: ExternalLink }`. Never pass `a`. */
  components?: Components;
  /** Site-specific typography merged after the base sx. */
  sx?: SxProps<Theme>;
}) {
  return (
    <Box sx={[BASE_MARKDOWN_SX, ...(Array.isArray(sx) ? sx : [sx])]}>
      <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={{ a: ExternalLink, ...components }}>
        {children}
      </ReactMarkdown>
    </Box>
  );
}
