"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorBanner } from "@/components/ErrorBanner";
import { listFaqArticles } from "@/lib/api";
import { FaqArticle } from "@/lib/types";

function groupByCategory(articles: FaqArticle[]): [string, FaqArticle[]][] {
  const groups = new Map<string, FaqArticle[]>();
  for (const article of articles) {
    const key = article.category || "General";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(article);
  }
  return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
}

export default function FaqPage() {
  const [articles, setArticles] = useState<FaqArticle[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listFaqArticles()
      .then(setArticles)
      .catch(() => setError("Could not load the knowledge base. Is the backend running?"));
  }, []);

  return (
    <div className="mx-auto max-w-2xl px-5 pt-6 pb-16">
      <header className="mb-5 flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Knowledge Base</h1>
        <Link href="/" className="text-sm text-primary hover:underline">
          Back to chat
        </Link>
      </header>

      {error && <ErrorBanner message={error} onRetry={() => window.location.reload()} />}

      {!articles && !error && <p className="text-sm text-muted-foreground">Loading...</p>}

      {articles && articles.length === 0 && <p className="text-sm text-muted-foreground">No FAQ articles found.</p>}

      {articles &&
        groupByCategory(articles).map(([category, items]) => (
          <section key={category} className="mb-7">
            <h2 className="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{category}</h2>
            <div className="flex flex-col gap-2.5">
              {items.map((article) => (
                <Card key={article.id}>
                  <CardContent>
                    <h3 className="mb-1.5 text-sm font-semibold">{article.question}</h3>
                    <p className="text-sm leading-relaxed text-foreground/80">{article.answer}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>
        ))}
    </div>
  );
}
