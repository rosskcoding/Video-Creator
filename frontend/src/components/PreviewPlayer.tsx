"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Play, Pause, SkipBack, SkipForward, Volume2, VolumeX, X, Maximize2, Minimize2 } from "lucide-react";
import { SlideWithScripts } from "@/lib/api";

interface PreviewPlayerProps {
  slides: SlideWithScripts[];
  lang: string;
  musicUrl?: string;
  musicVolume?: number; // 0-100
  voiceVolume?: number; // 0-100
  onClose: () => void;
}

interface TimelineItem {
  slideIndex: number;
  imageUrl: string;
  audioUrl: string | null;
  duration: number; // seconds
  startTime: number; // cumulative start time
}

export function PreviewPlayer({
  slides,
  lang,
  musicUrl,
  musicVolume = 30,
  voiceVolume = 100,
  onClose,
}: PreviewPlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  
  const voiceAudioRef = useRef<HTMLAudioElement | null>(null);
  const musicAudioRef = useRef<HTMLAudioElement | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const currentSlideIndexRef = useRef(0);

  // Build timeline from slides
  const timeline: TimelineItem[] = [];
  let cumulativeTime = 0;
  
  const sortedSlides = [...slides].sort((a, b) => a.slide_index - b.slide_index);
  
  for (const slide of sortedSlides) {
    const audio = slide.audio_files?.find(a => a.lang === lang);
    const duration = audio?.duration_sec || 3; // Default 3 sec for slides without audio
    
    timeline.push({
      slideIndex: slide.slide_index,
      imageUrl: slide.image_url,
      audioUrl: audio?.audio_url || null,
      duration,
      startTime: cumulativeTime,
    });
    
    cumulativeTime += duration;
  }

  const totalDuration = cumulativeTime;

  // Find current slide based on currentTime
  const getCurrentSlideIndex = useCallback((time: number): number => {
    for (let i = timeline.length - 1; i >= 0; i--) {
      if (time >= timeline[i].startTime) {
        return i;
      }
    }
    return 0;
  }, [timeline]);

  const currentSlideIdx = getCurrentSlideIndex(currentTime);
  const currentSlide = timeline[currentSlideIdx];

  // Play audio for current slide
  const playSlideAudio = useCallback((slideIdx: number) => {
    const slide = timeline[slideIdx];
    if (!slide) return;

    // Stop previous audio
    if (voiceAudioRef.current) {
      voiceAudioRef.current.pause();
      voiceAudioRef.current.currentTime = 0;
    }

    // Play new audio if exists
    if (slide.audioUrl) {
      voiceAudioRef.current = new Audio(slide.audioUrl);
      voiceAudioRef.current.volume = isMuted ? 0 : (voiceVolume / 100);
      voiceAudioRef.current.play().catch(() => {});
    }
  }, [timeline, isMuted, voiceVolume]);

  // Main playback loop
  useEffect(() => {
    if (isPlaying) {
      const startTimestamp = Date.now();
      const startTime = currentTime;

      timerRef.current = setInterval(() => {
        const elapsed = (Date.now() - startTimestamp) / 1000;
        const newTime = startTime + elapsed;
        
        if (newTime >= totalDuration) {
          setCurrentTime(totalDuration);
          setIsPlaying(false);
          return;
        }

        setCurrentTime(newTime);

        // Check if we need to switch slides
        const newSlideIdx = getCurrentSlideIndex(newTime);
        if (newSlideIdx !== currentSlideIndexRef.current) {
          currentSlideIndexRef.current = newSlideIdx;
          playSlideAudio(newSlideIdx);
        }
      }, 50);

      // Start audio for current slide
      playSlideAudio(getCurrentSlideIndex(currentTime));

      // Start background music
      if (musicUrl && musicAudioRef.current) {
        musicAudioRef.current.currentTime = currentTime;
        musicAudioRef.current.volume = isMuted ? 0 : (musicVolume / 100);
        musicAudioRef.current.play().catch(() => {});
      }
    } else {
      // Pause everything
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      if (voiceAudioRef.current) {
        voiceAudioRef.current.pause();
      }
      if (musicAudioRef.current) {
        musicAudioRef.current.pause();
      }
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [isPlaying, currentTime, totalDuration, getCurrentSlideIndex, playSlideAudio, musicUrl, isMuted, musicVolume]);

  // Update volumes when changed
  useEffect(() => {
    if (voiceAudioRef.current) {
      voiceAudioRef.current.volume = isMuted ? 0 : (voiceVolume / 100);
    }
    if (musicAudioRef.current) {
      musicAudioRef.current.volume = isMuted ? 0 : (musicVolume / 100);
    }
  }, [isMuted, voiceVolume, musicVolume]);

  // Initialize music audio
  useEffect(() => {
    if (musicUrl) {
      musicAudioRef.current = new Audio(musicUrl);
      musicAudioRef.current.loop = true;
      musicAudioRef.current.volume = musicVolume / 100;
    }
    return () => {
      if (musicAudioRef.current) {
        musicAudioRef.current.pause();
        musicAudioRef.current = null;
      }
      if (voiceAudioRef.current) {
        voiceAudioRef.current.pause();
        voiceAudioRef.current = null;
      }
    };
  }, [musicUrl, musicVolume]);

  // Seek to position
  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newTime = parseFloat(e.target.value);
    setCurrentTime(newTime);
    currentSlideIndexRef.current = getCurrentSlideIndex(newTime);
    
    if (isPlaying) {
      playSlideAudio(currentSlideIndexRef.current);
      if (musicAudioRef.current) {
        musicAudioRef.current.currentTime = newTime;
      }
    }
  };

  // Skip to prev/next slide
  const skipToPrevSlide = () => {
    const prevIdx = Math.max(0, currentSlideIdx - 1);
    const newTime = timeline[prevIdx].startTime;
    setCurrentTime(newTime);
    currentSlideIndexRef.current = prevIdx;
    if (isPlaying) playSlideAudio(prevIdx);
  };

  const skipToNextSlide = () => {
    const nextIdx = Math.min(timeline.length - 1, currentSlideIdx + 1);
    const newTime = timeline[nextIdx].startTime;
    setCurrentTime(newTime);
    currentSlideIndexRef.current = nextIdx;
    if (isPlaying) playSlideAudio(nextIdx);
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const togglePlay = () => {
    if (currentTime >= totalDuration) {
      setCurrentTime(0);
      currentSlideIndexRef.current = 0;
    }
    setIsPlaying(!isPlaying);
  };

  return (
    <div className={`
      bg-card border border-border rounded-lg shadow-lg overflow-hidden
      transition-all duration-300
      ${isExpanded ? "fixed inset-4 z-50" : "w-full"}
    `}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-muted/50 border-b border-border">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Preview ({lang.toUpperCase()})
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            title={isExpanded ? "Minimize" : "Expand"}
          >
            {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            title="Close preview"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Slide Display */}
      <div className={`
        relative bg-black flex items-center justify-center
        ${isExpanded ? "flex-1 h-[calc(100%-120px)]" : "aspect-video"}
      `}>
        {currentSlide && (
          <img
            src={currentSlide.imageUrl}
            alt={`Slide ${currentSlide.slideIndex + 1}`}
            className="max-w-full max-h-full object-contain transition-opacity duration-500"
            key={currentSlide.slideIndex}
          />
        )}
        {/* Slide counter */}
        <div className="absolute bottom-2 right-2 bg-black/60 text-white text-xs px-2 py-1 rounded">
          {currentSlideIdx + 1} / {timeline.length}
        </div>
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
            max={totalDuration}
            step={0.1}
            value={currentTime}
            onChange={handleSeek}
            className="flex-1 h-1.5 bg-muted rounded-full appearance-none cursor-pointer
              [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3
              [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full
              [&::-webkit-slider-thumb]:shadow-sm [&::-webkit-slider-thumb]:cursor-pointer"
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
            title="Previous slide"
          >
            <SkipBack className="w-4 h-4" />
          </button>
          
          <button
            onClick={togglePlay}
            className="p-3 rounded-full bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-md"
            title={isPlaying ? "Pause" : "Play"}
          >
            {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
          </button>
          
          <button
            onClick={skipToNextSlide}
            className="p-2 rounded-full hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            title="Next slide"
          >
            <SkipForward className="w-4 h-4" />
          </button>

          <div className="w-px h-6 bg-border mx-2" />

          <button
            onClick={() => setIsMuted(!isMuted)}
            className="p-2 rounded-full hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            title={isMuted ? "Unmute" : "Mute"}
          >
            {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}

