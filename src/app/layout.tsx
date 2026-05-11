import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import HealthStrip from "@/components/HealthStrip";

const inter = Inter({ subsets: ["latin"] });

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
