import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import HealthStrip from "@/components/HealthStrip";

const inter = Inter({ subsets: ["latin"] });

// O chrome do layout (Sidebar + HealthStrip) lê o estado do squire no
// filesystem a cada render. O build roda SEM o volume de dados — qualquer
// rota prerenderizada congelaria sidebar vazia e sessão falsa (já mordeu
// em /, /api/health e /projects/new). force-dynamic aqui se aplica a
// todas as páginas; route handlers precisam do export próprio.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Squire Dashboard",
  description: "Visualização em tempo real do estado do squire",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body className={inter.className}>
        <div className="flex min-h-screen bg-gray-50 dark:bg-gray-900">
          <Sidebar />
          <main className="flex-1 min-w-0 flex flex-col">
            <HealthStrip />
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
