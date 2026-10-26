import type { Metadata } from "next";
import "@fontsource-variable/archivo/wdth.css";
import "./globals.css";
import Footer from "@/components/Footer";
import Header from "@/components/Header";

export const metadata: Metadata = {
  title: "MEDISIGHT, Your Intelligent Pharmaceutical Companion",
  description: "Information pharmaceutique sourcée pour le Maroc : médicaments, prix, génériques et pharmacies.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className="flex min-h-screen flex-col">
        <a href="#contenu" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
          Aller au contenu
        </a>
        <Header />
        <main id="contenu" className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
