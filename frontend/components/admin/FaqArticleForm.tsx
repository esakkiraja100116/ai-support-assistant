"use client";

import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ErrorBanner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
    <form className="mt-4.5 flex max-w-lg flex-col gap-3.5" onSubmit={handleSubmit}>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="faq-question">Question</Label>
        <Input id="faq-question" value={question} onChange={(e) => setQuestion(e.target.value)} required />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="faq-answer">Answer</Label>
        <Textarea id="faq-answer" value={answer} onChange={(e) => setAnswer(e.target.value)} rows={5} required />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="faq-category">Category (optional)</Label>
        <Input id="faq-category" value={category} onChange={(e) => setCategory(e.target.value)} />
      </div>
      {error && <ErrorBanner message={error} onRetry={() => setError(null)} />}
      {success && <p className="text-sm font-medium text-green-700">Article created and embedded in the knowledge base.</p>}
      <Button type="submit" disabled={submitting} className="w-fit">
        {submitting ? "Creating..." : "Create article"}
      </Button>
    </form>
  );
}
