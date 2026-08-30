interface Props {
  message: string;
}

export function EmptyState({ message }: Props) {
  return <div className="m-auto max-w-xs px-5 py-5 text-center text-sm text-muted-foreground">{message}</div>;
}
