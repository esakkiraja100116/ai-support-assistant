"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function AdminHome() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/admin/users");
  }, [router]);

  return <div className="page-loading">Loading...</div>;
}
