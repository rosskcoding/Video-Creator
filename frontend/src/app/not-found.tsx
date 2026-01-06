"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/api";

export default function NotFound() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    // Check auth status and redirect accordingly
    async function checkAuthAndRedirect() {
      const authenticated = await isAuthenticated();
      if (authenticated) {
        router.replace("/");
      } else {
        router.replace("/login");
      }
      setChecking(false);
    }
    
    checkAuthAndRedirect();
  }, [router]);

  if (!checking) return null;

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900">
      <div className="text-slate-400 text-lg">Redirecting...</div>
    </div>
  );
}
