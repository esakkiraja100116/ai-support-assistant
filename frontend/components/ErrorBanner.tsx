import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

interface Props {
  message: string;
  onRetry: () => void;
}

export function ErrorBanner({ message, onRetry }: Props) {
  return (
    <Alert variant="destructive" className="flex flex-row items-center justify-between gap-3">
      <span>{message}</span>
      <Button variant="outline" size="sm" className="border-destructive/40 text-destructive" onClick={onRetry}>
        Retry
      </Button>
    </Alert>
  );
}
