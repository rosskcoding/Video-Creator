"use client";

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, Marker } from "@/lib/api";
import { Button, Input } from "@/components/ui";
import { Plus, Trash2, Tag, X, Check } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

interface MarkersManagerProps {
  slideId: string;
  lang: string;
  scriptText: string;
  onSelectWord?: (word: string, charStart: number, charEnd: number) => void;
  selectedWordIndex?: number;
}

export function MarkersManager({
  slideId,
  lang,
  scriptText,
  onSelectWord,
  selectedWordIndex,
}: MarkersManagerProps) {
  const queryClient = useQueryClient();
  const [editingMarkerId, setEditingMarkerId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [showAddMarker, setShowAddMarker] = useState(false);
  const [newMarkerName, setNewMarkerName] = useState("");
  const [newMarkerWordIndex, setNewMarkerWordIndex] = useState<number | null>(null);

  // Fetch markers
  const { data: markersData } = useQuery({
    queryKey: ["markers", slideId, lang],
    queryFn: () => api.getSlideMarkers(slideId, lang),
    enabled: !!slideId && !!lang,
  });

  const markers = markersData?.markers || [];

  // Update markers mutation
  const updateMarkersMutation = useMutation({
    mutationFn: (newMarkers: Marker[]) => api.updateSlideMarkers(slideId, lang, newMarkers),
    onSuccess: (_, __, context) => {
      queryClient.invalidateQueries({ queryKey: ["markers", slideId, lang] });
    },
    onError: () => {
      toast.error("Failed to update markers");
    },
  });

  // Tokenize script into words with positions
  const words = useMemo(() => {
    const result: { text: string; start: number; end: number; index: number }[] = [];
    const regex = /\S+/g;
    let match;
    let index = 0;
    while ((match = regex.exec(scriptText)) !== null) {
      result.push({
        text: match[0],
        start: match.index,
        end: match.index + match[0].length,
        index: index++,
      });
    }
    return result;
  }, [scriptText]);

  // Handle word click
  const handleWordClick = (wordIndex: number) => {
    const word = words[wordIndex];
    if (!word) return;

    if (showAddMarker) {
      setNewMarkerWordIndex(wordIndex);
    } else {
      onSelectWord?.(word.text, word.start, word.end);
    }
  };

  // Add new marker
  const handleAddMarker = () => {
    if (!newMarkerName.trim() || newMarkerWordIndex === null) {
      toast.error("Please enter a name and select a word");
      return;
    }

    const word = words[newMarkerWordIndex];
    if (!word) return;

    const newMarker: Marker = {
      id: `marker-${Date.now()}`,
      name: newMarkerName.trim(),
      charStart: word.start,
      charEnd: word.end,
      wordText: word.text,
      timeSeconds: 0, // Will be calculated after TTS
    };

    updateMarkersMutation.mutate([...markers, newMarker], {
      onSuccess: () => {
        toast.success("Marker added");
      },
    });
    setShowAddMarker(false);
    setNewMarkerName("");
    setNewMarkerWordIndex(null);
  };

  // Delete marker
  const handleDeleteMarker = (markerId: string) => {
    updateMarkersMutation.mutate(markers.filter((m) => m.id !== markerId), {
      onSuccess: () => {
        toast.success("Marker deleted");
      },
    });
  };

  // Rename marker
  const handleRenameMarker = (markerId: string) => {
    if (!editingName.trim()) return;
    updateMarkersMutation.mutate(
      markers.map((m) => (m.id === markerId ? { ...m, name: editingName.trim() } : m))
    );
    setEditingMarkerId(null);
    setEditingName("");
  };

  // Find markers for a word position
  const getMarkerForWord = (wordStart: number, wordEnd: number) => {
    return markers.find(
      (m) => m.charStart !== undefined && m.charEnd !== undefined && wordStart >= m.charStart && wordEnd <= m.charEnd
    );
  };

  return (
    <div className="bg-[#1e1e1e] border border-[#333] rounded-lg overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 bg-[#252525] border-b border-[#333] flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-white/70">
          <Tag className="w-3.5 h-3.5" />
          <span>Markers ({markers.length})</span>
        </div>
        {!showAddMarker && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowAddMarker(true)}
            className="h-6 px-2 text-xs"
          >
            <Plus className="w-3 h-3 mr-1" />
            Add
          </Button>
        )}
      </div>

      {/* Add marker form */}
      {showAddMarker && (
        <div className="px-3 py-2 bg-[#2a2a2a] border-b border-[#333] space-y-2">
          <div className="flex items-center gap-2">
            <Input
              placeholder="Marker name..."
              value={newMarkerName}
              onChange={(e) => setNewMarkerName(e.target.value)}
              className="h-7 text-xs bg-[#333] border-[#444]"
            />
            <Button
              variant="ghost"
              size="sm"
              onClick={handleAddMarker}
              disabled={!newMarkerName.trim() || newMarkerWordIndex === null}
              className="h-7 px-2"
            >
              <Check className="w-3 h-3" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setShowAddMarker(false);
                setNewMarkerName("");
                setNewMarkerWordIndex(null);
              }}
              className="h-7 px-2"
            >
              <X className="w-3 h-3" />
            </Button>
          </div>
          <p className="text-[10px] text-white/40">
            {newMarkerWordIndex !== null
              ? `Selected: "${words[newMarkerWordIndex]?.text}"`
              : "Click a word below to set marker position"}
          </p>
        </div>
      )}

      {/* Script with clickable words */}
      <div className="p-3">
        <div className="text-xs leading-relaxed">
          {words.length === 0 ? (
            <span className="text-white/30 italic">No script text</span>
          ) : (
            words.map((word, idx) => {
              const marker = getMarkerForWord(word.start, word.end);
              const isSelected = showAddMarker && newMarkerWordIndex === idx;
              const isHighlighted = selectedWordIndex === idx;

              return (
                <span key={idx}>
                  <span
                    onClick={() => handleWordClick(idx)}
                    className={cn(
                      "cursor-pointer px-0.5 rounded transition-colors",
                      marker && "bg-yellow-500/30 text-yellow-300",
                      isSelected && "bg-primary/50 text-white",
                      isHighlighted && "bg-blue-500/30 text-blue-300",
                      !marker && !isSelected && !isHighlighted && "hover:bg-white/10 text-white/80"
                    )}
                    title={marker ? `Marker: ${marker.name || "(unnamed)"}` : "Click to select"}
                  >
                    {word.text}
                  </span>
                  {" "}
                </span>
              );
            })
          )}
        </div>
      </div>

      {/* Markers list */}
      {markers.length > 0 && (
        <div className="border-t border-[#333]">
          <div className="px-3 py-1.5 text-[10px] text-white/40 uppercase tracking-wider">
            Markers List
          </div>
          <div className="max-h-32 overflow-y-auto">
            {markers.map((marker) => (
              <div
                key={marker.id}
                className="px-3 py-1.5 flex items-center gap-2 hover:bg-white/5 group"
              >
                <Tag className="w-3 h-3 text-yellow-400" />
                {editingMarkerId === marker.id ? (
                  <div className="flex-1 flex items-center gap-1">
                    <Input
                      value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleRenameMarker(marker.id);
                        if (e.key === "Escape") setEditingMarkerId(null);
                      }}
                      className="h-5 text-xs bg-[#333] border-[#444] flex-1"
                      autoFocus
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRenameMarker(marker.id)}
                      className="h-5 w-5 p-0"
                    >
                      <Check className="w-3 h-3" />
                    </Button>
                  </div>
                ) : (
                  <>
                    <span
                      className="flex-1 text-xs text-white/80 truncate cursor-pointer"
                      onClick={() => {
                        setEditingMarkerId(marker.id);
                        setEditingName(marker.name || "");
                      }}
                    >
                      {marker.name || "(unnamed)"}
                    </span>
                    <span className="text-[10px] text-white/40">
                      "{marker.wordText}"
                    </span>
                  </>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDeleteMarker(marker.id)}
                  className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300"
                >
                  <Trash2 className="w-3 h-3" />
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

