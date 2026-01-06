"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { 
  Download, 
  Search,
  Trash2, 
  RefreshCw, 
  FileVideo, 
  FileText,
  Presentation,
  Calendar,
  HardDrive,
  Film,
  Globe,
  AlertCircle,
  WifiOff
} from "lucide-react";
import { toast } from "sonner";
import { api, WorkspaceExport } from "@/lib/api";
import { Button, Badge, Card, CardHeader, CardTitle, CardDescription, CardContent, Input } from "@/components/ui";
import { cn, getLanguageName } from "@/lib/utils";

export default function WorkspacePage() {
  const queryClient = useQueryClient();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Fetch workspace exports
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["workspace-exports"],
    queryFn: () => api.getWorkspaceExports(),
    retry: 1, // Only retry once on error
    retryDelay: 1000,
  });

  const exports = data?.exports || [];

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: ({ projectId, versionId, lang }: { projectId: string; versionId: string; lang: string }) =>
      api.deleteWorkspaceExport(projectId, versionId, lang),
    onSuccess: () => {
      toast.success("Export deleted");
      queryClient.invalidateQueries({ queryKey: ["workspace-exports"] });
      setDeletingId(null);
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || "Failed to delete export");
      setDeletingId(null);
    },
  });

  const handleDelete = (item: WorkspaceExport) => {
    const id = `${item.project_id}-${item.version_id}-${item.lang}`;
    if (confirm(`Delete ${item.project_name} (${item.lang.toUpperCase()}) export?`)) {
      setDeletingId(id);
      deleteMutation.mutate({
        projectId: item.project_id,
        versionId: item.version_id,
        lang: item.lang,
      });
    }
  };

  const handleDownload = (item: WorkspaceExport, type: "video" | "srt" | "pptx") => {
    if (type === "pptx") {
      const url = api.getPptxDownloadUrl(item.project_id, item.version_id);
      window.open(url, "_blank");
      return;
    }
    const filename = type === "video" 
      ? `deck_${item.lang}.mp4`
      : `deck_${item.lang}.srt`;
    const url = api.getDownloadUrl(item.project_id, item.version_id, item.lang, filename);
    window.open(url, "_blank");
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  // Group by project
  const groupedExports = exports.reduce((acc, item) => {
    const key = item.project_id;
    if (!acc[key]) {
      acc[key] = {
        project_name: item.project_name,
        project_id: item.project_id,
        items: [],
      };
    }
    acc[key].items.push(item);
    return acc;
  }, {} as Record<string, { project_name: string; project_id: string; items: WorkspaceExport[] }>);

  const projectGroups = Object.values(groupedExports);

  // Filter by project name and/or language (supports Cyrillic)
  const q = searchQuery.trim().toLowerCase();
  const filteredProjectGroups = !q
    ? projectGroups
    : projectGroups
        .map((group) => {
          const projectMatches = group.project_name.toLowerCase().includes(q);
          const filteredItems = projectMatches
            ? group.items
            : group.items.filter((item) => {
                const langCode = item.lang.toLowerCase();
                const langName = getLanguageName(item.lang).toLowerCase();
                return langCode.includes(q) || langName.includes(q);
              });
          return { ...group, items: filteredItems };
        })
        .filter((group) => group.items.length > 0);

  const displayStats = {
    exportCount: filteredProjectGroups.reduce((sum, g) => sum + g.items.length, 0),
    sizeMb: filteredProjectGroups
      .flatMap((g) => g.items)
      .reduce((sum, e) => sum + e.video_size_mb, 0),
    projectCount: filteredProjectGroups.length,
  };

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <header className="shrink-0 bg-surface border-b border-border px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-page-title">Workspace</h1>
            <p className="text-[13px] text-muted-foreground mt-1">
              Download and manage exported videos
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search exports..."
                className="pl-9 text-[13px]"
                aria-label="Search exports by project name or language"
              />
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isLoading}
              title="Reload the exports list"
            >
              <RefreshCw className={cn("w-4 h-4", isLoading && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>
      </header>

      {/* Stats Bar */}
      <div className="shrink-0 bg-muted/30 border-b border-border px-6 py-3">
        <div className="flex items-center gap-6 text-[13px]">
          <div className="flex items-center gap-2">
            <Film className="w-4 h-4 text-muted-foreground" />
            <span className="text-muted-foreground">Total exports:</span>
            <span className="font-medium">{displayStats.exportCount}</span>
          </div>
          <div className="flex items-center gap-2">
            <HardDrive className="w-4 h-4 text-muted-foreground" />
            <span className="text-muted-foreground">Total size:</span>
            <span className="font-medium">
              {displayStats.sizeMb.toFixed(1)} MB
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Globe className="w-4 h-4 text-muted-foreground" />
            <span className="text-muted-foreground">Projects:</span>
            <span className="font-medium">{displayStats.projectCount}</span>
          </div>
        </div>
      </div>

      {/* Content */}
      <main className="flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">
            Loading exports...
          </div>
        ) : isError ? (
          <Card className="max-w-lg mx-auto mt-12 border-destructive/30">
            <CardContent className="flex flex-col items-center py-12">
              <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
                {(error as any)?.isNetworkError ? (
                  <WifiOff className="w-8 h-8 text-destructive" />
                ) : (
                  <AlertCircle className="w-8 h-8 text-destructive" />
                )}
              </div>
              <h3 className="text-lg font-medium mb-2">
                {(error as any)?.isNetworkError ? "Server Unavailable" : "Failed to load exports"}
              </h3>
              <p className="text-[13px] text-muted-foreground text-center max-w-xs mb-4">
                {(error as any)?.message || "An error occurred while loading the workspace. Please try again."}
              </p>
              <Button onClick={() => refetch()} variant="outline" size="sm">
                <RefreshCw className="w-4 h-4 mr-2" />
                Try Again
              </Button>
            </CardContent>
          </Card>
        ) : exports.length === 0 ? (
          <Card className="max-w-lg mx-auto mt-12">
            <CardContent className="flex flex-col items-center py-12">
              <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
                <Film className="w-8 h-8 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-medium mb-2">No exports yet</h3>
              <p className="text-[13px] text-muted-foreground text-center max-w-xs">
                When you render videos in your projects, they will appear here for easy download and management.
              </p>
            </CardContent>
          </Card>
        ) : filteredProjectGroups.length === 0 ? (
          <Card className="max-w-lg mx-auto mt-12">
            <CardContent className="flex flex-col items-center py-12">
              <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
                <Search className="w-8 h-8 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-medium mb-2">No matching exports</h3>
              <p className="text-[13px] text-muted-foreground text-center max-w-xs mb-4">
                Try a different search term (project name, language code, or language name).
              </p>
              <Button onClick={() => setSearchQuery("")} variant="outline" size="sm">
                Clear Search
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-6">
            {filteredProjectGroups.map((group) => (
              <Card key={group.project_id}>
                <CardHeader className="pb-3">
                  <CardTitle className="text-[15px]">{group.project_name}</CardTitle>
                  <CardDescription>
                    {group.items.length} language{group.items.length !== 1 ? "s" : ""} exported
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {group.items.map((item) => {
                      const itemId = `${item.project_id}-${item.version_id}-${item.lang}`;
                      const isDeleting = deletingId === itemId;

                      return (
                        <div
                          key={itemId}
                          className={cn(
                            "flex items-center justify-between p-3 rounded-lg border border-border bg-surface hover:bg-muted/30 transition-colors",
                            isDeleting && "opacity-50"
                          )}
                        >
                          {/* Left side - info */}
                          <div className="flex items-center gap-4">
                            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                              <FileVideo className="w-5 h-5 text-primary" />
                            </div>
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-medium text-[14px]">
                                  {getLanguageName(item.lang)}
                                </span>
                                <Badge variant="secondary" className="text-[10px]">
                                  {item.lang.toUpperCase()}
                                </Badge>
                                {item.has_srt && (
                                  <Badge variant="outline" className="text-[10px]">
                                    +SRT
                                  </Badge>
                                )}
                                {item.has_pptx && (
                                  <Badge variant="outline" className="text-[10px]">
                                    +PPTX
                                  </Badge>
                                )}
                              </div>
                              <div className="flex items-center gap-3 text-[12px] text-muted-foreground mt-0.5">
                                <span className="flex items-center gap-1">
                                  <HardDrive className="w-3 h-3" />
                                  {item.video_size_mb} MB
                                </span>
                                <span className="flex items-center gap-1">
                                  <Calendar className="w-3 h-3" />
                                  {formatDate(item.created_at)}
                                </span>
                              </div>
                            </div>
                          </div>

                          {/* Right side - actions */}
                          <div className="flex items-center gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleDownload(item, "video")}
                              title="Download rendered video (.mp4)"
                            >
                              <Download className="w-3.5 h-3.5" />
                              Video
                            </Button>
                            {item.has_srt && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDownload(item, "srt")}
                                title="Download subtitles (.srt)"
                              >
                                <FileText className="w-3.5 h-3.5" />
                                SRT
                              </Button>
                            )}
                            {item.has_pptx && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDownload(item, "pptx")}
                                title="Download original presentation (.pptx)"
                              >
                                <Presentation className="w-3.5 h-3.5" />
                                PPTX
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-red-600 hover:text-red-700 hover:bg-red-50"
                              onClick={() => handleDelete(item)}
                              disabled={isDeleting}
                              title="Delete this export from workspace"
                              aria-label="Delete export"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

