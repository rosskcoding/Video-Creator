"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Canvas, FabricImage, Textbox, Rect, FabricObject } from "fabric";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, SlideLayer } from "@/lib/api";
import { toast } from "sonner";
import { LayerPanel } from "./LayerPanel";
import { PropertiesPanel } from "./PropertiesPanel";
import { AssetLibrary } from "./AssetLibrary";
import { AnimationPreview } from "./AnimationPreview";
import { Button } from "@/components/ui";
import { Type, Square, ImageIcon, Save, ZoomIn, ZoomOut, Maximize2, PlayCircle, Languages, ChevronDown, Loader2 } from "lucide-react";
import { getLanguageName } from "@/lib/utils";

interface CanvasEditorProps {
  slideId: string;
  projectId: string;
  slideImageUrl: string;
  availableLanguages?: string[];
  baseLanguage?: string;
  onClose?: () => void;
}

// Extend FabricObject to include custom data
declare module 'fabric' {
  interface FabricObject {
    data?: { layerId: string };
  }
}

// Generate unique layer ID
const generateLayerId = () => `layer-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

export function CanvasEditor({ 
  slideId, 
  projectId, 
  slideImageUrl, 
  availableLanguages = [], 
  baseLanguage = "en",
  onClose 
}: CanvasEditorProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fabricRef = useRef<Canvas | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  
  // Render generation counter to prevent ghost images from stale async loads
  const renderGenRef = useRef(0);
  // Separate generation counter for background loads (do not couple to layer renderGenRef)
  const bgGenRef = useRef(0);

  const [selectedLayerId, setSelectedLayerId] = useState<string | null>(null);
  const [layers, setLayers] = useState<SlideLayer[]>([]);
  const [zoom, setZoom] = useState(0.5);
  const [showAssetLibrary, setShowAssetLibrary] = useState(false);
  const [showAnimationPreview, setShowAnimationPreview] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  
  // Language state
  const [selectedLang, setSelectedLang] = useState(baseLanguage);
  const [showLangDropdown, setShowLangDropdown] = useState(false);

  // Fetch scene data
  const { data: scene, isLoading } = useQuery({
    queryKey: ["scene", slideId],
    queryFn: () => api.getSlideScene(slideId),
    enabled: !!slideId,
  });

  // Fetch resolved scene (word triggers -> time triggers) for the selected language.
  // Note: resolution is based on the saved scene in DB, so we disable it when there are unsaved changes.
  const { data: resolvedScene } = useQuery({
    queryKey: ["resolvedScene", slideId, selectedLang, scene?.render_key],
    queryFn: () => api.getResolvedScene(slideId, selectedLang),
    enabled: !!slideId && !!selectedLang && showAnimationPreview && !isDirty,
  });

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: (sceneLayers: SlideLayer[]) => 
      api.updateSlideScene(slideId, { layers: sceneLayers }),
    onSuccess: async () => {
      setIsDirty(false);
      toast.success("Scene saved");
      queryClient.invalidateQueries({ queryKey: ["scene", slideId] });
      
      // Generate preview with rendered layers
      try {
        await api.generateSlidePreview(slideId, selectedLang);
        // Refresh slide + slides list so preview_url is picked up
        queryClient.invalidateQueries({ queryKey: ["slide", slideId] });
        // Prefix invalidation: refresh any slides lists regardless of version id
        queryClient.invalidateQueries({ queryKey: ["slides"] });
      } catch (err) {
        console.warn("Preview generation failed:", err);
        // Don't show error toast - preview is optional
      }
    },
    onError: () => {
      toast.error("Failed to save scene");
    },
  });

  // Translate mutation
  const translateMutation = useMutation({
    mutationFn: (targetLang: string) => api.translateSceneLayers(slideId, targetLang),
    onSuccess: (data) => {
      if (data.translated_count > 0) {
        toast.success(`Translated ${data.translated_count} text layer(s) to ${getLanguageName(data.target_lang)}`);
        queryClient.invalidateQueries({ queryKey: ["scene", slideId] });
      } else {
        toast.info("No new translations needed");
      }
    },
    onError: () => {
      toast.error("Failed to translate layers");
    },
  });

  // Update layer from fabric object
  const updateLayerFromFabricObj = useCallback((obj: FabricObject) => {
    const layerId = obj.data?.layerId;
    if (!layerId) return;
    
    const canvas = fabricRef.current;

    const scaleX = obj.scaleX || 1;
    const scaleY = obj.scaleY || 1;
    const newWidth = (obj.width || 100) * scaleX;
    const newHeight = (obj.height || 100) * scaleY;
    
    // Check if this is a text object and calculate new fontSize synchronously
    const isTextObject = 'fontSize' in obj;
    const currentFabricFontSize = isTextObject ? (obj as any).fontSize : null;
    let newFontSize: number | null = null;
    
    if (isTextObject && currentFabricFontSize && (scaleX !== 1 || scaleY !== 1)) {
      const scaleFactor = Math.sqrt(scaleX * scaleY);
      newFontSize = Math.round(currentFabricFontSize * scaleFactor);
      newFontSize = Math.max(8, Math.min(256, newFontSize));
      console.log(`Text layer resized: fontSize ${currentFabricFontSize} → ${newFontSize} (scale: ${scaleFactor.toFixed(2)})`);
    }

    // Update React state
    setLayers((prev) =>
      prev.map((layer) => {
        if (layer.id !== layerId) return layer;

        const updates: Partial<SlideLayer> = {
          position: { x: obj.left || 0, y: obj.top || 0 },
          size: { width: newWidth, height: newHeight },
          rotation: obj.angle || 0,
        };

        // For text layers: update fontSize in state
        if (layer.type === "text" && layer.text && newFontSize !== null) {
          updates.text = {
            ...layer.text,
            style: {
              ...layer.text.style,
              fontSize: newFontSize,
            },
          };
        }

        return { ...layer, ...updates };
      })
    );

    // IMMEDIATELY update the Fabric object to prevent visual snap-back
    // Reset scale to 1 and apply new dimensions
    obj.set({ 
      scaleX: 1, 
      scaleY: 1,
      width: newWidth,
      height: newHeight,
    });
    
    // For text objects: also update fontSize on the Fabric object
    if (newFontSize !== null && isTextObject) {
      (obj as any).set({ fontSize: newFontSize });
    }
    
    // Force immediate re-render to apply changes
    if (canvas) {
      canvas.renderAll();
    }
  }, []);

  // Initialize Fabric canvas
  // We add `isLoading` to dependencies because when loading completes, the canvas element
  // appears in the DOM and we need to initialize Fabric.js on it.
  useEffect(() => {
    // Skip if loading (canvas not in DOM yet) or already initialized
    if (isLoading || !canvasRef.current || fabricRef.current) return;

    const canvas = new Canvas(canvasRef.current, {
      width: 1920,
      height: 1080,
      backgroundColor: "#000000",
      selection: true,
      preserveObjectStacking: true,
      enableRetinaScaling: false,
    });

    fabricRef.current = canvas;

    // Handle object selection
    canvas.on("selection:created", (e: { selected?: FabricObject[] }) => {
      const obj = e.selected?.[0];
      if (obj?.data?.layerId) {
        setSelectedLayerId(obj.data.layerId);
      }
    });

    canvas.on("selection:updated", (e: { selected?: FabricObject[] }) => {
      const obj = e.selected?.[0];
      if (obj?.data?.layerId) {
        setSelectedLayerId(obj.data.layerId);
      }
    });

    canvas.on("selection:cleared", () => {
      setSelectedLayerId(null);
    });

    // Handle object modifications
    canvas.on("object:modified", (e: { target?: FabricObject }) => {
      const obj = e.target;
      if (obj?.data?.layerId) {
        updateLayerFromFabricObj(obj);
        setIsDirty(true);
      }
    });

    canvas.on("object:moving", () => setIsDirty(true));
    canvas.on("object:scaling", () => setIsDirty(true));
    canvas.on("object:rotating", () => setIsDirty(true));

    return () => {
      canvas.dispose();
      fabricRef.current = null;
    };
  }, [isLoading, updateLayerFromFabricObj]);

  // Load background image
  // Depends on isLoading to ensure canvas is initialized first
  useEffect(() => {
    const canvas = fabricRef.current;
    if (isLoading || !canvas || !slideImageUrl) return;

    const bgGen = ++bgGenRef.current;
    let cancelled = false;
    let blobUrl: string | null = null;

    const applyBackgroundFromUrl = async (url: string) => {
      const img = await FabricImage.fromURL(url);
      if (cancelled || bgGen !== bgGenRef.current) return;

      img.set({
        selectable: false,
        evented: false,
      });
      const scaleX = (canvas.width || 1920) / (img.width || 1);
      const scaleY = (canvas.height || 1080) / (img.height || 1);
      img.scale(Math.min(scaleX, scaleY));
      canvas.backgroundImage = img;
      canvas.renderAll();
    };

    const loadBackground = async () => {
      const baseImageUrl = api.getSlideImageUrl(slideImageUrl);
      // Bust any cached responses that may have been stored without proper CORS headers.
      const imageUrl = `${baseImageUrl}${baseImageUrl.includes("?") ? "&" : "?"}cb=${Date.now()}`;

      try {
        // Prefer a credentialed fetch so the canvas is not tainted (works when CORS is properly configured)
        const response = await fetch(imageUrl, { credentials: "include", cache: "no-store" });
        if (!response.ok) {
          throw new Error(`Failed to fetch image: ${response.status}`);
        }

        const blob = await response.blob();
        blobUrl = URL.createObjectURL(blob);
        await applyBackgroundFromUrl(blobUrl);
      } catch (err) {
        // Fallback: load directly via <img> (no CORS), but this may taint the canvas for export APIs
        console.warn("Background fetch failed; falling back to direct image load:", err);
        try {
          await applyBackgroundFromUrl(imageUrl);
        } catch (err2) {
          console.error("Failed to load background image:", err2);
        }
      } finally {
        if (blobUrl) {
          URL.revokeObjectURL(blobUrl);
          blobUrl = null;
        }
      }
    };

    loadBackground();

    return () => {
      cancelled = true;
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
        blobUrl = null;
      }
    };
  }, [isLoading, slideImageUrl]);

  // Get text content for current language
  const getTextForLanguage = useCallback((layer: SlideLayer): string => {
    if (!layer.text) return "Text";
    
    // If base language or no translation, use base content
    if (selectedLang === baseLanguage || !layer.text.isTranslatable) {
      return layer.text.baseContent || "Text";
    }
    
    // Try to get translation
    const translation = layer.text.translations?.[selectedLang];
    return translation || layer.text.baseContent || "Text";
  }, [selectedLang, baseLanguage]);

  // Calculate font size for shrinkFont overflow mode
  const calculateShrunkFontSize = useCallback((
    text: string,
    maxWidth: number,
    maxHeight: number,
    baseFontSize: number,
    minFontSize: number,
    fontFamily: string,
    fontWeight: string,
    lineHeight: number
  ): number => {
    // Create temporary canvas context for text measurement
    const tempCanvas = document.createElement("canvas");
    const ctx = tempCanvas.getContext("2d");
    if (!ctx) return baseFontSize;

    let fontSize = baseFontSize;
    const step = 1;

    while (fontSize > minFontSize) {
      ctx.font = `${fontWeight} ${fontSize}px ${fontFamily}`;
      
      // Split text into lines and calculate total height
      const words = text.split(" ");
      let lines = 1;
      let currentLineWidth = 0;
      
      for (const word of words) {
        const wordWidth = ctx.measureText(word + " ").width;
        if (currentLineWidth + wordWidth > maxWidth && currentLineWidth > 0) {
          lines++;
          currentLineWidth = wordWidth;
        } else {
          currentLineWidth += wordWidth;
        }
      }
      
      const totalHeight = lines * fontSize * lineHeight;
      
      if (totalHeight <= maxHeight) {
        return fontSize;
      }
      
      fontSize -= step;
    }

    return minFontSize;
  }, []);

  // Create Fabric text object with overflow handling
  const createTextObject = useCallback((layer: SlideLayer): Textbox => {
    const style = layer.text?.style || {};
    console.log("createTextObject - layer.text.style:", JSON.stringify(style));
    console.log("createTextObject - style.color:", style.color);
    const textContent = getTextForLanguage(layer);
    // Default to expandHeight so user-selected fontSize is preserved.
    // shrinkFont can still be enabled explicitly per-layer.
    const overflow = layer.text?.overflow || "expandHeight";
    const minFontSize = layer.text?.minFontSize || 12;
    
    let fontSize = style.fontSize || 24;
    const fontFamily = style.fontFamily || "Inter";
    const fontWeight = (style.fontWeight || "normal") as string;
    const lineHeight = style.lineHeight || 1.4;

    // Handle shrinkFont overflow
    if (overflow === "shrinkFont" && textContent.length > 0) {
      fontSize = calculateShrunkFontSize(
        textContent,
        layer.size.width,
        layer.size.height,
        fontSize,
        minFontSize,
        fontFamily,
        fontWeight,
        lineHeight
      );
    }

    const textbox = new Textbox(textContent, {
      left: layer.position.x,
      top: layer.position.y,
      width: layer.size.width,
      fontSize,
      fontFamily,
      fontWeight,
      fontStyle: (style.fontStyle || "normal") as string,
      fill: style.color || "#000000",
      textAlign: style.align || "left",
      opacity: layer.opacity ?? 1,
      angle: layer.rotation || 0,
      lineHeight,
    });

    // Handle different overflow modes
    if (overflow === "clip") {
      // Clip to a fixed height
      textbox.set({ height: layer.size.height });

      // Fabric doesn't automatically clip text by height, so add a clipPath
      const clipRect = new Rect({
        left: 0,
        top: 0,
        originX: "left",
        originY: "top",
        width: layer.size.width,
        height: layer.size.height,
      });
      // Avoid interaction with clip object
      clipRect.set({ selectable: false, evented: false } as any);
      textbox.set({ clipPath: clipRect } as any);
    } else {
      // Ensure no leftover clipPath when switching modes/languages
      textbox.set({ clipPath: undefined } as any);
    }
    // For "expandHeight", Fabric's default behavior handles it (no height limit)

    return textbox;
  }, [getTextForLanguage, calculateShrunkFontSize]);

  // Create Fabric plate (rect) object
  const createPlateObject = useCallback((layer: SlideLayer): Rect => {
    const plate = layer.plate!;
    return new Rect({
      left: layer.position.x,
      top: layer.position.y,
      width: layer.size.width,
      height: layer.size.height,
      fill: plate.backgroundColor,
      opacity: (layer.opacity ?? 1) * (plate.backgroundOpacity ?? 1),
      rx: plate.borderRadius || 0,
      ry: plate.borderRadius || 0,
      stroke: plate.border?.color,
      strokeWidth: plate.border?.width || 0,
      angle: layer.rotation || 0,
    });
  }, []);

  // Create Fabric image object (async)
  // Accepts renderGen to prevent ghost images when canvas has been re-rendered
  const createImageObject = useCallback(async (
    layer: SlideLayer, 
    canvas: Canvas,
    renderGen: number
  ) => {
    const imageUrl = api.getAssetUrl(layer.image?.assetUrl || "");
    if (!imageUrl) return;

    try {
      // Fetch image with credentials (cookies) for authenticated access
      const response = await fetch(imageUrl, {
        credentials: "include",
      });
      
      if (!response.ok) {
        throw new Error(`Failed to fetch image: ${response.status}`);
      }
      
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      
      const img = await FabricImage.fromURL(blobUrl);
      
      // Clean up blob URL
      URL.revokeObjectURL(blobUrl);
      
      // CRITICAL: Check if this render generation is still current
      // If not, the canvas has been cleared and re-rendered, so skip adding this stale image
      if (renderGen !== renderGenRef.current) {
        return;
      }
      
      img.set({
        left: layer.position.x,
        top: layer.position.y,
        scaleX: layer.size.width / (img.width || 1),
        scaleY: layer.size.height / (img.height || 1),
        opacity: layer.opacity ?? 1,
        angle: layer.rotation || 0,
        selectable: !layer.locked,
        evented: !layer.locked,
      });
      img.data = { layerId: layer.id };
      canvas.add(img);
      // Fix z-order: async images load later, so explicitly move to correct position
      // moveTo uses 0-based index in canvas objects array
      const zIndex = layer.zIndex ?? 0;
      // Fabric typings don't always expose moveTo on FabricImage; use a safe runtime call.
      if (typeof (canvas as any).moveObjectTo === "function") {
        (canvas as any).moveObjectTo(img, zIndex);
      } else if (typeof (img as any).moveTo === "function") {
        (img as any).moveTo(zIndex);
      }
      canvas.renderAll();
    } catch (err) {
      console.error("Failed to load image:", err);
    }
  }, []);

  // Render layers to canvas
  const renderLayersToCanvas = useCallback((layersToRender: SlideLayer[], restoreSelectionId?: string | null) => {
    const canvas = fabricRef.current;
    if (!canvas) return;

    // Increment render generation to invalidate any in-flight async image loads
    renderGenRef.current += 1;
    const currentGen = renderGenRef.current;

    // Remove existing layer objects (keep background)
    const objects = canvas.getObjects().filter((obj: FabricObject) => obj.data?.layerId);
    objects.forEach((obj: FabricObject) => canvas.remove(obj));

    // Sort by zIndex and render (be defensive if older data lacks zIndex)
    const sorted = [...layersToRender].sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));

    sorted.forEach((layer) => {
      // Use strict equality - undefined/missing visible should be treated as true (visible)
      if (layer.visible === false) return;

      let obj: FabricObject | null = null;

      if (layer.type === "text" && layer.text) {
        obj = createTextObject(layer);
      } else if (layer.type === "plate" && layer.plate) {
        obj = createPlateObject(layer);
      } else if (layer.type === "image" && layer.image) {
        createImageObject(layer, canvas, currentGen);
        return; // Async, handled separately
      }

      if (obj) {
        obj.data = { layerId: layer.id };
        obj.selectable = !layer.locked;
        obj.evented = !layer.locked;
        canvas.add(obj);
      }
    });

    canvas.renderAll();
    
    // Restore selection after re-render to prevent selection loss
    if (restoreSelectionId) {
      const objToSelect = canvas.getObjects().find(
        (o: FabricObject) => o.data?.layerId === restoreSelectionId
      );
      if (objToSelect) {
        canvas.setActiveObject(objToSelect);
        canvas.renderAll();
      }
    }
  }, [createTextObject, createPlateObject, createImageObject]);

  // Load layers from scene - but don't overwrite unsaved local changes
  useEffect(() => {
    if (!scene?.layers) return;
    // Skip if we have unsaved changes - don't overwrite user's work
    if (isDirty) return;
    setLayers(scene.layers);
    // Don't pass selection here - it will be set when user interacts
    renderLayersToCanvas(scene.layers);
  }, [scene, renderLayersToCanvas, isDirty]);

  // Re-render when language changes - preserve selection
  useEffect(() => {
    if (layers.length > 0) {
      renderLayersToCanvas(layers, selectedLayerId);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLang]); // Only trigger on language change, not on every layer/selection update

  // Apply zoom by resizing the canvas element (CSS-only) while keeping the internal coordinate system fixed (1920×1080).
  // This avoids pointer/selection drift caused by changing internal dimensions.
  // Note: We include isLoading in deps to re-apply zoom after canvas is initialized.
  useEffect(() => {
    const canvas = fabricRef.current;
    if (!canvas) return;

    // Keep internal coords stable (no viewport zoom).
    canvas.setZoom(1);

    // Resize DOM element only.
    canvas.setDimensions({ width: 1920 * zoom, height: 1080 * zoom }, { cssOnly: true });

    // Recompute offsets so mouse mapping stays correct after CSS resize.
    canvas.calcOffset();
    canvas.renderAll();
  }, [zoom, isLoading]);

  // Select layer in canvas (moved here so addLayer can use it)
  const selectLayerInCanvas = useCallback((layerId: string) => {
    const canvas = fabricRef.current;
    if (!canvas) return;
    
    const obj = canvas.getObjects().find((o: FabricObject) => o.data?.layerId === layerId);
    if (obj) {
      canvas.setActiveObject(obj);
      canvas.renderAll();
    }
    setSelectedLayerId(layerId);
  }, []);

  // Add new layer
  const addLayer = useCallback((type: "text" | "plate" | "image", assetUrl?: string) => {
    const newLayer: SlideLayer = {
      id: generateLayerId(),
      type,
      name: `${type.charAt(0).toUpperCase() + type.slice(1)} ${layers.length + 1}`,
      position: { x: 100, y: 100 },
      size: { width: type === "text" ? 400 : 300, height: type === "text" ? 60 : 200 },
      visible: true,
      locked: false,
      zIndex: layers.length,
    };

    if (type === "text") {
      newLayer.text = {
        baseContent: "New Text",
        translations: {},
        isTranslatable: true,
        style: {
          fontFamily: "Inter",
          fontSize: 32,
          fontWeight: "normal",
          fontStyle: "normal",
          color: "#FFFFFF",
          align: "left",
          verticalAlign: "top",
          lineHeight: 1.4,
        },
      };
    } else if (type === "plate") {
      newLayer.plate = {
        backgroundColor: "#FFFFFF",
        backgroundOpacity: 0.9,
        borderRadius: 12,
        padding: { top: 16, right: 16, bottom: 16, left: 16 },
      };
    } else if (type === "image" && assetUrl) {
      newLayer.image = {
        assetId: "",
        assetUrl,
        fit: "contain",
      };
    }

    const newLayers = [...layers, newLayer];
    setLayers(newLayers);
    // Render and restore selection to the new layer
    renderLayersToCanvas(newLayers, newLayer.id);
    setSelectedLayerId(newLayer.id);
    // Also select on canvas to show selection handles
    setTimeout(() => selectLayerInCanvas(newLayer.id), 0);
    setIsDirty(true);
  }, [layers, renderLayersToCanvas, selectLayerInCanvas]);

  // Update layer - preserves selection
  const updateLayer = useCallback((layerId: string, updates: Partial<SlideLayer>) => {
    console.log("updateLayer called with:", layerId, JSON.stringify(updates));
    setLayers(prev => {
      const newLayers = prev.map(l => l.id === layerId ? { ...l, ...updates } : l);
      const updatedLayer = newLayers.find(l => l.id === layerId);
      console.log("Updated layer text.style:", JSON.stringify(updatedLayer?.text?.style));
      renderLayersToCanvas(newLayers, layerId);
      return newLayers;
    });
    setIsDirty(true);
  }, [renderLayersToCanvas]);

  // Delete layer
  const deleteLayer = useCallback((layerId: string) => {
    setLayers(prev => {
      const newLayers = prev.filter(l => l.id !== layerId);
      renderLayersToCanvas(newLayers);
      return newLayers;
    });
    if (selectedLayerId === layerId) {
      setSelectedLayerId(null);
    }
    setIsDirty(true);
  }, [selectedLayerId, renderLayersToCanvas]);

  // Reorder layers - preserves current selection
  const reorderLayers = useCallback((newOrder: SlideLayer[]) => {
    const reindexed = newOrder.map((l, i) => ({ ...l, zIndex: i }));
    setLayers(reindexed);
    renderLayersToCanvas(reindexed, selectedLayerId);
    setIsDirty(true);
  }, [renderLayersToCanvas, selectedLayerId]);

  // Save scene
  const handleSave = useCallback(() => {
    saveMutation.mutate(layers);
  }, [layers, saveMutation]);

  const selectedLayer = layers.find(l => l.id === selectedLayerId);
  const previewLayers = isDirty ? layers : (resolvedScene?.layers ?? layers);

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-[#1a1a1a]">
      {/* Toolbar */}
      <div className="h-12 bg-[#252525] border-b border-[#333] px-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => addLayer("text")}
            className="text-white/70 hover:text-white hover:bg-white/10"
          >
            <Type className="w-4 h-4 mr-1" />
            Text
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => addLayer("plate")}
            className="text-white/70 hover:text-white hover:bg-white/10"
          >
            <Square className="w-4 h-4 mr-1" />
            Plate
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowAssetLibrary(true)}
            className="text-white/70 hover:text-white hover:bg-white/10"
          >
            <ImageIcon className="w-4 h-4 mr-1" />
            Image
          </Button>
          
          <div className="w-px h-6 bg-[#444] mx-2" />

          {/* Language Switcher */}
          {availableLanguages.length > 0 && (
            <div className="relative">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowLangDropdown(!showLangDropdown)}
                className="text-white/70 hover:text-white hover:bg-white/10 gap-1"
              >
                <Languages className="w-4 h-4" />
                {getLanguageName(selectedLang)}
                <ChevronDown className="w-3 h-3" />
              </Button>
              
              {showLangDropdown && (
                <>
                  <div 
                    className="fixed inset-0 z-40" 
                    onClick={() => setShowLangDropdown(false)} 
                  />
                  <div className="absolute top-full left-0 mt-1 bg-[#333] border border-[#444] rounded-md shadow-lg z-50 min-w-[140px] py-1">
                    {[baseLanguage, ...availableLanguages.filter(l => l !== baseLanguage)].map(lang => (
                      <button
                        key={lang}
                        onClick={() => {
                          setSelectedLang(lang);
                          setShowLangDropdown(false);
                        }}
                        className={`w-full px-3 py-1.5 text-left text-sm hover:bg-white/10 flex items-center justify-between ${
                          selectedLang === lang ? "text-primary" : "text-white/80"
                        }`}
                      >
                        <span>{getLanguageName(lang)}</span>
                        {lang === baseLanguage && (
                          <span className="text-[10px] text-white/50 ml-2">base</span>
                        )}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {/* Translate button */}
          {selectedLang !== baseLanguage && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => translateMutation.mutate(selectedLang)}
              disabled={translateMutation.isPending}
              className="text-white/70 hover:text-white hover:bg-white/10"
              title={`Translate text layers to ${getLanguageName(selectedLang)}`}
            >
              {translateMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Languages className="w-4 h-4" />
              )}
              Translate
            </Button>
          )}

          <div className="w-px h-6 bg-[#444] mx-2" />

          <Button
            variant={showAnimationPreview ? "default" : "ghost"}
            size="sm"
            onClick={() => setShowAnimationPreview(!showAnimationPreview)}
            className={showAnimationPreview ? "" : "text-white/70 hover:text-white hover:bg-white/10"}
          >
            <PlayCircle className="w-4 h-4 mr-1" />
            Preview
          </Button>
          
          <div className="w-px h-6 bg-[#444] mx-2" />
          
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setZoom(z => Math.max(0.25, z - 0.1))}
              className="text-white/70 hover:text-white hover:bg-white/10 w-8 h-8"
            >
              <ZoomOut className="w-4 h-4" />
            </Button>
            <span className="text-white/70 text-xs w-12 text-center">{Math.round(zoom * 100)}%</span>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setZoom(z => Math.min(1.5, z + 0.1))}
              className="text-white/70 hover:text-white hover:bg-white/10 w-8 h-8"
            >
              <ZoomIn className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setZoom(0.5)}
              className="text-white/70 hover:text-white hover:bg-white/10 w-8 h-8"
            >
              <Maximize2 className="w-4 h-4" />
            </Button>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isDirty && (
            <span className="text-xs text-yellow-500 mr-2">Unsaved changes</span>
          )}
          <Button
            variant="default"
            size="sm"
            onClick={handleSave}
            disabled={saveMutation.isPending || !isDirty}
          >
            <Save className="w-4 h-4 mr-1" />
            {saveMutation.isPending ? "Saving..." : "Save"}
          </Button>
          {onClose && (
            <Button variant="ghost" size="sm" onClick={onClose} className="text-white/70 hover:text-white">
              Close
            </Button>
          )}
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Layer panel */}
        <LayerPanel
          layers={layers}
          selectedLayerId={selectedLayerId}
          onSelectLayer={selectLayerInCanvas}
          onUpdateLayer={updateLayer}
          onDeleteLayer={deleteLayer}
          onReorderLayers={reorderLayers}
        />

        {/* Canvas area */}
        <div 
          ref={containerRef}
          className="flex-1 overflow-auto bg-[#1a1a1a] flex items-center justify-center p-8"
        >
          <div className="shadow-2xl" style={{ width: 1920 * zoom, height: 1080 * zoom }}>
            <canvas ref={canvasRef} />
          </div>
        </div>

        {/* Properties panel */}
        <div className="flex flex-col">
          <PropertiesPanel
            layer={selectedLayer}
            onUpdateLayer={(updates) => selectedLayerId && updateLayer(selectedLayerId, updates)}
          />
          
          {/* Animation Preview Panel */}
          {showAnimationPreview && (
            <div className="w-72 border-t border-[#333]">
              <AnimationPreview
                layers={previewLayers}
                duration={10}
              />
            </div>
          )}
        </div>
      </div>

      {/* Asset Library Modal */}
      {showAssetLibrary && (
        <AssetLibrary
          projectId={projectId}
          onSelect={(asset) => {
            addLayer("image", asset.url);
            setShowAssetLibrary(false);
          }}
          onClose={() => setShowAssetLibrary(false)}
        />
      )}
    </div>
  );
}
