"use client";

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";
import { api, Asset } from "@/lib/api";
import { toast } from "sonner";
import { Button, Card } from "@/components/ui";
import { X, Upload, Trash2, ImageIcon, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface AssetLibraryProps {
  projectId: string;
  onSelect: (asset: Asset) => void;
  onClose: () => void;
}

export function AssetLibrary({ projectId, onSelect, onClose }: AssetLibraryProps) {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<"all" | "image" | "background" | "icon">("all");

  // Fetch assets
  const { data, isLoading } = useQuery({
    queryKey: ["assets", projectId, filter === "all" ? undefined : filter],
    queryFn: () => api.getProjectAssets(projectId, filter === "all" ? undefined : filter),
    enabled: !!projectId,
  });

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: ({ file, type }: { file: File; type: "image" | "background" | "icon" }) =>
      api.uploadAsset(projectId, file, type),
    onSuccess: () => {
      toast.success("Asset uploaded");
      queryClient.invalidateQueries({ queryKey: ["assets", projectId] });
    },
    onError: () => {
      toast.error("Upload failed");
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (assetId: string) => api.deleteAsset(assetId),
    onSuccess: () => {
      toast.success("Asset deleted");
      queryClient.invalidateQueries({ queryKey: ["assets", projectId] });
    },
    onError: () => {
      toast.error("Delete failed");
    },
  });

  // Dropzone
  const onDrop = useCallback((acceptedFiles: File[]) => {
    acceptedFiles.forEach((file) => {
      uploadMutation.mutate({ file, type: "image" });
    });
  }, [uploadMutation]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "image/png": [".png"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/webp": [".webp"],
      "image/gif": [".gif"],
    },
    maxFiles: 10,
  });

  const assets = data?.assets || [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#252525] rounded-lg shadow-2xl w-[800px] max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#333]">
          <h2 className="text-sm font-medium text-white">Asset Library</h2>
          <Button variant="ghost" size="icon" onClick={onClose} className="text-white/60 hover:text-white">
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-[#333]">
          {(["all", "image", "background", "icon"] as const).map((type) => (
            <button
              key={type}
              onClick={() => setFilter(type)}
              className={cn(
                "px-3 py-1 rounded text-xs transition-colors",
                filter === type
                  ? "bg-primary text-white"
                  : "bg-[#333] text-white/60 hover:bg-[#444]"
              )}
            >
              {type.charAt(0).toUpperCase() + type.slice(1)}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {/* Upload zone */}
          <div
            {...getRootProps()}
            className={cn(
              "border-2 border-dashed rounded-lg p-6 mb-4 text-center cursor-pointer transition-colors",
              isDragActive
                ? "border-primary bg-primary/10"
                : "border-[#444] hover:border-[#555]"
            )}
          >
            <input {...getInputProps()} />
            {uploadMutation.isPending ? (
              <div className="flex items-center justify-center gap-2 text-white/60">
                <Loader2 className="w-5 h-5 animate-spin" />
                <span className="text-sm">Uploading...</span>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 text-white/60">
                <Upload className="w-8 h-8" />
                <span className="text-sm">
                  {isDragActive ? "Drop files here" : "Drag & drop images or click to upload"}
                </span>
                <span className="text-xs text-white/40">PNG, JPG, WebP, GIF</span>
              </div>
            )}
          </div>

          {/* Assets grid */}
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-white/40" />
            </div>
          ) : assets.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-white/40">
              <ImageIcon className="w-12 h-12 mb-2" />
              <span className="text-sm">No assets yet</span>
            </div>
          ) : (
            <div className="grid grid-cols-4 gap-3">
              {assets.map((asset) => (
                <div
                  key={asset.id}
                  className="group relative aspect-square bg-[#333] rounded-lg overflow-hidden cursor-pointer hover:ring-2 hover:ring-primary transition-all"
                  onClick={() => onSelect(asset)}
                >
                  {/* Thumbnail */}
                  <img
                    src={api.getAssetUrl(asset.thumbnail_url || asset.url)}
                    alt={asset.filename}
                    className="w-full h-full object-cover"
                  />

                  {/* Overlay on hover */}
                  <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-end justify-between p-2">
                    <span className="text-xs text-white truncate flex-1 mr-2">
                      {asset.filename}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm("Delete this asset?")) {
                          deleteMutation.mutate(asset.id);
                        }
                      }}
                      className="p-1 rounded bg-red-500/20 text-red-400 hover:bg-red-500/40 transition-colors"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>

                  {/* Type badge */}
                  <div className="absolute top-1 left-1">
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-black/50 text-white/70">
                      {asset.type}
                    </span>
                  </div>

                  {/* Dimensions */}
                  {asset.width && asset.height && (
                    <div className="absolute top-1 right-1">
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-black/50 text-white/70">
                        {asset.width}×{asset.height}
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-[#333] flex items-center justify-between">
          <span className="text-xs text-white/40">
            {assets.length} asset{assets.length !== 1 ? "s" : ""}
          </span>
          <Button variant="ghost" size="sm" onClick={onClose} className="text-white/60 hover:text-white">
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}

