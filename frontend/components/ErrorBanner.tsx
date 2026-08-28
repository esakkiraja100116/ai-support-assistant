interface Props {
  message: string;
  onRetry: () => void;
}

export function ErrorBanner({ message, onRetry }: Props) {
  return (
    <div className="error-banner">
      <span>{message}</span>
      <button onClick={onRetry}>Retry</button>
    </div>
  );
}
