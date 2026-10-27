import type { Metadata } from "next";
import { Suspense } from "react";
import { Loading } from "@/components/States";
import Chat from "./Chat";

export const metadata: Metadata = { title: "Assistant pharmaceutique — MEDISIGHT" };

export default function ChatPage() {
  return (
    <div className="mx-auto max-w-page px-5 py-10">
      <p className="label-wide text-sm text-clinic">Challenge 1 · NLP multilingue + PostgreSQL</p>
      <h1 className="display mt-2 text-4xl md:text-5xl">Assistant pharmaceutique</h1>
      <p className="prose-copy mt-3 text-muted">
        Posez votre question en français, en arabe ou en darija. Les réponses sont construites à partir de la base MEDISIGHT
        et citent leur source ; une information absente est signalée comme absente.
      </p>
      <Suspense fallback={<Loading />}><Chat /></Suspense>
    </div>
  );
}
