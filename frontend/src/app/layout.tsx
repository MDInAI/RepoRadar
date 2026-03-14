import type { Metadata } from "next";
import { AppProviders } from "./providers";
import { IconRail } from "@/components/layout/IconRail";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agentic-Workflow · Mission Control",
  description: "Local-first intelligent repository discovery and analysis",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body style={{ overflow: 'hidden', height: '100vh' }}>
        <AppProviders>
          <div style={{ display: 'grid', gridTemplateColumns: '56px 1fr', height: '100vh' }}>
            <IconRail />
            <main style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              {children}
            </main>
          </div>
        </AppProviders>
      </body>
    </html>
  );
}
