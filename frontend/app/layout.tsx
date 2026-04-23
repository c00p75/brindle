import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Trading Bot Platform",
  description: "Paper-trading-first trading bot platform",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
