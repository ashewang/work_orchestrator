import { useQuery } from '@tanstack/react-query';
import * as api from '../api/client';

export function useProjects() {
  return useQuery({ queryKey: ['projects'], queryFn: api.getProjects });
}

export function useProject(id: string) {
  return useQuery({ queryKey: ['project', id], queryFn: () => api.getProject(id), enabled: !!id });
}

export function useProjectTasks(projectId: string, status?: string) {
  return useQuery({
    queryKey: ['tasks', projectId, status],
    queryFn: () => api.getProjectTasks(projectId, status),
    enabled: !!projectId,
  });
}

export function useProjectSummary(projectId: string) {
  return useQuery({
    queryKey: ['summary', projectId],
    queryFn: () => api.getProjectSummary(projectId),
    enabled: !!projectId,
  });
}

export function useAgents(status?: string, project?: string) {
  return useQuery({
    queryKey: ['agents', status, project],
    queryFn: () => api.getAgents(status, project),
    refetchInterval: 5000,
  });
}

export function useSlots(projectId: string) {
  return useQuery({
    queryKey: ['slots', projectId],
    queryFn: () => api.getSlots(projectId),
    enabled: !!projectId,
    refetchInterval: 10000,
  });
}

