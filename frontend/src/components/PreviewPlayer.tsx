"use client";

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { Play, Pause, SkipBack, SkipForward, Volume2, VolumeX, X, Maximize2, Minimize2 } from "lucide-react";
import { SlideWithScripts, api } from "@/lib/api";

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
  const [currentSlideIdx, setCurrentSlideIdx] = useState(0);
  
  const voiceAudioRef = useRef<HTMLAudioElement | null>(null);
  const musicAudioRef = useRef<HTMLAudioElement | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const playStartTimeRef = useRef<number>(0);
  const playStartPositionRef = useRef<number>(0);

  // Build timeline from slides (memoized)
  const timeline = useMemo(() => {
    const items: TimelineItem[] = [];
    let cumulativeTime = 0;
    
    const sortedSlides = [...slides].sort((a, b) => a.slide_index - b.slide_index);
    
    for (const slide of sortedSlides) {
      const audio = slide.audio_files?.find(a => a.lang === lang);
      const duration = audio?.duration_sec || 3; // Default 3 sec for slides without audio
      
      // Convert relative URLs to full URLs
      const imageUrl = api.getSlideImageUrl(slide.image_url);
      const audioUrl = audio?.audio_url ? `${api.getSlideImageUrl(audio.audio_url).replace('/static/slides/', '/static/audio/')}` : null;
      
      items.push({
        slideIndex: slide.slide_index,
        imageUrl,
        audioUrl: audio?.audio_url ? api.getSlideImageUrl(audio.audio_url) : null,
        duration,
        startTime: cumulativeTime,
      });
      
      cumulativeTime += duration;
    }
    
    return items;
  }, [slides, lang]);

  const totalDuration = useMemo(() => {
    return timeline.reduce((acc, item) => acc + item.duration, 0);
  }, [timeline]);

  const currentSlide = timeline[currentSlideIdx];

  // Find slide index for a given time
  const getSlideIndexForTime = useCallback((time: number): number => {
    for (let i = timeline.length - 1; i >= 0; i--) {
      if (time >= timeline[i].startTime) {
        return i;
      }
    }
    return 0;
  }, [timeline]);

  // Stop all audio
  const stopAllAudio = useCallback(() => {
    if (voiceAudioRef.current) {
      voiceAudioRef.current.pause();
      voiceAudioRef.current.src = "";
    }
    if (musicAudioRef.current) {
      musicAudioRef.current.pause();
    }
  }, []);

  // Play voice audio for a slide
  const playVoiceForSlide = useCallback((slideIdx: number, seekOffset: number = 0) => {
    const slide = timeline[slideIdx];
    if (!slide?.audioUrl) return;

    // Create new audio element for each play to avoid issues
    if (voiceAudioRef.current) {
      voiceAudioRef.current.pause();
      voiceAudioRef.current.src = "";
    }
    
    const audio = new Audio(slide.audioUrl);
    audio.volume = isMuted ? 0 : (voiceVolume / 100);
    
    if (seekOffset > 0 && seekOffset < slide.duration) {
      audio.currentTime = seekOffset;
    }
    
    voiceAudioRef.current = audio;
    audio.play().catch(err => console.log("Voice play failed:", err));
  }, [timeline, isMuted, voiceVolume]);

  // Animation loop for smooth playback
  const updatePlayback = useCallback(() => {
    if (!isPlaying) return;

    const elapsed = (performance.now() - playStartTimeRef.current) / 1000;
    const newTime = Math.min(playStartPositionRef.current + elapsed, totalDuration);
    
    setCurrentTime(newTime);
    
    // Check if we need to change slides
    const newSlideIdx = getSlideIndexForTime(newTime);
    setCurrentSlideIdx(prev => {
      if (prev !== newSlideIdx) {
        // New slide - play its audio
        playVoiceForSlide(newSlideIdx);
        return newSlideIdx;
      }
      return prev;
    });
    
    // Check if playback ended
    if (newTime >= totalDuration) {
      setIsPlaying(false);
      stopAllAudio();
      return;
    }
    
    animationFrameRef.current = requestAnimationFrame(updatePlayback);
  }, [isPlaying, totalDuration, getSlideIndexForTime, playVoiceForSlide, stopAllAudio]);

  // Start/stop playback
  useEffect(() => {
    if (isPlaying) {
      playStartTimeRef.current = performance.now();
      playStartPositionRef.current = currentTime;
      
      // Start voice for current slide
      const slideIdx = getSlideIndexForTime(currentTime);
      const slide = timeline[slideIdx];
      const offsetInSlide = currentTime - slide.startTime;
      playVoiceForSlide(slideIdx, offsetInSlide);
      
      // Start music
      if (musicUrl && musicAudioRef.current) {
        musicAudioRef.current.currentTime = currentTime % (musicAudioRef.current.duration || 1);
        musicAudioRef.current.volume = isMuted ? 0 : (musicVolume / 100);
        musicAudioRef.current.play().catch(err => console.log("Music play failed:", err));
      }
      
      // Start animation loop
      animationFrameRef.current = requestAnimationFrame(updatePlayback);
    } else {
      // Stop everything
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
      stopAllAudio();
    }

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [isPlaying]);

  // Initialize music audio element
  useEffect(() => {
    if (musicUrl) {
      const audio = new Audio(musicUrl);
      audio.loop = true;
      audio.volume = musicVolume / 100;
      audio.preload = "auto";
      musicAudioRef.current = audio;
    }
    
    return () => {
      stopAllAudio();
    };
  }, [musicUrl]);

  // Update volumes
  useEffect(() => {
    if (voiceAudioRef.current) {
      voiceAudioRef.current.volume = isMuted ? 0 : (voiceVolume / 100);
    }
    if (musicAudioRef.current) {
      musicAudioRef.current.volume = isMuted ? 0 : (musicVolume / 100);
    }
  }, [isMuted, voiceVolume, musicVolume]);

  // Seek to position
  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newTime = parseFloat(e.target.value);
    setCurrentTime(newTime);
    
    const newSlideIdx = getSlideIndexForTime(newTime);
    setCurrentSlideIdx(newSlideIdx);
    
    if (isPlaying) {
      playStartTimeRef.current = performance.now();
      playStartPositionRef.current = newTime;
      
      const slide = timeline[newSlideIdx];
      const offsetInSlide = newTime - slide.startTime;
      playVoiceForSlide(newSlideIdx, offsetInSlide);
      
      if (musicAudioRef.current) {
        musicAudioRef.current.currentTime = newTime % (musicAudioRef.current.duration || 1);
      }
    }
  };

  // Skip to prev/next slide
  const skipToPrevSlide = () => {
    const prevIdx = Math.max(0, currentSlideIdx - 1);
    const newTime = timeline[prevIdx].startTime;
    setCurrentTime(newTime);
    setCurrentSlideIdx(prevIdx);
    
    if (isPlaying) {
      playStartTimeRef.current = performance.now();
      playStartPositionRef.current = newTime;
      playVoiceForSlide(prevIdx);
    }
  };

  const skipToNextSlide = () => {
    const nextIdx = Math.min(timeline.length - 1, currentSlideIdx + 1);
    const newTime = timeline[nextIdx].startTime;
    setCurrentTime(newTime);
    setCurrentSlideIdx(nextIdx);
    
    if (isPlaying) {
      playStartTimeRef.current = performance.now();
      playStartPositionRef.current = newTime;
      playVoiceForSlide(nextIdx);
    }
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const togglePlay = () => {
    if (currentTime >= totalDuration) {
      setCurrentTime(0);
      setCurrentSlideIdx(0);
    }
    setIsPlaying(!isPlaying);
  };

  return (
    <div className={`
      bg-card border border-border rounded-lg shadow-lg overflow-hidden
      transition-all duration-300 flex flex-col
      ${isExpanded ? "fixed inset-4 z-50" : "w-full"}
    `}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-muted/50 border-b border-border shrink-0">
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
            onClick={() => { stopAllAudio(); onClose(); }}
            className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            title="Close preview"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Slide Display */}
      <div className={`
        relative bg-black flex items-center justify-center flex-1
        ${isExpanded ? "" : "aspect-video"}
      `}>
        {currentSlide && (
          <img
            src={currentSlide.imageUrl}
            alt={`Slide ${currentSlide.slideIndex + 1}`}
            className="max-w-full max-h-full object-contain"
            key={currentSlide.slideIndex}
          />
        )}
        {/* Slide counter */}
        <div className="absolute bottom-2 right-2 bg-black/60 text-white text-xs px-2 py-1 rounded">
          {currentSlideIdx + 1} / {timeline.length}
        </div>
        {/* Audio indicator */}
        {currentSlide?.audioUrl && (
          <div className="absolute bottom-2 left-2 bg-black/60 text-white text-xs px-2 py-1 rounded flex items-center gap-1">
            <Volume2 className="w-3 h-3" />
            <span>Audio</span>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="p-3 bg-card shrink-0">
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
