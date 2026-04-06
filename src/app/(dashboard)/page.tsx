"use client"

import { useEffect, useState } from "react"
import {
  Phone,
  MessageCircle,
  Globe,
  Bot,
  TrendingUp,
  TrendingDown,
  Users,
  Clock,
  Activity,
} from "lucide-react"
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Cell,
} from "recharts"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Skeleton } from "@/components/ui/skeleton"
import { dashboardApi, conversationApi, type DashboardOverview } from "@/lib/api"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type Channel = "Voice" | "WhatsApp" | "Chatbot"

const channelConfig: Record<Channel, { color: string; icon: React.ElementType }> = {
  Voice: { color: "bg-chart-2/15 text-chart-2", icon: Phone },
  WhatsApp: { color: "bg-primary/15 text-primary", icon: MessageCircle },
  Chatbot: { color: "bg-chart-4/15 text-chart-4", icon: Globe },
}

function ChannelBadge({ channel }: { channel: Channel }) {
  const cfg = channelConfig[channel]
  const Icon = cfg.icon
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${cfg.color}`}
    >
      <Icon className="size-3" />
      {channel}
    </span>
  )
}

function getInitials(name: string) {
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2)
}

// ---------------------------------------------------------------------------
// Custom tooltip for area chart
// ---------------------------------------------------------------------------

function ConversationTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-border/60 bg-card px-3 py-2 text-sm shadow-none ring-1 ring-white/[0.04]">
      <p className="mb-1 font-medium text-card-foreground">{label}</p>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2 text-muted-foreground">
          <span
            className="inline-block size-2 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="capitalize">{entry.name}:</span>
          <span className="font-medium text-card-foreground">{entry.value}</span>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Custom tooltip for funnel chart
// ---------------------------------------------------------------------------

function FunnelTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ payload: { stage: string; count: number; percent: number; fill: string } }>
}) {
  if (!active || !payload?.length) return null
  const data = payload[0].payload
  return (
    <div className="rounded-xl border border-border/60 bg-card px-3 py-2 text-sm shadow-none ring-1 ring-white/[0.04]">
      <p className="font-medium text-card-foreground">{data.stage}</p>
      <p className="text-muted-foreground">
        {data.count.toLocaleString()} conversations ({data.percent}%)
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function DashboardSkeleton() {
  return (
    <div className="p-6 space-y-6">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-4 w-64 mt-1" />
        </div>
        <Skeleton className="h-6 w-24" />
      </div>
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between pb-0">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-4 w-4" />
            </CardHeader>
            <CardContent className="pt-0">
              <Skeleton className="h-8 w-16 mt-2" />
              <Skeleton className="h-3 w-32 mt-2" />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-7">
        <Card className="lg:col-span-4">
          <CardHeader>
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-4 w-64 mt-1" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-[300px] w-full" />
          </CardContent>
        </Card>
        <Card className="lg:col-span-3">
          <CardHeader>
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-4 w-56 mt-1" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-[300px] w-full" />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const [data, setData] = useState<DashboardOverview | null>(null)
  const [recentConvs, setRecentConvs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([
      dashboardApi.overview(),
      conversationApi.list({ page: 1 }),
    ])
      .then(([overview, convsRes]) => {
        if (!cancelled) {
          setData(overview)
          setRecentConvs(convsRes?.items ?? [])
          setError(null)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          console.error("Failed to load dashboard:", err)
          setError(err.message)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (loading) return <DashboardSkeleton />

  // Compute derived stats from API response
  const totalAgents = data?.total_agents ?? 0
  const activeAgents = data?.active_agents ?? 0
  const totalConversations = data?.total_conversations ?? 0
  const activeConversations = data?.active_conversations ?? 0
  const completedConversations = data?.conversations_by_status?.completed ?? 0
  const completionRate = totalConversations > 0
    ? Math.round((completedConversations / totalConversations) * 100)
    : null
  const avgMsgs = data?.avg_messages_per_conversation ?? 0

  const kpiCards = [
    {
      title: "Total Agents",
      value: String(totalAgents),
      subtitle: `${activeAgents} active, ${totalAgents - activeAgents} draft`,
      icon: Bot,
      trend: null as null | { value: string; direction: "up" | "down" },
    },
    {
      title: "Total Conversations",
      value: String(totalConversations),
      subtitle: `${activeConversations} active`,
      icon: MessageCircle,
      trend: null as null | { value: string; direction: "up" | "down" },
    },
    {
      title: "Completion Rate",
      value: completionRate != null ? `${completionRate}%` : "--",
      subtitle: `${completedConversations} completed`,
      icon: Activity,
      trend: null as null | { value: string; direction: "up" | "down" },
    },
    {
      title: "Avg Messages",
      value: avgMsgs > 0 ? avgMsgs.toFixed(1) : "--",
      subtitle: "per conversation",
      icon: Clock,
      trend: null as null | { value: string; direction: "up" | "down" },
    },
  ]

  // Conversations Over Time — use today's aggregate since we don't have daily data yet
  const byChannel = data?.conversations_by_channel ?? {}
  const today = new Date().toLocaleDateString("en-IN", { day: "numeric", month: "short" })
  const hasChannelData = Object.keys(byChannel).length > 0
  const conversationData = hasChannelData
    ? [{ date: today, voice: byChannel.voice ?? 0, whatsapp: byChannel.whatsapp ?? 0, chatbot: byChannel.chatbot ?? 0 }]
    : []

  // Conversation Funnel — from status breakdown
  const byStatus = data?.conversations_by_status ?? {}
  const funnelTotal = totalConversations || 1
  const funnelData = [
    { stage: "Active", count: byStatus.active ?? 0, percent: Math.round(((byStatus.active ?? 0) / funnelTotal) * 100), fill: "var(--chart-1)" },
    { stage: "Completed", count: byStatus.completed ?? 0, percent: Math.round(((byStatus.completed ?? 0) / funnelTotal) * 100), fill: "var(--chart-2)" },
    { stage: "Escalated", count: byStatus.escalated ?? 0, percent: Math.round(((byStatus.escalated ?? 0) / funnelTotal) * 100), fill: "var(--chart-3)" },
    { stage: "Abandoned", count: byStatus.abandoned ?? 0, percent: Math.round(((byStatus.abandoned ?? 0) / funnelTotal) * 100), fill: "var(--chart-5)" },
  ].filter((d) => d.count > 0)

  // Recent conversations from API
  const recentConversations = recentConvs.slice(0, 5).map((c: any) => ({
    id: c.id,
    contact: c.external_user_phone || c.external_user_name || "--",
    agent: c.agent_name || "--",
    channel: (c.channel_type === "whatsapp" ? "WhatsApp" : c.channel_type === "voice" ? "Voice" : "Chatbot") as "Voice" | "WhatsApp" | "Chatbot",
    stateReached: c.current_state_name || "--",
    timeAgo: c.started_at ? new Date(c.started_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "--",
  }))

  // Map top agents from API response
  const topAgents = (data?.top_agents ?? []).map((a) => ({
    name: a.name,
    conversations: a.conversation_count,
    completionRate: 0,
    channels: [] as Channel[],
  }))

  return (
    <div className="p-6 space-y-6">
      {/* ---------------------------------------------------------------- */}
      {/* Page Header                                                      */}
      {/* ---------------------------------------------------------------- */}
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Organisation-wide overview for today, {new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
          </p>
        </div>
        <Badge variant="secondary" className="w-fit text-xs">
          Last 7 days
        </Badge>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Could not load dashboard data. Showing empty state.
        </div>
      )}

      {/* ---------------------------------------------------------------- */}
      {/* KPI Cards                                                        */}
      {/* ---------------------------------------------------------------- */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {kpiCards.map((kpi) => {
          const Icon = kpi.icon
          return (
            <Card key={kpi.title} className="border-border/60 ring-1 ring-white/[0.04]">
              <CardHeader className="flex flex-row items-center justify-between pb-0">
                <CardDescription className="text-sm font-medium">
                  {kpi.title}
                </CardDescription>
                <Icon className="size-4 text-muted-foreground" />
              </CardHeader>
              <CardContent className="pt-0">
                <div className="text-3xl font-light tracking-tight">{kpi.value}</div>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  {kpi.trend && (
                    <span
                      className={`inline-flex items-center gap-0.5 font-medium ${
                        kpi.trend.direction === "up"
                          ? "text-primary"
                          : "text-destructive"
                      }`}
                    >
                      {kpi.trend.direction === "up" ? (
                        <TrendingUp className="size-3" />
                      ) : (
                        <TrendingDown className="size-3" />
                      )}
                      {kpi.trend.value}
                    </span>
                  )}
                  <span>{kpi.subtitle}</span>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Charts Row                                                       */}
      {/* ---------------------------------------------------------------- */}
      <div className="grid gap-6 lg:grid-cols-7">
        {/* Conversations over time */}
        <Card className="lg:col-span-4 border-border/60 ring-1 ring-white/[0.04]">
          <CardHeader>
            <CardTitle>Conversations Over Time</CardTitle>
            <CardDescription>
              Daily breakdown by channel (last 7 days)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] min-h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={conversationData}
                  margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="gradVoice" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="oklch(0.7 0.15 200)" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="oklch(0.7 0.15 200)" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="gradWhatsApp" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="oklch(0.87 0.2 165)" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="oklch(0.87 0.2 165)" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="gradChatbot" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="oklch(0.7 0.15 300)" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="oklch(0.7 0.15 300)" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 12 }}
                    className="fill-muted-foreground"
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 12 }}
                    className="fill-muted-foreground"
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip content={<ConversationTooltip />} />
                  <Legend
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
                  />
                  <Area
                    type="monotone"
                    dataKey="voice"
                    name="Voice"
                    stackId="1"
                    stroke="oklch(0.7 0.15 200)"
                    fill="url(#gradVoice)"
                    strokeWidth={2}
                  />
                  <Area
                    type="monotone"
                    dataKey="whatsapp"
                    name="WhatsApp"
                    stackId="1"
                    stroke="oklch(0.87 0.2 165)"
                    fill="url(#gradWhatsApp)"
                    strokeWidth={2}
                  />
                  <Area
                    type="monotone"
                    dataKey="chatbot"
                    name="Chatbot"
                    stackId="1"
                    stroke="oklch(0.7 0.15 300)"
                    fill="url(#gradChatbot)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Funnel chart */}
        <Card className="lg:col-span-3 border-border/60 ring-1 ring-white/[0.04]">
          <CardHeader>
            <CardTitle>Conversation Funnel</CardTitle>
            <CardDescription>
              Stage progression and drop-off rates
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] min-h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={funnelData}
                  layout="vertical"
                  margin={{ top: 4, right: 30, left: 10, bottom: 0 }}
                >
                  <CartesianGrid
                    horizontal={false}
                    strokeDasharray="3 3"
                    className="stroke-border"
                  />
                  <XAxis
                    type="number"
                    tick={{ fontSize: 12 }}
                    className="fill-muted-foreground"
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    type="category"
                    dataKey="stage"
                    tick={{ fontSize: 12 }}
                    className="fill-muted-foreground"
                    tickLine={false}
                    axisLine={false}
                    width={110}
                  />
                  <Tooltip content={<FunnelTooltip />} />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={28}>
                    {funnelData.map((entry) => (
                      <Cell key={entry.stage} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            {/* Drop-off labels */}
            {funnelData.length > 1 && (
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              {funnelData.slice(1).map((stage, i) => {
                const prev = funnelData[i]
                const dropOff = prev.percent - stage.percent
                return (
                  <span key={stage.stage} className="flex items-center gap-1">
                    <TrendingDown className="size-3 text-red-500" />
                    {prev.stage} &rarr; {stage.stage}: -{dropOff}%
                  </span>
                )
              })}
            </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Bottom Section                                                   */}
      {/* ---------------------------------------------------------------- */}
      <div className="grid gap-6 lg:grid-cols-5">
        {/* Recent Conversations */}
        <Card className="lg:col-span-3 border-border/60 ring-1 ring-white/[0.04]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="size-4" />
              Recent Conversations
            </CardTitle>
            <CardDescription>Latest interactions across all agents</CardDescription>
          </CardHeader>
          <CardContent>
            {recentConversations.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <MessageCircle className="h-12 w-12 text-muted-foreground/50 mb-4" />
                <h3 className="text-lg font-medium">No conversations yet</h3>
                <p className="text-sm text-muted-foreground mt-1">Conversations will appear here once agents start interacting</p>
              </div>
            ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Contact</TableHead>
                  <TableHead>Agent</TableHead>
                  <TableHead>Channel</TableHead>
                  <TableHead>State Reached</TableHead>
                  <TableHead className="text-right">Time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentConversations.map((conv) => (
                  <TableRow key={conv.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Avatar size="sm">
                          <AvatarFallback>{getInitials(conv.contact)}</AvatarFallback>
                        </Avatar>
                        <span className="font-medium">{conv.contact}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {conv.agent}
                    </TableCell>
                    <TableCell>
                      <ChannelBadge channel={conv.channel} />
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{conv.stateReached}</Badge>
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {conv.timeAgo}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            )}
          </CardContent>
        </Card>

        {/* Top Agents */}
        <Card className="lg:col-span-2 border-border/60 ring-1 ring-white/[0.04]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="size-4" />
              Top Agents
            </CardTitle>
            <CardDescription>Ranked by conversation volume</CardDescription>
          </CardHeader>
          <CardContent>
            {topAgents.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <Bot className="h-12 w-12 text-muted-foreground/50 mb-4" />
                <h3 className="text-lg font-medium">No agents yet</h3>
                <p className="text-sm text-muted-foreground mt-1">Create your first agent to see performance rankings</p>
              </div>
            ) : (
            <div className="space-y-5">
              {topAgents.map((agent, index) => (
                <div key={agent.name} className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                        {index + 1}
                      </span>
                      <div>
                        <p className="text-sm font-medium leading-tight">
                          {agent.name}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {agent.conversations.toLocaleString()} conversations
                        </p>
                      </div>
                    </div>
                    <span className="text-sm font-semibold tabular-nums">
                      {agent.completionRate}%
                    </span>
                  </div>
                  {/* Completion bar */}
                  <div className="relative h-2 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary transition-all"
                      style={{ width: `${agent.completionRate}%` }}
                    />
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {agent.channels.map((ch) => (
                      <ChannelBadge key={ch} channel={ch} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
