const API_BASE_URL = import.meta.env.VITE_API_URL ?? '/api';

const getWebSocketBaseUrl = () => {
  const configured = import.meta.env.VITE_WS_URL as string | undefined;
  if (configured) {
    return configured.replace(/\/$/, '');
  }

  const apiUrl = new URL(API_BASE_URL, window.location.origin);
  apiUrl.protocol = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  return apiUrl.origin;
};

export interface AuthPayload {
  email: string;
  login: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserBase {
  login: string;
}

export interface UserDefinition {
  name_company: string | null;
  definition: string | null;
}

export interface Project {
  id: string;
  name: string;
  created_at: string;
}

export interface ModelConfig {
  id: number;
  name: string;
  type: string;
}

export interface ClassType {
  id: string;
  name_ru: string;
  name_eng: string;
  project_id: string;
}

export interface ProjectImage {
  id: string;
  file_path?: string | null;
  width: number | null;
  height: number | null;
  format: string | null;
  annotations: Record<string, AnnotationResponse>;
}

export type AnnotationApiType = 'detection' | 'segmentation';

export interface AnnotationPayload {
  type: AnnotationApiType;
  class_name: string;
  data: unknown;
}

export interface AnnotationResponse {
  id: string;
  image_id?: string;
  type: AnnotationApiType | 'detect' | 'segment';
  class_name: string;
  data: unknown;
  is_selected?: boolean;
}

export interface AnalysisTaskCreatedMessage {
  type: 'task_created';
  task_id: string;
  status: 'queued';
  message?: string;
}

export interface AnalysisTaskUpdateMessage {
  type: 'task_update';
  task_id: string;
  image_id: string;
  event: 'processing' | 'completed' | 'failed';
  status: string;
  result?: Record<string, unknown> | null;
  error?: string | null;
  timestamp?: string;
}

export interface AnalysisErrorMessage {
  type: 'error';
  message: string;
}

export interface ProjectsListResponse {
  projects: Project[];
}

export type AnalysisSocketMessage = AnalysisTaskCreatedMessage | AnalysisTaskUpdateMessage | AnalysisErrorMessage | { type: string;[key: string]: unknown };

export interface ApiErrorPayload {
  detail?: string | { message?: string; error?: string };
  message?: string;
}

class ApiError extends Error {
  status: number;
  payload: ApiErrorPayload | null;

  constructor(status: number, payload: ApiErrorPayload | null) {
    const detail = payload?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message ?? payload?.message ?? `HTTP ${status}`;
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

const tokenStorage = {
  getAccess: () => localStorage.getItem('seglabel.accessToken'),
  getRefresh: () => localStorage.getItem('seglabel.refreshToken'),
  set: (tokens: AuthResponse) => {
    localStorage.setItem('seglabel.accessToken', tokens.access_token);
    localStorage.setItem('seglabel.refreshToken', tokens.refresh_token);
  },
  clear: () => {
    localStorage.removeItem('seglabel.accessToken');
    localStorage.removeItem('seglabel.refreshToken');
  }
};

const makeHeaders = (headers?: HeadersInit, isFormData = false): HeadersInit => {
  const accessToken = tokenStorage.getAccess();
  return {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    ...headers
  };
};

const parseResponse = async <T>(response: Response): Promise<T> => {
  const text = await response.text();
  const contentType = response.headers.get('content-type') ?? '';
  const data = text && contentType.includes('application/json') ? JSON.parse(text) : text ? { message: text } : null;

  if (!response.ok) {
    throw new ApiError(response.status, data);
  }

  return data as T;
};

const refreshTokens = async () => {
  const refreshToken = tokenStorage.getRefresh();
  if (!refreshToken) {
    throw new ApiError(401, { detail: 'Не найден refresh token' });
  }

  const response = await fetch(`${API_BASE_URL}/auth/refresh/`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'X-Refresh-Token': refreshToken }
  });
  const tokens = await parseResponse<AuthResponse>(response);
  tokenStorage.set(tokens);
  return tokens;
};

const request = async <T>(path: string, init: RequestInit = {}, retry = true): Promise<T> => {
  const isFormData = init.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: makeHeaders(init.headers, isFormData)
  });

  if (response.status === 401 && retry && tokenStorage.getRefresh()) {
    await refreshTokens();
    return request<T>(path, init, false);
  }

  return parseResponse<T>(response);
};

const requestBlob = async (path: string, retry = true): Promise<Blob> => {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: makeHeaders(undefined, true)
  });

  if (response.status === 401 && retry && tokenStorage.getRefresh()) {
    await refreshTokens();
    return requestBlob(path, false);
  }

  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(response.status, text ? { message: text } : null);
  }

  return response.blob();
};

const startAnalysisViaWebSocket = (payload: {
  imageId: string;
  modelConfigId: number;
  classTypeIds: string[];
  onMessage?: (message: AnalysisSocketMessage) => void;
}) =>
  new Promise<AnalysisTaskUpdateMessage>((resolve, reject) => {
    const token = tokenStorage.getAccess();
    if (!token) {
      reject(new ApiError(401, { detail: 'Не найден access token' }));
      return;
    }

    const socket = new WebSocket(`${getWebSocketBaseUrl()}/api/analyze/analysis?token=${encodeURIComponent(token)}`);
    const timeout = window.setTimeout(() => {
      socket.close();
      reject(new Error('Таймаут ожидания результата анализа'));
    }, 120_000);

    socket.addEventListener('open', () => {
      socket.send(JSON.stringify({ cmd: 'subscribe', image_id: payload.imageId }));
      socket.send(
        JSON.stringify({
          cmd: 'start_analysis',
          image_id: payload.imageId,
          model_config_id: payload.modelConfigId,
          class_type_ids: payload.classTypeIds
        })
      );
    });

    socket.addEventListener('message', (event) => {
      const message = JSON.parse(event.data) as AnalysisSocketMessage;
      payload.onMessage?.(message);

      if (message.type === 'error') {
        window.clearTimeout(timeout);
        socket.close();
        reject(new Error((message as AnalysisErrorMessage).message));
      }

      if (message.type === 'task_update') {
        const update = message as AnalysisTaskUpdateMessage;
        if (update.event === 'completed') {
          window.clearTimeout(timeout);
          socket.close();
          resolve(update);
        }
        if (update.event === 'failed') {
          window.clearTimeout(timeout);
          socket.close();
          reject(new Error(update.error ?? 'Анализ завершился ошибкой'));
        }
      }
    });

    socket.addEventListener('error', () => {
      window.clearTimeout(timeout);
      reject(new Error('WebSocket анализа недоступен'));
    });
  });

export const api = {
  tokenStorage,

  login: async (payload: AuthPayload) => {
    const tokens = await request<AuthResponse>('/auth/login/', {
      method: 'POST',
      body: JSON.stringify(payload)
    }, false);
    tokenStorage.set(tokens);
    return tokens;
  },

  register: (payload: AuthPayload) =>
    request<{ message: string }>('/auth/register/', {
      method: 'POST',
      body: JSON.stringify(payload)
    }, false),

  logout: async () => {
    try {
      await request<{ message: string }>('/auth/logout/', { method: 'POST' });
    } finally {
      tokenStorage.clear();
    }
  },

  getMe: () => request<UserBase>('/user/me/'),
  getDefinitionMe: () => request<UserDefinition>('/user/about/me'),

  listProjects: async () => {
    const response = await request<ProjectsListResponse>('/projects/');
    return response.projects;
  },
  createProject: (name: string) =>
    request<Project>('/projects/', {
      method: 'POST',
      body: JSON.stringify({ name })
    }),
  deleteProject: (projectId: string) => request<{ detail: string }>(`/projects/${projectId}`, { method: 'DELETE' }),

  getProjectModels: (projectId: string) => request<ModelConfig[]>(`/projects/${projectId}/models`),
  getProjectClasses: (projectId: string) => request<ClassType[]>(`/projects/${projectId}/classes`),
  createProjectClass: (projectId: string, name: string) =>
    request<ClassType>(`/projects/${projectId}/classes`, {
      method: 'POST',
      body: JSON.stringify({ name_eng: name })
    }),
  getProjectImages: (projectId: string) => request<ProjectImage[]>(`/image/${projectId}/images`),
  getImageObjectUrl: async (projectId: string, imageId: string) => {
    const blob = await requestBlob(`/image/${projectId}/images/${imageId}/download`);
    return URL.createObjectURL(blob);
  },

  getAnnotations: (projectId: string, imageId: string) =>
    request<AnnotationResponse[]>(`/annotations/${projectId}/images/${imageId}`),
  runModels: (projectId: string, imageId: string, modelIds: number[], className: string) =>
    request<AnnotationResponse[]>(`/models/${projectId}/images/${imageId}/run`, {
      method: 'POST',
      body: JSON.stringify({ model_ids: modelIds, class_name: className })
    }),
  startAnalysisViaWebSocket,
  createAnnotation: (projectId: string, imageId: string, payload: AnnotationPayload) =>
    request<AnnotationResponse>(`/annotations/${projectId}/images/${imageId}`, {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  updateAnnotation: (projectId: string, imageId: string, annotationId: string, payload: Partial<AnnotationPayload>) =>
    request<AnnotationResponse>(`/annotations/${projectId}/images/${imageId}/${annotationId}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),
  deleteAnnotation: (projectId: string, imageId: string, annotationId: string) =>
    request<{ status: string; deleted_count: number }>(`/annotations/${projectId}/images/${imageId}/${annotationId}`, {
      method: 'DELETE'
    }),

  uploadImages: (projectId: string, files: File[]) => {
    const formData = new FormData();
    formData.append(
      'metadata_json',
      JSON.stringify(files.map((file) => ({ format: file.type.split('/')[1] ?? file.name.split('.').pop() ?? null })))
    );
    files.forEach((file) => formData.append('files', file));
    return request<ProjectImage[]>(`/image/${projectId}/images/upload`, {
      method: 'POST',
      body: formData
    });
  },

  imageDownloadUrl: (projectId: string, imageId: string) => `${API_BASE_URL}/image/${projectId}/images/${imageId}/download`
};

export { ApiError };
