import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { normalizeChatMarkdown } from "../utils/normalizeChatMarkdown";

type MarkdownChatProps = {
  children: string;
  className?: string;
};

function TableWrap({ children }: { children?: ReactNode }) {
  return <div className="prose-table-wrap">{children}</div>;
}

export function MarkdownChat({ children, className = "prose-chat" }: MarkdownChatProps) {
  const markdown = normalizeChatMarkdown(children);

  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: ({ children: tableChildren }) => (
            <TableWrap>
              <table>{tableChildren}</table>
            </TableWrap>
          ),
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
