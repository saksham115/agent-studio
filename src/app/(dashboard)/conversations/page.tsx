"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import {
  MessageSquare,
  Phone,
  Globe,
  Search,
  Download,
  Clock,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  conversationApi,
  agentApi,
  type AgentResponse,
} from "@/lib/api";

type Channel = "voice" | "whatsapp" | "chatbot";
type ConversationStatus = "active" | "completed" | "escalated" | "dropped" | "abandoned";

const channelConfig: Record<
  Channel,
  { icon: typeof Phone; label: string; className: string }
> = {
  voice: {
    icon: Phone,
    label: "Voice",
    className:
      "bg-chart-2/15 text-chart-2",
  },
  whatsapp: {
    icon: MessageSquare,
    label: "WhatsApp",
    className:
      "bg-primary/15 text-primary",
  },
  chatbot: {
    icon: Globe,
    label: "Chatbot",
    className:
      "bg-chart-4/15 text-chart-4",
  },
};

const statusConfig: Record<
  ConversationStatus,
  { label: string; dotClass: string; textClass: string }
> = {
  active: {
    label: "Active",
    dotClass: "bg-primary",
    textClass: "text-primary",
  },
  completed: {
    label: "Completed",
    dotClass: "bg-chart-2",
    textClass: "text-chart-2",
  },
  escalated: {
    label: "Escalated",
    dotClass: "bg-warning",
    textClass: "text-warning",
  },
  dropped: {
    label: "Dropped",
    dotClass: "bg-destructive",
    textClass: "text-destructive",
  },
  abandoned: {
    label: "Abandoned",
    dotClass: "bg-destructive",
    textClass: "text-destructive",
  },
};

function TableSkeleton() {
  return (
    <div className="rounded-xl border bg-card ring-1 ring-foreground/10">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Contact</TableHead>
            <TableHead>Agent</TableHead>
            <TableHead>Channel</TableHead>
            <TableHead>Current State</TableHead>
            <TableHead className="text-center">Messages</TableHead>
            <TableHead>Duration</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Started</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: 5 }).map((_, i) => (
            <TableRow key={i}>
              <TableCell><Skeleton className="h-5 w-32" /></TableCell>
              <TableCell><Skeleton className="h-5 w-24" /></TableCell>
              <TableCell><Skeleton className="h-5 w-20" /></TableCell>
              <TableCell><Skeleton className="h-5 w-24" /></TableCell>
              <TableCell className="text-center"><Skeleton className="h-5 w-8 mx-auto" /></TableCell>
              <TableCell><Skeleton className="h-5 w-16" /></TableCell>
              <TableCell><Skeleton className="h-5 w-20" /></TableCell>
              <TableCell><Skeleton className="h-5 w-16" /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export default function ConversationsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [channelFilter, setChannelFilter] = useState<string>("all");
  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [page, setPage] = useState(1);

  const [conversations, setConversations] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [agentNames, setAgentNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fetch agent names for the filter dropdown
  useEffect(() => {
    agentApi
      .list()
      .then((res) => {
        const items = res.items ?? res;
        if (Array.isArray(items)) {
          setAgentNames(items.map((a: AgentResponse) => a.name).filter(Boolean));
        }
      })
      .catch(() => {
        // non-critical, leave dropdown empty
      });
  }, []);

  const fetchConversations = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      let res;
      if (searchQuery.trim()) {
        res = await conversationApi.search(searchQuery.trim());
      } else {
        res = await conversationApi.list({
          agent_id: agentFilter !== "all" ? agentFilter : undefined,
          status: statusFilter !== "all" ? statusFilter : undefined,
          page,
        });
      }

      const items = res.items ?? (Array.isArray(res) ? res : []);
      setConversations(items);
      setTotal(res.total ?? items.length);
    } catch (err: any) {
      console.error("Failed to load conversations:", err);
      setError(err.message);
      setConversations([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [agentFilter, statusFilter, page, searchQuery]);

  // Debounced fetch for search, immediate for filter changes
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);

    if (searchQuery) {
      searchTimerRef.current = setTimeout(() => {
        fetchConversations();
      }, 400);
    } else {
      fetchConversations();
    }

    return () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    };
  }, [fetchConversations, searchQuery]);

  // Client-side channel filter (API may not support channel filter directly)
  const filteredConversations = conversations.filter((conv: any) => {
    return channelFilter === "all" || (conv.channel_type ?? "chatbot") === channelFilter;
  });

  return (
    <div className="p-6 space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <MessageSquare className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Conversations</h1>
            <p className="text-sm text-muted-foreground">
              Monitor and review all agent conversations
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative w-64">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              placeholder="Search contacts, agents..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8"
            />
          </div>
          <Button variant="outline">
            <Download className="h-4 w-4 mr-1.5" />
            Export
          </Button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap gap-3">
        <Select value={channelFilter} onValueChange={(v) => setChannelFilter(v ?? "all")}>
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Channel" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Channels</SelectItem>
            <SelectItem value="voice">Voice</SelectItem>
            <SelectItem value="whatsapp">WhatsApp</SelectItem>
            <SelectItem value="chatbot">Chatbot</SelectItem>
          </SelectContent>
        </Select>

        <Select value={agentFilter} onValueChange={(v) => { setAgentFilter(v ?? "all"); setPage(1); }}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Agent" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Agents</SelectItem>
            {agentNames.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v ?? "all"); setPage(1); }}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="escalated">Escalated</SelectItem>
            <SelectItem value="dropped">Dropped</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Could not load conversations. Showing empty state.
        </div>
      )}

      {/* Table */}
      {loading ? (
        <TableSkeleton />
      ) : (
        <div className="rounded-xl border bg-card ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Contact</TableHead>
                <TableHead>Agent</TableHead>
                <TableHead>Channel</TableHead>
                <TableHead>Current State</TableHead>
                <TableHead className="text-center">Messages</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredConversations.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="h-24 text-center">
                    <div className="flex flex-col items-center gap-2 text-muted-foreground">
                      <MessageSquare className="h-8 w-8 opacity-40" />
                      <p className="text-sm font-medium">No conversations yet</p>
                      <p className="text-xs">Conversations will appear here once agents start interacting</p>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                filteredConversations.map((conv: any) => {
                  const chType = conv.channel_type ?? "chatbot";
                  const channel = channelConfig[chType as Channel] ?? channelConfig.chatbot;
                  const status = statusConfig[conv.status as ConversationStatus] ?? statusConfig.active;
                  const ChannelIcon = channel.icon;
                  const startedAt = conv.started_at ? new Date(conv.started_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "--";

                  return (
                    <TableRow key={conv.id} className="cursor-pointer">
                      <TableCell>
                        <Link
                          href={`/conversations/${conv.id}`}
                          className="block"
                        >
                          <div className="font-medium text-foreground">
                            {conv.external_user_name || conv.external_user_phone || "--"}
                          </div>
                          {conv.external_user_phone && conv.external_user_name && (
                            <div className="text-xs text-muted-foreground">
                              {conv.external_user_phone}
                            </div>
                          )}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Link
                          href={`/conversations/${conv.id}`}
                          className="block text-sm"
                        >
                          {conv.agent_name ?? "--"}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Link href={`/conversations/${conv.id}`} className="block">
                          <Badge
                            variant="secondary"
                            className={`gap-1 font-normal ${channel.className}`}
                          >
                            <ChannelIcon className="h-3 w-3" />
                            {channel.label}
                          </Badge>
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Link href={`/conversations/${conv.id}`} className="block text-sm text-muted-foreground">
                          {conv.current_state_name ?? "--"}
                        </Link>
                      </TableCell>
                      <TableCell className="text-center">
                        <Link
                          href={`/conversations/${conv.id}`}
                          className="block text-sm tabular-nums"
                        >
                          {conv.message_count ?? 0}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Link
                          href={`/conversations/${conv.id}`}
                          className="block text-sm tabular-nums text-muted-foreground"
                        >
                          <span className="inline-flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            --
                          </span>
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Link href={`/conversations/${conv.id}`} className="block">
                          <span className="inline-flex items-center gap-1.5">
                            <span
                              className={`h-2 w-2 rounded-full ${status.dotClass} ${
                                conv.status === "active" ? "animate-pulse" : ""
                              }`}
                            />
                            <span className={`text-sm font-medium ${status.textClass}`}>
                              {status.label}
                            </span>
                          </span>
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Link
                          href={`/conversations/${conv.id}`}
                          className="block text-sm text-muted-foreground"
                        >
                          {startedAt}
                        </Link>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Showing <span className="font-medium text-foreground">{filteredConversations.length === 0 ? "0" : `1-${filteredConversations.length}`}</span> of{" "}
          <span className="font-medium text-foreground">{total}</span> conversations
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            <ChevronLeft className="h-4 w-4" />
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={filteredConversations.length < 20}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
