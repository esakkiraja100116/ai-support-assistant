export function LoadingIndicator() {
  return (
    <div className="flex items-center gap-1 py-1" aria-label="Assistant is typing">
      <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]" />
      <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]" />
      <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground" />
    </div>
  );
}
