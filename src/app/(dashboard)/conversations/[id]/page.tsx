"use client";

import { useState } from "react";
import Link from "next/link";
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
  Send,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";

type Channel = "voice" | "whatsapp" | "chatbot";
type MessageSender = "agent" | "user" | "system";

interface Message {
  id: string;
  sender: MessageSender;
  content: string;
  timestamp: string;
}

interface StateTransition {
  state: string;
  timestamp: string;
  duration: string;
}

interface ActionTriggered {
  id: string;
  name: string;
  status: "success" | "failed";
  timestamp: string;
  payload: Record<string, string>;
}

interface GuardrailTriggered {
  id: string;
  name: string;
  severity: "low" | "medium" | "high";
  details: string;
  timestamp: string;
}

const conversationData = {
  id: "conv-1001",
  contact: "+91 98XXX XX234",
  contactName: "Ramesh Subramaniam",
  channel: "whatsapp" as Channel,
  direction: "inbound",
  status: "active",
  startedAt: "04 Apr 2026, 2:28 PM",
  duration: "8m 32s",
  messageCount: 12,
  agentName: "Priya Sharma",
  agentId: "agt-001",
};

const messages: Message[] = [
  {
    id: "msg-1",
    sender: "agent",
    content:
      "Namaste! I am Priya from HDFC ERGO. Thank you for reaching out. How can I help you with your insurance needs today?",
    timestamp: "2:28 PM",
  },
  {
    id: "msg-2",
    sender: "user",
    content:
      "Hi, I want health insurance for my family. We are a family of 4 - me, my wife, and two kids.",
    timestamp: "2:29 PM",
  },
  {
    id: "msg-3",
    sender: "agent",
    content:
      "That's wonderful that you're looking to protect your family's health! I'd love to help you find the right plan. Could you please share a few details?\n\n1. Your age and your wife's age?\n2. Ages of your children?\n3. Any pre-existing medical conditions in the family?\n4. Your preferred sum insured range?",
    timestamp: "2:29 PM",
  },
  {
    id: "msg-4",
    sender: "user",
    content:
      "I am 35, wife is 32. Kids are 8 and 5 years old. No major conditions, but my wife has thyroid. Budget around 20-25k per year. We stay in Pune.",
    timestamp: "2:31 PM",
  },
  {
    id: "msg-5",
    sender: "agent",
    content:
      "Thank you, Ramesh! Based on your family profile, I'd recommend these plans:\n\n1. *Optima Secure* - Rs 10L cover, Rs 18,450/yr\n   - Restore benefit, no room rent capping\n\n2. *Optima Super Secure* - Rs 15L cover, Rs 23,200/yr\n   - Includes maternity, OPD cover\n\n3. *My Health Suraksha* - Rs 10L cover, Rs 16,800/yr\n   - Zone-based pricing, fits Pune well\n\nThyroid is covered after a 2-year waiting period in all plans. Shall I generate a detailed quote for any of these?",
    timestamp: "2:32 PM",
  },
  {
    id: "msg-6",
    sender: "user",
    content:
      "The Optima Super Secure with 15L sounds good. Can you tell me the exact premium and what all is covered?",
    timestamp: "2:33 PM",
  },
  {
    id: "msg-7",
    sender: "system",
    content: "State changed: Needs Discovery -> Quote Generation",
    timestamp: "2:33 PM",
  },
  {
    id: "msg-8",
    sender: "system",
    content: "Action triggered: Generate Quote Link (HDFC ERGO Quote API)",
    timestamp: "2:33 PM",
  },
  {
    id: "msg-9",
    sender: "agent",
    content:
      "Great choice! Here's your personalized quote for *HDFC ERGO Optima Super Secure*:\n\n- Sum Insured: Rs 15,00,000\n- Family Floater: 4 members\n- Annual Premium: Rs 23,200 (incl. GST)\n- Cashless Hospitals in Pune: 142\n\nKey Benefits:\n- Restore benefit (100% sum insured restored)\n- No room rent capping\n- Day care procedures covered\n- Annual health check-up\n\nView full details: https://quote.hdfcergo.com/q/HE20260404R234\n\nWould you like to proceed with this plan?",
    timestamp: "2:34 PM",
  },
  {
    id: "msg-10",
    sender: "user",
    content:
      "Looks good, let's proceed. What do I need to do?",
    timestamp: "2:35 PM",
  },
  {
    id: "msg-11",
    sender: "system",
    content: "State changed: Quote Generation -> Document Collection",
    timestamp: "2:35 PM",
  },
  {
    id: "msg-12",
    sender: "agent",
    content:
      "Excellent decision, Ramesh! To proceed with your application, I'll need the following documents for all insured members:\n\n1. Aadhaar Card (front & back)\n2. PAN Card\n3. Recent passport-size photograph\n4. Medical reports for thyroid (wife's last prescription)\n\nYou can simply share photos of these documents here on WhatsApp. All data is encrypted and handled as per IRDAI guidelines.\n\nShall I start with your documents first?",
    timestamp: "2:36 PM",
  },
];

const stateTimeline: StateTransition[] = [
  {
    state: "Greeting",
    timestamp: "2:28 PM",
    duration: "1m",
  },
  {
    state: "Needs Discovery",
    timestamp: "2:29 PM",
    duration: "4m",
  },
  {
    state: "Plan Recommendation",
    timestamp: "2:32 PM",
    duration: "1m",
  },
  {
    state: "Quote Generation",
    timestamp: "2:33 PM",
    duration: "2m",
  },
  {
    state: "Document Collection",
    timestamp: "2:35 PM",
    duration: "ongoing",
  },
];

const actionsTriggered: ActionTriggered[] = [
  {
    id: "act-1",
    name: "Customer Lookup (CRM)",
    status: "success",
    timestamp: "2:28 PM",
    payload: {
      customerId: "CRM-892341",
      existingPolicies: "Motor (Active), Travel (Expired)",
      loyaltyTier: "Silver",
    },
  },
  {
    id: "act-2",
    name: "Generate Quote Link",
    status: "success",
    timestamp: "2:33 PM",
    payload: {
      quoteId: "HE20260404R234",
      plan: "Optima Super Secure",
      sumInsured: "15,00,000",
      premium: "23,200",
      quoteUrl: "https://quote.hdfcergo.com/q/HE20260404R234",
    },
  },
  {
    id: "act-3",
    name: "Send WhatsApp Template",
    status: "success",
    timestamp: "2:34 PM",
    payload: {
      templateName: "quote_summary_v2",
      recipientPhone: "+919812XX234",
      messageId: "wamid.HBgN...",
    },
  },
  {
    id: "act-4",
    name: "DND Registry Check",
    status: "failed",
    timestamp: "2:28 PM",
    payload: {
      phone: "+919812XX234",
      error: "DND API timeout after 3s, proceeded with consent flag",
    },
  },
];

const guardrailsTriggered: GuardrailTriggered[] = [
  {
    id: "gr-1",
    name: "PII Detection",
    severity: "medium",
    details:
      "User shared Aadhaar number in message. Auto-masked in logs per DPDP Act compliance.",
    timestamp: "2:31 PM",
  },
  {
    id: "gr-2",
    name: "Premium Accuracy Check",
    severity: "low",
    details:
      "Agent-quoted premium Rs 23,200 verified against rate engine. Match confirmed.",
    timestamp: "2:34 PM",
  },
  {
    id: "gr-3",
    name: "Competitor Mention Block",
    severity: "low",
    details:
      "User mentioned 'Star Health'. Agent correctly redirected without disparagement.",
    timestamp: "2:33 PM",
  },
];

const channelConfig: Record<
  Channel,
  { icon: typeof Phone; label: string; className: string }
> = {
  voice: {
    icon: Phone,
    label: "Voice",
    className:
      "bg-blue-500/15 text-blue-600 dark:bg-blue-500/20 dark:text-blue-400",
  },
  whatsapp: {
    icon: MessageSquare,
    label: "WhatsApp",
    className:
      "bg-emerald-500/15 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400",
  },
  chatbot: {
    icon: Globe,
    label: "Chatbot",
    className:
      "bg-purple-500/15 text-purple-600 dark:bg-purple-500/20 dark:text-purple-400",
  },
};

const severityConfig: Record<
  string,
  { className: string }
> = {
  low: {
    className:
      "bg-blue-500/15 text-blue-600 dark:bg-blue-500/20 dark:text-blue-400",
  },
  medium: {
    className:
      "bg-amber-500/15 text-amber-600 dark:bg-amber-500/20 dark:text-amber-400",
  },
  high: {
    className:
      "bg-red-500/15 text-red-600 dark:bg-red-500/20 dark:text-red-400",
  },
};

export default function ConversationDetailPage() {
  const [expandedActions, setExpandedActions] = useState<Set<string>>(
    new Set()
  );

  const channel = channelConfig[conversationData.channel];
  const ChannelIcon = channel.icon;

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
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
                  Active
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
            <div className="p-4 space-y-4">
              {messages.map((msg) => {
                if (msg.sender === "system") {
                  return (
                    <div key={msg.id} className="flex justify-center">
                      <div className="inline-flex items-center gap-2 rounded-full bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground italic">
                        <Activity className="h-3 w-3" />
                        {msg.content}
                        <span className="text-[10px] opacity-70">
                          {msg.timestamp}
                        </span>
                      </div>
                    </div>
                  );
                }

                const isAgent = msg.sender === "agent";

                return (
                  <div
                    key={msg.id}
                    className={`flex ${isAgent ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                        isAgent
                          ? "bg-primary/10 text-foreground rounded-br-md"
                          : "bg-muted text-foreground rounded-bl-md"
                      }`}
                    >
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                      <div
                        className={`text-[10px] mt-1.5 ${
                          isAgent
                            ? "text-right text-primary/60"
                            : "text-muted-foreground"
                        }`}
                      >
                        {isAgent ? "Priya (Agent)" : "Ramesh"} &middot;{" "}
                        {msg.timestamp}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>

          {/* Input Area */}
          <div className="border-t p-3">
            <div className="flex items-center gap-2">
              <Input
                placeholder="Live input not available"
                disabled
                className="flex-1 opacity-50"
              />
              <Button size="icon" disabled>
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
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
                  <div className="flex items-center gap-2">
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10">
                      <Activity className="h-4 w-4 text-primary" />
                    </span>
                    <div>
                      <p className="font-semibold text-sm">Document Collection</p>
                      <p className="text-xs text-muted-foreground">
                        Since 2:35 PM (ongoing)
                      </p>
                    </div>
                  </div>
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
                  {guardrailsTriggered.map((gr) => {
                    const severity = severityConfig[gr.severity];
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
