"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Bot,
  Phone,
  MessageCircle,
  Globe,
  Settings,
  Eye,
  Key,
  Shield,
  GitBranch,
  Database,
  Zap,
  Plus,
  MoreVertical,
  ArrowLeft,
  Calendar,
  Languages,
  Sparkles,
  Copy,
  CheckCircle2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardAction,
} from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  agentApi,
  actionApi,
  stateApi,
  channelApi,
  guardrailApi,
  conversationApi,
  type AgentResponse,
} from "@/lib/api";

type AgentStatus = "active" | "draft" | "paused";
type Channel = "voice" | "whatsapp" | "chatbot";

interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  status: "active" | "revoked";
  createdAt: string;
  lastUsed: string;
}

interface ConversationRow {
  id: string;
  phoneOrChannel: string;
  channel: Channel;
  status: "completed" | "dropped" | "escalated" | "in-progress";
  duration: string;
  startedAt: string;
  currentState: string;
}

const statusConfig: Record<AgentStatus, { label: string; className: string }> =
  {
    active: {
      label: "Active",
      className:
        "bg-emerald-500/15 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400",
    },
    draft: {
      label: "Draft",
      className:
        "bg-amber-500/15 text-amber-600 dark:bg-amber-500/20 dark:text-amber-400",
    },
    paused: {
      label: "Paused",
      className:
        "bg-zinc-500/15 text-zinc-600 dark:bg-zinc-500/20 dark:text-zinc-400",
    },
  };

const channelConfig: Record<Channel, { icon: typeof Phone; label: string }> = {
  voice: { icon: Phone, label: "Voice" },
  whatsapp: { icon: MessageCircle, label: "WhatsApp" },
  chatbot: { icon: Globe, label: "Chatbot" },
};

const convStatusConfig: Record<
  ConversationRow["status"],
  { label: string; className: string }
> = {
  completed: {
    label: "Completed",
    className:
      "bg-emerald-500/15 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400",
  },
  dropped: {
    label: "Dropped",
    className:
      "bg-red-500/15 text-red-600 dark:bg-red-500/20 dark:text-red-400",
  },
  escalated: {
    label: "Escalated",
    className:
      "bg-amber-500/15 text-amber-600 dark:bg-amber-500/20 dark:text-amber-400",
  },
  "in-progress": {
    label: "In Progress",
    className:
      "bg-blue-500/15 text-blue-600 dark:bg-blue-500/20 dark:text-blue-400",
  },
};

function formatNumber(n: number): string {
  if (n >= 1000) {
    return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  }
  return n.toString();
}

// ---------------------------------------------------------------------------
// Loading Skeleton
// ---------------------------------------------------------------------------

function DetailSkeleton() {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-4">
        <Skeleton className="h-9 w-9" />
        <div className="flex items-center gap-3 flex-1">
          <Skeleton className="h-10 w-10 rounded-lg" />
          <div className="space-y-1.5">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-64" />
          </div>
        </div>
      </div>
      <div className="flex gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-28" />
        ))}
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} size="sm">
            <CardHeader>
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-8 w-16 mt-1" />
            </CardHeader>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-tab components
// ---------------------------------------------------------------------------

function OverviewTab({ agent }: { agent: AgentResponse }) {
  const status = statusConfig[(agent.status as AgentStatus) ?? "draft"];

  return (
    <div className="space-y-6">
      {/* Agent Info Card */}
      <Card>
        <CardHeader>
          <CardTitle>Agent Information</CardTitle>
          <CardDescription>Core identity and configuration</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-4">
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Agent Name
              </p>
              <p className="text-sm font-semibold">{agent.name}</p>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Persona
              </p>
              <p className="text-sm font-semibold">{agent.persona}</p>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Customer
              </p>
              <p className="text-sm font-semibold">{agent.customer}</p>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Status
              </p>
              <Badge variant="secondary" className={status.className}>
                {status.label}
              </Badge>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Created
              </p>
              <div className="flex items-center gap-1.5 text-sm">
                <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
                {agent.createdAt}
              </div>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Last Updated
              </p>
              <div className="flex items-center gap-1.5 text-sm">
                <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
                {agent.updatedAt ?? "--"}
              </div>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Languages
              </p>
              <div className="flex items-center gap-1.5 text-sm">
                <Languages className="h-3.5 w-3.5 text-muted-foreground" />
                {(agent.languages ?? []).join(", ") || "--"}
              </div>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Tone
              </p>
              <div className="flex items-center gap-1.5 text-sm">
                <Sparkles className="h-3.5 w-3.5 text-muted-foreground" />
                {agent.tone ?? "--"}
              </div>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Channels
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(agent.channels ?? []).map((ch) => {
                  const config = channelConfig[ch as Channel];
                  if (!config) return null;
                  const Icon = config.icon;
                  return (
                    <Badge
                      key={ch}
                      variant="outline"
                      className="gap-1 font-normal"
                    >
                      <Icon className="h-3 w-3" />
                      {config.label}
                    </Badge>
                  );
                })}
              </div>
            </div>
          </div>
          <Separator className="my-4" />
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              System Prompt Preview
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed rounded-md bg-muted/50 p-3 border border-border/50">
              {agent.systemPromptPreview ?? agent.systemPrompt ?? "Not configured"}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Performance Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card size="sm">
          <CardHeader>
            <CardDescription>Total Conversations</CardDescription>
            <CardTitle className="text-2xl">
              {formatNumber(agent.conversations ?? 0)}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>Completion Rate</CardDescription>
            <CardTitle className="text-2xl">
              {(agent.completionRate ?? 0) > 0 ? `${agent.completionRate}%` : "--"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>Avg. Conversation Length</CardDescription>
            <CardTitle className="text-2xl">
              {agent.avgConversationLength ?? "--"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>Guardrail Triggers</CardDescription>
            <CardTitle className="text-2xl">
              {agent.guardrailTriggers ?? 0}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>
    </div>
  );
}

function ConfigurationTab({
  agent,
  configData,
}: {
  agent: AgentResponse;
  configData: {
    actionsCount: number;
    statesCount: number;
    kbDocsCount: number;
    guardrailsCount: number;
  };
}) {
  const configSections = [
    {
      title: "Identity & System Prompt",
      description: `Persona: ${agent.persona} | Tone: ${agent.tone ?? "--"} | Languages: ${(agent.languages ?? []).join(", ") || "--"}`,
      icon: Bot,
      detail: "Fully configured",
      color: "text-blue-500",
    },
    {
      title: "Knowledge Base",
      description: `${configData.kbDocsCount} documents uploaded and indexed`,
      icon: Database,
      detail: `${configData.kbDocsCount} docs`,
      color: "text-violet-500",
    },
    {
      title: "Actions",
      description: `${configData.actionsCount} actions configured (API calls, link generation, notifications)`,
      icon: Zap,
      detail: `${configData.actionsCount} actions`,
      color: "text-amber-500",
    },
    {
      title: "State Diagram",
      description: `${configData.statesCount} states defined in the sales lifecycle flow`,
      icon: GitBranch,
      detail: `${configData.statesCount} states`,
      color: "text-emerald-500",
    },
    {
      title: "Channels",
      description: (agent.channels ?? [])
        .map((ch) => channelConfig[ch as Channel]?.label ?? ch)
        .join(", ") || "None",
      icon: Globe,
      detail: `${(agent.channels ?? []).length} channels`,
      color: "text-cyan-500",
    },
    {
      title: "Guardrails",
      description: `${configData.guardrailsCount} safety rules active (IRDAI compliance, PII masking, escalation triggers)`,
      icon: Shield,
      detail: `${configData.guardrailsCount} rules`,
      color: "text-red-500",
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {configSections.map((section) => {
        const Icon = section.icon;
        return (
          <Card
            key={section.title}
            className="cursor-pointer transition-colors hover:bg-muted/30"
          >
            <CardHeader>
              <div className="flex items-start gap-3">
                <div
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted ${section.color}`}
                >
                  <Icon className="h-4.5 w-4.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <CardTitle>{section.title}</CardTitle>
                  <CardDescription className="mt-0.5">
                    {section.description}
                  </CardDescription>
                </div>
              </div>
              <CardAction>
                <Badge variant="secondary">{section.detail}</Badge>
              </CardAction>
            </CardHeader>
          </Card>
        );
      })}
    </div>
  );
}

function ConversationsTab({
  agentId,
  conversationsData,
}: {
  agentId: string;
  conversationsData: ConversationRow[];
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Recent conversations for this agent
        </p>
        <Link href={`/conversations?agent=${agentId}`}>
          <Button variant="outline" size="sm">
            <Eye className="h-3.5 w-3.5 mr-1.5" />
            View All
          </Button>
        </Link>
      </div>
      {conversationsData.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <MessageCircle className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <h3 className="text-lg font-medium">No conversations yet</h3>
          <p className="text-sm text-muted-foreground mt-1">Conversations will appear here once this agent starts interacting</p>
        </div>
      ) : (
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Contact</TableHead>
                <TableHead>Channel</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Current State</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Started At</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {conversationsData.map((conv) => {
                const chConfig = channelConfig[conv.channel];
                const ChIcon = chConfig.icon;
                const convStatus = convStatusConfig[conv.status];
                return (
                  <TableRow key={conv.id}>
                    <TableCell className="font-mono text-xs">
                      {conv.id}
                    </TableCell>
                    <TableCell className="font-medium">
                      {conv.phoneOrChannel}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className="gap-1 font-normal"
                      >
                        <ChIcon className="h-3 w-3" />
                        {chConfig.label}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={convStatus.className}
                      >
                        {convStatus.label}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {conv.currentState}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {conv.duration}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {conv.startedAt}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      )}
    </div>
  );
}

function ApiKeysTab() {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const apiKeysData: ApiKey[] = []; // TODO: fetch from API when endpoint is available

  function handleCopy(keyId: string, prefix: string) {
    navigator.clipboard.writeText(prefix);
    setCopiedId(keyId);
    setTimeout(() => setCopiedId(null), 2000);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">API Keys</p>
          <p className="text-sm text-muted-foreground">
            Manage API keys for programmatic access to this agent
          </p>
        </div>
        <Button size="sm">
          <Plus className="h-3.5 w-3.5 mr-1.5" />
          Generate Key
        </Button>
      </div>
      {apiKeysData.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Key className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <h3 className="text-lg font-medium">No API keys yet</h3>
          <p className="text-sm text-muted-foreground mt-1">Generate an API key for programmatic access to this agent</p>
        </div>
      ) : (
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Key</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Last Used</TableHead>
                <TableHead className="w-[60px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {apiKeysData.map((apiKey) => (
                <TableRow key={apiKey.id}>
                  <TableCell className="font-medium">{apiKey.name}</TableCell>
                  <TableCell>
                    <code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono">
                      {apiKey.prefix}
                    </code>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="secondary"
                      className={
                        apiKey.status === "active"
                          ? "bg-emerald-500/15 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400"
                          : "bg-zinc-500/15 text-zinc-600 dark:bg-zinc-500/20 dark:text-zinc-400"
                      }
                    >
                      {apiKey.status === "active" ? "Active" : "Revoked"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {apiKey.createdAt}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {apiKey.lastUsed}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      onClick={() => handleCopy(apiKey.id, apiKey.prefix)}
                      disabled={apiKey.status === "revoked"}
                    >
                      {copiedId === apiKey.id ? (
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AgentDetailPage() {
  const params = useParams();
  const agentId = params.id as string;

  const [agent, setAgent] = useState<AgentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [configData, setConfigData] = useState({
    actionsCount: 0,
    statesCount: 0,
    kbDocsCount: 0,
    guardrailsCount: 0,
  });
  const [conversationsData, setConversationsData] = useState<ConversationRow[]>([]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);

        // Fetch agent details
        const agentData = await agentApi.get(agentId);
        if (cancelled) return;
        setAgent(agentData);

        // Fetch configuration data in parallel
        const [actionsRes, statesRes, channelsRes, guardrailsRes, convsRes] = await Promise.allSettled([
          actionApi.list(agentId),
          stateApi.get(agentId),
          channelApi.list(agentId),
          guardrailApi.list(agentId),
          conversationApi.list({ agent_id: agentId }),
        ]);

        if (cancelled) return;

        const actionsData = actionsRes.status === "fulfilled" ? actionsRes.value : [];
        const statesData = statesRes.status === "fulfilled" ? statesRes.value : {};
        const guardrailsData = guardrailsRes.status === "fulfilled" ? guardrailsRes.value : [];

        setConfigData({
          actionsCount: agentData.actionsCount ?? (Array.isArray(actionsData) ? actionsData.length : (actionsData?.items?.length ?? 0)),
          statesCount: agentData.statesCount ?? (statesData?.nodes?.length ?? 0),
          kbDocsCount: agentData.kbDocsCount ?? 0,
          guardrailsCount: agentData.guardrailsCount ?? (Array.isArray(guardrailsData) ? guardrailsData.length : (guardrailsData?.items?.length ?? 0)),
        });

        // Map conversations
        if (convsRes.status === "fulfilled") {
          const convItems = convsRes.value?.items ?? (Array.isArray(convsRes.value) ? convsRes.value : []);
          setConversationsData(
            convItems.map((c: any) => ({
              id: c.id,
              phoneOrChannel: c.contact ?? c.contactName ?? "--",
              channel: c.channel ?? "chatbot",
              status: c.status ?? "completed",
              duration: c.duration ?? "--",
              startedAt: c.startedAt ?? c.startedRelative ?? "--",
              currentState: c.currentState ?? "--",
            }))
          );
        }
      } catch (err: any) {
        if (!cancelled) {
          console.error("Failed to load agent:", err);
          setError(err.message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  if (loading) return <DetailSkeleton />;

  if (error || !agent) {
    return (
      <div className="p-6">
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Bot className="h-12 w-12 text-muted-foreground/40 mb-4" />
          <h3 className="text-lg font-semibold">Agent not found</h3>
          <p className="text-sm text-muted-foreground mt-1 mb-4">
            {error
              ? `Error: ${error}`
              : `The agent with ID "${agentId}" does not exist.`}
          </p>
          <Link href="/agents">
            <Button variant="outline">
              <ArrowLeft className="h-4 w-4 mr-1.5" />
              Back to Agents
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  const status = statusConfig[(agent.status as AgentStatus) ?? "draft"];

  return (
    <div className="p-6 space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <Link href="/agents">
          <Button variant="ghost" size="icon-sm">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Bot className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight truncate">
                {agent.name}
              </h1>
              <Badge variant="secondary" className={status.className}>
                {status.label}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {agent.persona} &middot; {agent.customer}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="outline" size="sm">
            <Settings className="h-3.5 w-3.5 mr-1.5" />
            Edit Agent
          </Button>
          <Button variant="ghost" size="icon-sm">
            <MoreVertical className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="overview">
        <TabsList variant="line">
          <TabsTrigger value="overview">
            <Eye className="h-4 w-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="configuration">
            <Settings className="h-4 w-4" />
            Configuration
          </TabsTrigger>
          <TabsTrigger value="conversations">
            <MessageCircle className="h-4 w-4" />
            Conversations
          </TabsTrigger>
          <TabsTrigger value="api-keys">
            <Key className="h-4 w-4" />
            API Keys
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <OverviewTab agent={agent} />
        </TabsContent>

        <TabsContent value="configuration" className="mt-4">
          <ConfigurationTab agent={agent} configData={configData} />
        </TabsContent>

        <TabsContent value="conversations" className="mt-4">
          <ConversationsTab agentId={agentId} conversationsData={conversationsData} />
        </TabsContent>

        <TabsContent value="api-keys" className="mt-4">
          <ApiKeysTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
