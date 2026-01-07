"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, FolderOpen, Languages, Image, Clock, AlertCircle, WifiOff, RefreshCw, Trash2, MoreVertical } from "lucide-react";
import { api, Project, isAuthenticated } from "@/lib/api";
import { Button, Input, Badge, Card } from "@/components/ui";
import { CreateProjectModal } from "@/components/CreateProjectModal";
import { toast } from "sonner";
import Link from "next/link";

export default function ProjectsPage() {
  const router = useRouter();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [authChecked, setAuthChecked] = useState(false);

  // Check auth on mount (async)
  useEffect(() => {
    async function checkAuth() {
      const authenticated = await isAuthenticated();
      if (!authenticated) {
        router.push("/login");
      } else {
        setAuthChecked(true);
      }
    }
    checkAuth();
  }, [router]);

  const { data: projects, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["projects"],
    queryFn: api.getProjects,
    retry: 1,
    retryDelay: 1000,
    enabled: authChecked, // Only fetch when auth is confirmed
  });

  const filteredProjects = projects?.filter((p) =>
    p.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Show loading while checking auth
  if (!authChecked) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <header className="shrink-0 bg-surface border-b border-border px-6 py-4">
        <div className="flex items-center justify-between">
          <h1 className="text-page-title">Projects</h1>
          <div className="flex items-center gap-3">
            <div className="relative w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search projects..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
            <Button
              onClick={() => setShowCreateModal(true)}
              title="Open the project creation dialog"
            >
              <Plus className="w-4 h-4" />
              New Project
            </Button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-[140px] bg-muted rounded-lg animate-pulse" />
            ))}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center h-[60vh] text-center">
            <div className="w-16 h-16 rounded-2xl bg-destructive/10 flex items-center justify-center mb-4">
              {(error as any)?.isNetworkError ? (
                <WifiOff className="w-8 h-8 text-destructive" />
              ) : (
                <AlertCircle className="w-8 h-8 text-destructive" />
              )}
            </div>
            <h2 className="text-section mb-1">
              {(error as any)?.isNetworkError ? "Server Unavailable" : "Failed to load projects"}
            </h2>
            <p className="text-[13px] text-muted-foreground mb-6 max-w-[280px]">
              {(error as any)?.message || "An error occurred while loading projects. Please try again."}
            </p>
            <Button onClick={() => refetch()} variant="outline">
              <RefreshCw className="w-4 h-4" />
              Try Again
            </Button>
          </div>
        ) : !filteredProjects?.length ? (
          <EmptyState onCreateClick={() => setShowCreateModal(true)} />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredProjects.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
        )}
      </main>

      {showCreateModal && (
        <CreateProjectModal onClose={() => setShowCreateModal(false)} />
      )}
    </div>
  );
}

function ProjectCard({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const [showMenu, setShowMenu] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteProject(project.id),
    onSuccess: () => {
      toast.success(`Project "${project.name}" deleted`);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: () => {
      toast.error("Failed to delete project");
    },
  });

  const handleDelete = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (confirmDelete) {
      deleteMutation.mutate();
      setConfirmDelete(false);
      setShowMenu(false);
    } else {
      setConfirmDelete(true);
      // Reset confirm after 3 seconds
      setTimeout(() => setConfirmDelete(false), 3000);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "ready":
        return <Badge variant="success">Ready</Badge>;
      case "rendering":
        return <Badge variant="warning">Rendering</Badge>;
      case "done":
        return <Badge variant="success">Done</Badge>;
      case "failed":
        return <Badge variant="error">Failed</Badge>;
      default:
        return <Badge variant="secondary">Draft</Badge>;
    }
  };

  return (
    <div className="relative">
      <Link href={`/projects/${project.id}`}>
        <Card className="p-4 hover:shadow-card-hover hover:border-primary/30 transition-all duration-200 cursor-pointer group">
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <Image className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h3 className="font-medium text-[14px] group-hover:text-primary transition-colors">
                  {project.name}
                </h3>
                <p className="text-label text-muted-foreground">
                  Base: {project.base_language.toUpperCase()}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {getStatusBadge(project.status)}
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setShowMenu(!showMenu);
                }}
                className="p-1 rounded hover:bg-muted opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <MoreVertical className="w-4 h-4 text-muted-foreground" />
              </button>
            </div>
          </div>

          <div className="flex items-center gap-4 text-label text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Image className="w-3.5 h-3.5" />
              {project.slide_count} slides
            </span>
            <span className="flex items-center gap-1.5">
              <Languages className="w-3.5 h-3.5" />
              {project.language_count} {project.language_count === 1 ? "language" : "languages"}
            </span>
          </div>

          <div className="flex items-center gap-1.5 mt-3 pt-3 border-t border-border text-label text-muted-foreground">
            <Clock className="w-3.5 h-3.5" />
            <span>Updated {formatRelativeTime(project.updated_at)}</span>
          </div>
        </Card>
      </Link>

      {/* Delete menu */}
      {showMenu && (
        <>
          <div 
            className="fixed inset-0 z-10" 
            onClick={() => { setShowMenu(false); setConfirmDelete(false); }}
          />
          <div className="absolute right-2 top-12 z-20 bg-surface border border-border rounded-lg shadow-lg py-1 min-w-[140px]">
            <button
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
              className="w-full px-3 py-2 text-left text-sm flex items-center gap-2 hover:bg-muted text-destructive"
            >
              <Trash2 className="w-4 h-4" />
              {deleteMutation.isPending ? "Deleting..." : confirmDelete ? "Click to confirm" : "Delete project"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function EmptyState({ onCreateClick }: { onCreateClick: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-[60vh] text-center">
      <div className="w-16 h-16 rounded-2xl bg-muted flex items-center justify-center mb-4">
        <FolderOpen className="w-8 h-8 text-muted-foreground" />
      </div>
      <h2 className="text-section mb-1">No projects yet</h2>
      <p className="text-[13px] text-muted-foreground mb-6 max-w-[280px]">
        Upload a PPTX to create your first multilingual video presentation
      </p>
      <Button onClick={onCreateClick} title="Open the project creation dialog">
        <Plus className="w-4 h-4" />
        Create Project
      </Button>
    </div>
  );
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}
