"use client";

import { FormEvent, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { adminCreateFaqArticle } from "@/lib/api";

export function FaqArticleForm() {
  const { session } = useAuth();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [category, setCategory] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!session || !question.trim() || !answer.trim()) return;
    setSubmitting(true);
    setError(null);
    setSuccess(false);
    try {
      await adminCreateFaqArticle(session.accessToken, {
        question: question.trim(),
        answer: answer.trim(),
        category: category.trim() || null,
        tags: category.trim() ? [category.trim()] : null,
      });
      setQuestion("");
      setAnswer("");
      setCategory("");
      setSuccess(true);
    } catch {
      setError("Could not create this article. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="faq-form" onSubmit={handleSubmit}>
      <label className="faq-form-field">
        Question
        <input value={question} onChange={(e) => setQuestion(e.target.value)} required />
      </label>
      <label className="faq-form-field">
        Answer
        <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} rows={5} required />
      </label>
      <label className="faq-form-field">
        Category (optional)
        <input value={category} onChange={(e) => setCategory(e.target.value)} />
      </label>
      {error && <div className="error-banner">{error}</div>}
      {success && <p className="faq-form-success">Article created and embedded in the knowledge base.</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "Creating..." : "Create article"}
      </button>
    </form>
  );
}
