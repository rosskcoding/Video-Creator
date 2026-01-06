"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Upload,
  Music4,
  Languages,
  Mic,
  Video,
  Download,
  Play,
  Pause,
  ChevronDown,
  Check,
  AlertTriangle,
  Wand2,
  MoreHorizontal,
  Copy,
  Search,
  Loader2,
  Clock,
  FileVideo,
  FileText,
  BookText,
  Trash2,
  Plus,
  GripVertical,
  ImagePlus,
  X,
} from "lucide-react";
import { api, Slide, Voice } from "@/lib/api";
import { cn, getLanguageName, estimateDuration, formatDuration, formatRelativeTime, LANGUAGES } from "@/lib/utils";
import { toast } from "sonner";
import Link from "next/link";
import { useDropzone } from "react-dropzone";
import { Button, Badge, Input, Textarea, Select } from "@/components/ui";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

type SlideFilter = "all" | "needs-audio" | "ready";

export default function ProjectEditorPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = (params?.id as string) || "";
  const queryClient = useQueryClient();

  // State
  const [selectedSlideId, setSelectedSlideId] = useState<string | null>(null);
  const [selectedLang, setSelectedLang] = useState<string>("en");
  const [scriptText, setScriptText] = useState("");
  const [isSaved, setIsSaved] = useState(true);
  const [slideFilter, setSlideFilter] = useState<SlideFilter>("all");
  const [showAddLang, setShowAddLang] = useState(false);
  const [showRenderMenu, setShowRenderMenu] = useState(false);
  const [showDownloadMenu, setShowDownloadMenu] = useState(false);
  const [selectedVoiceId, setSelectedVoiceId] = useState<string | null>(null);
  const [activeRenderJob, setActiveRenderJob] = useState<{
    jobId: string;
    lang: string;
    status: string;
    progress: number;
    startedAt: Date;
  } | null>(null);
  const [activeTranslationJob, setActiveTranslationJob] = useState<{
    taskId: string;
    targetLang: string;
    slideCount: number;
    status: string;
    startedAt: Date;
  } | null>(null);
  const [slideMenuId, setSlideMenuId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Queries
  const { data: project, isLoading: projectLoading } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
    enabled: !!projectId,
  });

  const { data: versions } = useQuery({
    queryKey: ["versions", projectId],
    queryFn: () => api.getVersions(projectId),
    enabled: !!project,
  });

  const currentVersion = versions?.[0];

  const { data: slides, refetch: refetchSlides } = useQuery({
    queryKey: ["slides", projectId, currentVersion?.id],
    queryFn: () => api.getSlides(projectId, currentVersion!.id),
    enabled: !!currentVersion?.id && currentVersion.status === "ready",
  });

  const { data: selectedSlide } = useQuery({
    queryKey: ["slide", selectedSlideId],
    queryFn: () => api.getSlide(selectedSlideId!),
    enabled: !!selectedSlideId,
  });

  // Exports query
  const { data: exports, refetch: refetchExports } = useQuery({
    queryKey: ["exports", projectId, currentVersion?.id],
    queryFn: () => api.getExports(projectId, currentVersion!.id),
    enabled: !!currentVersion?.id,
    // Override global staleTime (60s). If render finishes while user is on another page,
    // we want fresh exports immediately upon returning.
    refetchOnMount: "always",
  });

  // Voices query
  const { data: voicesData } = useQuery({
    queryKey: ["voices"],
    queryFn: () => api.getVoices(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Audio settings query
  const { data: audioSettings } = useQuery({
    queryKey: ["audioSettings", projectId],
    queryFn: () => api.getAudioSettings(projectId),
    enabled: !!projectId,
  });

  // Poll render job status
  useEffect(() => {
    if (!activeRenderJob) return;
    
    const pollInterval = setInterval(async () => {
      try {
        const job = await api.getJobStatus(activeRenderJob.jobId);
        
        if (job.status === "done") {
          setActiveRenderJob(null);
          toast.success(`Video rendered successfully!`);
          refetchExports();
        } else if (job.status === "failed") {
          setActiveRenderJob(null);
          toast.error(`Render failed: ${job.error_message || "Unknown error"}`);
        } else {
          setActiveRenderJob(prev => prev ? {
            ...prev,
            status: job.status,
            progress: job.progress_pct,
          } : null);
        }
      } catch (e) {
        console.error("Error polling job status:", e);
      }
    }, 2000);
    
    return () => clearInterval(pollInterval);
  }, [activeRenderJob?.jobId]);

  // Poll translation job status
  useEffect(() => {
    if (!activeTranslationJob) return;
    
    const pollInterval = setInterval(async () => {
      try {
        const task = await api.getTaskStatus(activeTranslationJob.taskId);
        
        if (task.ready) {
          setActiveTranslationJob(null);
          if (task.status === "SUCCESS") {
            toast.success(`Translation complete! ${task.result?.translated_count || 0} slides translated.`);
            // Refresh slide data
            queryClient.invalidateQueries({ queryKey: ["slide", selectedSlideId] });
            refreshSlidesStatus();
          } else if (task.status === "FAILURE") {
            toast.error(`Translation failed: ${task.error || "Unknown error"}`);
          }
        } else {
          setActiveTranslationJob(prev => prev ? {
            ...prev,
            status: task.status,
          } : null);
        }
      } catch (e) {
        console.error("Error polling translation status:", e);
      }
    }, 1500);
    
    return () => clearInterval(pollInterval);
  }, [activeTranslationJob?.taskId]);

  // Initialize
  useEffect(() => {
    if (slides?.length && !selectedSlideId) {
      setSelectedSlideId(slides[0].id);
    }
  }, [slides, selectedSlideId]);

  useEffect(() => {
    if (project) {
      setSelectedLang(project.base_language);
    }
  }, [project]);

  useEffect(() => {
    if (selectedSlide) {
      const script = selectedSlide.scripts.find((s) => s.lang === selectedLang);
      setScriptText(script?.text || "");
      setIsSaved(true);
    }
  }, [selectedSlide, selectedLang]);

  // Initialize voice from audio settings
  useEffect(() => {
    if (audioSettings?.voice_id) {
      setSelectedVoiceId(audioSettings.voice_id);
    }
  }, [audioSettings]);

  // Restore active render job on page load (if user navigated away during render)
  useEffect(() => {
    if (!projectId || activeRenderJob) return;
    
    const checkActiveJobs = async () => {
      try {
        const jobs = await api.getProjectJobs(projectId);
        // Find the most recent running or queued render job
        const activeJob = jobs.find(
          (j) => j.status === "running" || j.status === "queued"
        );
        
        if (activeJob) {
          setActiveRenderJob({
            jobId: activeJob.id,
            lang: activeJob.lang,
            status: activeJob.status,
            progress: activeJob.progress_pct || 0,
            startedAt: activeJob.started_at ? new Date(activeJob.started_at) : new Date(),
          });
          toast.info(`Resuming render tracking for ${getLanguageName(activeJob.lang)}...`);
        }
      } catch (e) {
        console.error("Error checking active jobs:", e);
      }
    };
    
    checkActiveJobs();
  }, [projectId]);

  const availableLanguages = selectedSlide?.scripts.map((s) => s.lang) || [project?.base_language || "en"];

  // Mutations
  const uploadMutation = useMutation({
    mutationFn: (file: File) => api.uploadMedia(projectId, file),
    onSuccess: async (data) => {
      toast.success("File uploaded! Converting...");
      const { task_id } = await api.convertPPTX(projectId, data.version_id);
      pollConversionStatus(data.version_id, task_id);
    },
    onError: (error: any) => {
      const detail = error?.response?.data?.detail;
      toast.error(detail || "Upload failed");
    },
  });

  const pollConversionStatus = async (versionId: string, taskId?: string) => {
    const check = async () => {
      const versions = await api.getVersions(projectId);
      const version = versions.find((v) => v.id === versionId);
      if (version?.status === "ready") {
        toast.success("Slides ready!");
        // Invalidate versions first, then slides with correct version ID
        await queryClient.invalidateQueries({ queryKey: ["versions", projectId] });
        await queryClient.invalidateQueries({ queryKey: ["slides", projectId, versionId] });
        // Also refetch to ensure UI updates immediately
        await queryClient.refetchQueries({ queryKey: ["versions", projectId] });
      } else if (version?.status === "failed") {
        // Try to show a more specific error (e.g. unsupported aspect ratio)
        if (taskId) {
          try {
            const task = await api.getTaskStatus(taskId);
            const message =
              task?.result?.message ||
              task?.error ||
              "Conversion failed";
            toast.error(message);
          } catch {
            toast.error("Conversion failed");
          }
        } else {
          toast.error("Conversion failed");
        }
      } else {
        setTimeout(check, 2000);
      }
    };
    check();
  };

  const updateScriptMutation = useMutation({
    mutationFn: ({ slideId, lang, text }: { slideId: string; lang: string; text: string }) =>
      api.updateScript(slideId, lang, text),
    onSuccess: () => {
      setIsSaved(true);
      queryClient.invalidateQueries({ queryKey: ["slide", selectedSlideId] });
    },
  });

  // Track pending save for cleanup
  const pendingSaveRef = useRef<{ slideId: string; lang: string; text: string } | null>(null);

  // Save pending changes immediately (used when switching slides/languages)
  const flushPendingSave = useCallback(() => {
    if (pendingSaveRef.current) {
      const { slideId, lang, text } = pendingSaveRef.current;
      api.updateScript(slideId, lang, text).catch(console.error);
      pendingSaveRef.current = null;
      setIsSaved(true);
    }
  }, []);

  // Save before switching slides
  useEffect(() => {
    // When selectedSlideId changes, flush any pending save for the previous slide
    return () => {
      flushPendingSave();
    };
  }, [selectedSlideId, flushPendingSave]);

  // Save before switching languages
  useEffect(() => {
    return () => {
      flushPendingSave();
    };
  }, [selectedLang, flushPendingSave]);

  // Autosave with debounce
  useEffect(() => {
    if (!selectedSlideId) return;

    const script = selectedSlide?.scripts.find((s) => s.lang === selectedLang);
    if (script?.text === scriptText) {
      pendingSaveRef.current = null;
      return;
    }

    setIsSaved(false);
    // Track pending save so it can be flushed if user switches slides
    pendingSaveRef.current = { slideId: selectedSlideId, lang: selectedLang, text: scriptText };

    const timer = setTimeout(() => {
      updateScriptMutation.mutate({
        slideId: selectedSlideId,
        lang: selectedLang,
        text: scriptText,
      });
      pendingSaveRef.current = null;
    }, 1000); // Reduced to 1 second for better UX

    return () => clearTimeout(timer);
  }, [scriptText, selectedSlideId, selectedLang]);

  const addLanguageMutation = useMutation({
    mutationFn: (lang: string) => api.addLanguage(projectId, currentVersion!.id, lang),
    onSuccess: (_, lang) => {
      toast.success(`${getLanguageName(lang)} added!`);
      queryClient.invalidateQueries({ queryKey: ["slide", selectedSlideId] });
      setShowAddLang(false);
      setSelectedLang(lang);
    },
  });

  const removeLanguageMutation = useMutation({
    mutationFn: (lang: string) => api.removeLanguage(projectId, currentVersion!.id, lang),
    onSuccess: (_, lang) => {
      toast.success(`${getLanguageName(lang)} removed`);
      queryClient.invalidateQueries({ queryKey: ["slide", selectedSlideId] });
      if (selectedLang === lang) {
        setSelectedLang(project?.base_language || "en");
      }
    },
    onError: (error: any) => {
      const detail = error?.response?.data?.detail;
      toast.error(detail || "Failed to remove language");
    },
  });

  const handleRemoveLanguage = (lang: string) => {
    const baseLang = project?.base_language || "en";
    if (lang === baseLang) {
      toast.error("Base language cannot be removed");
      return;
    }
    const ok = window.confirm(
      `Remove ${getLanguageName(lang)} (${lang.toUpperCase()}) from this project?\n\nThis will delete scripts and generated audio for this language.`
    );
    if (!ok) return;
    removeLanguageMutation.mutate(lang);
  };

  const translateMutation = useMutation({
    mutationFn: () => api.translateAll(projectId, currentVersion!.id, selectedLang),
    onSuccess: (data) => {
      setActiveTranslationJob({
        taskId: data.task_id,
        targetLang: selectedLang,
        slideCount: data.slide_count,
        status: "PENDING",
        startedAt: new Date(),
      });
      toast.success(`Translating to ${getLanguageName(selectedLang)}...`);
    },
    onError: () => {
      toast.error("Failed to start translation");
    },
  });

  const generateTTSMutation = useMutation({
    mutationFn: () => api.generateAllTTS(projectId, currentVersion!.id, selectedLang, selectedVoiceId || undefined),
    onSuccess: () => {
      toast.success("Generating audio for all slides...");
      // Refresh status after a delay
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["slide"] });
        refreshSlidesStatus();
      }, 3000);
    },
  });

  const generateSlideTTSMutation = useMutation({
    mutationFn: (slideId: string) => api.generateSlideTTS(slideId, selectedLang, selectedVoiceId || undefined),
    onSuccess: () => {
      toast.success("Generating audio for this slide...");
      queryClient.invalidateQueries({ queryKey: ["slide", selectedSlideId] });
      // Refresh status after a delay
      setTimeout(() => {
        refreshSlidesStatus();
      }, 2000);
    },
  });

  const updateVoiceMutation = useMutation({
    mutationFn: (voiceId: string) => api.updateAudioSettings(projectId, { voice_id: voiceId }),
    onSuccess: () => {
      toast.success("Voice updated");
      queryClient.invalidateQueries({ queryKey: ["audioSettings", projectId] });
    },
  });

  const deleteSlideMutation = useMutation({
    mutationFn: (slideId: string) => api.deleteSlide(slideId),
    onSuccess: (data) => {
      toast.success(`Slide ${data.deleted_index} deleted`);
      // If we deleted the selected slide, select another
      if (selectedSlideId && data.deleted_id === selectedSlideId) {
        setSelectedSlideId(null);
      }
      // Refresh slides list
      queryClient.invalidateQueries({ queryKey: ["slides", projectId, currentVersion?.id] });
      refreshSlidesStatus();
      setSlideMenuId(null);
    },
    onError: () => {
      toast.error("Failed to delete slide");
    },
  });

  const addSlideMutation = useMutation({
    mutationFn: (file: File) => api.addSlide(projectId, currentVersion!.id, file),
    onSuccess: (data) => {
      toast.success(`Slide added at position ${data.slide_index}`);
      queryClient.invalidateQueries({ queryKey: ["slides", projectId, currentVersion?.id] });
      refreshSlidesStatus();
      // Select the new slide
      setSelectedSlideId(data.id);
    },
    onError: () => {
      toast.error("Failed to add slide");
    },
  });

  const reorderSlidesMutation = useMutation({
    mutationFn: (slideIds: string[]) => api.reorderSlides(projectId, currentVersion!.id, slideIds),
    onSuccess: () => {
      toast.success("Slides reordered");
      queryClient.invalidateQueries({ queryKey: ["slides", projectId, currentVersion?.id] });
    },
    onError: () => {
      toast.error("Failed to reorder slides");
    },
  });

  const renderVideoMutation = useMutation({
    mutationFn: () => api.renderVideo(projectId, currentVersion!.id, selectedLang),
    onSuccess: (data) => {
      setActiveRenderJob({
        jobId: data.job_id,
        lang: selectedLang,
        status: "running",
        progress: 0,
        startedAt: new Date(),
      });
      toast.success(`Rendering ${getLanguageName(selectedLang)} video...`);
      setShowRenderMenu(false);
    },
    onError: () => {
      toast.error("Failed to start render");
    },
  });

  // Dropzone
  const onDrop = useCallback((files: File[]) => {
    if (files[0]) uploadMutation.mutate(files[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
      "application/vnd.ms-powerpoint": [".ppt"],
      "application/pdf": [".pdf"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/png": [".png"],
      "image/webp": [".webp"],
    },
    maxFiles: 1,
    noClick: !!slides?.length,
  });

  // Slide status cache - fetch all slides status for current language
  const [slidesStatus, setSlidesStatus] = useState<Record<string, { hasScript: boolean; hasAudio: boolean }>>({});
  
  const refreshSlidesStatus = useCallback(async () => {
    if (!slides?.length) return;

    const statuses: Record<string, { hasScript: boolean; hasAudio: boolean }> = {};

    // Fetch each slide's details (could be optimized with batch API)
    for (const slide of slides) {
      try {
        const details = await api.getSlide(slide.id);
        const script = details.scripts.find((s) => s.lang === selectedLang);
        const audio = details.audio_files.find((a) => a.lang === selectedLang);
        statuses[slide.id] = {
          hasScript: !!script?.text && script.text.length > 0,
          hasAudio: !!audio,
        };
      } catch {
        statuses[slide.id] = { hasScript: false, hasAudio: false };
      }
    }

    setSlidesStatus(statuses);
  }, [slides, selectedLang]);

  // Fetch status for all slides when version/language changes
  useEffect(() => {
    refreshSlidesStatus();
  }, [refreshSlidesStatus]);
  
  // Helpers
  const getSlideStatus = (slideId: string): SlideStatus => {
    const status = slidesStatus[slideId];
    if (!status) return "missing";
    if (status.hasAudio) return "ready";
    if (status.hasScript) return "script-only";
    return "missing";
  };
  
  // Audio status summary
  const audioStats = {
    total: slides?.length || 0,
    withAudio: Object.values(slidesStatus).filter(s => s.hasAudio).length,
    withScript: Object.values(slidesStatus).filter(s => s.hasScript).length,
    missing: Object.values(slidesStatus).filter(s => !s.hasScript).length,
  };

  const estimatedTime = estimateDuration(scriptText);
  const isTooLong = estimatedTime > 30;

  // DnD sensors
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  // Handle drag end for reordering
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    
    if (over && active.id !== over.id && slides) {
      const oldIndex = slides.findIndex((s: Slide) => s.id === active.id);
      const newIndex = slides.findIndex((s: Slide) => s.id === over.id);
      
      if (oldIndex !== -1 && newIndex !== -1) {
        const newOrder = arrayMove(slides, oldIndex, newIndex);
        // Optimistic UI update so the list doesn't "snap back" while we save.
        queryClient.setQueryData<Slide[]>(
          ["slides", projectId, currentVersion?.id],
          newOrder
        );
        reorderSlidesMutation.mutate(newOrder.map((s: Slide) => s.id), {
          onError: () => {
            // Revert on failure
            queryClient.setQueryData<Slide[]>(
              ["slides", projectId, currentVersion?.id],
              slides
            );
          },
        });
      }
    }
  };

  // Dropzone for adding new slides (images)
  const onDropSlideImage = useCallback((files: File[]) => {
    if (files[0] && currentVersion) {
      addSlideMutation.mutate(files[0]);
    }
  }, [currentVersion]);

  const { getRootProps: getSlideDropRootProps, getInputProps: getSlideDropInputProps, isDragActive: isSlideDropActive } = useDropzone({
    onDrop: onDropSlideImage,
    accept: {
      "image/png": [".png"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/webp": [".webp"],
    },
    maxFiles: 1,
    noClick: false,
  });

  if (projectLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Top Bar */}
      <header className="shrink-0 h-14 bg-surface border-b border-border px-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="p-2 -ml-2 rounded-sm hover:bg-muted transition-colors"
            title="Back to Projects"
            aria-label="Back to Projects"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div className="flex items-center gap-2">
            <span className="font-medium text-[14px]">{project?.name}</span>
            <Badge variant="secondary">v{currentVersion?.version_number || 1}</Badge>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Language Selector */}
          <Select
            value={selectedLang}
            onChange={(e) => setSelectedLang(e.target.value)}
            className="w-32"
          >
            {availableLanguages.map((lang) => (
              <option key={lang} value={lang}>
                {getLanguageName(lang)}
              </option>
            ))}
          </Select>

          {/* Status */}
          <Badge variant={currentVersion?.status === "ready" ? "success" : "warning"}>
            {currentVersion?.status === "ready" ? "Ready" : "Processing"}
          </Badge>

          {/* Render Progress or Button */}
          {activeRenderJob ? (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-primary/10 border border-primary/30 rounded-lg">
              <Loader2 className="w-4 h-4 animate-spin text-primary" />
              <div className="text-[13px]">
                <span className="font-medium">Rendering {getLanguageName(activeRenderJob.lang)}...</span>
                <span className="text-muted-foreground ml-2">{activeRenderJob.progress}%</span>
              </div>
              <div className="w-20 h-1.5 bg-muted rounded-full overflow-hidden">
                <div 
                  className="h-full bg-primary transition-all duration-300" 
                  style={{ width: `${activeRenderJob.progress}%` }} 
                />
              </div>
              <button
                onClick={async () => {
                  try {
                    await api.cancelJob(activeRenderJob.jobId);
                    setActiveRenderJob(null);
                    toast.success("Render cancelled");
                  } catch (e) {
                    toast.error("Failed to cancel render");
                  }
                }}
                className="ml-1 p-1 rounded hover:bg-red-500/20 text-muted-foreground hover:text-red-500 transition-colors"
                title="Cancel render"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="relative">
              <Button
                onClick={() => setShowRenderMenu(!showRenderMenu)}
                title="Open render options (start video rendering)"
              >
                <Video className="w-4 h-4" />
                Render
                {audioStats.withAudio > 0 && audioStats.withAudio < audioStats.total && (
                  <span className="ml-1 text-[10px] text-amber-500">({audioStats.withAudio}/{audioStats.total})</span>
                )}
                <ChevronDown className="w-3 h-3" />
              </Button>
              {showRenderMenu && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setShowRenderMenu(false)} />
                  <div className="absolute right-0 mt-1 w-64 bg-surface border border-border rounded-lg shadow-dropdown z-50 py-1">
                    {/* Audio status info */}
                    {audioStats.withAudio < audioStats.total && (
                      <div className="px-3 py-2 text-[11px] text-muted-foreground border-b border-border bg-muted/30">
                        {audioStats.withAudio === 0 ? (
                          <span className="text-red-500 flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3" />
                            No audio generated yet
                          </span>
                        ) : (
                          <span className="flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3 text-amber-500" />
                            {audioStats.withAudio}/{audioStats.total} slides have audio.
                            <br />
                            Slides without audio will be skipped.
                          </span>
                        )}
                      </div>
                    )}
                    <button
                      onClick={() => renderVideoMutation.mutate()}
                      disabled={audioStats.withAudio === 0 || renderVideoMutation.isPending}
                      className="w-full px-3 py-2 text-left text-[13px] hover:bg-muted flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                      title={`Start rendering a video for ${getLanguageName(selectedLang)}`}
                    >
                      <Video className="w-4 h-4" />
                      Render {getLanguageName(selectedLang)}
                    </button>
                    <button
                      onClick={() => {
                        toast.info("Render all coming soon");
                      }}
                      className="w-full px-3 py-2 text-left text-[13px] hover:bg-muted flex items-center gap-2"
                      title="Start rendering videos for all languages (coming soon)"
                    >
                      <Languages className="w-4 h-4" />
                      Render All Languages
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Download Dropdown */}
          <div className="relative">
            <Button 
              variant="outline" 
              onClick={() => setShowDownloadMenu(!showDownloadMenu)}
              disabled={!exports?.exports?.length}
              title="Show available exports for download"
            >
              <Download className="w-4 h-4" />
              Download
              {exports?.exports?.length > 0 && (
                <Badge variant="success" className="ml-1 text-[10px] px-1.5 py-0">
                  {exports.exports.length}
                </Badge>
              )}
              <ChevronDown className="w-3 h-3" />
            </Button>
                {showDownloadMenu && exports?.exports?.length > 0 && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setShowDownloadMenu(false)} />
                    <div className="absolute right-0 mt-1 w-72 bg-surface border border-border rounded-lg shadow-dropdown z-50 py-1">
                      <div className="px-3 py-2 text-[11px] text-muted-foreground border-b border-border">
                        Available exports
                      </div>
                      {exports.exports.map((exp: { lang: string; files: { type: string; filename: string; size_mb?: number; size_kb?: number }[]; created_at?: string }) => (
                        <div key={exp.lang} className="px-3 py-2 border-b border-border last:border-0">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-medium text-[13px]">{getLanguageName(exp.lang)}</span>
                            {exp.created_at && (
                              <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                {formatRelativeTime(exp.created_at)}
                              </span>
                            )}
                          </div>
                          <div className="space-y-1">
                            {exp.files.map((file) => (
                              <a
                                key={file.filename}
                                href={api.getDownloadUrl(projectId, currentVersion!.id, exp.lang, file.filename)}
                                download
                                className="flex items-center gap-2 text-[12px] text-primary hover:underline"
                              >
                                {file.type === "video" ? (
                                  <FileVideo className="w-3.5 h-3.5" />
                                ) : (
                                  <FileText className="w-3.5 h-3.5" />
                                )}
                                {file.filename}
                                <span className="text-muted-foreground">
                                  ({file.size_mb ? `${file.size_mb} MB` : `${file.size_kb} KB`})
                                </span>
                              </a>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
          </div>

          <Link href={`/projects/${projectId}/glossary`}>
            <Button
              variant="ghost"
              size="icon"
              title="Translation Glossary"
              aria-label="Translation Glossary"
            >
              <BookText className="w-4 h-4" />
            </Button>
          </Link>

          <Link href={`/projects/${projectId}/settings`}>
            <Button
              variant="ghost"
              size="icon"
              title="Audio & Render Settings"
              aria-label="Audio & Render Settings"
            >
              <Music4 className="w-4 h-4" />
            </Button>
          </Link>
        </div>
      </header>

      {/* Main Content - 3 Columns */}
      <div className="flex-1 flex overflow-hidden" {...getRootProps()}>
        <input {...getInputProps()} />

        {/* Column A: Slides List (240px) */}
        <aside className="w-60 border-r border-border bg-surface flex flex-col">
          {/* Filter */}
          <div className="p-3 border-b border-border">
            <Select
              value={slideFilter}
              onChange={(e) => setSlideFilter(e.target.value as SlideFilter)}
              className="text-[13px]"
            >
              <option value="all">All Slides</option>
              <option value="needs-audio">Needs Audio</option>
              <option value="ready">Ready</option>
            </Select>
          </div>

          {/* Slides */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-2">
            {!slides?.length ? (
              <div
                className={cn(
                  "border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors",
                  isDragActive ? "border-primary bg-primary/5" : "border-border hover:border-primary/40"
                )}
              >
                <Upload className="w-6 h-6 mx-auto mb-2 text-muted-foreground" />
                <p className="text-[13px] font-medium">Upload file</p>
                <p className="text-label text-muted-foreground mt-0.5">
                  PPTX, PDF, or image
                </p>
              </div>
            ) : (
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handleDragEnd}
              >
                <SortableContext
                  items={slides.map((s) => s.id)}
                  strategy={verticalListSortingStrategy}
                >
                  {slides.map((slide, index) => (
                    <SortableSlideThumb
                      key={slide.id}
                      slide={slide}
                      index={index}
                      isSelected={selectedSlideId === slide.id}
                      onClick={() => setSelectedSlideId(slide.id)}
                      status={getSlideStatus(slide.id)}
                      showMenu={slideMenuId === slide.id}
                      onMenuToggle={() => setSlideMenuId(slideMenuId === slide.id ? null : slide.id)}
                      onDelete={() => {
                        if (confirm(`Delete slide ${index + 1}? This action cannot be undone.`)) {
                          deleteSlideMutation.mutate(slide.id);
                        }
                      }}
                      isDeleting={deleteSlideMutation.isPending && slideMenuId === slide.id}
                    />
                  ))}
                </SortableContext>
              </DndContext>
            )}
          </div>

          {/* Add Slide Button */}
          {slides?.length ? (
            <div className="p-3 border-t border-border">
              <div
                {...getSlideDropRootProps()}
                className={cn(
                  "border-2 border-dashed rounded-lg p-3 text-center cursor-pointer transition-colors",
                  isSlideDropActive ? "border-primary bg-primary/5" : "border-border hover:border-primary/40",
                  addSlideMutation.isPending && "opacity-50 pointer-events-none"
                )}
              >
                <input {...getSlideDropInputProps()} />
                {addSlideMutation.isPending ? (
                  <Loader2 className="w-5 h-5 mx-auto animate-spin text-muted-foreground" />
                ) : (
                  <>
                    <ImagePlus className="w-5 h-5 mx-auto mb-1 text-muted-foreground" />
                    <p className="text-[12px] text-muted-foreground">
                      Add slide (PNG, JPG)
                    </p>
                  </>
                )}
              </div>
            </div>
          ) : null}
        </aside>

        {/* Column B: Slide Preview */}
        <main className="flex-1 flex flex-col bg-background/50 overflow-hidden">
          {selectedSlide ? (
            <>
              {/* Preview */}
              <div className="flex-1 flex items-center justify-center p-6">
                <div className="aspect-video w-full max-w-4xl bg-white rounded-lg shadow-card border border-border overflow-hidden">
                  <img
                    src={api.getSlideImageUrl(selectedSlide.image_url)}
                    alt={`Slide ${slides?.findIndex((s) => s.id === selectedSlideId)! + 1}`}
                    className="w-full h-full object-contain bg-white"
                    loading="eager"
                  />
                </div>
              </div>

              {/* Metrics */}
              <div className="shrink-0 px-6 pb-4 flex items-center gap-4">
                <div className="flex items-center gap-2 text-[13px]">
                  <span className="text-muted-foreground">Estimated:</span>
                  <span className="font-medium">{formatDuration(estimatedTime + 6)}</span>
                </div>
                {isTooLong && (
                  <Badge variant="warning" className="gap-1">
                    <AlertTriangle className="w-3 h-3" />
                    Too long (&gt;30s)
                  </Badge>
                )}
                {!selectedSlide.audio_files.find((a) => a.lang === selectedLang) && scriptText && (
                  <Badge variant="error" className="gap-1">
                    No audio
                  </Badge>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Upload className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
                <p className="font-medium">Upload PPTX, PDF or image to start</p>
              </div>
            </div>
          )}
        </main>

        {/* Column C: Script Editor (420px) */}
        {selectedSlide && (
          <aside className="w-[420px] border-l border-border bg-surface flex flex-col">
            {/* Language Tabs */}
            <div className="shrink-0 p-4 pb-0">
              <div className="flex items-center gap-1 flex-wrap">
                {availableLanguages.map((lang) => {
                  const isSelected = selectedLang === lang;
                  const isBase = lang === (project?.base_language || "en");
                  return (
                    <div
                      key={lang}
                      className={cn(
                        "inline-flex items-stretch rounded-md overflow-hidden",
                        isSelected
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground hover:text-foreground"
                      )}
                    >
                      <button
                        onClick={() => setSelectedLang(lang)}
                        title={`Edit script in ${getLanguageName(lang)}`}
                        className="px-3 py-1.5 text-[13px] font-medium transition-colors"
                        type="button"
                      >
                        {lang.toUpperCase()}
                      </button>
                      {!isBase && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRemoveLanguage(lang);
                          }}
                          disabled={removeLanguageMutation.isPending}
                          title={`Remove ${getLanguageName(lang)} from this project`}
                          aria-label={`Remove language ${lang.toUpperCase()}`}
                          className={cn(
                            "px-2 flex items-center justify-center transition-colors disabled:opacity-50",
                            isSelected ? "hover:bg-primary/80" : "hover:bg-muted/80"
                          )}
                        >
                          <X className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  );
                })}
                <button
                  onClick={() => setShowAddLang(true)}
                  title="Add a new language to this project"
                  className="px-3 py-1.5 rounded-md text-[13px] border border-dashed border-border hover:border-primary text-muted-foreground hover:text-foreground transition-colors"
                >
                  + Add
                </button>

                {/* Saved indicator */}
                <div className="ml-auto">
                  {isSaved ? (
                    <span className="saved-indicator text-label text-muted-foreground flex items-center gap-1">
                      <Check className="w-3 h-3" />
                      Saved
                    </span>
                  ) : (
                    <span className="text-label text-muted-foreground">Saving...</span>
                  )}
                </div>
              </div>

              {/* Voice selector */}
              <div className="flex items-center gap-2 mt-3">
                <span className="text-label text-muted-foreground">Voice:</span>
                <Select 
                  value={selectedVoiceId || ""}
                  onChange={(e) => {
                    const voiceId = e.target.value;
                    setSelectedVoiceId(voiceId);
                    updateVoiceMutation.mutate(voiceId);
                  }}
                  className="flex-1 h-8 text-[13px]"
                >
                  <option value="">Select voice...</option>
                  {voicesData?.voices?.map((voice) => (
                    <option key={voice.voice_id} value={voice.voice_id}>
                      {voice.name} ({voice.labels.gender === "female" ? "♀" : voice.labels.gender === "male" ? "♂" : "●"})
                    </option>
                  ))}
                </Select>
                {selectedVoiceId && voicesData?.voices?.find(v => v.voice_id === selectedVoiceId)?.preview_url && (
                  <button
                    onClick={() => {
                      const voice = voicesData?.voices?.find(v => v.voice_id === selectedVoiceId);
                      if (voice?.preview_url) {
                        const audio = new Audio(voice.preview_url);
                        audio.play();
                      }
                    }}
                    className="p-1.5 rounded hover:bg-muted transition-colors"
                    title="Preview voice"
                    aria-label="Preview voice"
                  >
                    <Play className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>

            {/* Script Textarea */}
            <div className="flex-1 p-4 flex flex-col">
              <Textarea
                value={scriptText}
                onChange={(e) => setScriptText(e.target.value)}
                placeholder="Enter script for this slide..."
                className="flex-1 min-h-0"
              />
              
              <div className="flex items-center justify-between mt-2 text-label text-muted-foreground">
                <span>{scriptText.length} characters</span>
                <span>~{formatDuration(estimatedTime)} voice time</span>
              </div>
            </div>

            {/* Audio Status Summary */}
            {slides && slides.length > 0 && (
              <div className="shrink-0 px-4 py-2 bg-muted/50 border-t border-border">
                <div className="flex items-center justify-between text-[12px]">
                  <div className="flex items-center gap-3">
                    <span className="text-muted-foreground">Audio status:</span>
                    <span className="flex items-center gap-1">
                      <div className="w-2 h-2 rounded-full bg-emerald-500" />
                      {audioStats.withAudio}/{audioStats.total} ready
                    </span>
                    {audioStats.withScript - audioStats.withAudio > 0 && (
                      <span className="flex items-center gap-1 text-amber-600">
                        <div className="w-2 h-2 rounded-full bg-amber-500" />
                        {audioStats.withScript - audioStats.withAudio} need audio
                      </span>
                    )}
                    {audioStats.missing > 0 && (
                      <span className="flex items-center gap-1 text-red-600">
                        <div className="w-2 h-2 rounded-full bg-red-500" />
                        {audioStats.missing} no script
                      </span>
                    )}
                  </div>
                  {audioStats.withAudio < audioStats.total && audioStats.withAudio > 0 && (
                    <span className="text-muted-foreground">
                      ✓ OK to render with partial audio
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Translation Progress */}
            {activeTranslationJob && (
              <div className="shrink-0 px-4 py-3 bg-primary/5 border-t border-primary/20">
                <div className="flex items-center gap-3">
                  <Loader2 className="w-4 h-4 animate-spin text-primary" />
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[13px] font-medium">
                        Translating to {getLanguageName(activeTranslationJob.targetLang)}...
                      </span>
                      <span className="text-[11px] text-muted-foreground">
                        {activeTranslationJob.slideCount} slides
                      </span>
                    </div>
                    <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-primary animate-pulse" 
                        style={{ width: activeTranslationJob.status === "STARTED" ? "60%" : "30%" }} 
                      />
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      // Translation tasks don't have a cancel endpoint yet, but we can clear the UI
                      setActiveTranslationJob(null);
                      toast.info("Translation tracking cancelled (task may still complete in background)");
                    }}
                    className="p-1 rounded hover:bg-red-500/20 text-muted-foreground hover:text-red-500 transition-colors"
                    title="Stop tracking translation"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="shrink-0 p-4 pt-3 flex flex-wrap gap-2 border-t border-border">
              {selectedLang !== project?.base_language && !activeTranslationJob && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => translateMutation.mutate()}
                  disabled={translateMutation.isPending}
                  title={`Translate all slides into ${getLanguageName(selectedLang)}`}
                >
                  <Wand2 className="w-3.5 h-3.5" />
                  Translate All
                </Button>
              )}
              
              {/* Single slide TTS */}
              <Button
                variant="secondary"
                size="sm"
                onClick={() => generateSlideTTSMutation.mutate(selectedSlideId!)}
                disabled={generateSlideTTSMutation.isPending || !scriptText}
                title="Generate audio for this slide only"
              >
                <Mic className="w-3.5 h-3.5" />
                This Slide
              </Button>
              
              {/* All slides TTS */}
              <Button
                variant="secondary"
                size="sm"
                onClick={() => generateTTSMutation.mutate()}
                disabled={generateTTSMutation.isPending}
                title="Generate audio for all slides"
              >
                <Mic className="w-3.5 h-3.5" />
                All Slides
              </Button>
              
              {selectedSlide.audio_files.find((a) => a.lang === selectedLang) && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    const audioFile = selectedSlide.audio_files.find((a) => a.lang === selectedLang);
                    if (audioFile) {
                      const audioUrl = api.getSlideAudioUrl(audioFile.audio_url);
                      if (audioUrl) {
                        const audio = new Audio(audioUrl);
                        audio.play().catch(() => {
                          toast.error("Failed to play audio");
                        });
                      } else {
                        toast.error("Audio URL is invalid");
                      }
                    }
                  }}
                  title="Preview generated audio for this slide"
                >
                  <Play className="w-3.5 h-3.5" />
                  Preview
                </Button>
              )}
            </div>
          </aside>
        )}
      </div>

      {/* Add Language Modal */}
      {showAddLang && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowAddLang(false)} />
          <div className="relative bg-surface rounded-lg border border-border shadow-dropdown w-full max-w-sm p-5 animate-slide-up">
            <h3 className="text-section font-medium mb-4">Add Language</h3>
            <div className="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto">
              {LANGUAGES.filter((l) => !availableLanguages.includes(l.code)).map((lang) => (
                <button
                  key={lang.code}
                  onClick={() => addLanguageMutation.mutate(lang.code)}
                  disabled={addLanguageMutation.isPending}
                  title={`Add ${lang.name} (${lang.code.toUpperCase()}) to this project`}
                  className="px-3 py-2 rounded-md border border-border hover:bg-muted hover:border-primary/40 transition-colors text-[13px] text-left"
                >
                  {lang.name}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

type SlideStatus = "ready" | "script-only" | "missing";

interface SlideWithStatus extends Slide {
  hasScript?: boolean;
  hasAudio?: boolean;
}

interface SlideThumbProps {
  slide: SlideWithStatus;
  index: number;
  isSelected: boolean;
  onClick: () => void;
  status: SlideStatus;
  showMenu: boolean;
  onMenuToggle: () => void;
  onDelete: () => void;
  isDeleting: boolean;
}

function SortableSlideThumb(props: SlideThumbProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: props.slide.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 50 : undefined,
  };

  return (
    <div ref={setNodeRef} style={style}>
      <SlideThumb {...props} dragHandleProps={{ ...attributes, ...listeners }} isDragging={isDragging} />
    </div>
  );
}

function SlideThumb({
  slide,
  index,
  isSelected,
  onClick,
  status,
  showMenu,
  onMenuToggle,
  onDelete,
  isDeleting,
  dragHandleProps,
  isDragging,
}: SlideThumbProps & {
  dragHandleProps?: Record<string, any>;
  isDragging?: boolean;
}) {
  return (
    <div className="relative">
      <div
        className={cn(
          "slide-thumb w-full rounded-lg overflow-hidden border-2 text-left group",
          isSelected ? "border-primary active" : "border-transparent",
          isDragging && "shadow-lg"
        )}
      >
        <div className="aspect-video bg-white flex items-center justify-center relative border border-border">
          <button
            type="button"
            onClick={onClick}
            title={`Select slide ${index + 1}`}
            className="absolute inset-0 z-10"
          />
          <img
            src={api.getSlideImageUrl(slide.image_url)}
            alt={`Slide ${index + 1}`}
            className="w-full h-full object-contain bg-white pointer-events-none"
            loading="lazy"
          />
          
          {/* Slide number */}
          <div className="absolute bottom-1 left-1.5 text-[10px] font-medium text-white bg-black/60 px-1.5 py-0.5 rounded z-20">
            {index + 1}
          </div>
          
          {/* Status indicator */}
          <div className="absolute top-1.5 right-1.5 z-20">
            {status === "ready" && (
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" title="Audio ready" />
            )}
            {status === "script-only" && (
              <div className="w-2.5 h-2.5 rounded-full bg-amber-500" title="Script only - no audio" />
            )}
            {status === "missing" && (
              <div className="w-2.5 h-2.5 rounded-full bg-red-500" title="Missing script" />
            )}
          </div>

          {/* Drag handle */}
          {dragHandleProps && (
            <button
              type="button"
              className={cn(
                "absolute top-1.5 left-1.5 p-1 rounded bg-black/50 text-white transition-opacity z-20 cursor-grab active:cursor-grabbing",
                "opacity-0 group-hover:opacity-100"
              )}
              {...dragHandleProps}
              title="Drag to reorder"
              aria-label="Drag to reorder"
            >
              <GripVertical className="w-3.5 h-3.5" />
            </button>
          )}

          {/* Menu button */}
          <button
            type="button"
            className={cn(
              "absolute top-1.5 left-8 p-1 rounded bg-black/50 text-white transition-opacity z-20",
              showMenu ? "opacity-100" : "opacity-0 group-hover:opacity-100"
            )}
            onClick={(e) => {
              e.stopPropagation();
              onMenuToggle();
            }}
            title="More slide actions"
            aria-label="More slide actions"
          >
            <MoreHorizontal className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Dropdown menu */}
      {showMenu && (
        <>
          <div className="fixed inset-0 z-40" onClick={onMenuToggle} />
          <div className="absolute left-0 top-full mt-1 w-36 bg-surface border border-border rounded-lg shadow-dropdown z-50 py-1">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              disabled={isDeleting}
              className="w-full px-3 py-2 text-left text-[13px] hover:bg-red-500/10 text-red-600 flex items-center gap-2 disabled:opacity-50"
            >
              {isDeleting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Trash2 className="w-3.5 h-3.5" />
              )}
              Delete Slide
            </button>
          </div>
        </>
      )}
    </div>
  );
}
