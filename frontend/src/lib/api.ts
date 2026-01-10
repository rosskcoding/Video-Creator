import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

// CSRF token management
let csrfToken: string | null = null;

function getCsrfToken(): string | null {
  if (typeof window === "undefined") return null;
  
  // Try to get from cookie first (set by server)
  const match = document.cookie.match(/csrf_token=([^;]+)/);
  if (match) {
    csrfToken = match[1];
  }
  return csrfToken;
}

function setCsrfToken(token: string): void {
  csrfToken = token;
}

const client = axios.create({
  baseURL: `${API_URL}/api`,
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true, // Important: sends cookies with requests
});

// Add CSRF token to state-changing requests
client.interceptors.request.use((config) => {
  const method = config.method?.toUpperCase();
  
  // Add CSRF token for state-changing methods
  if (method && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const token = getCsrfToken();
    if (token) {
      config.headers["X-CSRF-Token"] = token;
    }
  }
  
  return config;
});

// Handle errors - 401 redirects to login, 403 may need CSRF refresh
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (typeof window !== "undefined") {
      if (error.response?.status === 401) {
        // Session expired or invalid - redirect to login
        if (!window.location.pathname.startsWith("/login")) {
          window.location.href = "/login";
        }
      } else if (error.response?.status === 403 && error.response?.data?.detail?.includes("CSRF")) {
        // CSRF token issue - try to refresh it (only once to prevent infinite loop)
        const originalRequest = error.config;
        if (originalRequest._csrfRetry) {
          // Already retried once, redirect to login
          window.location.href = "/login";
          return Promise.reject(error);
        }
        try {
          const response = await axios.get(`${API_URL}/api/auth/csrf-token`, {
            withCredentials: true,
          });
          setCsrfToken(response.data.csrf_token);
          // Mark as retried and retry the original request
          originalRequest._csrfRetry = true;
          originalRequest.headers["X-CSRF-Token"] = response.data.csrf_token;
          return axios(originalRequest);
        } catch {
          // CSRF refresh failed, redirect to login
          window.location.href = "/login";
        }
      } else if (!error.response && error.code === "ERR_NETWORK") {
        // Network error - server is unreachable
        error.isNetworkError = true;
        error.message = "Server is unavailable. Please check if the backend is running.";
      }
    }
    return Promise.reject(error);
  }
);

// Auth functions
export async function login(username: string, password: string): Promise<{ success: boolean; error?: string }> {
  try {
    const response = await client.post("/auth/login", { username, password });
    // Store CSRF token from response
    if (response.data.csrf_token) {
      setCsrfToken(response.data.csrf_token);
    }
    return { success: true };
  } catch (error: any) {
    return { 
      success: false, 
      error: error.response?.data?.detail || "Login failed" 
    };
  }
}

export async function logout(): Promise<void> {
  try {
    await client.post("/auth/logout");
  } catch {
    // Ignore errors on logout
  }
  csrfToken = null;
}

export async function isAuthenticated(): Promise<boolean> {
  try {
    await client.get("/auth/me");
    return true;
  } catch {
    return false;
  }
}

// Legacy functions for backwards compatibility (deprecated)
/** @deprecated Use login() instead */
export function setAuth(username: string, password: string): void {
  // No-op: credentials are now handled via httpOnly cookies
  console.warn("setAuth is deprecated. Use login() instead.");
}

/** @deprecated Use logout() instead */
export function clearAuth(): void {
  // No-op: use logout() instead
  console.warn("clearAuth is deprecated. Use logout() instead.");
}

// Types
export interface Project {
  id: string;
  name: string;
  base_language: string;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
  // Summary fields
  status: string;
  slide_count: number;
  language_count: number;
}

export interface ProjectVersion {
  id: string;
  version_number: number;
  status: string;
  pptx_asset_path: string | null;
  slides_hash: string | null;
  comment: string | null;
  created_at: string;
}

export interface Slide {
  id: string;
  slide_index: number;
  image_url: string;  // URL served by backend (original slide)
  preview_url?: string | null;  // URL for rendered preview with canvas layers
  notes_text: string | null;
  slide_hash: string | null;
}

export interface SlideScript {
  id: string;
  slide_id: string;
  lang: string;
  text: string;
  source: string;
  updated_at: string;
}

export interface SlideWithScripts extends Slide {
  scripts: SlideScript[];
  audio_files: {
    id: string;
    lang: string;
    voice_id: string;
    audio_url: string;  // URL served by backend
    duration_sec: number;
    created_at?: string;
    script_text_hash?: string;  // Hash of script used for TTS (for sync tracking)
  }[];
}

export interface RenderJob {
  id: string;
  lang: string;
  job_type: string;
  status: string;
  progress_pct: number;
  download_video_url: string | null;
  download_srt_url: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  // Extended fields from /render/jobs endpoint
  project_id?: string;
  project_name?: string;
  version_id?: string;
}

export interface RenderStartJob {
  job_id: string;
  task_id: string;
  lang: string;
}

export interface RenderAllResponse {
  jobs: RenderStartJob[];
  languages_count: number;
}

export interface WorkspaceExport {
  project_id: string;
  project_name: string;
  version_id: string;
  lang: string;
  video_file: string;
  video_size_mb: number;
  has_srt: boolean;
  has_pptx: boolean;
  pptx_file: string | null;
  created_at: string;
}

export interface AudioSettings {
  // Audio settings
  background_music_enabled: boolean;
  music_asset_id: string | null;
  voice_gain_db: number;
  music_gain_db: number;
  ducking_enabled: boolean;
  ducking_strength: string;
  target_lufs: number;
  voice_id: string | null;
  music_fade_in_sec: number;
  music_fade_out_sec: number;
  // Render/timing settings
  pre_padding_sec: number;
  post_padding_sec: number;
  first_slide_hold_sec: number;
  last_slide_hold_sec: number;
  transition_type: string;
  transition_duration_sec: number;
}

export interface Voice {
  voice_id: string;
  name: string;
  category: string;
  labels: {
    gender: string;
    accent: string;
    age: string;
    description: string;
    use_case: string;
  };
  preview_url: string | null;
}

export interface TranslationRules {
  do_not_translate: string[];
  preferred_translations: { term: string; lang: string; translation: string }[];
  style: string;
  extra_rules: string | null;
}

// Canvas Editor Types
export interface Position {
  x: number;
  y: number;
}

export interface Size {
  width: number;
  height: number;
}

export interface TextStyle {
  fontFamily: string;
  fontSize: number;
  fontWeight: "normal" | "bold";
  fontStyle: "normal" | "italic";
  color: string;
  align: "left" | "center" | "right";
  verticalAlign: "top" | "middle" | "bottom";
  lineHeight: number;
}

export interface TextContent {
  baseContent: string;
  translations: Record<string, string>;
  isTranslatable: boolean;
  style?: Partial<TextStyle>;
  overflow?: "shrinkFont" | "expandHeight" | "clip";
  minFontSize?: number;
}

export interface ImageContent {
  assetId: string;
  assetUrl?: string;
  fit?: "contain" | "cover" | "fill";
}

export interface PlateContent {
  backgroundColor: string;
  backgroundOpacity?: number;
  borderRadius?: number;
  border?: {
    width: number;
    color: string;
    style: "solid" | "dashed";
  };
  accent?: {
    position: "left" | "top" | "right" | "bottom";
    width: number;
    color: string;
  };
  padding?: {
    top: number;
    right: number;
    bottom: number;
    left: number;
  };
}

export interface AnimationTrigger {
  type: "time" | "marker" | "start" | "end" | "word";
  seconds?: number;
  markerId?: string;
  offsetSeconds?: number;
  charStart?: number;
  charEnd?: number;
  wordText?: string;
}

export interface AnimationConfig {
  type: "fadeIn" | "fadeOut" | "slideLeft" | "slideRight" | "slideUp" | "slideDown" | "none";
  duration: number;
  delay: number;
  easing: "linear" | "easeIn" | "easeOut" | "easeInOut";
  trigger: AnimationTrigger;
}

export interface LayerAnimation {
  entrance?: AnimationConfig;
  exit?: AnimationConfig;
}

export interface SlideLayer {
  id: string;
  type: "text" | "image" | "plate";
  name: string;
  position: Position;
  size: Size;
  anchor?: string;
  rotation?: number;
  opacity?: number;
  visible: boolean;
  locked: boolean;
  zIndex: number;
  groupId?: string;
  text?: TextContent;
  image?: ImageContent;
  plate?: PlateContent;
  animation?: LayerAnimation;
}

export interface CanvasSettings {
  width: number;
  height: number;
}

export interface SlideScene {
  id: string;
  slide_id: string;
  canvas: CanvasSettings;
  layers: SlideLayer[];
  schema_version: number;
  render_key: string | null;
  created_at: string;
  updated_at: string;
}

export interface Marker {
  id: string;
  name?: string;
  charStart: number;
  charEnd: number;
  wordText: string;
  timeSeconds?: number;
}

export interface SlideMarkers {
  id: string;
  slide_id: string;
  lang: string;
  markers: Marker[];
  created_at: string;
  updated_at: string;
}

export interface Asset {
  id: string;
  project_id: string;
  type: "image" | "background" | "icon";
  filename: string;
  file_path: string;
  thumbnail_path?: string;
  width?: number;
  height?: number;
  file_size?: number;
  url: string;
  thumbnail_url?: string;
  created_at: string;
}

// API functions
export const api = {
  // Projects
  async getProjects(): Promise<Project[]> {
    const { data } = await client.get("/projects");
    return data;
  },

  async getProject(id: string): Promise<Project> {
    const { data } = await client.get(`/projects/${id}`);
    return data;
  },

  async createProject(name: string, base_language: string = "en"): Promise<Project> {
    const { data } = await client.post("/projects", { name, base_language });
    return data;
  },

  async updateProject(id: string, updates: Partial<Project>): Promise<Project> {
    const { data } = await client.patch(`/projects/${id}`, updates);
    return data;
  },

  async deleteProject(id: string): Promise<void> {
    await client.delete(`/projects/${id}`);
  },

  // Media Upload (PPTX, PDF, Images)
  async uploadMedia(projectId: string, file: File, comment?: string): Promise<{ version_id: string; file_type: string }> {
    const formData = new FormData();
    formData.append("file", file);
    if (comment) formData.append("comment", comment);

    const { data } = await client.post(`/projects/${projectId}/upload`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  // DEV helper: upload media by server-side path (avoids OS file picker limitations in automation)
  async uploadMediaFromPath(
    projectId: string,
    path: string,
    comment?: string
  ): Promise<{ version_id: string; file_type: string }> {
    const { data } = await client.post(`/projects/${projectId}/upload_from_path`, {
      path,
      comment,
    });
    return data;
  },

  // Legacy alias
  async uploadPPTX(projectId: string, file: File, comment?: string): Promise<{ version_id: string }> {
    return this.uploadMedia(projectId, file, comment);
  },

  // Versions
  async getVersions(projectId: string): Promise<ProjectVersion[]> {
    const { data } = await client.get(`/projects/${projectId}/versions`);
    return data;
  },

  async ensureCurrentVersion(projectId: string): Promise<ProjectVersion> {
    const { data } = await client.post(`/projects/${projectId}/versions/ensure`);
    return data;
  },

  async convertPPTX(projectId: string, versionId: string): Promise<{ task_id: string }> {
    const { data } = await client.post(`/projects/${projectId}/versions/${versionId}/convert`);
    return data;
  },

  // Slides
  async getSlides(projectId: string, versionId: string): Promise<SlideWithScripts[]> {
    const { data } = await client.get(`/slides/projects/${projectId}/versions/${versionId}/slides`);
    return data;
  },

  async getSlide(slideId: string): Promise<SlideWithScripts> {
    const { data } = await client.get(`/slides/${slideId}`);
    return data;
  },

  async deleteSlide(slideId: string): Promise<{ deleted_id: string; deleted_index: number; files_deleted: number; slides_reindexed: number }> {
    const { data } = await client.delete(`/slides/${slideId}`);
    return data;
  },

  async addSlide(projectId: string, versionId: string, file: File, position?: number): Promise<{ id: string; slide_index: number; image_url: string; total_slides: number }> {
    const formData = new FormData();
    formData.append("file", file);
    const params = position ? `?position=${position}` : "";
    const { data } = await client.post(
      `/slides/projects/${projectId}/versions/${versionId}/slides/add${params}`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    return data;
  },

  async reorderSlides(projectId: string, versionId: string, slideIds: string[]): Promise<{ success: boolean; new_order: string[]; slides_reordered: number }> {
    const { data } = await client.put(
      `/slides/projects/${projectId}/versions/${versionId}/slides/reorder`,
      { slide_ids: slideIds }
    );
    return data;
  },

  async updateScript(slideId: string, lang: string, text: string): Promise<SlideScript> {
    const { data } = await client.patch(`/slides/${slideId}/scripts/${lang}`, { text });
    return data;
  },

  // Languages
  async addLanguage(projectId: string, versionId: string, lang: string): Promise<void> {
    await client.post(`/slides/projects/${projectId}/versions/${versionId}/languages/add?lang=${lang}`);
  },

  async removeLanguage(projectId: string, versionId: string, lang: string): Promise<void> {
    await client.post(`/slides/projects/${projectId}/versions/${versionId}/languages/remove?lang=${lang}`);
  },

  async importNotes(projectId: string, versionId: string, lang: string = "en"): Promise<{ lang: string; imported_count: number }> {
    const { data } = await client.post(
      `/slides/projects/${projectId}/versions/${versionId}/import_notes?lang=${lang}`
    );
    return data;
  },

  async translateAll(projectId: string, versionId: string, targetLang: string): Promise<{ task_id: string; slide_count: number }> {
    const { data } = await client.post(
      `/slides/projects/${projectId}/versions/${versionId}/translate?target_lang=${targetLang}`
    );
    return data;
  },

  async getTaskStatus(taskId: string): Promise<{ task_id: string; status: string; ready: boolean; result?: any; error?: string }> {
    const { data } = await client.get(`/slides/tasks/${taskId}/status`);
    return data;
  },

  // TTS
  async generateSlideTTS(slideId: string, lang: string, voiceId?: string): Promise<{ task_id: string }> {
    const params = new URLSearchParams({ lang });
    if (voiceId) params.append("voice_id", voiceId);
    const { data } = await client.post(`/slides/${slideId}/tts?${params}`);
    return data;
  },

  async generateAllTTS(projectId: string, versionId: string, lang: string, voiceId?: string): Promise<{ task_id: string }> {
    const params = new URLSearchParams({ lang });
    if (voiceId) params.append("voice_id", voiceId);
    const { data } = await client.post(
      `/slides/projects/${projectId}/versions/${versionId}/tts?${params}`
    );
    return data;
  },

  // Render
  async renderVideo(projectId: string, versionId: string, lang: string): Promise<{ job_id: string }> {
    const { data } = await client.post(
      `/render/projects/${projectId}/versions/${versionId}/render?lang=${lang}`
    );
    return data;
  },

  async renderAll(projectId: string, versionId: string): Promise<RenderAllResponse> {
    const { data } = await client.post(
      `/render/projects/${projectId}/versions/${versionId}/render_all`
    );
    return data;
  },

  async getJobStatus(jobId: string): Promise<RenderJob> {
    const { data } = await client.get(`/render/jobs/${jobId}`);
    return data;
  },

  async getProjectJobs(projectId: string): Promise<RenderJob[]> {
    const { data } = await client.get(`/render/projects/${projectId}/jobs`);
    return data;
  },

  async getAllJobs(limit: number = 50): Promise<RenderJob[]> {
    const { data } = await client.get(`/render/jobs?limit=${limit}`);
    return data;
  },

  async cancelJob(jobId: string): Promise<{ status: string; message: string }> {
    const { data } = await client.post(`/render/jobs/${jobId}/cancel`);
    return data;
  },

  async cancelAllProjectJobs(
    projectId: string
  ): Promise<{ project_id: string; cancelled_count: number; cancelled_job_ids: string[] }> {
    const { data } = await client.post(`/render/projects/${projectId}/jobs/cancel_all`);
    return data;
  },

  // Workspace
  async getWorkspaceExports(): Promise<{ exports: WorkspaceExport[] }> {
    const { data } = await client.get("/render/workspace");
    return data;
  },

  async deleteWorkspaceExport(projectId: string, versionId: string, lang: string): Promise<void> {
    await client.delete(`/render/workspace/exports/${projectId}/${versionId}/${lang}`);
  },

  // Exports
  async getExports(projectId: string, versionId: string, lang?: string) {
    const params = lang ? `?lang=${lang}` : "";
    const { data } = await client.get(
      `/render/projects/${projectId}/versions/${versionId}/exports${params}`
    );
    return data;
  },

  getDownloadUrl(projectId: string, versionId: string, lang: string, filename: string): string {
    return `${API_URL}/api/render/projects/${projectId}/versions/${versionId}/download/${lang}/${filename}`;
  },

  getPptxDownloadUrl(projectId: string, versionId: string): string {
    return `${API_URL}/api/render/projects/${projectId}/versions/${versionId}/download-pptx`;
  },

  // Audio Settings
  async getAudioSettings(projectId: string): Promise<AudioSettings> {
    const { data } = await client.get(`/projects/${projectId}/audio_settings`);
    return data;
  },

  async updateAudioSettings(projectId: string, settings: Partial<AudioSettings>): Promise<void> {
    await client.put(`/projects/${projectId}/audio_settings`, settings);
  },

  async uploadMusic(projectId: string, file: File): Promise<{ asset_id: string }> {
    const formData = new FormData();
    formData.append("file", file);
    const { data } = await client.post(`/projects/${projectId}/upload_music`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  // Translation Rules
  async getTranslationRules(projectId: string): Promise<TranslationRules> {
    const { data } = await client.get(`/projects/${projectId}/translation_rules`);
    return data;
  },

  async updateTranslationRules(projectId: string, rules: Partial<TranslationRules>): Promise<void> {
    await client.put(`/projects/${projectId}/translation_rules`, rules);
  },

  // Voices
  async getVoices(): Promise<{ voices: Voice[] }> {
    const { data } = await client.get("/projects/voices");
    return data;
  },

  // Slide image URL helper - prepend API_URL to relative URL from backend
  getSlideImageUrl(imageUrl: string): string {
    if (!imageUrl) return "";
    // Backend now returns URLs like "/static/slides/{project_id}/{version_id}/{filename}"
    return `${API_URL}${imageUrl}`;
  },

  // Slide audio URL helper - prepend API_URL to relative URL from backend
  getSlideAudioUrl(audioUrl: string): string {
    if (!audioUrl) return "";
    // Backend now returns URLs like "/static/audio/{project_id}/{version_id}/{lang}/{filename}"
    return `${API_URL}${audioUrl}`;
  },

  // Music URL helper - get URL for project's corporate music
  getMusicUrl(projectId: string): string {
    if (!projectId) return "";
    return `${API_URL}/static/music/${projectId}/corporate.mp3`;
  },

  // ==================== CANVAS EDITOR API ====================

  // Scene CRUD
  async getSlideScene(slideId: string): Promise<SlideScene> {
    const { data } = await client.get(`/canvas/slides/${slideId}/scene`);
    return data;
  },

  async updateSlideScene(slideId: string, scene: { canvas?: CanvasSettings; layers?: SlideLayer[] }): Promise<SlideScene> {
    const { data } = await client.put(`/canvas/slides/${slideId}/scene`, scene);
    return data;
  },

  async generateSlidePreview(slideId: string, lang: string = "en"): Promise<{ success: boolean; preview_url: string; slide_id: string }> {
    const { data } = await client.post(`/canvas/slides/${slideId}/preview?lang=${lang}`);
    return data;
  },

  async addLayer(slideId: string, layer: Partial<SlideLayer>): Promise<SlideScene> {
    const { data } = await client.post(`/canvas/slides/${slideId}/scene/layers`, layer);
    return data;
  },

  async updateLayer(slideId: string, layerId: string, layer: Partial<SlideLayer>): Promise<SlideScene> {
    const { data } = await client.put(`/canvas/slides/${slideId}/scene/layers/${layerId}`, layer);
    return data;
  },

  async deleteLayer(slideId: string, layerId: string): Promise<SlideScene> {
    const { data } = await client.delete(`/canvas/slides/${slideId}/scene/layers/${layerId}`);
    return data;
  },

  async reorderLayers(slideId: string, layerIds: string[]): Promise<{ status: string; layers_count: number }> {
    const { data } = await client.put(`/canvas/slides/${slideId}/scene/layers/reorder`, { layer_ids: layerIds });
    return data;
  },

  // Markers
  async getSlideMarkers(slideId: string, lang: string): Promise<SlideMarkers> {
    const { data } = await client.get(`/canvas/slides/${slideId}/markers/${lang}`);
    return data;
  },

  async updateSlideMarkers(slideId: string, lang: string, markers: Marker[]): Promise<SlideMarkers> {
    const { data } = await client.put(`/canvas/slides/${slideId}/markers/${lang}`, { markers });
    return data;
  },

  // Assets
  async getProjectAssets(projectId: string, type?: string): Promise<{ assets: Asset[]; total: number }> {
    const params = type ? `?type=${type}` : "";
    const { data } = await client.get(`/canvas/projects/${projectId}/assets${params}`);
    return data;
  },

  async uploadAsset(projectId: string, file: File, type: "image" | "background" | "icon" = "image"): Promise<Asset> {
    const formData = new FormData();
    formData.append("file", file);
    const { data } = await client.post(`/canvas/projects/${projectId}/assets?type=${type}`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  async deleteAsset(assetId: string): Promise<void> {
    await client.delete(`/canvas/assets/${assetId}`);
  },

  // Translate scene text layers
  async translateSceneLayers(
    slideId: string,
    targetLang: string
  ): Promise<{ translated_count: number; target_lang: string; layers_updated: string[] }> {
    const { data } = await client.post(`/canvas/slides/${slideId}/scene/translate`, {
      target_lang: targetLang,
    });
    return data;
  },

  // Get scene with resolved word triggers (converted to time-based)
  async getResolvedScene(
    slideId: string,
    lang: string
  ): Promise<{
    id: string;
    slide_id: string;
    canvas: CanvasSettings;
    layers: SlideLayer[];
    lang: string;
    triggers_resolved: number;
    schema_version: number;
    render_key: string | null;
  }> {
    const { data } = await client.get(`/canvas/slides/${slideId}/scene/resolved?lang=${lang}`);
    return data;
  },

  // Asset URL helper
  getAssetUrl(url: string): string {
    if (!url) return "";
    return `${API_URL}${url}`;
  },
};
