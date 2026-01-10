"use client";

import { useState } from "react";
import { SlideLayer, TextContent, PlateContent, AnimationConfig, AnimationTrigger, LayerAnimation } from "@/lib/api";
import { Input, Slider } from "@/components/ui";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronRight, Zap, Play, Square } from "lucide-react";

// Animation type options
const ANIMATION_TYPES = [
  { value: "none", label: "None" },
  { value: "fadeIn", label: "Fade In" },
  { value: "fadeOut", label: "Fade Out" },
  { value: "slideLeft", label: "Slide Left" },
  { value: "slideRight", label: "Slide Right" },
  { value: "slideUp", label: "Slide Up" },
  { value: "slideDown", label: "Slide Down" },
] as const;

const ENTRANCE_TYPES = ANIMATION_TYPES.filter(t => 
  ["none", "fadeIn", "slideLeft", "slideRight", "slideUp", "slideDown"].includes(t.value)
);

const EXIT_TYPES = ANIMATION_TYPES.filter(t => 
  ["none", "fadeOut", "slideLeft", "slideRight", "slideUp", "slideDown"].includes(t.value)
);

const EASING_OPTIONS = [
  { value: "linear", label: "Linear" },
  { value: "easeIn", label: "Ease In" },
  { value: "easeOut", label: "Ease Out" },
  { value: "easeInOut", label: "Ease In Out" },
] as const;

const TRIGGER_TYPES = [
  { value: "start", label: "Slide Start" },
  { value: "end", label: "Slide End" },
  { value: "time", label: "Time (sec)" },
  { value: "marker", label: "Marker" },
  { value: "word", label: "Word" },
] as const;

interface PropertiesPanelProps {
  layer: SlideLayer | undefined;
  onUpdateLayer: (updates: Partial<SlideLayer>) => void;
}

export function PropertiesPanel({ layer, onUpdateLayer }: PropertiesPanelProps) {
  if (!layer) {
    return (
      <div className="w-72 bg-[#252525] border-l border-[#333] flex flex-col">
        <div className="h-10 px-3 flex items-center border-b border-[#333]">
          <span className="text-xs font-medium text-white/70 uppercase tracking-wider">Properties</span>
        </div>
        <div className="flex-1 flex items-center justify-center p-4 text-white/40 text-xs text-center">
          Select a layer to edit its properties
        </div>
      </div>
    );
  }

  const updateText = (updates: Partial<TextContent>) => {
    if (!layer.text) return;
    onUpdateLayer({
      text: { ...layer.text, ...updates },
    });
  };

  const updateTextStyle = (updates: Partial<NonNullable<TextContent["style"]>>) => {
    if (!layer.text) return;
    console.log("updateTextStyle called with:", updates);
    const newText = { ...layer.text, style: { ...layer.text.style, ...updates } };
    console.log("New text object:", newText);
    
    // Auto-adjust layer height when fontSize changes
    const layerUpdates: Partial<SlideLayer> = { text: newText };
    const newFontSize = updates.fontSize;
    if (newFontSize !== undefined) {
      const lineHeight = newText.style?.lineHeight || 1.4;
      const minHeight = newFontSize * lineHeight;
      // Only expand height, never shrink (user might have intentionally set a larger height)
      if (layer.size.height < minHeight) {
        layerUpdates.size = { ...layer.size, height: Math.ceil(minHeight) };
        console.log("Auto-expanding height to:", minHeight);
      }
    }
    
    onUpdateLayer(layerUpdates);
  };

  const updatePlate = (updates: Partial<PlateContent>) => {
    if (!layer.plate) return;
    onUpdateLayer({
      plate: { ...layer.plate, ...updates },
    });
  };

  return (
    <div className="w-72 bg-[#252525] border-l border-[#333] flex flex-col">
      <div className="h-10 px-3 flex items-center border-b border-[#333]">
        <span className="text-xs font-medium text-white/70 uppercase tracking-wider">Properties</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* General properties */}
        <Section title="General">
          <Field label="Name">
            <Input
              value={layer.name}
              onChange={(e) => onUpdateLayer({ name: e.target.value })}
              className="bg-[#333] border-[#444] text-white text-xs h-7"
            />
          </Field>
        </Section>

        {/* Transform */}
        <Section title="Transform">
          <div className="grid grid-cols-2 gap-2">
            <Field label="X">
              <Input
                type="number"
                value={Math.round(layer.position.x)}
                onChange={(e) => onUpdateLayer({ position: { ...layer.position, x: Number(e.target.value) } })}
                className="bg-[#333] border-[#444] text-white text-xs h-7"
              />
            </Field>
            <Field label="Y">
              <Input
                type="number"
                value={Math.round(layer.position.y)}
                onChange={(e) => onUpdateLayer({ position: { ...layer.position, y: Number(e.target.value) } })}
                className="bg-[#333] border-[#444] text-white text-xs h-7"
              />
            </Field>
            <Field label="Width">
              <Input
                type="number"
                value={Math.round(layer.size.width)}
                onChange={(e) => onUpdateLayer({ size: { ...layer.size, width: Number(e.target.value) } })}
                className="bg-[#333] border-[#444] text-white text-xs h-7"
              />
            </Field>
            <Field label="Height">
              <Input
                type="number"
                value={Math.round(layer.size.height)}
                onChange={(e) => onUpdateLayer({ size: { ...layer.size, height: Number(e.target.value) } })}
                className="bg-[#333] border-[#444] text-white text-xs h-7"
              />
            </Field>
          </div>
          <Field label="Rotation">
            <div className="flex items-center gap-2">
              <Slider
                value={layer.rotation || 0}
                min={-180}
                max={180}
                step={1}
                onChange={(e) => onUpdateLayer({ rotation: Number(e.target.value) })}
                className="flex-1"
                showValue={false}
              />
              <span className="text-xs text-white/60 w-8">{layer.rotation || 0}°</span>
            </div>
          </Field>
          <Field label="Opacity">
            <div className="flex items-center gap-2">
              <Slider
                value={Math.round((layer.opacity ?? 1) * 100)}
                min={0}
                max={100}
                step={1}
                onChange={(e) => onUpdateLayer({ opacity: Number(e.target.value) / 100 })}
                className="flex-1"
                showValue={false}
              />
              <span className="text-xs text-white/60 w-8">{Math.round((layer.opacity ?? 1) * 100)}%</span>
            </div>
          </Field>
        </Section>

        {/* Text properties */}
        {layer.type === "text" && layer.text && (
          <Section title="Text">
            <Field label="Content">
              <textarea
                value={layer.text.baseContent}
                onChange={(e) => updateText({ baseContent: e.target.value })}
                className="w-full bg-[#333] border border-[#444] rounded text-white text-xs p-2 min-h-[60px] resize-none focus:outline-none focus:border-primary"
              />
            </Field>
            <Field label="Font">
              <select
                value={layer.text.style?.fontFamily || "Inter"}
                onChange={(e) => updateTextStyle({ fontFamily: e.target.value })}
                className="w-full bg-[#333] border border-[#444] rounded text-white text-xs h-7 px-2 focus:outline-none focus:border-primary"
              >
                {/* Font list synced with render-service Docker image fonts */}
                <option value="Inter">Inter</option>
                <option value="Roboto">Roboto</option>
                <option value="Open Sans">Open Sans</option>
                <option value="Lato">Lato</option>
                <option value="DejaVu Sans">DejaVu Sans</option>
                <option value="Liberation Sans">Liberation Sans</option>
                <option value="Noto Sans">Noto Sans</option>
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Size">
                <select
                  value={layer.text.style?.fontSize || 24}
                  onChange={(e) => updateTextStyle({ fontSize: Number(e.target.value) })}
                  className="w-full bg-[#333] border border-[#444] rounded text-white text-xs h-7 px-2 focus:outline-none focus:border-primary"
                >
                  <option value="8">8</option>
                  <option value="9">9</option>
                  <option value="10">10</option>
                  <option value="11">11</option>
                  <option value="12">12</option>
                  <option value="14">14</option>
                  <option value="16">16</option>
                  <option value="18">18</option>
                  <option value="20">20</option>
                  <option value="24">24</option>
                  <option value="28">28</option>
                  <option value="32">32</option>
                  <option value="36">36</option>
                  <option value="48">48</option>
                  <option value="64">64</option>
                  <option value="72">72</option>
                  <option value="96">96</option>
                  <option value="128">128</option>
                </select>
              </Field>
              <Field label="Color">
                <div className="flex items-center gap-1">
                  <input
                    type="color"
                    value={layer.text.style?.color || "#000000"}
                    onChange={(e) => updateTextStyle({ color: e.target.value })}
                    className="w-7 h-7 rounded border border-[#444] bg-transparent cursor-pointer"
                  />
                  <Input
                    value={layer.text.style?.color || "#000000"}
                    onChange={(e) => updateTextStyle({ color: e.target.value })}
                    className="flex-1 bg-[#333] border-[#444] text-white text-xs h-7"
                  />
                </div>
              </Field>
            </div>
            <Field label="Style">
              <div className="flex items-center gap-1">
                <button
                  onClick={() => updateTextStyle({ 
                    fontWeight: layer.text?.style?.fontWeight === "bold" ? "normal" : "bold" 
                  })}
                  className={cn(
                    "w-7 h-7 rounded text-xs font-bold",
                    layer.text.style?.fontWeight === "bold" 
                      ? "bg-primary text-white" 
                      : "bg-[#333] text-white/60 hover:bg-[#444]"
                  )}
                >
                  B
                </button>
                <button
                  onClick={() => updateTextStyle({ 
                    fontStyle: layer.text?.style?.fontStyle === "italic" ? "normal" : "italic" 
                  })}
                  className={cn(
                    "w-7 h-7 rounded text-xs italic",
                    layer.text.style?.fontStyle === "italic" 
                      ? "bg-primary text-white" 
                      : "bg-[#333] text-white/60 hover:bg-[#444]"
                  )}
                >
                  I
                </button>
              </div>
            </Field>
            <Field label="Align">
              <div className="flex items-center gap-1">
                {(["left", "center", "right"] as const).map((align) => (
                  <button
                    key={align}
                    onClick={() => updateTextStyle({ align })}
                    className={cn(
                      "flex-1 h-7 rounded text-xs",
                      layer.text?.style?.align === align 
                        ? "bg-primary text-white" 
                        : "bg-[#333] text-white/60 hover:bg-[#444]"
                    )}
                  >
                    {align.charAt(0).toUpperCase() + align.slice(1)}
                  </button>
                ))}
              </div>
            </Field>
          </Section>
        )}

        {/* Plate properties */}
        {layer.type === "plate" && layer.plate && (
          <Section title="Plate">
            <Field label="Background">
              <div className="flex items-center gap-1">
                <input
                  type="color"
                  value={layer.plate.backgroundColor}
                  onChange={(e) => updatePlate({ backgroundColor: e.target.value })}
                  className="w-7 h-7 rounded border border-[#444] bg-transparent cursor-pointer"
                />
                <Input
                  value={layer.plate.backgroundColor}
                  onChange={(e) => updatePlate({ backgroundColor: e.target.value })}
                  className="flex-1 bg-[#333] border-[#444] text-white text-xs h-7"
                />
              </div>
            </Field>
            <Field label="Opacity">
              <div className="flex items-center gap-2">
                <Slider
                  value={Math.round((layer.plate.backgroundOpacity ?? 1) * 100)}
                  min={0}
                  max={100}
                  step={1}
                  onChange={(e) => updatePlate({ backgroundOpacity: Number(e.target.value) / 100 })}
                  className="flex-1"
                  showValue={false}
                />
                <span className="text-xs text-white/60 w-8">
                  {Math.round((layer.plate.backgroundOpacity ?? 1) * 100)}%
                </span>
              </div>
            </Field>
            <Field label="Corner Radius">
              <div className="flex items-center gap-2">
                <Slider
                  value={layer.plate.borderRadius || 0}
                  min={0}
                  max={50}
                  step={1}
                  onChange={(e) => updatePlate({ borderRadius: Number(e.target.value) })}
                  className="flex-1"
                  showValue={false}
                />
                <span className="text-xs text-white/60 w-8">{layer.plate.borderRadius || 0}px</span>
              </div>
            </Field>
          </Section>
        )}

        {/* Image properties */}
        {layer.type === "image" && layer.image && (
          <Section title="Image">
            <Field label="Fit">
              <select
                value={layer.image.fit || "contain"}
                onChange={(e) => onUpdateLayer({ 
                  image: { ...layer.image!, fit: e.target.value as "contain" | "cover" | "fill" } 
                })}
                className="w-full bg-[#333] border border-[#444] rounded text-white text-xs h-7 px-2 focus:outline-none focus:border-primary"
              >
                <option value="contain">Contain</option>
                <option value="cover">Cover</option>
                <option value="fill">Fill</option>
              </select>
            </Field>
          </Section>
        )}

        {/* Animation properties */}
        <AnimationSection layer={layer} onUpdateLayer={onUpdateLayer} />
      </div>
    </div>
  );
}

// Helper components
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-[#333]">
      <div className="px-3 py-2 text-[10px] font-medium text-white/50 uppercase tracking-wider">
        {title}
      </div>
      <div className="px-3 pb-3 space-y-3">
        {children}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-[10px] text-white/50">{label}</label>
      {children}
    </div>
  );
}

// Animation Section Component
interface AnimationSectionProps {
  layer: SlideLayer;
  onUpdateLayer: (updates: Partial<SlideLayer>) => void;
}

function AnimationSection({ layer, onUpdateLayer }: AnimationSectionProps) {
  const [entranceOpen, setEntranceOpen] = useState(true);
  const [exitOpen, setExitOpen] = useState(false);

  const animation = layer.animation || {};
  const entrance = animation.entrance;
  const exit = animation.exit;

  const updateAnimation = (updates: Partial<LayerAnimation>) => {
    onUpdateLayer({
      animation: { ...animation, ...updates },
    });
  };

  const updateEntrance = (updates: Partial<AnimationConfig>) => {
    const current = entrance || createDefaultAnimation("fadeIn", "start");
    updateAnimation({
      entrance: { ...current, ...updates },
    });
  };

  const updateExit = (updates: Partial<AnimationConfig>) => {
    const current = exit || createDefaultAnimation("fadeOut", "end");
    updateAnimation({
      exit: { ...current, ...updates },
    });
  };

  const updateEntranceTrigger = (updates: Partial<AnimationTrigger>) => {
    const current = entrance || createDefaultAnimation("fadeIn", "start");
    updateAnimation({
      entrance: { ...current, trigger: { ...current.trigger, ...updates } },
    });
  };

  const updateExitTrigger = (updates: Partial<AnimationTrigger>) => {
    const current = exit || createDefaultAnimation("fadeOut", "end");
    updateAnimation({
      exit: { ...current, trigger: { ...current.trigger, ...updates } },
    });
  };

  return (
    <div className="border-b border-[#333]">
      <div className="px-3 py-2 text-[10px] font-medium text-white/50 uppercase tracking-wider flex items-center gap-1">
        <Zap className="w-3 h-3" />
        Animation
      </div>
      
      <div className="px-3 pb-3 space-y-2">
        {/* Entrance Animation */}
        <div className="bg-[#2a2a2a] rounded border border-[#3a3a3a]">
          <button
            onClick={() => setEntranceOpen(!entranceOpen)}
            className="w-full px-2 py-1.5 flex items-center gap-2 text-xs text-white/80 hover:bg-white/5"
          >
            {entranceOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            <Play className="w-3 h-3 text-green-400" />
            <span>Entrance</span>
            {entrance?.type && entrance.type !== "none" && (
              <span className="ml-auto text-[10px] text-white/40">{entrance.type}</span>
            )}
          </button>
          
          {entranceOpen && (
            <div className="px-2 pb-2 space-y-2 border-t border-[#3a3a3a]">
              <AnimationConfigUI
                config={entrance}
                types={ENTRANCE_TYPES}
                onUpdateConfig={updateEntrance}
                onUpdateTrigger={updateEntranceTrigger}
              />
            </div>
          )}
        </div>

        {/* Exit Animation */}
        <div className="bg-[#2a2a2a] rounded border border-[#3a3a3a]">
          <button
            onClick={() => setExitOpen(!exitOpen)}
            className="w-full px-2 py-1.5 flex items-center gap-2 text-xs text-white/80 hover:bg-white/5"
          >
            {exitOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            <Square className="w-3 h-3 text-red-400" />
            <span>Exit</span>
            {exit?.type && exit.type !== "none" && (
              <span className="ml-auto text-[10px] text-white/40">{exit.type}</span>
            )}
          </button>
          
          {exitOpen && (
            <div className="px-2 pb-2 space-y-2 border-t border-[#3a3a3a]">
              <AnimationConfigUI
                config={exit}
                types={EXIT_TYPES}
                onUpdateConfig={updateExit}
                onUpdateTrigger={updateExitTrigger}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Animation Config UI
interface AnimationConfigUIProps {
  config: AnimationConfig | undefined;
  types: readonly { value: string; label: string }[];
  onUpdateConfig: (updates: Partial<AnimationConfig>) => void;
  onUpdateTrigger: (updates: Partial<AnimationTrigger>) => void;
}

function AnimationConfigUI({ config, types, onUpdateConfig, onUpdateTrigger }: AnimationConfigUIProps) {
  const trigger = config?.trigger;

  return (
    <div className="space-y-2 pt-2">
      {/* Animation Type */}
      <div className="space-y-1">
        <label className="text-[10px] text-white/40">Effect</label>
        <select
          value={config?.type || "none"}
          onChange={(e) => onUpdateConfig({ type: e.target.value as AnimationConfig["type"] })}
          className="w-full bg-[#333] border border-[#444] rounded text-white text-xs h-6 px-1.5 focus:outline-none focus:border-primary"
        >
          {types.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      {config?.type && config.type !== "none" && (
        <>
          {/* Duration & Delay */}
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <label className="text-[10px] text-white/40">Duration</label>
              <div className="flex items-center gap-1">
                <Input
                  type="number"
                  step={0.1}
                  min={0}
                  value={config.duration ?? 0.3}
                  onChange={(e) => onUpdateConfig({ duration: Number(e.target.value) })}
                  className="bg-[#333] border-[#444] text-white text-xs h-6 w-full"
                />
                <span className="text-[10px] text-white/40">s</span>
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-white/40">Delay</label>
              <div className="flex items-center gap-1">
                <Input
                  type="number"
                  step={0.1}
                  min={0}
                  value={config.delay ?? 0}
                  onChange={(e) => onUpdateConfig({ delay: Number(e.target.value) })}
                  className="bg-[#333] border-[#444] text-white text-xs h-6 w-full"
                />
                <span className="text-[10px] text-white/40">s</span>
              </div>
            </div>
          </div>

          {/* Easing */}
          <div className="space-y-1">
            <label className="text-[10px] text-white/40">Easing</label>
            <select
              value={config.easing || "easeOut"}
              onChange={(e) => onUpdateConfig({ easing: e.target.value as AnimationConfig["easing"] })}
              className="w-full bg-[#333] border border-[#444] rounded text-white text-xs h-6 px-1.5 focus:outline-none focus:border-primary"
            >
              {EASING_OPTIONS.map((e) => (
                <option key={e.value} value={e.value}>{e.label}</option>
              ))}
            </select>
          </div>

          {/* Trigger */}
          <div className="space-y-1">
            <label className="text-[10px] text-white/40">Trigger</label>
            <select
              value={trigger?.type || "start"}
              onChange={(e) => onUpdateTrigger({ type: e.target.value as AnimationTrigger["type"] })}
              className="w-full bg-[#333] border border-[#444] rounded text-white text-xs h-6 px-1.5 focus:outline-none focus:border-primary"
            >
              {TRIGGER_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {/* Trigger-specific fields */}
          {trigger?.type === "time" && (
            <div className="space-y-1">
              <label className="text-[10px] text-white/40">Time (seconds)</label>
              <Input
                type="number"
                step={0.1}
                min={0}
                value={trigger.seconds ?? 0}
                onChange={(e) => onUpdateTrigger({ seconds: Number(e.target.value) })}
                className="bg-[#333] border-[#444] text-white text-xs h-6"
              />
            </div>
          )}

          {(trigger?.type === "start" || trigger?.type === "end") && (
            <div className="space-y-1">
              <label className="text-[10px] text-white/40">Offset (seconds)</label>
              <Input
                type="number"
                step={0.1}
                value={trigger.offsetSeconds ?? 0}
                onChange={(e) => onUpdateTrigger({ offsetSeconds: Number(e.target.value) })}
                className="bg-[#333] border-[#444] text-white text-xs h-6"
              />
            </div>
          )}

          {trigger?.type === "marker" && (
            <div className="space-y-1">
              <label className="text-[10px] text-white/40">Marker ID</label>
              <Input
                type="text"
                placeholder="Select marker..."
                value={trigger.markerId || ""}
                onChange={(e) => onUpdateTrigger({ markerId: e.target.value })}
                className="bg-[#333] border-[#444] text-white text-xs h-6"
              />
              <p className="text-[9px] text-white/30">Use Markers panel to create markers</p>
            </div>
          )}

          {trigger?.type === "word" && (
            <div className="space-y-1">
              <label className="text-[10px] text-white/40">Word</label>
              <Input
                type="text"
                placeholder="Click word in script..."
                value={trigger.wordText || ""}
                onChange={(e) => onUpdateTrigger({ wordText: e.target.value })}
                className="bg-[#333] border-[#444] text-white text-xs h-6"
              />
              <p className="text-[9px] text-white/30">Click a word in script editor</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// Helper: create default animation config
function createDefaultAnimation(type: AnimationConfig["type"], triggerType: AnimationTrigger["type"]): AnimationConfig {
  return {
    type,
    duration: 0.3,
    delay: 0,
    easing: "easeOut",
    trigger: { type: triggerType },
  };
}

