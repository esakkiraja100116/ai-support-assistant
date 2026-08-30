import { FaqArticleForm } from "@/components/admin/FaqArticleForm";

export default function AdminFaqNewPage() {
  return (
    <div className="mx-auto max-w-3xl px-5 pt-6 pb-16">
      <h1 className="mb-1.5 text-2xl font-semibold tracking-tight">Add FAQ article</h1>
      <p className="text-sm text-muted-foreground">
        Creates a new knowledge base article and generates its embedding immediately, so the assistant can retrieve
        it right away.
      </p>
      <FaqArticleForm />
    </div>
  );
}
