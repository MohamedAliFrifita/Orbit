import "../styles/tokens.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ORBIT",
  description: "Pipeline métier de l'agent ORBIT",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className="bg-bg text-white min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
