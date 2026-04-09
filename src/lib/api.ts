// ---------------------------------------------------------------------------
// API Client — typed wrapper around fetch for the FastAPI backend
// ---------------------------------------------------------------------------

// API calls go through the Next.js proxy at /api/v1/* which adds auth headers
const API_BASE = "";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AgentResponse {
  id: string;
  org_id: string;
  created_by: string | null;
  name: string;
  description: string | null;
  system_prompt: string | null;
  persona: string | null;
  status: string;
  languages: string[] | null;
  model_config: Record<string, any> | null;
  welcome_message: string | null;
  fallback_message: string | null;
  escalation_message: string | null;
  max_turns: number | null;
  published_at: string | null;
  published_version: number | null;
  created_at: string;
  updated_at: string;
  // Derived fields (not from DB, computed or joined)
  channels?: string[];
  customer?: string;
  tone?: string;
  conversations?: number;
  completionRate?: number;
  avgConversationLength?: string;
  guardrailTriggers?: number;
  kbDocsCount?: number;
  actionsCount?: number;
  statesCount?: number;
  guardrailsCount?: number;
}

export interface AgentListResponse {
  items: AgentResponse[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AgentCreate {
  name: string;
  persona?: string;
  system_prompt?: string;
  description?: string;
  languages?: string[];
  welcome_message?: string;
  fallback_message?: string;
  escalation_message?: string;
  max_turns?: number;
}

// Matches backend DashboardStatsResponse (snake_case from Python)
export interface DashboardOverview {
  total_agents: number;
  active_agents: number;
  total_conversations: number;
  active_conversations: number;
  avg_completion_rate: number;
  total_messages: number;
  avg_response_time_ms: number;
  guardrail_triggers: number;
  conversations_today: number;
  messages_today: number;
  conversations_by_status?: Record<string, number>;
  avg_messages_per_conversation?: number;
  conversations_by_channel?: Record<string, number>;
  top_agents?: Array<{ name: string; conversation_count: number }>;
}

export interface DashboardTimeSeriesPoint {
  date: string;
  conversations: number;
  messages: number;
  completion_rate: number;
}

export interface DashboardChannelBreakdown {
  channel: string;
  conversations: number;
  messages: number;
  percentage: number;
}

export interface DashboardAgentPerformance {
  agent_id: string;
  agent_name: string;
  conversations: number;
  completion_rate: number;
  avg_messages: number;
  avg_response_time_ms: number;
}

// ---------------------------------------------------------------------------
// Fetch wrapper
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}/api/v1${path}`;

  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string>),
  };

  // Only set Content-Type for non-FormData bodies
  if (init?.body && !(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(url, {
    ...init,
    headers,
    credentials: "include",
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let detail = `API error ${res.status}`;
    try {
      const json = JSON.parse(text);
      detail = json.detail || detail;
    } catch {
      if (text) detail = text;
    }
    throw new Error(detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export const agentApi = {
  list: (params?: { status?: string; search?: string; page?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.status && params.status !== "all") searchParams.set("status", params.status);
    if (params?.search) searchParams.set("search", params.search);
    if (params?.page) searchParams.set("page", String(params.page));
    const qs = searchParams.toString();
    return apiFetch<AgentListResponse>(`/agents${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => apiFetch<AgentResponse>(`/agents/${id}`),
  create: (data: AgentCreate) =>
    apiFetch<AgentResponse>("/agents", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<AgentCreate>) =>
    apiFetch<AgentResponse>(`/agents/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    apiFetch<void>(`/agents/${id}`, { method: "DELETE" }),
  publish: (id: string) =>
    apiFetch<AgentResponse>(`/agents/${id}/publish`, { method: "POST" }),
  call: (id: string, phoneNumber: string) =>
    apiFetch<{ success: boolean; call_sid?: string; error?: string }>(`/agents/${id}/call`, {
      method: "POST",
      body: JSON.stringify({ phone_number: phoneNumber }),
    }),
};

// ---------------------------------------------------------------------------
// Knowledge Base
// ---------------------------------------------------------------------------

export const kbApi = {
  listDocuments: (agentId: string) =>
    apiFetch<any>(`/agents/${agentId}/kb/documents`),
  uploadDocument: async (agentId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(
      `${API_BASE}/api/v1/agents/${agentId}/kb/documents`,
      {
        method: "POST",
        body: formData,
        credentials: "include",
      }
    );
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      let detail = `Upload failed (${res.status})`;
      try {
        detail = JSON.parse(text).detail || detail;
      } catch {}
      throw new Error(detail);
    }
    return res.json();
  },
  deleteDocument: (agentId: string, docId: string) =>
    apiFetch<void>(`/agents/${agentId}/kb/documents/${docId}`, {
      method: "DELETE",
    }),
};

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

export const actionApi = {
  list: (agentId: string) =>
    apiFetch<any>(`/agents/${agentId}/actions`),
  create: (agentId: string, data: any) =>
    apiFetch<any>(`/agents/${agentId}/actions`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (agentId: string, actionId: string, data: any) =>
    apiFetch<any>(`/agents/${agentId}/actions/${actionId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  delete: (agentId: string, actionId: string) =>
    apiFetch<void>(`/agents/${agentId}/actions/${actionId}`, {
      method: "DELETE",
    }),
};

// ---------------------------------------------------------------------------
// States
// ---------------------------------------------------------------------------

export const stateApi = {
  get: (agentId: string) =>
    apiFetch<any>(`/agents/${agentId}/states`),
  save: (agentId: string, data: any) =>
    apiFetch<any>(`/agents/${agentId}/states`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
};

// ---------------------------------------------------------------------------
// Channels
// ---------------------------------------------------------------------------

export const channelApi = {
  list: (agentId: string) =>
    apiFetch<any>(`/agents/${agentId}/channels`),
  update: (agentId: string, channelType: string, data: any) =>
    apiFetch<any>(`/agents/${agentId}/channels/${channelType}`, {
      method: "PUT",
      body: JSON.stringify({ config: data, is_active: true }),
    }),
};

// ---------------------------------------------------------------------------
// Guardrails
// ---------------------------------------------------------------------------

export const guardrailApi = {
  list: (agentId: string) =>
    apiFetch<any>(`/agents/${agentId}/guardrails`),
  create: (agentId: string, data: any) =>
    apiFetch<any>(`/agents/${agentId}/guardrails`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  generate: (agentId: string) =>
    apiFetch<any>(`/agents/${agentId}/guardrails/generate`, {
      method: "POST",
      body: JSON.stringify({ include_compliance: true }),
    }),
  bulkUpdate: (agentId: string, data: any[]) =>
    apiFetch<any>(`/agents/${agentId}/guardrails`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  delete: (agentId: string, guardrailId: string) =>
    apiFetch<void>(`/agents/${agentId}/guardrails/${guardrailId}`, {
      method: "DELETE",
    }),
};

// ---------------------------------------------------------------------------
// Conversations
// ---------------------------------------------------------------------------

export const conversationApi = {
  list: (params?: { agent_id?: string; status?: string; page?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.agent_id) searchParams.set("agent_id", params.agent_id);
    if (params?.status) searchParams.set("status", params.status);
    if (params?.page) searchParams.set("page", String(params.page));
    const qs = searchParams.toString();
    return apiFetch<any>(`/conversations${qs ? `?${qs}` : ""}`);
  },
  search: (q: string) =>
    apiFetch<any>(`/conversations/search?q=${encodeURIComponent(q)}`),
  get: (id: string) =>
    apiFetch<any>(`/conversations/${id}`),
};

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export const dashboardApi = {
  overview: () =>
    apiFetch<DashboardOverview>("/dashboard/overview"),
  timeseries: (days?: number) =>
    apiFetch<DashboardTimeSeriesPoint[]>(
      `/dashboard/timeseries${days ? `?days=${days}` : ""}`
    ),
  channelBreakdown: () =>
    apiFetch<DashboardChannelBreakdown[]>("/dashboard/channels"),
  agentPerformance: () =>
    apiFetch<DashboardAgentPerformance[]>("/dashboard/agents"),
};
