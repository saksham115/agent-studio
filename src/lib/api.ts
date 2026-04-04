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
  name: string;
  persona: string;
  customer: string;
  status: "active" | "draft" | "paused";
  channels: ("voice" | "whatsapp" | "chatbot")[];
  conversations: number;
  completionRate: number;
  avgConversationLength?: string;
  guardrailTriggers?: number;
  createdAt: string;
  updatedAt?: string;
  languages?: string[];
  tone?: string;
  systemPrompt?: string;
  systemPromptPreview?: string;
  kbDocsCount?: number;
  actionsCount?: number;
  statesCount?: number;
  guardrailsCount?: number;
}

export interface AgentListResponse {
  items: AgentResponse[];
  total: number;
  page: number;
  pageSize: number;
}

export interface AgentCreate {
  name: string;
  persona: string;
  customer: string;
  systemPrompt?: string;
  languages?: string[];
  tone?: string;
  channels?: ("voice" | "whatsapp" | "chatbot")[];
}

export interface DashboardOverview {
  totalAgents: number;
  activeAgents: number;
  draftAgents: number;
  totalConversations: number;
  completionRate: number | null;
  completionRateTrend: { value: string; direction: "up" | "down" } | null;
  avgResponseTime: string | null;
  avgResponseTimeTrend: { value: string; direction: "up" | "down" } | null;
  conversationData: { date: string; voice: number; whatsapp: number; chatbot: number }[];
  funnelData: { stage: string; count: number; percent: number; fill: string }[];
  recentConversations: {
    id: string;
    contact: string;
    agent: string;
    channel: "Voice" | "WhatsApp" | "Chatbot";
    stateReached: string;
    timeAgo: string;
  }[];
  topAgents: {
    name: string;
    conversations: number;
    completionRate: number;
    channels: ("Voice" | "WhatsApp" | "Chatbot")[];
  }[];
}

export interface ConversationListItem {
  id: string;
  contact: string;
  contactName: string;
  agentName: string;
  channel: "voice" | "whatsapp" | "chatbot";
  currentState: string;
  messages: number;
  duration: string;
  status: "active" | "completed" | "escalated" | "dropped";
  startedAt: string;
  startedRelative: string;
}

export interface ConversationListResponse {
  items: ConversationListItem[];
  total: number;
  page: number;
  pageSize: number;
  agentNames?: string[];
}

export interface ConversationMessage {
  id: string;
  sender: "agent" | "user" | "system";
  content: string;
  timestamp: string;
}

export interface StateTransition {
  state: string;
  timestamp: string;
  duration: string;
}

export interface ActionTriggered {
  id: string;
  name: string;
  status: "success" | "failed";
  timestamp: string;
  payload: Record<string, string>;
}

export interface GuardrailTriggered {
  id: string;
  name: string;
  severity: "low" | "medium" | "high";
  details: string;
  timestamp: string;
}

export interface ConversationDetail {
  id: string;
  contact: string;
  contactName: string;
  channel: "voice" | "whatsapp" | "chatbot";
  direction: string;
  status: string;
  startedAt: string;
  duration: string;
  messageCount: number;
  agentName: string;
  agentId: string;
  messages: ConversationMessage[];
  stateTimeline: StateTransition[];
  actionsTriggered: ActionTriggered[];
  guardrailsTriggered: GuardrailTriggered[];
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    credentials: "include", // forward cookies (NextAuth session)
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || "API error");
  }

  // Handle 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

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
};

// ---------------------------------------------------------------------------
// Knowledge Base
// ---------------------------------------------------------------------------

export const kbApi = {
  listDocuments: (agentId: string) =>
    apiFetch<any>(`/agents/${agentId}/kb/documents`),
  uploadDocument: (agentId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return fetch(`${API_BASE}/api/v1/agents/${agentId}/kb/documents`, {
      method: "POST",
      body: formData,
      credentials: "include",
    }).then((r) => r.json());
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
      body: JSON.stringify(data),
    }),
};

// ---------------------------------------------------------------------------
// Guardrails
// ---------------------------------------------------------------------------

export const guardrailApi = {
  list: (agentId: string) =>
    apiFetch<any>(`/agents/${agentId}/guardrails`),
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
};

// ---------------------------------------------------------------------------
// Conversations
// ---------------------------------------------------------------------------

export const conversationApi = {
  list: (params?: { agent_id?: string; status?: string; page?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.agent_id && params.agent_id !== "all") searchParams.set("agent_id", params.agent_id);
    if (params?.status && params.status !== "all") searchParams.set("status", params.status);
    if (params?.page) searchParams.set("page", String(params.page));
    const qs = searchParams.toString();
    return apiFetch<ConversationListResponse>(`/conversations${qs ? `?${qs}` : ""}`);
  },
  search: (q: string) =>
    apiFetch<ConversationListResponse>(
      `/conversations/search?q=${encodeURIComponent(q)}`
    ),
  get: (id: string) =>
    apiFetch<ConversationDetail>(`/conversations/${id}`),
};

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export const dashboardApi = {
  overview: () => apiFetch<DashboardOverview>("/dashboard/overview"),
  agentStats: (agentId: string) =>
    apiFetch<any>(`/dashboard/${agentId}/stats`),
};
