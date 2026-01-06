"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Plus,
  Trash2,
  Save,
  BookText,
  Languages,
  X,
} from "lucide-react";
import { api, TranslationRules } from "@/lib/api";
import { LANGUAGES, getLanguageName } from "@/lib/utils";
import { toast } from "sonner";
import Link from "next/link";
import {
  Button,
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Input,
  Select,
  Textarea,
  Badge,
} from "@/components/ui";

interface PreferredTranslation {
  term: string;
  lang: string;
  translation: string;
}

export default function GlossaryPage() {
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

  const { data: translationRules, isLoading } = useQuery({
    queryKey: ["translationRules", projectId],
    queryFn: () => api.getTranslationRules(projectId),
    enabled: Boolean(projectId),
  });

  // Local state
  const [doNotTranslate, setDoNotTranslate] = useState<string[]>([]);
  const [preferredTranslations, setPreferredTranslations] = useState<PreferredTranslation[]>([]);
  const [style, setStyle] = useState<string>("formal");
  const [extraRules, setExtraRules] = useState<string>("");
  const [newTerm, setNewTerm] = useState("");
  const [hasChanges, setHasChanges] = useState(false);

  // New translation form
  const [newTranslation, setNewTranslation] = useState<PreferredTranslation>({
    term: "",
    lang: "",
    translation: "",
  });

  // Initialize from server data
  useEffect(() => {
    if (translationRules) {
      setDoNotTranslate(translationRules.do_not_translate || []);
      setPreferredTranslations(translationRules.preferred_translations || []);
      setStyle(translationRules.style || "formal");
      setExtraRules(translationRules.extra_rules || "");
      setHasChanges(false);
    }
  }, [translationRules]);

  // Mutation
  const updateRulesMutation = useMutation({
    mutationFn: (rules: Partial<TranslationRules>) =>
      api.updateTranslationRules(projectId, rules),
    onSuccess: () => {
      toast.success("Glossary saved!");
      setHasChanges(false);
      queryClient.invalidateQueries({ queryKey: ["translationRules", projectId] });
    },
    onError: () => {
      toast.error("Failed to save glossary");
    },
  });

  // Handlers
  const handleAddDoNotTranslate = () => {
    if (newTerm.trim() && !doNotTranslate.includes(newTerm.trim())) {
      setDoNotTranslate([...doNotTranslate, newTerm.trim()]);
      setNewTerm("");
      setHasChanges(true);
    }
  };

  const handleRemoveDoNotTranslate = (term: string) => {
    setDoNotTranslate(doNotTranslate.filter((t) => t !== term));
    setHasChanges(true);
  };

  const handleAddPreferredTranslation = () => {
    if (newTranslation.term && newTranslation.lang && newTranslation.translation) {
      setPreferredTranslations([...preferredTranslations, { ...newTranslation }]);
      setNewTranslation({ term: "", lang: "", translation: "" });
      setHasChanges(true);
    }
  };

  const handleRemovePreferredTranslation = (index: number) => {
    setPreferredTranslations(preferredTranslations.filter((_, i) => i !== index));
    setHasChanges(true);
  };

  const handleSave = () => {
    updateRulesMutation.mutate({
      do_not_translate: doNotTranslate,
      preferred_translations: preferredTranslations,
      style,
      extra_rules: extraRules || null,
    });
  };

  if (!projectId) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <p className="text-[13px] text-muted-foreground">Invalid project ID</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <header className="shrink-0 h-14 bg-surface border-b border-border px-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
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
            <p className="text-label text-muted-foreground">Translation Glossary</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {hasChanges && (
            <Badge variant="warning">Unsaved changes</Badge>
          )}
          <Button
            onClick={handleSave}
            disabled={updateRulesMutation.isPending || !hasChanges}
            title="Save glossary and translation rules"
          >
            <Save className="w-4 h-4" />
            Save Glossary
          </Button>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Do Not Translate */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BookText className="w-4 h-4 text-primary" />
                Do Not Translate
              </CardTitle>
              <p className="text-[13px] text-muted-foreground mt-1">
                Terms that should remain in the original language (brand names, acronyms, etc.)
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Add new term */}
              <div className="flex gap-2">
                <Input
                  value={newTerm}
                  onChange={(e) => setNewTerm(e.target.value)}
                  placeholder="Add term (e.g., IFRS, ESG, iPhone)..."
                  onKeyDown={(e) => e.key === "Enter" && handleAddDoNotTranslate()}
                  className="flex-1"
                />
                <Button onClick={handleAddDoNotTranslate} disabled={!newTerm.trim()}>
                  <Plus className="w-4 h-4" />
                  Add
                </Button>
              </div>

              {/* Terms list */}
              {doNotTranslate.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {doNotTranslate.map((term) => (
                    <span
                      key={term}
                      className="inline-flex items-center gap-1 px-3 py-1.5 bg-muted rounded-lg text-[13px] group"
                    >
                      {term}
                      <button
                        onClick={() => handleRemoveDoNotTranslate(term)}
                        className="p-0.5 rounded hover:bg-red-100 hover:text-red-600 transition-colors opacity-60 group-hover:opacity-100"
                        title="Remove this term from the list"
                        aria-label="Remove term"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-[13px] text-muted-foreground italic">
                  No terms added yet
                </p>
              )}
            </CardContent>
          </Card>

          {/* Preferred Translations */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Languages className="w-4 h-4 text-primary" />
                Preferred Translations
              </CardTitle>
              <p className="text-[13px] text-muted-foreground mt-1">
                Specific translations for technical terms, company names, or industry jargon
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Add new translation */}
              <div className="grid grid-cols-[1fr_140px_1fr_auto] gap-2 items-end">
                <div>
                  <label className="text-[12px] text-muted-foreground mb-1 block">
                    Original term
                  </label>
                  <Input
                    value={newTranslation.term}
                    onChange={(e) =>
                      setNewTranslation({ ...newTranslation, term: e.target.value })
                    }
                    placeholder="e.g., Revenue"
                  />
                </div>
                <div>
                  <label className="text-[12px] text-muted-foreground mb-1 block">
                    Language
                  </label>
                  <Select
                    value={newTranslation.lang}
                    onChange={(e) =>
                      setNewTranslation({ ...newTranslation, lang: e.target.value })
                    }
                  >
                    <option value="">Select...</option>
                    {LANGUAGES.filter((l) => l.code !== project?.base_language).map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.name}
                      </option>
                    ))}
                  </Select>
                </div>
                <div>
                  <label className="text-[12px] text-muted-foreground mb-1 block">
                    Translation
                  </label>
                  <Input
                    value={newTranslation.translation}
                    onChange={(e) =>
                      setNewTranslation({ ...newTranslation, translation: e.target.value })
                    }
                    placeholder="e.g., Выручка"
                  />
                </div>
                <Button
                  onClick={handleAddPreferredTranslation}
                  disabled={!newTranslation.term || !newTranslation.lang || !newTranslation.translation}
                  title="Add this preferred translation"
                  aria-label="Add preferred translation"
                >
                  <Plus className="w-4 h-4" />
                </Button>
              </div>

              {/* Translations table */}
              {preferredTranslations.length > 0 ? (
                <div className="border border-border rounded-lg overflow-hidden">
                  <table className="w-full">
                    <thead className="bg-muted/50">
                      <tr className="text-left text-[12px] text-muted-foreground">
                        <th className="px-4 py-2 font-medium">Original Term</th>
                        <th className="px-4 py-2 font-medium">Language</th>
                        <th className="px-4 py-2 font-medium">Translation</th>
                        <th className="px-4 py-2 w-10"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {preferredTranslations.map((pt, index) => (
                        <tr key={index} className="text-[13px] hover:bg-muted/30">
                          <td className="px-4 py-2 font-medium">{pt.term}</td>
                          <td className="px-4 py-2">
                            <Badge variant="secondary">{getLanguageName(pt.lang)}</Badge>
                          </td>
                          <td className="px-4 py-2">{pt.translation}</td>
                          <td className="px-4 py-2">
                            <button
                              onClick={() => handleRemovePreferredTranslation(index)}
                              className="p-1 rounded hover:bg-red-100 hover:text-red-600 transition-colors text-muted-foreground"
                              title="Remove this preferred translation"
                              aria-label="Remove preferred translation"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-[13px] text-muted-foreground italic">
                  No preferred translations added yet
                </p>
              )}
            </CardContent>
          </Card>

          {/* Translation Style */}
          <Card>
            <CardHeader>
              <CardTitle>Translation Style</CardTitle>
              <p className="text-[13px] text-muted-foreground mt-1">
                Choose the overall tone for translations
              </p>
            </CardHeader>
            <CardContent>
              <div className="flex gap-3">
                {[
                  { value: "formal", label: "Formal", desc: "Professional, corporate tone" },
                  { value: "neutral", label: "Neutral", desc: "Standard, balanced approach" },
                  { value: "friendly", label: "Friendly", desc: "Conversational, approachable" },
                ].map((option) => (
                  <button
                    key={option.value}
                    onClick={() => {
                      setStyle(option.value);
                      setHasChanges(true);
                    }}
                    title={`Use “${option.label}” translation tone`}
                    className={`flex-1 p-4 rounded-lg border-2 text-left transition-colors ${
                      style === option.value
                        ? "border-primary bg-primary/5"
                        : "border-border hover:border-primary/40"
                    }`}
                  >
                    <p className="font-medium text-[14px]">{option.label}</p>
                    <p className="text-[12px] text-muted-foreground mt-0.5">
                      {option.desc}
                    </p>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Extra Rules */}
          <Card>
            <CardHeader>
              <CardTitle>Additional Instructions</CardTitle>
              <p className="text-[13px] text-muted-foreground mt-1">
                Custom instructions for the AI translator (optional)
              </p>
            </CardHeader>
            <CardContent>
              <Textarea
                value={extraRules}
                onChange={(e) => {
                  setExtraRules(e.target.value);
                  setHasChanges(true);
                }}
                placeholder="Example: Always use 'Вы' (formal) instead of 'ты'. Preserve all number formatting. Use metric units..."
                rows={4}
              />
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}

