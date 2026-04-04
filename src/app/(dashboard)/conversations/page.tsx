"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import {
  MessageSquare,
  Phone,
  Globe,
  Search,
  Download,
  Clock,
  Activity,
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

type Channel = "voice" | "whatsapp" | "chatbot";
type ConversationStatus = "active" | "completed" | "escalated" | "dropped";

interface Conversation {
  id: string;
  contact: string;
  contactName: string;
  agentName: string;
  channel: Channel;
  currentState: string;
  messages: number;
  duration: string;
  status: ConversationStatus;
  startedAt: string;
  startedRelative: string;
}

const conversations: Conversation[] = [
  {
    id: "conv-1001",
    contact: "+91 98XXX XX234",
    contactName: "Ramesh S.",
    agentName: "Priya Sharma",
    channel: "voice",
    currentState: "Quote Generation",
    messages: 24,
    duration: "8m 32s",
    status: "active",
    startedAt: "2026-04-04T14:28:00",
    startedRelative: "2 min ago",
  },
  {
    id: "conv-1002",
    contact: "+91 87XXX XX891",
    contactName: "Sunita Devi",
    agentName: "Rajesh Kumar",
    channel: "whatsapp",
    currentState: "Document Collection",
    messages: 18,
    duration: "12m 05s",
    status: "active",
    startedAt: "2026-04-04T14:18:00",
    startedRelative: "12 min ago",
  },
  {
    id: "conv-1003",
    contact: "+91 70XXX XX456",
    contactName: "Amit Patel",
    agentName: "Ananya Reddy",
    channel: "voice",
    currentState: "Payment Confirmation",
    messages: 31,
    duration: "15m 48s",
    status: "completed",
    startedAt: "2026-04-04T13:45:00",
    startedRelative: "45 min ago",
  },
  {
    id: "conv-1004",
    contact: "+91 99XXX XX102",
    contactName: "Kavita Nair",
    agentName: "Vikram Mehta",
    channel: "chatbot",
    currentState: "Needs Discovery",
    messages: 8,
    duration: "3m 15s",
    status: "active",
    startedAt: "2026-04-04T14:27:00",
    startedRelative: "3 min ago",
  },
  {
    id: "conv-1005",
    contact: "+91 81XXX XX578",
    contactName: "Deepak Joshi",
    agentName: "Neha Gupta",
    channel: "whatsapp",
    currentState: "Escalated to Manager",
    messages: 22,
    duration: "9m 40s",
    status: "escalated",
    startedAt: "2026-04-04T14:05:00",
    startedRelative: "25 min ago",
  },
  {
    id: "conv-1006",
    contact: "+91 93XXX XX345",
    contactName: "Pradeep Rao",
    agentName: "Arjun Patel",
    channel: "voice",
    currentState: "Call Dropped",
    messages: 5,
    duration: "1m 52s",
    status: "dropped",
    startedAt: "2026-04-04T13:30:00",
    startedRelative: "1 hour ago",
  },
  {
    id: "conv-1007",
    contact: "+91 76XXX XX890",
    contactName: "Lakshmi Iyer",
    agentName: "Priya Sharma",
    channel: "chatbot",
    currentState: "Plan Comparison",
    messages: 14,
    duration: "6m 20s",
    status: "active",
    startedAt: "2026-04-04T14:10:00",
    startedRelative: "20 min ago",
  },
  {
    id: "conv-1008",
    contact: "+91 85XXX XX612",
    contactName: "Manoj Tiwari",
    agentName: "Rajesh Kumar",
    channel: "whatsapp",
    currentState: "Policy Issued",
    messages: 28,
    duration: "18m 10s",
    status: "completed",
    startedAt: "2026-04-04T12:00:00",
    startedRelative: "2 hours ago",
  },
  {
    id: "conv-1009",
    contact: "+91 62XXX XX789",
    contactName: "Sneha Kulkarni",
    agentName: "Ananya Reddy",
    channel: "voice",
    currentState: "Greeting",
    messages: 2,
    duration: "0m 35s",
    status: "active",
    startedAt: "2026-04-04T14:29:00",
    startedRelative: "1 min ago",
  },
  {
    id: "conv-1010",
    contact: "+91 91XXX XX223",
    contactName: "Farhan Sheikh",
    agentName: "Vikram Mehta",
    channel: "chatbot",
    currentState: "Not Interested",
    messages: 10,
    duration: "4m 55s",
    status: "dropped",
    startedAt: "2026-04-04T13:55:00",
    startedRelative: "35 min ago",
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

const statusConfig: Record<
  ConversationStatus,
  { label: string; dotClass: string; textClass: string }
> = {
  active: {
    label: "Active",
    dotClass: "bg-emerald-500",
    textClass: "text-emerald-600 dark:text-emerald-400",
  },
  completed: {
    label: "Completed",
    dotClass: "bg-blue-500",
    textClass: "text-blue-600 dark:text-blue-400",
  },
  escalated: {
    label: "Escalated",
    dotClass: "bg-amber-500",
    textClass: "text-amber-600 dark:text-amber-400",
  },
  dropped: {
    label: "Dropped",
    dotClass: "bg-red-500",
    textClass: "text-red-600 dark:text-red-400",
  },
};

const agentNames = Array.from(new Set(conversations.map((c) => c.agentName)));

export default function ConversationsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [channelFilter, setChannelFilter] = useState<string>("all");
  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const filteredConversations = useMemo(() => {
    return conversations.filter((conv) => {
      const matchesSearch =
        searchQuery === "" ||
        conv.contact.toLowerCase().includes(searchQuery.toLowerCase()) ||
        conv.contactName.toLowerCase().includes(searchQuery.toLowerCase()) ||
        conv.agentName.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesChannel =
        channelFilter === "all" || conv.channel === channelFilter;

      const matchesAgent =
        agentFilter === "all" || conv.agentName === agentFilter;

      const matchesStatus =
        statusFilter === "all" || conv.status === statusFilter;

      return matchesSearch && matchesChannel && matchesAgent && matchesStatus;
    });
  }, [searchQuery, channelFilter, agentFilter, statusFilter]);

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

        <Select value={agentFilter} onValueChange={(v) => setAgentFilter(v ?? "all")}>
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

        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v ?? "all")}>
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

      {/* Table */}
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
                    <p className="text-sm">No conversations match your filters</p>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              filteredConversations.map((conv) => {
                const channel = channelConfig[conv.channel];
                const status = statusConfig[conv.status];
                const ChannelIcon = channel.icon;

                return (
                  <TableRow key={conv.id} className="cursor-pointer">
                    <TableCell>
                      <Link
                        href={`/conversations/${conv.id}`}
                        className="block"
                      >
                        <div className="font-medium text-foreground">
                          {conv.contactName}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {conv.contact}
                        </div>
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/conversations/${conv.id}`}
                        className="block text-sm"
                      >
                        {conv.agentName}
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
                      <Link href={`/conversations/${conv.id}`} className="block">
                        <Badge variant="outline" className="font-normal">
                          {conv.currentState}
                        </Badge>
                      </Link>
                    </TableCell>
                    <TableCell className="text-center">
                      <Link
                        href={`/conversations/${conv.id}`}
                        className="block text-sm tabular-nums"
                      >
                        {conv.messages}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/conversations/${conv.id}`}
                        className="block text-sm tabular-nums text-muted-foreground"
                      >
                        <span className="inline-flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {conv.duration}
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
                        {conv.startedRelative}
                      </Link>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Showing <span className="font-medium text-foreground">1-10</span> of{" "}
          <span className="font-medium text-foreground">247</span> conversations
        </p>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled>
            <ChevronLeft className="h-4 w-4" />
            Previous
          </Button>
          <Button variant="outline" size="sm">
            Next
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
