import type { Metadata } from "next";
import { AppProviders } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agentic-Workflow Dashboard",
  description: "Local-first intelligent repository discovery and analysis",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen bg-neutral-900 text-neutral-100 font-sans selection:bg-indigo-500/30">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
