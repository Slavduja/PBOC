import "./globals.css";

export const metadata = {
  title: "PBoC Liquidity Index",
  description: "Component-level reconstruction of Michael Howell's PBoC net liquidity injection metric",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
