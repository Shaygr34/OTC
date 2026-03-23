import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "ATM Engine",
  description: "OTC penny stock decision support",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <div className="flex">
          <Sidebar />
          <main className="ml-56 flex-1 min-h-screen p-6">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
