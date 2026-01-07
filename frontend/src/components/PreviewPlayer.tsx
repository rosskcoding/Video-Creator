"use client";

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { Play, Pause, SkipBack, SkipForward, Volume2, VolumeX, X, Maximize2, Minimize2 } from "lucide-react";
import { SlideWithScripts } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

interface PreviewPlayerProps {
  slides: SlideWithScripts[];
  lang: string;
  onClose: () => void;
}

interface TimelineItem {
  slideIndex: number;
  imageUrl: string;
  audioUrl: string | null;
  duration: number;
  startTime: number;
}

export function PreviewPlayer({ slides, lang, onClose }: PreviewPlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [currentSlideIdx, setCurrentSlideIdx] = useState(0);
  
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const slideStartTimeRef = useRef(0);

  // Build URL helper
  const getFullUrl = (url: string) => {
    if (!url) return "";
    if (url.startsWith("http")) return url;
    return `${API_URL}${url}`;
  };

  // Build timeline from slides
  const timeline = useMemo(() => {
    const items: TimelineItem[] = [];
    let cumulativeTime = 0;
    
    const sortedSlides = [...slides].sort((a, b) => a.slide_index - b.slide_index);
    
    for (const slide of sortedSlides) {
      const audio = slide.audio_files?.find(a => a.lang === lang);
      const duration = audio?.duration_sec || 3;
      
      items.push({
        slideIndex: slide.slide_index,
        imageUrl: getFullUrl(slide.image_url),
        audioUrl: audio?.audio_url ? getFullUrl(audio.audio_url) : null,
        duration,
        startTime: cumulativeTime,
      });
      
      cumulativeTime += duration;
    }
    
    return items;
  }, [slides, lang]);

  const totalDuration = timeline.reduce((acc, item) => acc + item.duration, 0);
  const currentSlide = timeline[currentSlideIdx];

  // Play audio for current slide
  const playCurrentSlideAudio = useCallback(() => {
    const slide = timeline[currentSlideIdx];
    if (!slide?.audioUrl) return;

    // Stop previous
    if (audioRef.current) {
      audioRef.current.pause();
    }

    const audio = new Audio(slide.audioUrl);
    audio.volume = isMuted ? 0 : 1;
    audioRef.current = audio;
    audio.play().catch(() => {});
  }, [currentSlideIdx, timeline, isMuted]);

  // Move to next slide
  const goToNextSlide = useCallback(() => {
    if (currentSlideIdx >= timeline.length - 1) {
      // End of presentation
      setIsPlaying(false);
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }
    
    setCurrentSlideIdx(prev => prev + 1);
    slideStartTimeRef.current = Date.now();
  }, [currentSlideIdx, timeline.length]);

  // Main playback effect
  useEffect(() => {
    if (!isPlaying) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (audioRef.current) {
        audioRef.current.pause();
      }
      return;
    }

    // Start playing current slide audio
    playCurrentSlideAudio();
    slideStartTimeRef.current = Date.now();

    // Check every 100ms if we need to move to next slide
    intervalRef.current = setInterval(() => {
      const elapsed = (Date.now() - slideStartTimeRef.current) / 1000;
      const slideDuration = timeline[currentSlideIdx]?.duration || 3;
      
      // Update time display
      const newTime = timeline[currentSlideIdx].startTime + elapsed;
      setCurrentTime(Math.min(newTime, totalDuration));
      
      if (elapsed >= slideDuration) {
        goToNextSlide();
      }
    }, 100);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isPlaying, currentSlideIdx]);

  // Play audio when slide changes during playback
  useEffect(() => {
    if (isPlaying) {
      playCurrentSlideAudio();
    }
  }, [currentSlideIdx, isPlaying]);

  // Update volume
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = isMuted ? 0 : 1;
    }
  }, [isMuted]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (audioRef.current) audioRef.current.pause();
    };
  }, []);

  const togglePlay = () => {
    if (currentSlideIdx >= timeline.length - 1 && currentTime >= totalDuration - 0.5) {
      // Restart from beginning
      setCurrentSlideIdx(0);
      setCurrentTime(0);
    }
    setIsPlaying(!isPlaying);
  };

  const skipToPrevSlide = () => {
    const newIdx = Math.max(0, currentSlideIdx - 1);
    setCurrentSlideIdx(newIdx);
    setCurrentTime(timeline[newIdx].startTime);
    slideStartTimeRef.current = Date.now();
  };

  const skipToNextSlide = () => {
    const newIdx = Math.min(timeline.length - 1, currentSlideIdx + 1);
    setCurrentSlideIdx(newIdx);
    setCurrentTime(timeline[newIdx].startTime);
    slideStartTimeRef.current = Date.now();
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newTime = parseFloat(e.target.value);
    setCurrentTime(newTime);
    
    // Find which slide this time belongs to
    for (let i = timeline.length - 1; i >= 0; i--) {
      if (newTime >= timeline[i].startTime) {
        setCurrentSlideIdx(i);
        slideStartTimeRef.current = Date.now() - ((newTime - timeline[i].startTime) * 1000);
        break;
      }
    }
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const audioCount = timeline.filter(t => t.audioUrl).length;

  return (
    <div className={`
      bg-card border border-border rounded-lg shadow-lg overflow-hidden flex flex-col
      ${isExpanded ? "fixed inset-4 z-50" : "w-full"}
    `}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-muted/50 border-b border-border">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Preview ({lang.toUpperCase()})
          </span>
          <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
            {audioCount}/{timeline.length} audio
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
          >
            {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
          <button
            onClick={() => { 
              if (audioRef.current) audioRef.current.pause();
              onClose(); 
            }}
            className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Slide Display */}
      <div className={`relative bg-black flex items-center justify-center flex-1 ${isExpanded ? "" : "aspect-video"}`}>
        {currentSlide && (
          <img
            src={currentSlide.imageUrl}
            alt={`Slide ${currentSlideIdx + 1}`}
            className="max-w-full max-h-full object-contain"
          />
        )}
        
        <div className="absolute bottom-2 right-2 bg-black/60 text-white text-xs px-2 py-1 rounded">
          {currentSlideIdx + 1} / {timeline.length}
        </div>
        
        {currentSlide?.audioUrl && (
          <div className="absolute bottom-2 left-2 bg-green-600/80 text-white text-xs px-2 py-1 rounded flex items-center gap-1">
            <Volume2 className="w-3 h-3" />
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="p-3 bg-card">
        {/* Progress bar */}
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs text-muted-foreground w-10 text-right font-mono">
            {formatTime(currentTime)}
          </span>
          <input
            type="range"
            min={0}
            max={totalDuration || 1}
            step={0.1}
            value={currentTime}
            onChange={handleSeek}
            className="flex-1 h-1.5 bg-muted rounded-full appearance-none cursor-pointer
              [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3
              [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full
              [&::-webkit-slider-thumb]:cursor-pointer"
          />
          <span className="text-xs text-muted-foreground w-10 font-mono">
            {formatTime(totalDuration)}
          </span>
        </div>

        {/* Playback controls */}
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={skipToPrevSlide}
            className="p-2 rounded-full hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
          >
            <SkipBack className="w-4 h-4" />
          </button>
          
          <button
            onClick={togglePlay}
            className="p-3 rounded-full bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-md"
          >
            {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
          </button>
          
          <button
            onClick={skipToNextSlide}
            className="p-2 rounded-full hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
          >
            <SkipForward className="w-4 h-4" />
          </button>

          <div className="w-px h-6 bg-border mx-2" />

          <button
            onClick={() => setIsMuted(!isMuted)}
            className="p-2 rounded-full hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
          >
            {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}
