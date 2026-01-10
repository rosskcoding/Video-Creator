"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Music, Volume2, Sliders, Languages, Wand2, BookText, ChevronRight, Play, Pause, Loader2 } from "lucide-react";
import { api, AudioSettings } from "@/lib/api";
import { LANGUAGES, getLanguageName } from "@/lib/utils";
import { toast } from "sonner";
import Link from "next/link";
import { useDropzone } from "react-dropzone";
import {
  Button,
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Input,
  Select,
  Slider,
  Switch,
  Badge,
} from "@/components/ui";

export default function ProjectSettingsPage() {
  const params = useParams();
  const projectIdRaw = params?.id;
  const projectId =
    typeof projectIdRaw === "string"
      ? projectIdRaw
      : Array.isArray(projectIdRaw)
        ? projectIdRaw[0] ?? ""
        : "";
  const queryClient = useQueryClient();

  // Queries
  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
    enabled: Boolean(projectId),
  });

  const { data: audioSettings } = useQuery({
    queryKey: ["audioSettings", projectId],
    queryFn: () => api.getAudioSettings(projectId),
    enabled: Boolean(projectId),
  });

  const { data: translationRules } = useQuery({
    queryKey: ["translationRules", projectId],
    queryFn: () => api.getTranslationRules(projectId),
    enabled: Boolean(projectId),
  });

  // Convert dB gain to HTMLAudioElement.volume (0..1)
  const dbToHtmlAudioVolume = (db: number): number => {
    const linear = Math.pow(10, db / 20);
    return Math.max(0, Math.min(1, linear));
  };

  // Local state for settings
  const [localAudioSettings, setLocalAudioSettings] = useState<Partial<AudioSettings>>({});
  const [targetLanguages, setTargetLanguages] = useState<string[]>([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [baseLanguage, setBaseLanguage] = useState<string>("en");

  useEffect(() => {
    if (audioSettings) {
      setLocalAudioSettings(audioSettings);
    }
  }, [audioSettings]);

  // Apply Music Gain to preview immediately (no need to save)
  useEffect(() => {
    if (!audioRef.current) return;
    const musicGainDb = Number(localAudioSettings.music_gain_db ?? audioSettings?.music_gain_db ?? -22);
    audioRef.current.volume = dbToHtmlAudioVolume(musicGainDb);
  }, [localAudioSettings.music_gain_db, audioSettings?.music_gain_db]);

  useEffect(() => {
    if (project?.base_language) {
      setBaseLanguage(project.base_language);
    }
  }, [project?.base_language]);

  // Mutation to update project base language
  const updateBaseLanguageMutation = useMutation({
    mutationFn: (newLang: string) => api.updateProject(projectId, { base_language: newLang }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      toast.success("Base language updated!");
    },
    onError: () => {
      toast.error("Failed to update base language");
      // Reset to original
      if (project?.base_language) {
        setBaseLanguage(project.base_language);
      }
    },
  });

  const uploadMusicMutation = useMutation({
    mutationFn: (file: File) => api.uploadMusic(projectId, file),
    onMutate: () => {
      // Stop current preview when replacing the music.
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      setIsPlaying(false);
    },
    onSuccess: () => {
      toast.success("Music uploaded");
      queryClient.invalidateQueries({ queryKey: ["audioSettings", projectId] });
    },
    onError: (error: any) => {
      const detail = error?.response?.data?.detail;
      toast.error(detail || "Music upload failed");
    },
  });

  // Music drag-and-drop handler
  const onDropMusic = useCallback((acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith(".mp3")) {
        toast.error("Only MP3 files are supported");
        return;
      }
      uploadMusicMutation.mutate(file);
    }
  }, [uploadMusicMutation]);

  const {
    getRootProps: getMusicDropRootProps,
    getInputProps: getMusicDropInputProps,
    isDragActive: isMusicDragActive,
  } = useDropzone({
    onDrop: onDropMusic,
    accept: {
      "audio/mpeg": [".mp3"],
    },
    maxFiles: 1,
    noClick: false,
  });

  // Play/pause music preview
  const toggleMusicPlayback = () => {
    if (!audioSettings?.music_asset_id || !projectId) return;

    if (isPlaying) {
      audioRef.current?.pause();
      setIsPlaying(false);
    } else {
      const musicUrl = api.getMusicUrl(projectId);
      const musicGainDb = Number(localAudioSettings.music_gain_db ?? audioSettings?.music_gain_db ?? -22);
      if (!audioRef.current) {
        audioRef.current = new Audio(musicUrl);
        audioRef.current.volume = dbToHtmlAudioVolume(musicGainDb);
        audioRef.current.onended = () => setIsPlaying(false);
        audioRef.current.onerror = () => {
          toast.error("Failed to play music");
          setIsPlaying(false);
        };
      } else if (audioRef.current.src !== musicUrl) {
        // If URL changed (e.g. different project), refresh source.
        audioRef.current.src = musicUrl;
      }
      // Always re-apply current gain right before playback.
      audioRef.current.volume = dbToHtmlAudioVolume(musicGainDb);
      audioRef.current.play().catch(() => {
        toast.error("Failed to play music");
        setIsPlaying(false);
      });
      setIsPlaying(true);
    }
  };

  // Cleanup audio on unmount
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, []);

  // Mutations
  const updateAudioMutation = useMutation({
    mutationFn: (settings: Partial<AudioSettings>) =>
      api.updateAudioSettings(projectId, settings),
    onSuccess: () => {
      toast.success("Audio settings saved");
      queryClient.invalidateQueries({ queryKey: ["audioSettings", projectId] });
    },
  });

  const handleSaveAudio = () => {
    updateAudioMutation.mutate(localAudioSettings);
  };

  if (!projectId) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <p className="text-[13px] text-muted-foreground">Invalid project ID</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <header className="shrink-0 h-14 bg-surface border-b border-border px-6 flex items-center gap-4">
        <Link
          href={`/projects/${projectId}`}
          className="p-2 -ml-2 rounded-sm hover:bg-muted transition-colors"
          title="Back to Project"
          aria-label="Back to Project"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div>
          <h1 className="text-[15px] font-medium">{project?.name}</h1>
          <p className="text-label text-muted-foreground">Project Settings</p>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 overflow-auto p-6">
        <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-[340px_minmax(0,1fr)] gap-6">
          {/* Left: Instructions */}
          <aside className="lg:sticky lg:top-6 self-start">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BookText className="w-4 h-4 text-primary" />
                  Инструкция
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-[13px] text-muted-foreground">
                  Эти настройки применяются <span className="font-medium text-foreground">при следующем рендере</span>{" "}
                  (и пересборке аудио/субтитров). Уже готовые экспортированные файлы не меняются автоматически — нужно
                  запустить рендер заново.
                </p>

                <div className="space-y-3">
                  <div>
                    <p className="text-[13px] font-medium">Аудио</p>
                    <ul className="mt-2 space-y-1.5 text-[13px] text-muted-foreground">
                      <li>
                        <span className="font-medium text-foreground">Corporate Music</span> — загрузка MP3 трека фоновой
                        музыки. Используется только если включён <span className="font-medium text-foreground">Background Music</span>.
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Background Music</span> — включает/выключает фоновую
                        музыку в итоговом видео.
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Voice Gain</span> — громкость озвучки (в dB). Влияет
                        на баланс “голос vs музыка”.
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Music Gain</span> — громкость музыки (в dB). Чем более
                        отрицательное значение, тем тише музыка.
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Ducking</span> — автоматически приглушает музыку во
                        время речи, чтобы голос был разборчивее.
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Ducking Strength</span> — насколько сильно приглушать
                        музыку: Light (слабее) → Strong (сильнее).
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Target Loudness</span> — целевая громкость финального
                        микса (LUFS). -14 обычно громче, -16 — чуть тише.
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Music Fade In</span> — плавное нарастание музыки в начале
                        видео (сек). 0 = резкое начало.
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Music Fade Out</span> — плавное затухание музыки в конце
                        видео (сек). 0 = резкий обрыв.
                      </li>
                    </ul>
                  </div>

                  <div>
                    <p className="text-[13px] font-medium">Тайминги слайдов и рендер</p>
                    <ul className="mt-2 space-y-1.5 text-[13px] text-muted-foreground">
                      <li>
                        <span className="font-medium text-foreground">Pre-padding</span> — пауза <span className="font-medium text-foreground">перед</span>{" "}
                        озвучкой каждого слайда (кроме первого). Увеличивает длительность показа слайда и сдвигает начало
                        субтитров на этом слайде.
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Post-padding</span> — пауза <span className="font-medium text-foreground">после</span>{" "}
                        озвучки каждого слайда (кроме последнего). Увеличивает длительность показа слайда.
                      </li>
                      <li>
                        <span className="font-medium text-foreground">First Slide Hold</span> — пауза перед озвучкой{" "}
                        <span className="font-medium text-foreground">первого</span> слайда (используется вместо Pre-padding
                        для первого слайда).
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Last Slide Hold</span> — пауза после озвучки{" "}
                        <span className="font-medium text-foreground">последнего</span> слайда (используется вместо Post-padding
                        для последнего слайда).
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Transition Type</span> — тип перехода между слайдами:{" "}
                        None (резко), Fade (через затемнение), Crossfade (плавное наложение).
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Transition Duration</span> — длительность перехода (сек).
                        Чем больше — тем “мягче” переход.
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Output Format</span> — сейчас фиксирован: 16:9 (1920×1080).
                      </li>
                    </ul>
                  </div>

                  <div>
                    <p className="text-[13px] font-medium">Перевод</p>
                    <ul className="mt-2 space-y-1.5 text-[13px] text-muted-foreground">
                      <li>
                        <span className="font-medium text-foreground">Base Language</span> — базовый язык проекта (из него
                        делаются переводы).
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Target Languages</span> — языки, для которых вы хотите
                        делать перевод/озвучку/рендер.
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Generate Translations</span> — генерация переводов из
                        настроек пока в разработке.
                      </li>
                      <li>
                        <span className="font-medium text-foreground">Translation Glossary</span> — правила/термины для
                        переводчика (что не переводить, предпочтительные переводы и т.д.). Влияет на качество переводов.
                      </li>
                    </ul>

                    {translationRules && (
                      <div className="mt-3 rounded-md border border-border bg-muted/30 p-3">
                        <p className="text-[13px] font-medium">Глоссарий сейчас</p>
                        <p className="text-[13px] text-muted-foreground">
                          Не переводить: {translationRules.do_not_translate?.length ?? 0} · Предпочтительные переводы:{" "}
                          {translationRules.preferred_translations?.length ?? 0}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </aside>

          {/* Right: Settings */}
          <div className="space-y-6">
          {/* Audio Settings Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Volume2 className="w-4 h-4 text-primary" />
                Audio
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Music Upload */}
              <div>
                <label className="text-[13px] font-medium mb-2 block">
                  Corporate Music
                </label>
                <div className="flex items-center gap-3">
                  <div
                    {...getMusicDropRootProps()}
                    className={`flex-1 border-2 border-dashed rounded-md p-4 text-center cursor-pointer transition-colors ${
                      isMusicDragActive
                        ? "border-primary bg-primary/5"
                        : "border-border hover:border-primary/40"
                    } ${uploadMusicMutation.isPending ? "opacity-50 pointer-events-none" : ""}`}
                  >
                    <input {...getMusicDropInputProps()} className="hidden" />
                    {uploadMusicMutation.isPending ? (
                      <Loader2 className="w-5 h-5 mx-auto mb-1.5 text-muted-foreground animate-spin" />
                    ) : (
                      <Music className="w-5 h-5 mx-auto mb-1.5 text-muted-foreground" />
                    )}
                    <p className="text-[13px] text-muted-foreground">
                      {isMusicDragActive
                        ? "Drop MP3 here..."
                        : uploadMusicMutation.isPending
                          ? "Uploading..."
                          : audioSettings?.music_asset_id
                            ? "Drop to replace (MP3)"
                            : "Upload MP3"}
                    </p>
                  </div>
                  {audioSettings?.music_asset_id && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={toggleMusicPlayback}
                        className="p-2.5 rounded-full bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                        title={isPlaying ? "Pause music preview" : "Play music preview"}
                        aria-label={isPlaying ? "Pause music preview" : "Play music preview"}
                      >
                        {isPlaying ? (
                          <Pause className="w-4 h-4" />
                        ) : (
                          <Play className="w-4 h-4" />
                        )}
                      </button>
                      <Badge variant="success">Uploaded</Badge>
                    </div>
                  )}
                </div>
              </div>

              {/* Music Toggle */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[13px] font-medium">Background Music</p>
                  <p className="text-label text-muted-foreground">
                    Play music during presentation
                  </p>
                </div>
                <Switch
                  checked={localAudioSettings.background_music_enabled ?? false}
                  onChange={(e) =>
                    setLocalAudioSettings({
                      ...localAudioSettings,
                      background_music_enabled: e.target.checked,
                    })
                  }
                />
              </div>

              {/* Voice Gain */}
              <div>
                <label className="text-[13px] font-medium mb-2 block">
                  Voice Gain
                </label>
                <Slider
                  min={-12}
                  max={6}
                  step={1}
                  value={localAudioSettings.voice_gain_db ?? 0}
                  onChange={(e) =>
                    setLocalAudioSettings({
                      ...localAudioSettings,
                      voice_gain_db: Number(e.target.value),
                    })
                  }
                  unit=" dB"
                  minLabel="Тише"
                  maxLabel="Громче"
                />
              </div>

              {/* Music Gain */}
              <div>
                <label className="text-[13px] font-medium mb-2 block">
                  Music Gain
                </label>
                <Slider
                  min={-36}
                  max={-6}
                  step={1}
                  value={localAudioSettings.music_gain_db ?? -22}
                  onChange={(e) =>
                    setLocalAudioSettings({
                      ...localAudioSettings,
                      music_gain_db: Number(e.target.value),
                    })
                  }
                  unit=" dB"
                  minLabel="Тише"
                  maxLabel="Громче"
                />
              </div>

              {/* Ducking */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[13px] font-medium">Ducking</p>
                  <p className="text-label text-muted-foreground">
                    Lower music volume during voice
                  </p>
                </div>
                <Switch
                  checked={localAudioSettings.ducking_enabled ?? false}
                  onChange={(e) =>
                    setLocalAudioSettings({
                      ...localAudioSettings,
                      ducking_enabled: e.target.checked,
                    })
                  }
                />
              </div>

              {/* Ducking Strength */}
              {localAudioSettings.ducking_enabled && (
                <div>
                  <label className="text-[13px] font-medium mb-2 block">
                    Ducking Strength
                  </label>
                  <Select
                    value={localAudioSettings.ducking_strength ?? "default"}
                    onChange={(e) =>
                      setLocalAudioSettings({
                        ...localAudioSettings,
                        ducking_strength: e.target.value,
                      })
                    }
                  >
                    <option value="light">Light</option>
                    <option value="default">Default</option>
                    <option value="strong">Strong</option>
                  </Select>
                </div>
              )}

              {/* Target Loudness */}
              <div>
                <label className="text-[13px] font-medium mb-2 block">
                  Target Loudness
                </label>
                <Select
                  value={(localAudioSettings.target_lufs ?? -14).toString()}
                  onChange={(e) =>
                    setLocalAudioSettings({
                      ...localAudioSettings,
                      target_lufs: Number(e.target.value),
                    })
                  }
                >
                  <option value="-14">-14 LUFS (Streaming)</option>
                  <option value="-16">-16 LUFS (Podcast)</option>
                </Select>
              </div>

              {/* Music Fade In/Out */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[13px] font-medium mb-2 block">
                    Music Fade In
                  </label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      value={localAudioSettings.music_fade_in_sec ?? 2}
                      onChange={(e) =>
                        setLocalAudioSettings({
                          ...localAudioSettings,
                          music_fade_in_sec: Number(e.target.value),
                        })
                      }
                      min={0}
                      max={10}
                      step={0.5}
                      className="w-20"
                    />
                    <span className="text-[13px] text-muted-foreground">sec</span>
                  </div>
                </div>
                <div>
                  <label className="text-[13px] font-medium mb-2 block">
                    Music Fade Out
                  </label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      value={localAudioSettings.music_fade_out_sec ?? 3}
                      onChange={(e) =>
                        setLocalAudioSettings({
                          ...localAudioSettings,
                          music_fade_out_sec: Number(e.target.value),
                        })
                      }
                      min={0}
                      max={10}
                      step={0.5}
                      className="w-20"
                    />
                    <span className="text-[13px] text-muted-foreground">sec</span>
                  </div>
                </div>
              </div>

              <div className="pt-2">
                <Button
                  onClick={handleSaveAudio}
                  disabled={updateAudioMutation.isPending}
                  title="Save audio settings for this project"
                >
                  Save Audio Settings
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Render Settings Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-primary" />
                Render
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[13px] font-medium mb-2 block">
                    Pre-padding
                  </label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      value={localAudioSettings.pre_padding_sec ?? 3}
                      onChange={(e) =>
                        setLocalAudioSettings({
                          ...localAudioSettings,
                          pre_padding_sec: Number(e.target.value),
                        })
                      }
                      min={0}
                      max={10}
                      step={0.5}
                      className="w-20"
                    />
                    <span className="text-[13px] text-muted-foreground">sec</span>
                  </div>
                </div>
                <div>
                  <label className="text-[13px] font-medium mb-2 block">
                    Post-padding
                  </label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      value={localAudioSettings.post_padding_sec ?? 3}
                      onChange={(e) =>
                        setLocalAudioSettings({
                          ...localAudioSettings,
                          post_padding_sec: Number(e.target.value),
                        })
                      }
                      min={0}
                      max={10}
                      step={0.5}
                      className="w-20"
                    />
                    <span className="text-[13px] text-muted-foreground">sec</span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[13px] font-medium mb-2 block">
                    First Slide Hold
                  </label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      value={localAudioSettings.first_slide_hold_sec ?? 1}
                      onChange={(e) =>
                        setLocalAudioSettings({
                          ...localAudioSettings,
                          first_slide_hold_sec: Number(e.target.value),
                        })
                      }
                      min={0}
                      max={5}
                      step={0.5}
                      className="w-20"
                    />
                    <span className="text-[13px] text-muted-foreground">sec</span>
                  </div>
                </div>
                <div>
                  <label className="text-[13px] font-medium mb-2 block">
                    Last Slide Hold
                  </label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      value={localAudioSettings.last_slide_hold_sec ?? 1}
                      onChange={(e) =>
                        setLocalAudioSettings({
                          ...localAudioSettings,
                          last_slide_hold_sec: Number(e.target.value),
                        })
                      }
                      min={0}
                      max={5}
                      step={0.5}
                      className="w-20"
                    />
                    <span className="text-[13px] text-muted-foreground">sec</span>
                  </div>
                </div>
              </div>

              <div>
                <label className="text-[13px] font-medium mb-2 block">
                  Transition Type
                </label>
                <Select
                  value={localAudioSettings.transition_type ?? "fade"}
                  onChange={(e) =>
                    setLocalAudioSettings({
                      ...localAudioSettings,
                      transition_type: e.target.value,
                    })
                  }
                >
                  <option value="none">None</option>
                  <option value="fade">Fade</option>
                  <option value="crossfade">Crossfade</option>
                </Select>
              </div>

              <div>
                <label className="text-[13px] font-medium mb-2 block">
                  Transition Duration
                </label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    value={localAudioSettings.transition_duration_sec ?? 0.5}
                    onChange={(e) =>
                      setLocalAudioSettings({
                        ...localAudioSettings,
                        transition_duration_sec: Number(e.target.value),
                      })
                    }
                    min={0}
                    max={2}
                    step={0.1}
                    className="w-20"
                  />
                  <span className="text-[13px] text-muted-foreground">sec</span>
                </div>
              </div>

              <div>
                <label className="text-[13px] font-medium mb-2 block">
                  Output Format
                </label>
                <Badge variant="secondary">16:9 (1920×1080)</Badge>
              </div>

              <div className="pt-2">
                <Button
                  onClick={handleSaveAudio}
                  disabled={updateAudioMutation.isPending}
                  title="Save render settings for this project"
                >
                  Save Render Settings
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Translation Settings Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Languages className="w-4 h-4 text-primary" />
                Translation
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div>
                <label className="text-[13px] font-medium mb-2 block">
                  Base Language
                </label>
                <Select
                  value={baseLanguage}
                  onChange={(e) => {
                    const newLang = e.target.value;
                    setBaseLanguage(newLang);
                    updateBaseLanguageMutation.mutate(newLang);
                  }}
                  disabled={updateBaseLanguageMutation.isPending}
                  className="w-48"
                >
                  {LANGUAGES.map((lang) => (
                    <option key={lang.code} value={lang.code}>
                      {lang.name}
                    </option>
                  ))}
                </Select>
                <p className="text-label text-muted-foreground mt-1.5">
                  Original language of the presentation scripts
                </p>
              </div>

              <div>
                <label className="text-[13px] font-medium mb-2 block">
                  Target Languages
                </label>
                <div className="flex flex-wrap gap-2">
                  {LANGUAGES.filter((l) => l.code !== project?.base_language).map((lang) => (
                    <button
                      key={lang.code}
                      onClick={() => {
                        if (targetLanguages.includes(lang.code)) {
                          setTargetLanguages(targetLanguages.filter((l) => l !== lang.code));
                        } else {
                          setTargetLanguages([...targetLanguages, lang.code]);
                        }
                      }}
                      title={`Toggle ${lang.name} as a target language`}
                      className={`px-3 py-1.5 rounded-md text-[13px] border transition-colors ${
                        targetLanguages.includes(lang.code)
                          ? "bg-primary text-primary-foreground border-primary"
                          : "border-border hover:border-primary/40"
                      }`}
                    >
                      {lang.name}
                    </button>
                  ))}
                </div>
              </div>

              <Button
                variant="secondary"
                disabled={targetLanguages.length === 0}
                onClick={() => toast.info("Translation generation from settings is coming soon")}
                title="Generate translations for the selected target languages (coming soon)"
              >
                <Wand2 className="w-4 h-4" />
                Generate Translations ({targetLanguages.length})
              </Button>
            </CardContent>
          </Card>

          {/* Glossary Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BookText className="w-4 h-4 text-primary" />
                Translation Glossary
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-[13px] text-muted-foreground mb-4">
                Configure terms that should not be translated, preferred translations for specific words, and additional rules for the AI translator.
              </p>
              <Link href={`/projects/${projectId}/glossary`}>
                <Button variant="secondary" className="w-full justify-between">
                  <span className="flex items-center gap-2">
                    <BookText className="w-4 h-4" />
                    Open Glossary Editor
                  </span>
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </Link>
            </CardContent>
          </Card>
          </div>
        </div>
      </main>
    </div>
  );
}

