import type { ChatAnswer, LearningStep, ProjectMap, ProjectResponse } from '../types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers ?? {})
    },
    ...options
  });
  if (!response.ok) {
    const text = await response.text();
    let detail = text;
    try {
      const data = JSON.parse(text);
      detail = data.detail ?? text;
    } catch {
      detail = text;
    }
    throw new Error(detail || `请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function analyzeProject(repoUrl: string): Promise<{ project_id: string; status: string }> {
  return request('/api/projects/analyze', {
    method: 'POST',
    body: JSON.stringify({ repo_url: repoUrl })
  });
}

export async function getProject(projectId: string): Promise<ProjectResponse> {
  return request(`/api/projects/${projectId}`);
}

export async function getProjectMap(projectId: string): Promise<ProjectMap> {
  return request(`/api/projects/${projectId}/map`);
}

export async function getLearningPath(projectId: string): Promise<{ steps: LearningStep[] }> {
  return request(`/api/projects/${projectId}/learning-path`);
}

export async function askProject(projectId: string, question: string): Promise<ChatAnswer> {
  return request(`/api/projects/${projectId}/ask`, {
    method: 'POST',
    body: JSON.stringify({ question })
  });
}

export async function getReport(projectId: string): Promise<{ markdown: string }> {
  return request(`/api/projects/${projectId}/report`);
}
