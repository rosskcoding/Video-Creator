"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X, Upload, Download, Info, Mic, Copy, Check, Play, Pause } from "lucide-react";
import { toast } from "sonner";
import {
  Button,
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  Input,
  Select,
  Badge,
} from "@/components/ui";
import { LANGUAGES, getLanguageName } from "@/lib/utils";
import { api, Voice } from "@/lib/api";

// Note: This would typically be per-project. For now, showing a global admin view.
// In real implementation, this would redirect to select a project first.

// Default Voice ID from backend config
const DEFAULT_VOICE_ID = "iBcRJa9DRdlJlVihC0V6";

export default function AdminGlossaryPage() {
  const [doNotTranslate, setDoNotTranslate] = useState<string[]>([
    "IFRS", "CSRD", "ESG", "KPI", "EBITDA", "Scope 1", "Scope 2", "Scope 3"
  ]);
  const [newTerm, setNewTerm] = useState("");
  
  const [preferredTranslations, setPreferredTranslations] = useState([
    { id: "1", term: "materiality", lang: "ru", translation: "существенность" },
    { id: "2", term: "materiality", lang: "uk", translation: "суттєвість" },
    { id: "3", term: "stakeholder", lang: "ru", translation: "заинтересованная сторона" },
  ]);
  const [newTranslation, setNewTranslation] = useState({ term: "", lang: "ru", translation: "" });

  const [style, setStyle] = useState<"formal" | "neutral" | "friendly">("formal");

  // Voice settings state
  const [customVoiceId, setCustomVoiceId] = useState(DEFAULT_VOICE_ID);
  const [copiedVoiceId, setCopiedVoiceId] = useState<string | null>(null);
  const [playingPreview, setPlayingPreview] = useState<string | null>(null);
  const [audioRef, setAudioRef] = useState<HTMLAudioElement | null>(null);

  // Fetch voices from ElevenLabs
  const { data: voicesData, isLoading: voicesLoading } = useQuery({
    queryKey: ["voices"],
    queryFn: () => api.getVoices(),
  });

  // Copy voice ID to clipboard
  const handleCopyVoiceId = (voiceId: string) => {
    navigator.clipboard.writeText(voiceId);
    setCopiedVoiceId(voiceId);
    toast.success("Voice ID скопирован");
    setTimeout(() => setCopiedVoiceId(null), 2000);
  };

  // Play voice preview
  const handlePlayPreview = (voice: Voice) => {
    if (!voice.preview_url) {
      toast.error("Preview недоступен для этого голоса");
      return;
    }

    if (playingPreview === voice.voice_id && audioRef) {
      audioRef.pause();
      setPlayingPreview(null);
      return;
    }

    if (audioRef) {
      audioRef.pause();
    }

    const audio = new Audio(voice.preview_url);
    audio.onended = () => setPlayingPreview(null);
    audio.onerror = () => {
      toast.error("Не удалось воспроизвести preview");
      setPlayingPreview(null);
    };
    audio.play();
    setAudioRef(audio);
    setPlayingPreview(voice.voice_id);
  };

  // Cleanup audio on unmount
  useEffect(() => {
    return () => {
      if (audioRef) {
        audioRef.pause();
      }
    };
  }, [audioRef]);

  const handleAddTerm = () => {
    if (newTerm && !doNotTranslate.includes(newTerm)) {
      setDoNotTranslate([...doNotTranslate, newTerm]);
      setNewTerm("");
    }
  };

  const handleRemoveTerm = (term: string) => {
    setDoNotTranslate(doNotTranslate.filter((t) => t !== term));
  };

  const handleAddTranslation = () => {
    if (newTranslation.term && newTranslation.translation) {
      setPreferredTranslations([
        ...preferredTranslations,
        { ...newTranslation, id: Date.now().toString() },
      ]);
      setNewTranslation({ term: "", lang: "ru", translation: "" });
    }
  };

  const handleRemoveTranslation = (id: string) => {
    setPreferredTranslations(preferredTranslations.filter((t) => t.id !== id));
  };

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <header className="shrink-0 bg-surface border-b border-border px-6 py-4">
        <h1 className="text-page-title">Glossary & Translation Rules</h1>
        <p className="text-[13px] text-muted-foreground mt-1">
          Manage translation settings for all projects
        </p>
      </header>

      {/* Content */}
      <main className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Voice Settings Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Mic className="w-4 h-4 text-primary" />
                Voice Settings (ElevenLabs)
              </CardTitle>
              <CardDescription>
                Управление голосами для Text-to-Speech
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Current Voice ID */}
              <div>
                <label className="text-[13px] font-medium mb-2 block">
                  Default Voice ID
                </label>
                <div className="flex gap-2">
                  <Input
                    placeholder="Voice ID..."
                    value={customVoiceId}
                    onChange={(e) => setCustomVoiceId(e.target.value)}
                    className="font-mono text-[13px]"
                  />
                  <Button
                    variant="secondary"
                    onClick={() => handleCopyVoiceId(customVoiceId)}
                    title="Копировать Voice ID"
                  >
                    {copiedVoiceId === customVoiceId ? (
                      <Check className="w-4 h-4 text-green-500" />
                    ) : (
                      <Copy className="w-4 h-4" />
                    )}
                  </Button>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Используется по умолчанию для новых проектов
                </p>
              </div>

              {/* Available Voices */}
              <div>
                <label className="text-[13px] font-medium mb-2 block">
                  Доступные голоса ElevenLabs
                </label>
                {voicesLoading ? (
                  <div className="text-[13px] text-muted-foreground py-4 text-center">
                    Загрузка голосов...
                  </div>
                ) : (
                  <div className="border border-border rounded-lg overflow-hidden max-h-80 overflow-y-auto">
                    <table className="w-full text-[13px]">
                      <thead className="bg-muted sticky top-0">
                        <tr>
                          <th className="text-left font-medium px-3 py-2">Голос</th>
                          <th className="text-left font-medium px-3 py-2">Категория</th>
                          <th className="text-left font-medium px-3 py-2">Voice ID</th>
                          <th className="w-24"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {voicesData?.voices?.map((voice) => (
                          <tr
                            key={voice.voice_id}
                            className={`border-t border-border hover:bg-muted/50 ${
                              voice.voice_id === customVoiceId ? "bg-primary/5" : ""
                            }`}
                          >
                            <td className="px-3 py-2">
                              <div className="font-medium">{voice.name}</div>
                              <div className="text-[11px] text-muted-foreground">
                                {voice.labels.gender} • {voice.labels.accent}
                              </div>
                            </td>
                            <td className="px-3 py-2">
                              <Badge variant={voice.category === "premade" ? "default" : "secondary"}>
                                {voice.category}
                              </Badge>
                            </td>
                            <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">
                              {voice.voice_id.slice(0, 12)}...
                            </td>
                            <td className="px-3 py-2">
                              <div className="flex gap-1">
                                {voice.preview_url && (
                                  <button
                                    onClick={() => handlePlayPreview(voice)}
                                    className="p-1.5 hover:bg-background rounded text-muted-foreground hover:text-foreground"
                                    title="Прослушать"
                                  >
                                    {playingPreview === voice.voice_id ? (
                                      <Pause className="w-3.5 h-3.5" />
                                    ) : (
                                      <Play className="w-3.5 h-3.5" />
                                    )}
                                  </button>
                                )}
                                <button
                                  onClick={() => handleCopyVoiceId(voice.voice_id)}
                                  className="p-1.5 hover:bg-background rounded text-muted-foreground hover:text-foreground"
                                  title="Копировать Voice ID"
                                >
                                  {copiedVoiceId === voice.voice_id ? (
                                    <Check className="w-3.5 h-3.5 text-green-500" />
                                  ) : (
                                    <Copy className="w-3.5 h-3.5" />
                                  )}
                                </button>
                                <button
                                  onClick={() => {
                                    setCustomVoiceId(voice.voice_id);
                                    toast.success(`Выбран голос: ${voice.name}`);
                                  }}
                                  className="px-2 py-1 text-[11px] bg-primary/10 text-primary rounded hover:bg-primary/20"
                                  title="Использовать этот голос"
                                >
                                  Выбрать
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="flex items-start gap-2 p-3 bg-muted rounded-lg">
                <Info className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                <p className="text-[13px] text-muted-foreground">
                  Voice ID используется для генерации речи через ElevenLabs API. 
                  Выберите голос из списка или вставьте свой Voice ID.
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Do Not Translate Card */}
          <Card>
            <CardHeader>
              <CardTitle>Do Not Translate</CardTitle>
              <CardDescription>
                Terms that should remain in the original language
              </CardDescription>
            </CardHeader>
            <CardContent>
              {/* Tags */}
              <div className="flex flex-wrap gap-2 mb-4">
                {doNotTranslate.map((term) => (
                  <Badge
                    key={term}
                    variant="secondary"
                    className="gap-1 pr-1"
                  >
                    {term}
                    <button
                      onClick={() => handleRemoveTerm(term)}
                      className="p-0.5 hover:bg-background/50 rounded"
                      title="Remove this term"
                      aria-label="Remove term"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </Badge>
                ))}
              </div>

              {/* Add new */}
              <div className="flex gap-2">
                <Input
                  placeholder="Add term..."
                  value={newTerm}
                  onChange={(e) => setNewTerm(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddTerm()}
                  className="max-w-xs"
                />
                <Button variant="secondary" onClick={handleAddTerm}>
                  <Plus className="w-4 h-4" />
                  Add
                </Button>
              </div>

              {/* Bulk actions */}
              <div className="flex gap-2 mt-4 pt-4 border-t border-border">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => toast.info("Import is coming soon")}
                  title="Import glossary/rules (coming soon)"
                >
                  <Upload className="w-3.5 h-3.5" />
                  Import
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => toast.info("Export is coming soon")}
                  title="Export glossary/rules (coming soon)"
                >
                  <Download className="w-3.5 h-3.5" />
                  Export
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Preferred Translations Card */}
          <Card>
            <CardHeader>
              <CardTitle>Preferred Translations</CardTitle>
              <CardDescription>
                Specific translations for terms per language
              </CardDescription>
            </CardHeader>
            <CardContent>
              {/* Table */}
              <div className="border border-border rounded-lg overflow-hidden mb-4">
                <table className="w-full text-[13px]">
                  <thead className="bg-muted">
                    <tr>
                      <th className="text-left font-medium px-3 py-2">Term</th>
                      <th className="text-left font-medium px-3 py-2">Language</th>
                      <th className="text-left font-medium px-3 py-2">Translation</th>
                      <th className="w-12"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {preferredTranslations.map((row) => (
                      <tr key={row.id} className="border-t border-border">
                        <td className="px-3 py-2">{row.term}</td>
                        <td className="px-3 py-2">{getLanguageName(row.lang)}</td>
                        <td className="px-3 py-2">{row.translation}</td>
                        <td className="px-3 py-2">
                          <button
                            onClick={() => handleRemoveTranslation(row.id)}
                            className="p-1 hover:bg-muted rounded text-muted-foreground hover:text-foreground"
                            title="Remove this preferred translation"
                            aria-label="Remove preferred translation"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Add new row */}
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <label className="text-label text-muted-foreground mb-1 block">Term</label>
                  <Input
                    placeholder="e.g., sustainability"
                    value={newTranslation.term}
                    onChange={(e) =>
                      setNewTranslation({ ...newTranslation, term: e.target.value })
                    }
                  />
                </div>
                <div className="w-32">
                  <label className="text-label text-muted-foreground mb-1 block">Language</label>
                  <Select
                    value={newTranslation.lang}
                    onChange={(e) =>
                      setNewTranslation({ ...newTranslation, lang: e.target.value })
                    }
                  >
                    {LANGUAGES.map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.name}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="flex-1">
                  <label className="text-label text-muted-foreground mb-1 block">Translation</label>
                  <Input
                    placeholder="Translation..."
                    value={newTranslation.translation}
                    onChange={(e) =>
                      setNewTranslation({ ...newTranslation, translation: e.target.value })
                    }
                  />
                </div>
                <Button variant="secondary" onClick={handleAddTranslation}>
                  <Plus className="w-4 h-4" />
                  Add
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Style Card */}
          <Card>
            <CardHeader>
              <CardTitle>Translation Style</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-[13px] font-medium mb-2 block">Style</label>
                <div className="flex gap-2">
                  {(["formal", "neutral", "friendly"] as const).map((s) => (
                    <button
                      key={s}
                      onClick={() => setStyle(s)}
                      title={`Set translation tone to “${s}”`}
                      className={`px-4 py-2 rounded-md text-[13px] font-medium border transition-colors ${
                        style === s
                          ? "bg-primary text-primary-foreground border-primary"
                          : "border-border hover:border-primary/40"
                      }`}
                    >
                      {s.charAt(0).toUpperCase() + s.slice(1)}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-start gap-2 p-3 bg-muted rounded-lg">
                <Info className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                <p className="text-[13px] text-muted-foreground">
                  Numbers, percentages, tickers, and acronyms are always preserved automatically.
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Save */}
          <div className="flex justify-end">
            <Button
              onClick={() => toast.success("Settings saved")}
              title="Save changes (demo)"
            >
              Save Changes
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
}

