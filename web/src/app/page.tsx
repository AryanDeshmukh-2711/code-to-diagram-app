"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { isAuthed } from "@/lib/session";
import { Button } from "@/components/ui/button";

export default function Home() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!isAuthed()) {
      router.replace("/signin");
      return;
    }
    setChecked(true);
  }, [router]);

  if (!checked) return null;

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold tracking-tight">AI Software Architect</h1>
      <p className="text-sm text-muted-foreground">
        Signed in. Dropping a description or a PDF and turning it into a reviewable model lands
        in a later step — for now, the sample project shows the review screen working end to end.
      </p>
      <Button asChild className="w-fit">
        <Link href="/review/demo">Open the sample project</Link>
      </Button>
    </main>
  );
}
