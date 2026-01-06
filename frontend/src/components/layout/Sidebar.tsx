"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FolderOpen, Settings2, ListTodo, Video, Archive } from "lucide-react";
import { cn } from "@/lib/utils";

const navigation = [
  { name: "Projects", href: "/", icon: FolderOpen },
  { name: "Workspace", href: "/workspace", icon: Archive },
  { name: "Jobs", href: "/admin/jobs", icon: ListTodo },
  { name: "Admin", href: "/admin", icon: Settings2 },
];

export function Sidebar() {
  const pathname = usePathname() || "";
  
  // Hide sidebar only on login page
  if (pathname === "/login") return null;

  return (
    <aside className="w-16 bg-surface border-r border-border flex flex-col items-center py-4 gap-1">
      {/* Logo */}
      <Link 
        href="/"
        className="w-10 h-10 rounded-lg bg-primary flex items-center justify-center mb-4"
      >
        <Video className="w-5 h-5 text-white" />
      </Link>

      {/* Navigation */}
      <nav className="flex-1 flex flex-col gap-1">
        {navigation.map((item) => {
          const isActive = pathname === item.href || 
            (item.href !== "/" && pathname.startsWith(item.href));
          
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "w-10 h-10 rounded-lg flex items-center justify-center transition-colors group relative",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <item.icon className="w-5 h-5" />
              
              {/* Tooltip */}
              <span className="absolute left-full ml-2 px-2 py-1 bg-foreground text-background text-label rounded-md opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity whitespace-nowrap z-50">
                {item.name}
              </span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

