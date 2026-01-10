"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { SlideLayer, AnimationConfig, LayerAnimation } from "@/lib/api";
import { Button } from "@/components/ui";
import { Play, Pause, RotateCcw, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

interface AnimationPreviewProps {
  layers: SlideLayer[];
  duration?: number; // Total slide duration in seconds
  onTimeUpdate?: (time: number) => void;
}

export function AnimationPreview({ layers, duration = 10, onTimeUpdate }: AnimationPreviewProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const animationFrameRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number>(0);

  // Animation loop
  useEffect(() => {
    if (!isPlaying) {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
      return;
    }

    lastTimeRef.current = performance.now();

    const animate = (now: number) => {
      const delta = (now - lastTimeRef.current) / 1000;
      lastTimeRef.current = now;

      setCurrentTime((prev) => {
        const newTime = prev + delta;
        if (newTime >= duration) {
          setIsPlaying(false);
          return duration;
        }
        return newTime;
      });

      animationFrameRef.current = requestAnimationFrame(animate);
    };

    animationFrameRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [isPlaying, duration]);

  // Notify parent of time updates
  useEffect(() => {
    onTimeUpdate?.(currentTime);
  }, [currentTime, onTimeUpdate]);

  const handlePlayPause = () => {
    if (currentTime >= duration) {
      setCurrentTime(0);
    }
    setIsPlaying(!isPlaying);
  };

  const handleReset = () => {
    setIsPlaying(false);
    setCurrentTime(0);
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    setCurrentTime(time);
    setIsPlaying(false);
  };

  return (
    <div className="bg-[#1a1a1a] border border-[#333] rounded-lg overflow-hidden">
      {/* Preview Controls */}
      <div className="px-3 py-2 bg-[#252525] border-b border-[#333] flex items-center gap-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={handlePlayPause}
          className="h-7 px-2"
        >
          {isPlaying ? (
            <Pause className="w-4 h-4" />
          ) : (
            <Play className="w-4 h-4" />
          )}
        </Button>
        
        <Button
          variant="ghost"
          size="sm"
          onClick={handleReset}
          className="h-7 px-2"
        >
          <RotateCcw className="w-3 h-3" />
        </Button>

        {/* Timeline slider */}
        <div className="flex-1 flex items-center gap-2">
          <input
            type="range"
            min={0}
            max={duration}
            step={0.01}
            value={currentTime}
            onChange={handleSeek}
            className="flex-1 h-1.5 bg-[#444] rounded-full appearance-none cursor-pointer
              [&::-webkit-slider-thumb]:appearance-none
              [&::-webkit-slider-thumb]:w-3
              [&::-webkit-slider-thumb]:h-3
              [&::-webkit-slider-thumb]:rounded-full
              [&::-webkit-slider-thumb]:bg-primary
              [&::-webkit-slider-thumb]:cursor-pointer"
          />
        </div>

        {/* Time display */}
        <div className="flex items-center gap-1 text-xs text-white/60 min-w-[60px]">
          <Clock className="w-3 h-3" />
          <span>{formatTime(currentTime)} / {formatTime(duration)}</span>
        </div>
      </div>

      {/* Layer animation states */}
      <div className="p-3 space-y-1 max-h-48 overflow-y-auto">
        {layers.length === 0 ? (
          <p className="text-xs text-white/40 text-center py-2">No layers to animate</p>
        ) : (
          layers.map((layer) => (
            <LayerAnimationState
              key={layer.id}
              layer={layer}
              currentTime={currentTime}
              duration={duration}
            />
          ))
        )}
      </div>
    </div>
  );
}

// Individual layer animation state indicator
interface LayerAnimationStateProps {
  layer: SlideLayer;
  currentTime: number;
  duration: number;
}

function LayerAnimationState({ layer, currentTime, duration }: LayerAnimationStateProps) {
  const animation = layer.animation || {};
  const entranceState = getAnimationState(animation.entrance, currentTime, "entrance");
  const exitState = getAnimationState(animation.exit, currentTime, "exit", duration);

  const currentState = exitState !== "idle" ? exitState : entranceState;

  return (
    <div className="flex items-center gap-2 px-2 py-1 rounded bg-[#2a2a2a]">
      {/* State indicator */}
      <div
        className={cn(
          "w-2 h-2 rounded-full",
          currentState === "idle" && "bg-white/20",
          currentState === "animating" && "bg-green-400 animate-pulse",
          currentState === "complete" && "bg-blue-400",
          currentState === "hidden" && "bg-red-400/50"
        )}
      />
      
      {/* Layer name */}
      <span className="flex-1 text-xs text-white/70 truncate">{layer.name}</span>

      {/* Animation badges */}
      <div className="flex items-center gap-1">
        {animation.entrance?.type && animation.entrance.type !== "none" && (
          <span className="px-1.5 py-0.5 text-[9px] rounded bg-green-500/20 text-green-400">
            {animation.entrance.type}
          </span>
        )}
        {animation.exit?.type && animation.exit.type !== "none" && (
          <span className="px-1.5 py-0.5 text-[9px] rounded bg-red-500/20 text-red-400">
            {animation.exit.type}
          </span>
        )}
      </div>
    </div>
  );
}

// Calculate animation state based on current time
function getAnimationState(
  config: AnimationConfig | undefined,
  currentTime: number,
  type: "entrance" | "exit",
  slideDuration?: number
): "idle" | "animating" | "complete" | "hidden" {
  if (!config || config.type === "none") {
    return type === "entrance" ? "complete" : "idle";
  }

  const trigger = config.trigger;
  let triggerTime = 0;

  // Calculate trigger time based on trigger type
  switch (trigger.type) {
    case "start":
      triggerTime = trigger.offsetSeconds || 0;
      break;
    case "end":
      triggerTime = (slideDuration || 10) + (trigger.offsetSeconds || 0);
      break;
    case "time":
      triggerTime = trigger.seconds || 0;
      break;
    case "marker":
    case "word":
      // For marker/word triggers, we'd need the actual timing data
      // For preview, we'll default to a calculated position
      triggerTime = trigger.seconds || (type === "entrance" ? 0 : slideDuration || 10);
      break;
    default:
      triggerTime = 0;
  }

  const delay = config.delay || 0;
  const animationDuration = config.duration || 0.3;
  
  const startTime = triggerTime + delay;
  const endTime = startTime + animationDuration;

  if (currentTime < startTime) {
    return type === "entrance" ? "hidden" : "idle";
  } else if (currentTime >= startTime && currentTime < endTime) {
    return "animating";
  } else {
    return type === "entrance" ? "complete" : "hidden";
  }
}

// Format time as mm:ss.ms
function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 10);
  return `${mins}:${secs.toString().padStart(2, "0")}.${ms}`;
}

// CSS keyframe generation for canvas layers
export function getLayerAnimationStyle(
  layer: SlideLayer,
  currentTime: number,
  slideDuration: number = 10
): React.CSSProperties {
  const animation = layer.animation || {};
  
  // Check entrance animation
  if (animation.entrance && animation.entrance.type !== "none") {
    const state = getAnimationState(animation.entrance, currentTime, "entrance");
    if (state === "hidden") {
      return { opacity: 0, visibility: "hidden" };
    }
    if (state === "animating") {
      return getAnimatingStyle(animation.entrance, currentTime, "entrance");
    }
  }

  // Check exit animation
  if (animation.exit && animation.exit.type !== "none") {
    const state = getAnimationState(animation.exit, currentTime, "exit", slideDuration);
    if (state === "animating") {
      return getAnimatingStyle(animation.exit, currentTime, "exit", slideDuration);
    }
    if (state === "hidden") {
      return { opacity: 0, visibility: "hidden" };
    }
  }

  return { opacity: 1 };
}

// Calculate in-progress animation style
function getAnimatingStyle(
  config: AnimationConfig,
  currentTime: number,
  type: "entrance" | "exit",
  slideDuration?: number
): React.CSSProperties {
  const trigger = config.trigger;
  let triggerTime = 0;

  switch (trigger.type) {
    case "start":
      triggerTime = trigger.offsetSeconds || 0;
      break;
    case "end":
      triggerTime = (slideDuration || 10) + (trigger.offsetSeconds || 0);
      break;
    case "time":
      triggerTime = trigger.seconds || 0;
      break;
    default:
      triggerTime = type === "entrance" ? 0 : slideDuration || 10;
  }

  const delay = config.delay || 0;
  const animDuration = config.duration || 0.3;
  const startTime = triggerTime + delay;
  
  // Progress from 0 to 1
  let progress = Math.min(1, Math.max(0, (currentTime - startTime) / animDuration));
  
  // Apply easing
  progress = applyEasing(progress, config.easing || "easeOut");

  // For exit animations, reverse progress
  if (type === "exit") {
    progress = 1 - progress;
  }

  // Calculate style based on animation type
  switch (config.type) {
    case "fadeIn":
    case "fadeOut":
      return { opacity: progress };
    
    case "slideLeft":
      return { 
        opacity: progress,
        transform: `translateX(${(1 - progress) * (type === "entrance" ? 100 : -100)}px)`,
      };
    
    case "slideRight":
      return { 
        opacity: progress,
        transform: `translateX(${(1 - progress) * (type === "entrance" ? -100 : 100)}px)`,
      };
    
    case "slideUp":
      return { 
        opacity: progress,
        transform: `translateY(${(1 - progress) * (type === "entrance" ? 50 : -50)}px)`,
      };
    
    case "slideDown":
      return { 
        opacity: progress,
        transform: `translateY(${(1 - progress) * (type === "entrance" ? -50 : 50)}px)`,
      };
    
    default:
      return { opacity: progress };
  }
}

// Easing functions
function applyEasing(t: number, easing: AnimationConfig["easing"]): number {
  switch (easing) {
    case "linear":
      return t;
    case "easeIn":
      return t * t;
    case "easeOut":
      return 1 - (1 - t) * (1 - t);
    case "easeInOut":
      return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    default:
      return t;
  }
}

