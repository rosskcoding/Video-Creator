"use client";

import { useState } from "react";
import { SlideLayer } from "@/lib/api";
import { 
  Eye, EyeOff, Lock, Unlock, Trash2, GripVertical,
  Type, Square, ImageIcon, ChevronUp, ChevronDown, Copy
} from "lucide-react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";

interface LayerPanelProps {
  layers: SlideLayer[];
  selectedLayerId: string | null;
  onSelectLayer: (id: string) => void;
  onUpdateLayer: (id: string, updates: Partial<SlideLayer>) => void;
  onDeleteLayer: (id: string) => void;
  onReorderLayers: (layers: SlideLayer[]) => void;
}

export function LayerPanel({
  layers,
  selectedLayerId,
  onSelectLayer,
  onUpdateLayer,
  onDeleteLayer,
  onReorderLayers,
}: LayerPanelProps) {
  const [draggedId, setDraggedId] = useState<string | null>(null);

  // Sort layers by zIndex (reversed for visual display - top layer first)
  const sortedLayers = [...layers].sort((a, b) => b.zIndex - a.zIndex);

  const getLayerIcon = (type: string) => {
    switch (type) {
      case "text": return <Type className="w-3.5 h-3.5" />;
      case "plate": return <Square className="w-3.5 h-3.5" />;
      case "image": return <ImageIcon className="w-3.5 h-3.5" />;
      default: return <Square className="w-3.5 h-3.5" />;
    }
  };

  const handleDragStart = (e: React.DragEvent, layerId: string) => {
    setDraggedId(layerId);
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };

  const handleDrop = (e: React.DragEvent, targetId: string) => {
    e.preventDefault();
    if (!draggedId || draggedId === targetId) {
      setDraggedId(null);
      return;
    }

    const draggedIndex = sortedLayers.findIndex(l => l.id === draggedId);
    const targetIndex = sortedLayers.findIndex(l => l.id === targetId);

    const newOrder = [...sortedLayers];
    const [removed] = newOrder.splice(draggedIndex, 1);
    newOrder.splice(targetIndex, 0, removed);

    // Reverse back and re-index
    const reversed = newOrder.reverse();
    onReorderLayers(reversed);
    setDraggedId(null);
  };

  const moveLayer = (layerId: string, direction: "up" | "down") => {
    const idx = sortedLayers.findIndex(l => l.id === layerId);
    if (idx === -1) return;
    
    const newIndex = direction === "up" ? idx - 1 : idx + 1;
    if (newIndex < 0 || newIndex >= sortedLayers.length) return;

    const newOrder = [...sortedLayers];
    [newOrder[idx], newOrder[newIndex]] = [newOrder[newIndex], newOrder[idx]];
    
    // Reverse back and re-index
    const reversed = newOrder.reverse();
    onReorderLayers(reversed);
  };

  const duplicateLayer = (layer: SlideLayer) => {
    // Sort layers by zIndex first to ensure correct ordering
    const sortedByZIndex = [...layers].sort((a, b) => a.zIndex - b.zIndex);
    const maxZIndex = sortedByZIndex.length > 0 
      ? Math.max(...sortedByZIndex.map(l => l.zIndex)) 
      : -1;
    
    const newLayer: SlideLayer = {
      ...JSON.parse(JSON.stringify(layer)),
      id: `layer-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      name: `${layer.name} (copy)`,
      position: { x: layer.position.x + 20, y: layer.position.y + 20 },
      zIndex: maxZIndex + 1,
    };
    // Pass sorted layers with new layer at the end (highest zIndex)
    onReorderLayers([...sortedByZIndex, newLayer]);
  };

  return (
    <div className="w-60 bg-[#252525] border-r border-[#333] flex flex-col">
      <div className="h-10 px-3 flex items-center justify-between border-b border-[#333]">
        <span className="text-xs font-medium text-white/70 uppercase tracking-wider">Layers</span>
        <span className="text-xs text-white/40">{layers.length}</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {sortedLayers.length === 0 ? (
          <div className="p-4 text-center text-white/40 text-xs">
            No layers yet. Add text, plates, or images.
          </div>
        ) : (
          <div className="py-1">
            {sortedLayers.map((layer, index) => (
              <div
                key={layer.id}
                draggable
                onDragStart={(e) => handleDragStart(e, layer.id)}
                onDragOver={handleDragOver}
                onDrop={(e) => handleDrop(e, layer.id)}
                className={cn(
                  "group flex items-center gap-1.5 px-2 py-1.5 cursor-pointer transition-colors",
                  selectedLayerId === layer.id 
                    ? "bg-primary/20 text-white" 
                    : "text-white/70 hover:bg-white/5",
                  draggedId === layer.id && "opacity-50",
                  !layer.visible && "opacity-40"
                )}
                onClick={() => onSelectLayer(layer.id)}
              >
                {/* Drag handle */}
                <GripVertical className="w-3.5 h-3.5 text-white/30 cursor-grab active:cursor-grabbing" />

                {/* Type icon */}
                <div className={cn(
                  "w-5 h-5 rounded flex items-center justify-center",
                  layer.type === "text" && "bg-blue-500/20 text-blue-400",
                  layer.type === "plate" && "bg-orange-500/20 text-orange-400",
                  layer.type === "image" && "bg-green-500/20 text-green-400",
                )}>
                  {getLayerIcon(layer.type)}
                </div>

                {/* Name */}
                <span className="flex-1 text-xs truncate">{layer.name}</span>

                {/* Actions */}
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  {/* Visibility */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onUpdateLayer(layer.id, { visible: !layer.visible });
                    }}
                    className="p-1 rounded hover:bg-white/10"
                    title={layer.visible ? "Hide" : "Show"}
                  >
                    {layer.visible ? (
                      <Eye className="w-3 h-3" />
                    ) : (
                      <EyeOff className="w-3 h-3" />
                    )}
                  </button>

                  {/* Lock */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onUpdateLayer(layer.id, { locked: !layer.locked });
                    }}
                    className="p-1 rounded hover:bg-white/10"
                    title={layer.locked ? "Unlock" : "Lock"}
                  >
                    {layer.locked ? (
                      <Lock className="w-3 h-3 text-yellow-500" />
                    ) : (
                      <Unlock className="w-3 h-3" />
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Layer actions */}
      {selectedLayerId && (
        <div className="border-t border-[#333] p-2 flex items-center justify-between">
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="w-7 h-7 text-white/60 hover:text-white hover:bg-white/10"
              onClick={() => moveLayer(selectedLayerId, "up")}
              disabled={sortedLayers.findIndex(l => l.id === selectedLayerId) === 0}
              title="Move up"
            >
              <ChevronUp className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="w-7 h-7 text-white/60 hover:text-white hover:bg-white/10"
              onClick={() => moveLayer(selectedLayerId, "down")}
              disabled={sortedLayers.findIndex(l => l.id === selectedLayerId) === sortedLayers.length - 1}
              title="Move down"
            >
              <ChevronDown className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="w-7 h-7 text-white/60 hover:text-white hover:bg-white/10"
              onClick={() => {
                const layer = layers.find(l => l.id === selectedLayerId);
                if (layer) duplicateLayer(layer);
              }}
              title="Duplicate"
            >
              <Copy className="w-4 h-4" />
            </Button>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="w-7 h-7 text-red-400 hover:text-red-300 hover:bg-red-500/10"
            onClick={() => onDeleteLayer(selectedLayerId)}
            title="Delete"
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
      )}
    </div>
  );
}

