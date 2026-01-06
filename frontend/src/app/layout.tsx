import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { Toaster } from "sonner";
import { Sidebar } from "@/components/layout/Sidebar";

const inter = Inter({ 
  subsets: ["latin", "cyrillic"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Presenter - Multilingual Video Platform",
  description: "Create multilingual presentation videos with AI voiceover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} font-sans antialiased`}>
        <Providers>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-hidden">
              {children}
            </main>
          </div>
          <Toaster 
            richColors 
            position="bottom-right"
            expand={true}
            visibleToasts={5}
            gap={8}
            toastOptions={{
              style: {
                borderRadius: "8px",
              },
            }}
          />
        </Providers>
      </body>
    </html>
  );
}
