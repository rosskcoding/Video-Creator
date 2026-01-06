"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { LANGUAGES } from "@/lib/utils";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  Button,
  Input,
  Select,
} from "@/components/ui";

interface Props {
  onClose: () => void;
}

export function CreateProjectModal({ onClose }: Props) {
  const [name, setName] = useState("");
  const [baseLanguage, setBaseLanguage] = useState("en");
  const router = useRouter();
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: () => api.createProject(name, baseLanguage),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      toast.success("Project created!");
      onClose();
      router.push(`/projects/${project.id}`);
    },
    onError: () => {
      toast.error("Failed to create project");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast.error("Please enter a project name");
      return;
    }
    createMutation.mutate();
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create New Project</DialogTitle>
          <DialogDescription>
            Start by giving your project a name and selecting the base language
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="p-6 pt-4 space-y-4">
          <div>
            <label className="block text-[13px] font-medium mb-1.5">
              Project Name
            </label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Q4 Investor Presentation"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-[13px] font-medium mb-1.5">
              Base Language
            </label>
            <Select
              value={baseLanguage}
              onChange={(e) => setBaseLanguage(e.target.value)}
            >
              {LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.name}
                </option>
              ))}
            </Select>
            <p className="text-label text-muted-foreground mt-1.5">
              Scripts will be translated from this language
            </p>
          </div>
        </form>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            title="Close without creating a project"
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={createMutation.isPending}
            title="Create the project and open it"
          >
            {createMutation.isPending ? "Creating..." : "Create Project"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
