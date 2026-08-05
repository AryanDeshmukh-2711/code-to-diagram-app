import type { Metadata } from "next";
import "./globals.css";

import { AppHeader } from "@/components/AppHeader";

export const metadata: Metadata = {
  title: "AI Software Architect",
  description:
    "Turn a project description into a submission-ready SRS and a consistent UML diagram set.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <div className="flex h-screen flex-col">
          <AppHeader />
          <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        </div>
      </body>
    </html>
  );
}
