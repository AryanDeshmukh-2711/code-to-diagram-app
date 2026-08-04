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

  const newProjectId = `proj_${Math.random().toString(36).slice(2, 10)}`;

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold tracking-tight">AI Software Architect</h1>
      <p className="text-sm text-muted-foreground">
        Drop a PDF or paste a description and I&apos;ll turn it into a reviewable model.
      </p>
      <div className="flex flex-wrap gap-3">
        <Button asChild className="w-fit">
          <Link href={`/projects/${newProjectId}/chat`}>Start a new project</Link>
        </Button>
        <Button asChild variant="outline" className="w-fit">
          <Link href="/review/demo">Open the sample project</Link>
        </Button>
      </div>
    </main>
  );
}
