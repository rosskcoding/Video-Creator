"use client";

import React, { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, ChevronDown, ChevronRight, RotateCcw, AlertCircle, XCircle, Square } from "lucide-react";
import { toast } from "sonner";
import { api, RenderJob } from "@/lib/api";
import { Button, Badge, Progress, Card } from "@/components/ui";
import { cn } from "@/lib/utils";

export default function AdminJobsPage() {
  const [expandedJob, setExpandedJob] = useState<string | null>(null);
  const queryClient = useQueryClient();

  // Fetch all jobs from API
  const { data: jobs = [], isLoading, isFetching, refetch } = useQuery({
    queryKey: ["all-jobs"],
    queryFn: () => api.getAllJobs(50),
    refetchInterval: 5000, // Auto-refresh every 5 seconds
    retry: 1, // Only retry once on failure
  });

  const cancelableCountByProject = useMemo(() => {
    const m: Record<string, number> = {};
    for (const j of jobs) {
      if (j.project_id && (j.status === "running" || j.status === "queued")) {
        m[j.project_id] = (m[j.project_id] || 0) + 1;
      }
    }
    return m;
  }, [jobs]);

  // Cancel job mutation
  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => api.cancelJob(jobId),
    onSuccess: () => {
      toast.success("Job cancelled");
      queryClient.invalidateQueries({ queryKey: ["all-jobs"] });
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || "Failed to cancel job");
    },
  });

  const cancelProjectMutation = useMutation({
    mutationFn: (projectId: string) => api.cancelAllProjectJobs(projectId),
    onSuccess: (data) => {
      toast.success(`Cancelled ${data.cancelled_count} job(s) for project`);
      queryClient.invalidateQueries({ queryKey: ["all-jobs"] });
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || "Failed to cancel project jobs");
    },
  });

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "done":
        return <Badge variant="success">Done</Badge>;
      case "running":
        return <Badge variant="default">Running</Badge>;
      case "failed":
        return <Badge variant="error">Failed</Badge>;
      case "queued":
        return <Badge variant="secondary">Queued</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  const getJobTypeLabel = (type: string) => {
    switch (type) {
      case "convert":
        return "PPTX Convert";
      case "tts":
        return "Audio Generation";
      case "render":
        return "Video Render";
      case "preview":
        return "Preview";
      default:
        return type;
    }
  };

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  const canCancel = (status: string) => {
    return status === "running" || status === "queued";
  };

  const handleCancel = (e: React.MouseEvent, jobId: string) => {
    e.stopPropagation();
    if (confirm("Are you sure you want to cancel this job?")) {
      cancelMutation.mutate(jobId);
    }
  };

  const handleCancelProject = (e: React.MouseEvent, projectId: string, projectName?: string) => {
    e.stopPropagation();
    const name = projectName || "this project";
    if (confirm(`Cancel ALL queued/running jobs for ${name}?`)) {
      cancelProjectMutation.mutate(projectId);
    }
  };

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <header className="shrink-0 bg-surface border-b border-border px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-page-title">Jobs Monitor</h1>
            <p className="text-[13px] text-muted-foreground mt-1">
              Track background tasks and render jobs
            </p>
          </div>
          <Button 
            variant="outline" 
            size="sm" 
            onClick={() => refetch()}
            disabled={isFetching}
            title="Reload jobs list"
          >
            <RefreshCw className={cn("w-4 h-4", isFetching && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 overflow-auto p-6">
        <Card>
          <div className="border border-border rounded-lg overflow-hidden">
            <table className="w-full text-[13px]">
              <thead className="bg-muted">
                <tr>
                  <th className="w-8"></th>
                  <th className="text-left font-medium px-3 py-2.5">Job ID</th>
                  <th className="text-left font-medium px-3 py-2.5">Project</th>
                  <th className="text-left font-medium px-3 py-2.5">Type</th>
                  <th className="text-left font-medium px-3 py-2.5">Language</th>
                  <th className="text-left font-medium px-3 py-2.5">Status</th>
                  <th className="text-left font-medium px-3 py-2.5 w-32">Progress</th>
                  <th className="text-left font-medium px-3 py-2.5">Started</th>
                  <th className="w-20"></th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-muted-foreground">
                      Loading jobs...
                    </td>
                  </tr>
                ) : jobs.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-muted-foreground">
                      No jobs found
                    </td>
                  </tr>
                ) : (
                  jobs.map((job) => (
                    <React.Fragment key={job.id}>
                      <tr
                        className={cn(
                          "border-t border-border cursor-pointer hover:bg-muted/50 transition-colors",
                          expandedJob === job.id && "bg-muted/30"
                        )}
                        onClick={() =>
                          setExpandedJob(expandedJob === job.id ? null : job.id)
                        }
                      >
                        <td className="px-2">
                          {expandedJob === job.id ? (
                            <ChevronDown className="w-4 h-4 text-muted-foreground" />
                          ) : (
                            <ChevronRight className="w-4 h-4 text-muted-foreground" />
                          )}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-[12px]">
                          {job.id.slice(0, 8)}...
                        </td>
                        <td className="px-3 py-2.5">
                          {job.project_name || "Unknown Project"}
                        </td>
                        <td className="px-3 py-2.5">{getJobTypeLabel(job.job_type)}</td>
                        <td className="px-3 py-2.5">{job.lang?.toUpperCase() || "-"}</td>
                        <td className="px-3 py-2.5">{getStatusBadge(job.status)}</td>
                        <td className="px-3 py-2.5">
                          {job.status === "running" ? (
                            <div className="flex items-center gap-2">
                              <Progress value={job.progress_pct} className="flex-1" />
                              <span className="text-muted-foreground">{job.progress_pct}%</span>
                            </div>
                          ) : job.status === "done" ? (
                            <span className="text-muted-foreground">100%</span>
                          ) : (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-muted-foreground">
                          {formatTime(job.started_at)}
                        </td>
                        <td className="px-3 py-2.5">
                          <div className="flex gap-1 justify-end">
                            {canCancel(job.status) && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-red-600 hover:text-red-700 hover:bg-red-50"
                                onClick={(e) => handleCancel(e, job.id)}
                                disabled={cancelMutation.isPending}
                                title="Cancel this job"
                              >
                                <Square className="w-3.5 h-3.5 fill-current" />
                                Kill
                              </Button>
                            )}

                            {job.project_id && (cancelableCountByProject[job.project_id] || 0) > 0 && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-red-600 hover:text-red-700 hover:bg-red-50"
                                onClick={(e) =>
                                  handleCancelProject(e, job.project_id as string, job.project_name)
                                }
                                disabled={cancelProjectMutation.isPending}
                                title={`Cancel all queued/running jobs for this project (${cancelableCountByProject[job.project_id] || 0})`}
                              >
                                <Square className="w-3.5 h-3.5 fill-current" />
                                All
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>

                      {/* Expanded row */}
                      {expandedJob === job.id && (
                        <tr>
                          <td colSpan={9} className="bg-muted/20 px-6 py-4">
                            <div className="space-y-3">
                              {/* Error message */}
                              {job.error_message && (
                                <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-[13px]">
                                  <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                                  <div>
                                    <p className="font-medium text-red-800">Error</p>
                                    <p className="text-red-700 mt-0.5">{job.error_message}</p>
                                  </div>
                                </div>
                              )}

                              {/* Details */}
                              <div className="grid grid-cols-4 gap-4 text-[13px]">
                                <div>
                                  <p className="text-muted-foreground">Job ID</p>
                                  <p className="font-medium font-mono text-[12px]">{job.id}</p>
                                </div>
                                <div>
                                  <p className="text-muted-foreground">Started</p>
                                  <p className="font-medium">{formatTime(job.started_at)}</p>
                                </div>
                                <div>
                                  <p className="text-muted-foreground">Finished</p>
                                  <p className="font-medium">{formatTime(job.finished_at)}</p>
                                </div>
                                <div>
                                  <p className="text-muted-foreground">Output</p>
                                  <p className="font-medium font-mono text-[12px] truncate">
                                    {job.download_video_url ? (
                                      <a 
                                        href={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001'}${job.download_video_url}`} 
                                        className="text-primary hover:underline" 
                                        target="_blank"
                                        rel="noreferrer noopener"
                                      >
                                        Download Video
                                      </a>
                                    ) : "-"}
                                  </p>
                                </div>
                              </div>

                              {/* Actions */}
                              <div className="flex gap-2 pt-2">
                                {job.status === "failed" && (
                                  <Button
                                    variant="secondary"
                                    size="sm"
                                    onClick={() => toast.info("Retry is coming soon")}
                                    title="Retry this job (coming soon)"
                                  >
                                    <RotateCcw className="w-3.5 h-3.5" />
                                    Retry Job
                                  </Button>
                                )}
                                {canCancel(job.status) && (
                                  <Button 
                                    variant="destructive" 
                                    size="sm"
                                    onClick={(e) => handleCancel(e, job.id)}
                                    disabled={cancelMutation.isPending}
                                    title="Cancel this job"
                                  >
                                    <XCircle className="w-3.5 h-3.5" />
                                    Cancel Job
                                  </Button>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </main>
    </div>
  );
}
