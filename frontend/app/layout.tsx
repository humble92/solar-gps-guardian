import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Solar-GPS-Guardian",
  description: "Space-weather GPS hazard shield for drivers and autonomous fleets",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
