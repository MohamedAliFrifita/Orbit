export function Button({
  children,
  onClick,
  disabled = false,
  type = "button",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className="bg-accent text-white px-6 py-2 font-bold uppercase tracking-wider transition-opacity hover:opacity-80 disabled:opacity-40 disabled:cursor-not-allowed"
    >
      {children}
    </button>
  );
}
