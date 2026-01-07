"use client";

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { Play, Pause, SkipBack, SkipForward, Volume2, VolumeX, X, Maximize2, Minimize2, Loader2 } from "lucide-react";
import { SlideWithScripts } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

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
  audioElement?: HTMLAudioElement | null;
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
  const [isLoading, setIsLoading] = useState(true);
  const [loadProgress, setLoadProgress] = useState(0);
  const [preloadedAudio, setPreloadedAudio] = useState<Map<number, HTMLAudioElement>>(new Map());
  
  const musicAudioRef = useRef<HTMLAudioElement | null>(null);
  const currentVoiceRef = useRef<HTMLAudioElement | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const playStartTimeRef = useRef<number>(0);
  const playStartPositionRef = useRef<number>(0);

  // Build URL helper
  const getFullUrl = (url: string) => {
    if (!url) return "";
    if (url.startsWith("http")) return url;
    return `${API_URL}${url}`;
  };

  // Build timeline from slides (memoized)
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

  const totalDuration = useMemo(() => {
    return timeline.reduce((acc, item) => acc + item.duration, 0);
  }, [timeline]);

  const currentSlide = timeline[currentSlideIdx];

  // Preload all audio files
  useEffect(() => {
    setIsLoading(true);
    setLoadProgress(0);
    
    const audioItems = timeline.filter(t => t.audioUrl);
    const totalToLoad = audioItems.length + (musicUrl ? 1 : 0);
    
    if (totalToLoad === 0) {
      setIsLoading(false);
      return;
    }
    
    let loaded = 0;
    const audioMap = new Map<number, HTMLAudioElement>();
    
    const onLoad = () => {
      loaded++;
      setLoadProgress(Math.round((loaded / totalToLoad) * 100));
      if (loaded >= totalToLoad) {
        setPreloadedAudio(audioMap);
        setIsLoading(false);
      }
    };
    
    const onError = (url: string) => {
      console.error("Failed to load audio:", url);
      loaded++;
      setLoadProgress(Math.round((loaded / totalToLoad) * 100));
      if (loaded >= totalToLoad) {
        setPreloadedAudio(audioMap);
        setIsLoading(false);
      }
    };
    
    // Preload voice audio
    timeline.forEach((item, idx) => {
      if (item.audioUrl) {
        const audio = new Audio();
        audio.preload = "auto";
        audio.oncanplaythrough = onLoad;
        audio.onerror = () => onError(item.audioUrl!);
        audio.src = item.audioUrl;
        audioMap.set(idx, audio);
      }
    });
    
    // Preload music
    if (musicUrl) {
      const music = new Audio();
      music.preload = "auto";
      music.loop = true;
      music.oncanplaythrough = onLoad;
      music.onerror = () => onError(musicUrl);
      music.src = musicUrl;
      musicAudioRef.current = music;
    }
    
    // Timeout fallback - start anyway after 5 seconds
    const timeout = setTimeout(() => {
      if (loaded < totalToLoad) {
        console.warn("Audio preload timeout, starting anyway");
        setPreloadedAudio(audioMap);
        setIsLoading(false);
      }
    }, 5000);
    
    return () => {
      clearTimeout(timeout);
      audioMap.forEach(audio => {
        audio.pause();
        audio.src = "";
      });
    };
  }, [timeline, musicUrl]);

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
    if (currentVoiceRef.current) {
      currentVoiceRef.current.pause();
      currentVoiceRef.current.currentTime = 0;
    }
    if (musicAudioRef.current) {
      musicAudioRef.current.pause();
    }
  }, []);

  // Play voice audio for a slide
  const playVoiceForSlide = useCallback((slideIdx: number, seekOffset: number = 0) => {
    // Stop current voice
    if (currentVoiceRef.current) {
      currentVoiceRef.current.pause();
      currentVoiceRef.current.currentTime = 0;
    }
    
    const audio = preloadedAudio.get(slideIdx);
    if (!audio) return;
    
    audio.volume = isMuted ? 0 : (voiceVolume / 100);
    audio.currentTime = seekOffset;
    currentVoiceRef.current = audio;
    
    audio.play().catch(err => console.log("Voice play error:", err));
  }, [preloadedAudio, isMuted, voiceVolume]);

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
    if (isPlaying && !isLoading) {
      playStartTimeRef.current = performance.now();
      playStartPositionRef.current = currentTime;
      
      // Start voice for current slide
      const slideIdx = getSlideIndexForTime(currentTime);
      const slide = timeline[slideIdx];
      const offsetInSlide = currentTime - slide.startTime;
      playVoiceForSlide(slideIdx, offsetInSlide);
      
      // Start music
      if (musicAudioRef.current) {
        musicAudioRef.current.currentTime = currentTime % (musicAudioRef.current.duration || 60);
        musicAudioRef.current.volume = isMuted ? 0 : (musicVolume / 100);
        musicAudioRef.current.play().catch(err => console.log("Music play error:", err));
      }
      
      // Start animation loop
      animationFrameRef.current = requestAnimationFrame(updatePlayback);
    } else {
      // Stop everything
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
      if (!isPlaying) {
        stopAllAudio();
      }
    }

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [isPlaying, isLoading]);

  // Update volumes
  useEffect(() => {
    if (currentVoiceRef.current) {
      currentVoiceRef.current.volume = isMuted ? 0 : (voiceVolume / 100);
    }
    if (musicAudioRef.current) {
      musicAudioRef.current.volume = isMuted ? 0 : (musicVolume / 100);
    }
  }, [isMuted, voiceVolume, musicVolume]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopAllAudio();
      preloadedAudio.forEach(audio => {
        audio.pause();
        audio.src = "";
      });
    };
  }, []);

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
        musicAudioRef.current.currentTime = newTime % (musicAudioRef.current.duration || 60);
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
      playStartPositionRef.current = nextIdx;
      playVoiceForSlide(nextIdx);
    }
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const togglePlay = () => {
    if (isLoading) return;
    
    if (currentTime >= totalDuration) {
      setCurrentTime(0);
      setCurrentSlideIdx(0);
    }
    setIsPlaying(!isPlaying);
  };

  // Count audio slides
  const audioCount = timeline.filter(t => t.audioUrl).length;

  return (
    <div className={`
      bg-card border border-border rounded-lg shadow-lg overflow-hidden
      transition-all duration-300 flex flex-col
      ${isExpanded ? "fixed inset-4 z-50" : "w-full"}
    `}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-muted/50 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Preview ({lang.toUpperCase()})
          </span>
          {audioCount > 0 && (
            <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
              {audioCount} audio
            </span>
          )}
        </div>
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
        {/* Loading overlay */}
        {isLoading && (
          <div className="absolute inset-0 bg-black/80 flex flex-col items-center justify-center z-10">
            <Loader2 className="w-8 h-8 text-primary animate-spin mb-2" />
            <span className="text-white text-sm">Loading audio... {loadProgress}%</span>
          </div>
        )}
        
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
          <div className="absolute bottom-2 left-2 bg-green-600/80 text-white text-xs px-2 py-1 rounded flex items-center gap-1">
            <Volume2 className="w-3 h-3" />
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
            disabled={isLoading}
            className="flex-1 h-1.5 bg-muted rounded-full appearance-none cursor-pointer disabled:opacity-50
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
            disabled={isLoading}
            className="p-2 rounded-full hover:bg-muted transition-colors text-muted-foreground hover:text-foreground disabled:opacity-50"
            title="Previous slide"
          >
            <SkipBack className="w-4 h-4" />
          </button>
          
          <button
            onClick={togglePlay}
            disabled={isLoading}
            className="p-3 rounded-full bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-md disabled:opacity-50"
            title={isPlaying ? "Pause" : "Play"}
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : isPlaying ? (
              <Pause className="w-5 h-5" />
            ) : (
              <Play className="w-5 h-5 ml-0.5" />
            )}
          </button>
          
          <button
            onClick={skipToNextSlide}
            disabled={isLoading}
            className="p-2 rounded-full hover:bg-muted transition-colors text-muted-foreground hover:text-foreground disabled:opacity-50"
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
