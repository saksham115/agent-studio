"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Phone,
  MessageSquare,
  Globe,
  Clock,
  Activity,
  CheckCircle2,
  XCircle,
  Shield,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { conversationApi } from "@/lib/api";

type Channel = "voice" | "whatsapp" | "chatbot";

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

const severityConfig: Record<
  string,
  { className: string }
> = {
  low: {
    className:
      "bg-chart-2/15 text-chart-2",
  },
  medium: {
    className:
      "bg-warning/15 text-warning",
  },
  high: {
    className:
      "bg-destructive/15 text-destructive",
  },
};

// ---------------------------------------------------------------------------
// Loading Skeleton
// ---------------------------------------------------------------------------

function ConversationDetailSkeleton() {
  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <div className="flex items-center gap-3 border-b px-4 py-3">
        <Skeleton className="h-9 w-9" />
        <div className="space-y-1.5 flex-1">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-56" />
        </div>
      </div>
      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-col flex-1 lg:w-2/3 border-r p-4 space-y-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className={`flex ${i % 2 === 0 ? "justify-start" : "justify-end"}`}>
              <Skeleton className="h-16 w-3/5 rounded-2xl" />
            </div>
          ))}
        </div>
        <div className="hidden lg:flex lg:w-1/3 flex-col p-4 space-y-4">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-36 w-full" />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ConversationDetailPage() {
  const params = useParams();
  const conversationId = params.id as string;

  const [conversationData, setConversationData] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedActions, setExpandedActions] = useState<Set<string>>(
    new Set()
  );

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const data = await conversationApi.get(conversationId);
        if (!cancelled) {
          setConversationData(data);
        }
      } catch (err: any) {
        if (!cancelled) {
          console.error("Failed to load conversation:", err);
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
  }, [conversationId]);

  const toggleAction = (actionId: string) => {
    setExpandedActions((prev) => {
      const next = new Set(prev);
      if (next.has(actionId)) {
        next.delete(actionId);
      } else {
        next.add(actionId);
      }
      return next;
    });
  };

  if (loading) return <ConversationDetailSkeleton />;

  if (error || !conversationData) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)] flex-col items-center justify-center">
        <MessageSquare className="h-12 w-12 text-muted-foreground/50 mb-4" />
        <h3 className="text-lg font-medium">Conversation not found</h3>
        <p className="text-sm text-muted-foreground mt-1 mb-4">
          {error
            ? `Error: ${error}`
            : "This conversation does not exist or has not been loaded yet."}
        </p>
        <Link href="/conversations">
          <Button variant="outline">
            <ArrowLeft className="h-4 w-4 mr-1.5" />
            Back to Conversations
          </Button>
        </Link>
      </div>
    );
  }

  const channel = channelConfig[(conversationData.channel as Channel) ?? "chatbot"] ?? channelConfig.chatbot;
  const ChannelIcon = channel.icon;
  const messages: any[] = conversationData.messages ?? [];
  const stateTimeline: any[] = conversationData.stateTimeline ?? [];
  const actionsTriggered: any[] = conversationData.actionsTriggered ?? [];
  const guardrailsTriggered: any[] = conversationData.guardrailsTriggered ?? [];

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Top Bar */}
      <div className="flex items-center gap-3 border-b px-4 py-3">
        <Link href="/conversations">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-base font-semibold truncate">
                {conversationData.contactName}
              </h1>
              <Badge
                variant="secondary"
                className={`gap-1 font-normal shrink-0 ${channel.className}`}
              >
                <ChannelIcon className="h-3 w-3" />
                {channel.label}
              </Badge>
              <span className="inline-flex items-center gap-1.5 shrink-0">
                <span
                  className={`h-2 w-2 rounded-full ${
                    conversationData.status === "active"
                      ? "bg-primary animate-pulse"
                      : "bg-muted-foreground"
                  }`}
                />
                <span
                  className={`text-sm font-medium ${
                    conversationData.status === "active"
                      ? "text-primary"
                      : "text-muted-foreground"
                  }`}
                >
                  {conversationData.status?.charAt(0).toUpperCase() +
                    conversationData.status?.slice(1)}
                </span>
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              {conversationData.contact} &middot; Agent:{" "}
              {conversationData.agentName}
            </p>
          </div>
        </div>
      </div>

      {/* Split Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Panel - Message Thread */}
        <div className="flex flex-col flex-1 lg:w-2/3 border-r">
          <ScrollArea className="flex-1 overflow-y-auto">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <MessageSquare className="h-12 w-12 text-muted-foreground/50 mb-4" />
                <h3 className="text-lg font-medium">No messages yet</h3>
                <p className="text-sm text-muted-foreground mt-1">Messages will appear here as the conversation progresses</p>
              </div>
            ) : (
            <div className="p-4 space-y-3">
              {messages.map((msg: any, idx: number) => {
                const role = msg.role ?? msg.sender ?? "user";
                const timestamp = msg.created_at
                  ? new Date(msg.created_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
                  : msg.timestamp ?? "";

                if (role === "system" || role === "tool") {
                  return (
                    <div key={msg.id ?? idx} className="flex justify-center">
                      <div className="inline-flex items-center gap-2 rounded-full bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground italic">
                        <Activity className="h-3 w-3" />
                        {msg.content}
                        <span className="text-[10px] opacity-70">{timestamp}</span>
                      </div>
                    </div>
                  );
                }

                const isAgent = role === "assistant" || role === "agent";

                return (
                  <div
                    key={msg.id ?? idx}
                    className={`flex ${isAgent ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                        isAgent
                          ? "bg-primary/15 border border-primary/20 text-foreground rounded-br-sm"
                          : "bg-muted/80 border border-border/60 text-foreground rounded-bl-sm"
                      }`}
                    >
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                      <div
                        className={`text-[10px] mt-1.5 flex items-center gap-1 ${
                          isAgent
                            ? "justify-end text-primary/50"
                            : "text-muted-foreground/60"
                        }`}
                      >
                        <span className="font-medium">{isAgent ? "Agent" : "User"}</span>
                        <span>&middot;</span>
                        <span>{timestamp}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            )}
          </ScrollArea>

        </div>

        {/* Right Panel - Metadata Sidebar */}
        <div className="hidden lg:flex lg:w-1/3 flex-col overflow-hidden">
          <ScrollArea className="flex-1 overflow-y-auto">
            <div className="p-4 space-y-4">
              {/* Conversation Info */}
              <Card size="sm">
                <CardHeader className="border-b">
                  <CardTitle className="text-sm">Conversation Info</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 pt-3">
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <p className="text-xs text-muted-foreground">ID</p>
                      <p className="font-mono text-xs">{conversationData.id}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Channel</p>
                      <p className="capitalize">{conversationData.channel}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Direction</p>
                      <p className="capitalize">{conversationData.direction}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Started</p>
                      <p className="text-xs">{conversationData.startedAt}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Duration</p>
                      <p className="inline-flex items-center gap-1">
                        <Clock className="h-3 w-3 text-muted-foreground" />
                        {conversationData.duration}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Messages</p>
                      <p>{conversationData.messageCount}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Current State */}
              <Card size="sm">
                <CardHeader className="border-b">
                  <CardTitle className="text-sm">Current State</CardTitle>
                </CardHeader>
                <CardContent className="pt-3">
                  {stateTimeline.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No state transitions recorded</p>
                  ) : (
                  <div className="flex items-center gap-2">
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10">
                      <Activity className="h-4 w-4 text-primary" />
                    </span>
                    <div>
                      <p className="font-semibold text-sm">{stateTimeline[stateTimeline.length - 1].state}</p>
                      <p className="text-xs text-muted-foreground">
                        Since {stateTimeline[stateTimeline.length - 1].timestamp} ({stateTimeline[stateTimeline.length - 1].duration})
                      </p>
                    </div>
                  </div>
                  )}
                </CardContent>
              </Card>

              {/* State Timeline */}
              <Card size="sm">
                <CardHeader className="border-b">
                  <CardTitle className="text-sm">State Timeline</CardTitle>
                </CardHeader>
                <CardContent className="pt-3">
                  <div className="relative space-y-0">
                    {stateTimeline.map((transition, index) => {
                      const isLast = index === stateTimeline.length - 1;
                      const isCurrent = isLast;
                      return (
                        <div key={transition.state} className="flex gap-3 pb-4 last:pb-0">
                          <div className="flex flex-col items-center">
                            <div
                              className={`h-3 w-3 rounded-full border-2 shrink-0 ${
                                isCurrent
                                  ? "border-primary bg-primary"
                                  : "border-muted-foreground/40 bg-background"
                              }`}
                            />
                            {!isLast && (
                              <div className="w-px flex-1 bg-border mt-1" />
                            )}
                          </div>
                          <div className="flex-1 min-w-0 -mt-0.5">
                            <p
                              className={`text-sm font-medium ${
                                isCurrent ? "text-primary" : "text-foreground"
                              }`}
                            >
                              {transition.state}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {transition.timestamp} &middot;{" "}
                              {transition.duration}
                            </p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>

              {/* Actions Triggered */}
              <Card size="sm">
                <CardHeader className="border-b">
                  <CardTitle className="text-sm">
                    Actions Triggered ({actionsTriggered.length})
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-3 space-y-2">
                  {actionsTriggered.length === 0 && (
                    <p className="text-sm text-muted-foreground">No actions triggered</p>
                  )}
                  {actionsTriggered.map((action) => {
                    const isExpanded = expandedActions.has(action.id);
                    return (
                      <div
                        key={action.id}
                        className="rounded-lg border bg-background"
                      >
                        <button
                          className="flex items-center gap-2 w-full p-2.5 text-left text-sm"
                          onClick={() => toggleAction(action.id)}
                        >
                          {action.status === "success" ? (
                            <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                          ) : (
                            <XCircle className="h-4 w-4 text-red-500 shrink-0" />
                          )}
                          <span className="flex-1 min-w-0 truncate font-medium">
                            {action.name}
                          </span>
                          <span className="text-[10px] text-muted-foreground shrink-0">
                            {action.timestamp}
                          </span>
                          {isExpanded ? (
                            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                          ) : (
                            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                          )}
                        </button>
                        {isExpanded && (
                          <div className="border-t px-2.5 py-2 bg-muted/30">
                            <div className="space-y-1">
                              {Object.entries(action.payload).map(
                                ([key, value]) => (
                                  <div
                                    key={key}
                                    className="flex gap-2 text-xs"
                                  >
                                    <span className="text-muted-foreground shrink-0 font-mono">
                                      {key}:
                                    </span>
                                    <span className="font-mono break-all">
                                      {value}
                                    </span>
                                  </div>
                                )
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </CardContent>
              </Card>

              {/* Guardrails Triggered */}
              <Card size="sm">
                <CardHeader className="border-b">
                  <CardTitle className="text-sm">
                    Guardrails Triggered ({guardrailsTriggered.length})
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-3 space-y-2">
                  {guardrailsTriggered.length === 0 && (
                    <p className="text-sm text-muted-foreground">No guardrails triggered</p>
                  )}
                  {guardrailsTriggered.map((gr) => {
                    const severity = severityConfig[gr.severity] ?? severityConfig.low;
                    return (
                      <div
                        key={gr.id}
                        className="rounded-lg border bg-background p-2.5 space-y-1.5"
                      >
                        <div className="flex items-center gap-2">
                          <Shield className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                          <span className="text-sm font-medium flex-1 min-w-0 truncate">
                            {gr.name}
                          </span>
                          <Badge
                            variant="secondary"
                            className={`text-[10px] capitalize ${severity.className}`}
                          >
                            {gr.severity}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          {gr.details}
                        </p>
                        <p className="text-[10px] text-muted-foreground/60">
                          {gr.timestamp}
                        </p>
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            </div>
          </ScrollArea>
        </div>
      </div>
    </div>
  );
}
