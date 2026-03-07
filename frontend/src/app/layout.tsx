export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen bg-neutral-900 text-neutral-100 font-sans selection:bg-indigo-500/30">
        {children}
      </body>
    </html>
  );
}
