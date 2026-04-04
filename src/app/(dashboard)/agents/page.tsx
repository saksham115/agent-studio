"use client";

import { useState, useMemo } from "react";
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

type AgentStatus = "active" | "draft" | "paused";
type Channel = "voice" | "whatsapp" | "chatbot";

interface Agent {
  id: string;
  name: string;
  persona: string;
  customer: string;
  status: AgentStatus;
  channels: Channel[];
  conversations: number;
  completionRate: number;
  createdAt: string;
}

// TODO: fetch from API
const agents: Agent[] = [];

// TODO: fetch from API
const customers: string[] = [];

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

function formatNumber(n: number): string {
  if (n >= 1000) {
    return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  }
  return n.toString();
}

export default function AgentsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [customerFilter, setCustomerFilter] = useState<string>("all");

  const filteredAgents = useMemo(() => {
    return agents.filter((agent) => {
      const matchesSearch =
        searchQuery === "" ||
        agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        agent.persona.toLowerCase().includes(searchQuery.toLowerCase()) ||
        agent.customer.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesStatus =
        statusFilter === "all" || agent.status === statusFilter;

      const matchesCustomer =
        customerFilter === "all" || agent.customer === customerFilter;

      return matchesSearch && matchesStatus && matchesCustomer;
    });
  }, [searchQuery, statusFilter, customerFilter]);

  return (
    <div className="p-6 space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Bot className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Agents</h1>
            <p className="text-sm text-muted-foreground">
              Manage your AI-powered insurance sales agents
            </p>
          </div>
        </div>
        <Link href="/agents/new">
          <Button>
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
            className="pl-8"
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

      {/* Agent Cards Grid */}
      {filteredAgents.length === 0 ? (
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
            const status = statusConfig[agent.status];
            return (
              <Card key={agent.id} className="flex flex-col">
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
                  <p className="text-xs text-muted-foreground font-medium">
                    {agent.customer}
                  </p>
                </CardHeader>

                <CardContent className="flex-1 space-y-4">
                  {/* Channel Badges */}
                  <div className="flex flex-wrap gap-1.5">
                    {agent.channels.map((channel) => {
                      const config = channelConfig[channel];
                      const Icon = config.icon;
                      return (
                        <Badge
                          key={channel}
                          variant="outline"
                          className="gap-1 font-normal"
                        >
                          <Icon className="h-3 w-3" />
                          {config.label}
                        </Badge>
                      );
                    })}
                  </div>

                  {/* Stats Row */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">
                        Conversations
                      </p>
                      <p className="text-lg font-semibold leading-none">
                        {formatNumber(agent.conversations)}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">
                        Completion Rate
                      </p>
                      <p className="text-lg font-semibold leading-none">
                        {agent.completionRate > 0
                          ? `${agent.completionRate}%`
                          : "--"}
                      </p>
                    </div>
                  </div>
                </CardContent>

                <CardFooter className="gap-2">
                  <Link href={`/agents/${agent.id}`} className="flex-1">
                    <Button variant="outline" className="w-full" size="sm">
                      <Settings className="h-3.5 w-3.5 mr-1.5" />
                      Configure
                    </Button>
                  </Link>
                  <Link
                    href={`/agents/${agent.id}?tab=conversations`}
                    className="flex-1"
                  >
                    <Button variant="outline" className="w-full" size="sm">
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
