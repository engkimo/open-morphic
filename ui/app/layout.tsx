import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Morphic-Agent",
  description: "Mission Control for Intelligence",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground`}
      >
        <header className="flex items-center justify-between border-b border-border px-6 py-3">
          <div className="flex items-center gap-6">
            <Link
              href="/"
              className="font-mono text-lg font-bold tracking-tight text-accent"
            >
              Morphic-Agent
            </Link>
            <nav className="flex items-center gap-4 text-sm text-text-muted">
              <Link href="/marketplace" className="hover:text-accent">
                Marketplace
              </Link>
              <Link href="/models" className="hover:text-accent">
                Models
              </Link>
            </nav>
          </div>
          <span className="text-sm text-text-muted">v0.4.0-alpha</span>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
