import type {
  AuthResponse,
  OCRPrepareResponse,
  ScanResponse,
  User,
  ImageUploadResponse,
  ImageProcessResponse,
  ScanHistoryItem,
  ScanHistoryDetail,
} from '../types';

// Resolution order:
//  1. VITE_API_URL (build-time) - e.g. "/api/v1" or "https://api.example.com/api/v1"
//  2. Vite dev server (localhost) -> backend on :8000
//  3. Otherwise same-origin "/api/v1" (nginx / ingress proxies to the backend)
const API_BASE_URL: string = (() => {
  const configured = import.meta.env.VITE_API_URL as string | undefined;
  if (configured) return configured.replace(/\/+$/, '');
  if (import.meta.env.DEV && typeof window !== 'undefined') {
    const host = window.location.hostname === 'localhost' ? '127.0.0.1' : window.location.hostname;
    return `http://${host}:8000/api/v1`;
  }
  return '/api/v1';
})();

const TOKEN_KEY = 'dtoxout_token';
const USER_KEY = 'dtoxout_user';

export const authStorage = {
  getToken: (): string | null => localStorage.getItem(TOKEN_KEY),
  setToken: (token: string): void => localStorage.setItem(TOKEN_KEY, token),
  removeToken: (): void => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
  getUser: (): User | null => {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  },
  setUser: (user: User): void =>
    localStorage.setItem(USER_KEY, JSON.stringify(user)),
};

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = authStorage.getToken();
  const isFormData = options.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const url = `${API_BASE_URL}${endpoint}`;
  let response: Response;

  try {
    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (err: any) {
    throw new ApiError(
      `Unable to connect to DToxOut backend API at ${API_BASE_URL}. Please check your connection and try again.`,
      0
    );
  }

  if (response.status === 401) {
    authStorage.removeToken();
    window.dispatchEvent(new CustomEvent('dtoxout_auth_expired'));
    const errorBody = await response.json().catch(() => ({}));
    throw new ApiError(
      errorBody.detail || 'Session expired or unauthenticated. Please log in.',
      response.status,
      errorBody
    );
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    let msg = 'API Request Failed';
    if (typeof errorBody.detail === 'string') {
      msg = errorBody.detail;
    } else if (Array.isArray(errorBody.detail) && errorBody.detail[0]?.msg) {
      msg = errorBody.detail[0].msg;
    }
    throw new ApiError(msg, response.status, errorBody);
  }

  return (await response.json()) as T;
}

export const api = {
  login: async (emailOrUsername: string, password: string): Promise<AuthResponse> => {
    const data = await apiFetch<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: emailOrUsername, password }),
    });
    if (data.access_token) {
      authStorage.setToken(data.access_token);
      try {
        const user = await api.getCurrentUser();
        data.user = user;
      } catch {
        // Fallback user if me endpoint fails
      }
    }
    return data;
  },

  register: async (
    email: string,
    username: string,
    password: string
  ): Promise<AuthResponse> => {
    await apiFetch('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, username, password }),
    });
    // Auto login post registration
    return api.login(email, password);
  },

  getCurrentUser: async (): Promise<User> => {
    const user = await apiFetch<User>('/auth/me');
    authStorage.setUser(user);
    return user;
  },

  quickDemoLogin: async (): Promise<AuthResponse> => {
    const demoUsername = 'demouser';
    const demoPassword = 'DemoPassword123!';
    const demoEmail = 'demo@dtoxout.org';

    try {
      return await api.login(demoEmail, demoPassword);
    } catch {
      return await api.register(demoEmail, demoUsername, demoPassword);
    }
  },

  prepareText: async (rawText: string): Promise<OCRPrepareResponse> => {
    return apiFetch<OCRPrepareResponse>('/scan/prepare-text', {
      method: 'POST',
      body: JSON.stringify({ raw_text: rawText }),
    });
  },

  uploadImage: async (file: File): Promise<ImageUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    return apiFetch<ImageUploadResponse>('/scan/upload-image', {
      method: 'POST',
      body: formData,
    });
  },

  processImage: async (uploadId: string): Promise<ImageProcessResponse> => {
    return apiFetch<ImageProcessResponse>('/scan/process-image', {
      method: 'POST',
      body: JSON.stringify({ upload_id: uploadId }),
    });
  },

  analyzeIngredients: async (ingredients: string[]): Promise<ScanResponse> => {
    return apiFetch<ScanResponse>('/scan/analyze', {
      method: 'POST',
      body: JSON.stringify({ ingredients }),
    });
  },

  getScanHistory: async (): Promise<ScanHistoryItem[]> => {
    return apiFetch<ScanHistoryItem[]>('/scans');
  },

  getScanDetails: async (scanId: string): Promise<ScanHistoryDetail> => {
    return apiFetch<ScanHistoryDetail>(`/scans/${scanId}`);
  },

  logout: async (): Promise<{ message: string }> => {
    try {
      await apiFetch<{ message: string }>('/auth/logout', { method: 'POST' });
    } finally {
      authStorage.removeToken();
    }
    return { message: 'Logged out successfully.' };
  },

  deleteScan: async (scanId: string): Promise<{ message: string }> => {
    return apiFetch<{ message: string }>(`/scans/${scanId}`, {
      method: 'DELETE',
    });
  },
};
