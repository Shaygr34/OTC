import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "ATM Engine — OTC Decision Support",
  description: "OTC penny stock ATM pattern scanner and scoring engine",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <div className="flex">
          <Sidebar />
          <main className="ml-60 flex-1 min-h-screen p-5 bg-[#08080d]">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
