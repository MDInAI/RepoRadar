import { getRequiredApiBaseUrl } from '@/api/base-url';

interface ApiClientResponse<T = any> {
  data: T;
  status: number;
}

class ApiClient {
  private getBaseUrl(): string {
    return getRequiredApiBaseUrl();
  }

  async get<T>(path: string, options?: { params?: Record<string, any> }): Promise<ApiClientResponse<T>> {
    const url = new URL(`${this.getBaseUrl()}${path}`);
    if (options?.params) {
      Object.entries(options.params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          url.searchParams.append(key, String(value));
        }
      });
    }

    const response = await fetch(url.toString(), { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status} ${response.statusText}`);
    }
    const data = await response.json();
    return { data, status: response.status };
  }

  async post<T>(path: string, body?: any): Promise<ApiClientResponse<T>> {
    const response = await fetch(`${this.getBaseUrl()}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status} ${response.statusText}`);
    }
    const data = await response.json();
    return { data, status: response.status };
  }

  async put<T>(path: string, body?: any): Promise<ApiClientResponse<T>> {
    const response = await fetch(`${this.getBaseUrl()}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status} ${response.statusText}`);
    }
    const data = await response.json();
    return { data, status: response.status };
  }

  async delete<T>(path: string): Promise<ApiClientResponse<T>> {
    const response = await fetch(`${this.getBaseUrl()}${path}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status} ${response.statusText}`);
    }
    const data = response.status === 204 ? null : await response.json();
    return { data, status: response.status };
  }
}

export const apiClient = new ApiClient();
