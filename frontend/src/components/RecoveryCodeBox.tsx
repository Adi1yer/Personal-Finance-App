import { useState } from "react";
import { Button } from "./ui";

type Props = {
  code: string;
  className?: string;
};

/** Selectable recovery code with a Copy button (pywebview blocks selection unless enabled). */
export function RecoveryCodeBox({ code, className = "" }: Props) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(code);
      } else {
        const el = document.createElement("textarea");
        el.value = code;
        el.setAttribute("readonly", "");
        el.style.position = "fixed";
        el.style.left = "-9999px";
        document.body.appendChild(el);
        el.select();
        document.execCommand("copy");
        document.body.removeChild(el);
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className={`space-y-3 ${className}`}>
      <input
        readOnly
        value={code}
        aria-label="Recovery code"
        onFocus={(e) => e.currentTarget.select()}
        className="w-full cursor-text select-all rounded-lg border border-accent/40 bg-accent/10 px-4 py-3 text-center font-mono text-lg text-white outline-none focus:ring-2 focus:ring-accent/50"
      />
      <Button type="button" variant="secondary" className="w-full" onClick={copy}>
        {copied ? "Copied" : "Copy recovery code"}
      </Button>
      <p className="text-center text-xs text-muted">
        Store it in a password manager — you need it to reset your password.
      </p>
    </div>
  );
}
