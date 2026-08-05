import Link from "next/link";

export function AppHeader() {
  return (
    <header className="flex items-center justify-between border-b border-border px-6 py-3 sm:px-10">
      <Link href="/" className="text-sm font-semibold tracking-tight">
        AI Software Architect
      </Link>
    </header>
  );
}
