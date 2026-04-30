import type { ReactNode } from "react";
import "./globals.css";
import ChatBot from "../components/ChatBot";

export const metadata = {
  title: "Brindle Platform",
  description: "Paper-trading-first trading bot platform",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <ChatBot />
      </body>
    </html>
  );
}
