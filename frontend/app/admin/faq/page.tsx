"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { adminDeleteFaqArticle, listFaqArticles } from "@/lib/api";
import { FaqArticle } from "@/lib/types";

export default function AdminFaqListPage() {
  const { session } = useAuth();
  const [articles, setArticles] = useState<FaqArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    listFaqArticles()
      .then(setArticles)
      .catch(() => setError("Could not load FAQ articles."))
      .finally(() => setLoading(false));
  }, []);

  async function handleDelete(id: number) {
    if (!session) return;
    if (!window.confirm("Delete this article? The assistant will no longer be able to answer from it.")) return;
    setDeletingId(id);
    try {
      await adminDeleteFaqArticle(session.accessToken, id);
      setArticles((prev) => prev.filter((a) => a.id !== id));
    } catch {
      setError("Could not delete this article. Please try again.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h1>FAQ articles</h1>
        <Link href="/admin/faq/new" className="new-chat-button admin-page-header-action">
          + Add article
        </Link>
      </div>
      {loading && <p className="muted">Loading...</p>}
      {error && <p className="muted">{error}</p>}
      {!loading && !error && (
        <div className="faq-admin-list">
          {articles.length === 0 && <p className="muted">No articles yet.</p>}
          {articles.map((a) => (
            <div key={a.id} className="faq-admin-item">
              <div className="faq-admin-item-body">
                <h3>{a.question}</h3>
                <p>{a.answer}</p>
                {a.category && <span className="faq-admin-item-category">{a.category}</span>}
              </div>
              <button
                className="faq-admin-item-delete"
                onClick={() => handleDelete(a.id)}
                disabled={deletingId === a.id}
              >
                {deletingId === a.id ? "Deleting..." : "Delete"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
