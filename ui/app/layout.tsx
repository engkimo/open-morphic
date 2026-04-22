import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import NavBar from "@/components/NavBar";
import { Separator } from "@/components/ui/separator";
import { TooltipProvider } from "@/components/ui/tooltip";

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
        <TooltipProvider>
          <header className="flex items-center justify-between px-4 py-2">
            <div className="flex items-center gap-6">
              <Link
                href="/"
                className="font-mono text-sm font-bold tracking-tight text-accent"
              >
                Morphic-Agent
              </Link>
              <NavBar />
            </div>
            <span className="text-sm text-text-muted">v0.5.0-alpha</span>
          </header>
          <Separator />
          <main className="mx-auto max-w-7xl px-4 py-4">{children}</main>
        </TooltipProvider>
      </body>
    </html>
  );
}
