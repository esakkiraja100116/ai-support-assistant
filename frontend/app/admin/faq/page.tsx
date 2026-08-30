"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
    <div className="mx-auto max-w-3xl px-5 pt-6 pb-16">
      <div className="mb-5 flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">FAQ articles</h1>
        <Button render={<Link href="/admin/faq/new" />} nativeButton={false}>
          + Add article
        </Button>
      </div>
      {loading && <p className="text-sm text-muted-foreground">Loading...</p>}
      {error && <p className="text-sm text-muted-foreground">{error}</p>}
      {!loading && !error && (
        <div className="flex flex-col gap-2.5">
          {articles.length === 0 && <p className="text-sm text-muted-foreground">No articles yet.</p>}
          {articles.map((a) => (
            <Card key={a.id}>
              <CardContent className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="mb-1.5 text-sm font-semibold">{a.question}</h3>
                  <p className="mb-2 text-sm leading-relaxed text-foreground/80">{a.answer}</p>
                  {a.category && <Badge variant="outline">{a.category}</Badge>}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="shrink-0 border-destructive/40 text-destructive hover:bg-destructive/10"
                  onClick={() => handleDelete(a.id)}
                  disabled={deletingId === a.id}
                >
                  {deletingId === a.id ? "Deleting..." : "Delete"}
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
