"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
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
    <div className="faq-page">
      <header className="faq-header">
        <h1>Knowledge Base</h1>
        <Link href="/" className="text-button">
          Back to chat
        </Link>
      </header>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => window.location.reload()}>Retry</button>
        </div>
      )}

      {!articles && !error && <p className="muted">Loading...</p>}

      {articles && articles.length === 0 && <p className="muted">No FAQ articles found.</p>}

      {articles &&
        groupByCategory(articles).map(([category, items]) => (
          <section key={category} className="faq-category">
            <h2>{category}</h2>
            {items.map((article) => (
              <div key={article.id} className="faq-item">
                <h3>{article.question}</h3>
                <p>{article.answer}</p>
              </div>
            ))}
          </section>
        ))}
    </div>
  );
}
