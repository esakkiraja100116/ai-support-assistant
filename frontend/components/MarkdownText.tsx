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
    <div
      className="text-sm leading-relaxed
        [&>p]:my-2 [&>p:first-child]:mt-0 [&>p:last-child]:mb-0
        [&_ul]:my-2 [&_ol]:my-2 [&_ul]:pl-5 [&_ol]:pl-5
        [&_li]:my-0.5 [&_li>p]:my-0
        [&_strong]:font-bold
        [&_code]:rounded [&_code]:bg-black/5 [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[0.9em]"
    >
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  );
}
