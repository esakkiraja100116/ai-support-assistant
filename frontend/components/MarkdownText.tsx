import ReactMarkdown from "react-markdown";

interface Props {
  text: string;
}

// LLM-authored message text often includes markdown (**bold**, numbered/
// bulleted lists, paragraphs) that should render as formatted content, not
// literal asterisks. Deliberately does NOT enable raw HTML rendering
// (rehype-raw) - the model's own output should never become raw HTML in the
// DOM, only the safe subset of markdown react-markdown parses into elements.
export function MarkdownText({ text }: Props) {
  return (
    <div className="markdown-text">
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  );
}
