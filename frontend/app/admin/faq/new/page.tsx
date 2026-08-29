import { FaqArticleForm } from "@/components/admin/FaqArticleForm";

export default function AdminFaqNewPage() {
  return (
    <div className="admin-page">
      <h1>Add FAQ article</h1>
      <p className="muted">
        Creates a new knowledge base article and generates its embedding immediately, so the assistant can retrieve
        it right away.
      </p>
      <FaqArticleForm />
    </div>
  );
}
