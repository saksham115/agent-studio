"use client";

import { useState } from "react";
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

type AgentStatus = "active" | "draft" | "paused";
type Channel = "voice" | "whatsapp" | "chatbot";

interface AgentDetail {
  id: string;
  name: string;
  persona: string;
  customer: string;
  status: AgentStatus;
  channels: Channel[];
  conversations: number;
  completionRate: number;
  avgConversationLength: string;
  guardrailTriggers: number;
  createdAt: string;
  updatedAt: string;
  languages: string[];
  tone: string;
  systemPromptPreview: string;
  kbDocsCount: number;
  actionsCount: number;
  statesCount: number;
  guardrailsCount: number;
}

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

const agentsMap: Record<string, AgentDetail> = {
  "agt-001": {
    id: "agt-001",
    name: "Health Insurance Advisor",
    persona: "Priya Sharma",
    customer: "HDFC ERGO",
    status: "active",
    channels: ["voice", "whatsapp", "chatbot"],
    conversations: 12847,
    completionRate: 78.4,
    avgConversationLength: "4m 32s",
    guardrailTriggers: 156,
    createdAt: "2026-01-15",
    updatedAt: "2026-03-30",
    languages: ["English", "Hindi", "Hinglish"],
    tone: "Consultative",
    systemPromptPreview:
      "You are Priya Sharma, a knowledgeable health insurance advisor at HDFC ERGO. Help customers understand health insurance plans, compare coverage options, and guide them through the purchase process. Always mention IRDAI regulations when discussing policy terms.",
    kbDocsCount: 24,
    actionsCount: 8,
    statesCount: 7,
    guardrailsCount: 5,
  },
  "agt-002": {
    id: "agt-002",
    name: "Motor Renewal Bot",
    persona: "Rajesh Kumar",
    customer: "Bajaj Allianz",
    status: "active",
    channels: ["whatsapp", "chatbot"],
    conversations: 8432,
    completionRate: 85.2,
    avgConversationLength: "2m 18s",
    guardrailTriggers: 43,
    createdAt: "2026-02-03",
    updatedAt: "2026-03-25",
    languages: ["English", "Hindi"],
    tone: "Conversational",
    systemPromptPreview:
      "You are Rajesh Kumar, a motor insurance renewal specialist at Bajaj Allianz. Proactively reach out to customers whose policies are nearing expiry, explain no-claim bonus benefits, and facilitate quick renewals. Highlight IDV options and add-on covers.",
    kbDocsCount: 18,
    actionsCount: 6,
    statesCount: 5,
    guardrailsCount: 4,
  },
  "agt-003": {
    id: "agt-003",
    name: "Term Life Outbound",
    persona: "Ananya Reddy",
    customer: "Max Life Insurance",
    status: "paused",
    channels: ["voice"],
    conversations: 5621,
    completionRate: 42.7,
    avgConversationLength: "6m 45s",
    guardrailTriggers: 289,
    createdAt: "2025-11-20",
    updatedAt: "2026-03-10",
    languages: ["English", "Hindi", "Telugu"],
    tone: "Formal",
    systemPromptPreview:
      "You are Ananya Reddy, a term life insurance specialist at Max Life Insurance. Conduct outbound calls to qualified leads, assess their life insurance needs based on income, dependents, and existing coverage. Present Max Life term plans with clear premium breakdowns.",
    kbDocsCount: 31,
    actionsCount: 10,
    statesCount: 9,
    guardrailsCount: 7,
  },
  "agt-004": {
    id: "agt-004",
    name: "ULIP Cross-Sell Agent",
    persona: "Vikram Mehta",
    customer: "ICICI Prudential",
    status: "draft",
    channels: ["voice", "whatsapp"],
    conversations: 0,
    completionRate: 0,
    avgConversationLength: "--",
    guardrailTriggers: 0,
    createdAt: "2026-03-28",
    updatedAt: "2026-04-01",
    languages: ["English", "Hindi", "Gujarati"],
    tone: "Consultative",
    systemPromptPreview:
      "You are Vikram Mehta, an investment-cum-insurance advisor at ICICI Prudential. Engage existing policy holders to cross-sell ULIP products. Explain NAV-based returns, fund options, lock-in periods, and tax benefits under Section 80C and 10(10D).",
    kbDocsCount: 15,
    actionsCount: 5,
    statesCount: 6,
    guardrailsCount: 3,
  },
  "agt-005": {
    id: "agt-005",
    name: "Claim Status Helper",
    persona: "Neha Gupta",
    customer: "Star Health",
    status: "active",
    channels: ["whatsapp", "chatbot"],
    conversations: 21340,
    completionRate: 91.3,
    avgConversationLength: "1m 54s",
    guardrailTriggers: 67,
    createdAt: "2025-09-10",
    updatedAt: "2026-04-02",
    languages: ["English", "Hindi", "Tamil"],
    tone: "Conversational",
    systemPromptPreview:
      "You are Neha Gupta, a claims support agent at Star Health Insurance. Help policyholders check claim status, understand required documents for cashless and reimbursement claims, locate network hospitals, and escalate unresolved issues to the claims team.",
    kbDocsCount: 42,
    actionsCount: 12,
    statesCount: 6,
    guardrailsCount: 4,
  },
  "agt-006": {
    id: "agt-006",
    name: "Policy Renewal WhatsApp",
    persona: "Arjun Patel",
    customer: "Tata AIG",
    status: "active",
    channels: ["whatsapp"],
    conversations: 15290,
    completionRate: 88.1,
    avgConversationLength: "3m 12s",
    guardrailTriggers: 92,
    createdAt: "2025-12-05",
    updatedAt: "2026-03-28",
    languages: ["English", "Hindi", "Marathi"],
    tone: "Conversational",
    systemPromptPreview:
      "You are Arjun Patel, a renewal specialist at Tata AIG. Send timely renewal reminders via WhatsApp, share premium quotes, explain coverage changes, and generate secure payment links. Focus on retention by highlighting loyalty benefits and NCB discounts.",
    kbDocsCount: 20,
    actionsCount: 7,
    statesCount: 5,
    guardrailsCount: 4,
  },
};

const apiKeysData: ApiKey[] = [
  {
    id: "key-001",
    name: "Production - Web Widget",
    prefix: "sk-prod-a8f3...x2k9",
    status: "active",
    createdAt: "2026-02-10",
    lastUsed: "2026-04-03",
  },
  {
    id: "key-002",
    name: "Staging - Internal Testing",
    prefix: "sk-stg-d4e1...m7n2",
    status: "active",
    createdAt: "2026-01-22",
    lastUsed: "2026-04-01",
  },
  {
    id: "key-003",
    name: "Legacy Integration",
    prefix: "sk-leg-b2c5...p9q4",
    status: "revoked",
    createdAt: "2025-11-05",
    lastUsed: "2026-01-15",
  },
  {
    id: "key-004",
    name: "Partner API - Razorpay Webhook",
    prefix: "sk-prt-f6g8...t3u1",
    status: "active",
    createdAt: "2026-03-01",
    lastUsed: "2026-04-03",
  },
];

const conversationsData: ConversationRow[] = [
  {
    id: "conv-10234",
    phoneOrChannel: "+91 98765 43210",
    channel: "voice",
    status: "completed",
    duration: "5m 12s",
    startedAt: "2026-04-03 14:32",
    currentState: "Closure",
  },
  {
    id: "conv-10233",
    phoneOrChannel: "+91 87654 32109",
    channel: "whatsapp",
    status: "completed",
    duration: "3m 45s",
    startedAt: "2026-04-03 13:18",
    currentState: "Closure",
  },
  {
    id: "conv-10232",
    phoneOrChannel: "Web Session #8821",
    channel: "chatbot",
    status: "dropped",
    duration: "1m 20s",
    startedAt: "2026-04-03 12:55",
    currentState: "Product Pitch",
  },
  {
    id: "conv-10231",
    phoneOrChannel: "+91 76543 21098",
    channel: "whatsapp",
    status: "escalated",
    duration: "7m 03s",
    startedAt: "2026-04-03 11:40",
    currentState: "Objection Handling",
  },
  {
    id: "conv-10230",
    phoneOrChannel: "+91 65432 10987",
    channel: "voice",
    status: "completed",
    duration: "4m 28s",
    startedAt: "2026-04-03 10:15",
    currentState: "Closure",
  },
  {
    id: "conv-10229",
    phoneOrChannel: "+91 54321 09876",
    channel: "whatsapp",
    status: "in-progress",
    duration: "2m 10s",
    startedAt: "2026-04-03 09:50",
    currentState: "Need Discovery",
  },
  {
    id: "conv-10228",
    phoneOrChannel: "Web Session #8820",
    channel: "chatbot",
    status: "completed",
    duration: "3m 55s",
    startedAt: "2026-04-02 17:22",
    currentState: "Closure",
  },
  {
    id: "conv-10227",
    phoneOrChannel: "+91 43210 98765",
    channel: "voice",
    status: "dropped",
    duration: "0m 45s",
    startedAt: "2026-04-02 16:08",
    currentState: "Greeting",
  },
];

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

function OverviewTab({ agent }: { agent: AgentDetail }) {
  const status = statusConfig[agent.status];

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
                {agent.updatedAt}
              </div>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Languages
              </p>
              <div className="flex items-center gap-1.5 text-sm">
                <Languages className="h-3.5 w-3.5 text-muted-foreground" />
                {agent.languages.join(", ")}
              </div>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Tone
              </p>
              <div className="flex items-center gap-1.5 text-sm">
                <Sparkles className="h-3.5 w-3.5 text-muted-foreground" />
                {agent.tone}
              </div>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Channels
              </p>
              <div className="flex flex-wrap gap-1.5">
                {agent.channels.map((ch) => {
                  const config = channelConfig[ch];
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
              {agent.systemPromptPreview}
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
              {formatNumber(agent.conversations)}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>Completion Rate</CardDescription>
            <CardTitle className="text-2xl">
              {agent.completionRate > 0 ? `${agent.completionRate}%` : "--"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>Avg. Conversation Length</CardDescription>
            <CardTitle className="text-2xl">
              {agent.avgConversationLength}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>Guardrail Triggers</CardDescription>
            <CardTitle className="text-2xl">
              {agent.guardrailTriggers}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>
    </div>
  );
}

function ConfigurationTab({ agent }: { agent: AgentDetail }) {
  const configSections = [
    {
      title: "Identity & System Prompt",
      description: `Persona: ${agent.persona} | Tone: ${agent.tone} | Languages: ${agent.languages.join(", ")}`,
      icon: Bot,
      detail: "Fully configured",
      color: "text-blue-500",
    },
    {
      title: "Knowledge Base",
      description: `${agent.kbDocsCount} documents uploaded and indexed`,
      icon: Database,
      detail: `${agent.kbDocsCount} docs`,
      color: "text-violet-500",
    },
    {
      title: "Actions",
      description: `${agent.actionsCount} actions configured (API calls, link generation, notifications)`,
      icon: Zap,
      detail: `${agent.actionsCount} actions`,
      color: "text-amber-500",
    },
    {
      title: "State Diagram",
      description: `${agent.statesCount} states defined in the sales lifecycle flow`,
      icon: GitBranch,
      detail: `${agent.statesCount} states`,
      color: "text-emerald-500",
    },
    {
      title: "Channels",
      description: agent.channels
        .map((ch) => channelConfig[ch].label)
        .join(", "),
      icon: Globe,
      detail: `${agent.channels.length} channels`,
      color: "text-cyan-500",
    },
    {
      title: "Guardrails",
      description: `${agent.guardrailsCount} safety rules active (IRDAI compliance, PII masking, escalation triggers)`,
      icon: Shield,
      detail: `${agent.guardrailsCount} rules`,
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

function ConversationsTab() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Recent conversations for this agent
        </p>
        <Button variant="outline" size="sm">
          <Eye className="h-3.5 w-3.5 mr-1.5" />
          View All
        </Button>
      </div>
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
    </div>
  );
}

function ApiKeysTab() {
  const [copiedId, setCopiedId] = useState<string | null>(null);

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
    </div>
  );
}

export default function AgentDetailPage() {
  const params = useParams();
  const agentId = params.id as string;
  const agent = agentsMap[agentId];

  if (!agent) {
    return (
      <div className="p-6">
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Bot className="h-12 w-12 text-muted-foreground/40 mb-4" />
          <h3 className="text-lg font-semibold">Agent not found</h3>
          <p className="text-sm text-muted-foreground mt-1 mb-4">
            The agent with ID &quot;{agentId}&quot; does not exist.
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

  const status = statusConfig[agent.status];

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
          <ConfigurationTab agent={agent} />
        </TabsContent>

        <TabsContent value="conversations" className="mt-4">
          <ConversationsTab />
        </TabsContent>

        <TabsContent value="api-keys" className="mt-4">
          <ApiKeysTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
