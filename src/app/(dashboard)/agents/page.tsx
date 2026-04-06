"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  Bot,
  Plus,
  Search,
  Phone,
  MessageCircle,
  Globe,
  Settings,
  Eye,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { agentApi, type AgentResponse } from "@/lib/api";

type AgentStatus = "active" | "draft" | "published" | "paused" | "archived";
type Channel = "voice" | "whatsapp" | "chatbot";

const channelConfig: Record<Channel, { icon: typeof Phone; label: string }> = {
  voice: { icon: Phone, label: "Voice" },
  whatsapp: { icon: MessageCircle, label: "WhatsApp" },
  chatbot: { icon: Globe, label: "Chatbot" },
};

const statusConfig: Record<
  AgentStatus,
  { label: string; className: string }
> = {
  active: {
    label: "Active",
    className: "bg-primary/15 text-primary",
  },
  published: {
    label: "Published",
    className: "bg-primary/15 text-primary",
  },
  draft: {
    label: "Draft",
    className: "bg-muted text-muted-foreground",
  },
  paused: {
    label: "Paused",
    className: "bg-warning/15 text-warning dark:text-warning",
  },
  archived: {
    label: "Archived",
    className: "bg-muted text-muted-foreground",
  },
};

function formatNumber(n: number): string {
  if (n >= 1000) {
    return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  }
  return n.toString();
}

function AgentCardSkeleton() {
  return (
    <Card className="flex flex-col border-border/60 ring-1 ring-white/[0.04]">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-4 w-56" />
          </div>
          <Skeleton className="h-5 w-16" />
        </div>
        <Skeleton className="h-3 w-24 mt-1" />
      </CardHeader>
      <CardContent className="flex-1 space-y-4">
        <div className="flex gap-1.5">
          <Skeleton className="h-6 w-16" />
          <Skeleton className="h-6 w-20" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-6 w-12" />
          </div>
          <div className="space-y-1">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-6 w-12" />
          </div>
        </div>
      </CardContent>
      <CardFooter className="gap-2">
        <Skeleton className="h-8 flex-1" />
        <Skeleton className="h-8 flex-1" />
      </CardFooter>
    </Card>
  );
}

export default function AgentsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [customerFilter, setCustomerFilter] = useState<string>("all");

  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [customers, setCustomers] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await agentApi.list({
        status: statusFilter !== "all" ? statusFilter : undefined,
        search: searchQuery || undefined,
      });
      const items = res.items ?? res;
      setAgents(Array.isArray(items) ? items : []);
      setCustomers([]);
    } catch (err: any) {
      console.error("Failed to load agents:", err);
      setError(err.message);
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, searchQuery]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchAgents();
    }, searchQuery ? 300 : 0); // debounce search
    return () => clearTimeout(timer);
  }, [fetchAgents, searchQuery]);

  // Client-side customer filter (agents already fetched with status/search)
  const filteredAgents = agents;

  return (
    <div className="p-6 space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
            <Bot className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Agents</h1>
            <p className="text-sm text-muted-foreground">
              Manage your AI-powered insurance sales agents
            </p>
          </div>
        </div>
        <Link href="/agents/new">
          <Button className="rounded-full">
            <Plus className="h-4 w-4 mr-1.5" />
            Create Agent
          </Button>
        </Link>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <Input
            placeholder="Search agents, personas, customers..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 rounded-xl"
          />
        </div>
        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v ?? "all")}>
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="draft">Draft</SelectItem>
            <SelectItem value="paused">Paused</SelectItem>
          </SelectContent>
        </Select>
        <Select value={customerFilter} onValueChange={(v) => setCustomerFilter(v ?? "all")}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Customer" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Customers</SelectItem>
            {customers.map((customer) => (
              <SelectItem key={customer} value={customer}>
                {customer}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Could not load agents. Showing empty state.
        </div>
      )}

      {/* Agent Cards Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <AgentCardSkeleton key={i} />
          ))}
        </div>
      ) : filteredAgents.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Bot className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <h3 className="text-lg font-medium">No agents yet</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Create your first AI agent to get started.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredAgents.map((agent) => {
            const status = statusConfig[agent.status as AgentStatus] ?? statusConfig.draft;
            return (
              <Card key={agent.id} className="flex flex-col border-border/60 ring-1 ring-white/[0.04] transition-all hover:brightness-105 dark:hover:brightness-110">
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <CardTitle className="truncate">{agent.name}</CardTitle>
                      <CardDescription className="mt-0.5">
                        {agent.persona}
                      </CardDescription>
                    </div>
                    <Badge
                      variant="secondary"
                      className={status.className}
                    >
                      {status.label}
                    </Badge>
                  </div>
                </CardHeader>

                <CardContent className="flex-1 space-y-4">
                  {/* Stats Row */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">
                        Conversations
                      </p>
                      <p className="text-lg font-semibold leading-none">
                        {formatNumber((agent as any).conversation_count ?? 0)}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">
                        Completion Rate
                      </p>
                      <p className="text-lg font-semibold leading-none">
                        {(agent.completionRate ?? 0) > 0
                          ? `${agent.completionRate}%`
                          : "--"}
                      </p>
                    </div>
                  </div>
                </CardContent>

                <CardFooter className="gap-2">
                  <Link href={`/agents/${agent.id}`} className="flex-1">
                    <Button variant="outline" className="w-full rounded-full" size="sm">
                      <Settings className="h-3.5 w-3.5 mr-1.5" />
                      Configure
                    </Button>
                  </Link>
                  <Link
                    href={`/agents/${agent.id}?tab=conversations`}
                    className="flex-1"
                  >
                    <Button variant="outline" className="w-full rounded-full" size="sm">
                      <Eye className="h-3.5 w-3.5 mr-1.5" />
                      View Conversations
                    </Button>
                  </Link>
                </CardFooter>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
