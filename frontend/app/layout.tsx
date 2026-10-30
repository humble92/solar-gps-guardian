import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Solar-GPS-Guardian",
  description: "Space-weather GPS hazard shield for drivers and autonomous fleets",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <Link href="/" className="brand">Solar-GPS-Guardian</Link>
          <nav className="topnav">
            <Link href="/">Dashboard</Link>
            <Link href="/newsletters">Newsletters</Link>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
