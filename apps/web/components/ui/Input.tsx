/**
 * Composant Input réutilisable — respecte les design tokens ORBIT.
 * Utilisé dans le formulaire mission, la page login, etc.
 */

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  id: string;
}

export function Input({ label, id, className = "", ...props }: InputProps) {
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label
          htmlFor={id}
          className="text-xs font-semibold uppercase tracking-widest text-neutral-400"
        >
          {label}
        </label>
      )}
      <input
        id={id}
        className={`
          bg-bg border border-border text-white
          px-4 py-2 text-sm
          placeholder:text-neutral-600
          focus:outline-none focus:border-accent
          transition-colors
          disabled:opacity-40 disabled:cursor-not-allowed
          ${className}
        `}
        {...props}
      />
    </div>
  );
}
