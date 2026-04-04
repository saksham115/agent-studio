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

// TODO: fetch from API
const conversations: Conversation[] = [];

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

// TODO: fetch from API
const agentNames: string[] = [];

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
                    <p className="text-sm font-medium">No conversations yet</p>
                    <p className="text-xs">Conversations will appear here once agents start interacting</p>
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
          Showing <span className="font-medium text-foreground">{filteredConversations.length === 0 ? "0" : `1-${filteredConversations.length}`}</span> of{" "}
          <span className="font-medium text-foreground">{filteredConversations.length}</span> conversations
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
