import type { Metadata } from "next";
import { Suspense } from "react";
import { Loading } from "@/components/States";
import Chat from "./Chat";

export const metadata: Metadata = { title: "Assistant pharmaceutique — MEDISIGHT" };

export default function ChatPage() {
  return (
    <div className="bg-[linear-gradient(#FFFFFF,#F5F8FA_22rem)]">
      <div className="mx-auto max-w-[90rem] px-5 pb-4 pt-8 md:pt-10">
        <header className="max-w-3xl">
          <p className="inline-flex items-center gap-2 rounded-full border border-health/30 bg-white px-3 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[#11806B] sm:text-xs">
            <span aria-hidden="true">✦</span> Assistant pharmaceutique intelligent
          </p>
          <h1 className="display mt-4 text-3xl text-ink md:text-[2.6rem]">Votre assistant MedSight AI</h1>
          <p className="prose-copy mt-3 text-muted">Posez vos questions. MedSight vous répond.</p>
        </header>
        <Suspense fallback={<Loading />}><Chat /></Suspense>
      </div>
    </div>
  );
}
