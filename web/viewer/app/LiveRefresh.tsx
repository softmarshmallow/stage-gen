"use client";

// Re-reads the page from the server every two seconds while a run on it is live.
//
// router.refresh() re-renders the server components and keeps client state, so a
// reader's camera, selection and open panel survive each refresh. Nothing polls until
// the page is in a browser: the refresher mounts after hydration, which also keeps a
// static render of the page free of any router.

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export const LIVE_REFRESH_MS = 2000;

function Refresher() {
  const router = useRouter();
  useEffect(() => {
    const timer = window.setInterval(() => router.refresh(), LIVE_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [router]);
  return null;
}

export default function LiveRefresh({ live }: { live: boolean }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return live && mounted ? <Refresher /> : null;
}
