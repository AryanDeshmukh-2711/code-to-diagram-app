"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { signOut } from "@/lib/auth";
import { isAuthed } from "@/lib/session";
import { Button } from "@/components/ui/button";

/** Reads session state after mount, and again on every navigation.
 *
 * The header lives in the root layout, which the App Router does not remount
 * on a client-side navigation — so a plain mount-only check would freeze
 * "signed out" in place through the sign-in page's own redirect to `/`, and
 * never notice a session appearing (or a sign-out clearing one) afterward.
 * `pathname` changing is the signal that something navigated and the token
 * in localStorage might have too.
 */
export function AppHeader() {
  const router = useRouter();
  const pathname = usePathname();
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => setAuthed(isAuthed()), [pathname]);

  return (
    <header className="flex items-center justify-between border-b border-border px-6 py-3 sm:px-10">
      <Link href="/" className="text-sm font-semibold tracking-tight">
        AI Software Architect
      </Link>
      {authed ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            signOut();
            router.push("/signin");
          }}
        >
          Sign out
        </Button>
      ) : null}
    </header>
  );
}
