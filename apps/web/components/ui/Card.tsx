export function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-bg-card border border-border p-6 rounded-none">
      <h2 className="text-accent text-xl font-bold mb-4 uppercase tracking-wide">
        {title}
      </h2>
      <div>{children}</div>
    </div>
  );
}
