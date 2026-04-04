"use client"

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

// ---------------------------------------------------------------------------
// Data — TODO: fetch from API
// ---------------------------------------------------------------------------

const kpiCards = [
  {
    title: "Total Agents",
    value: "0",
    subtitle: "0 active, 0 draft",
    icon: Bot,
    trend: null as null | { value: string; direction: "up" | "down" },
  },
  {
    title: "Total Conversations",
    value: "0",
    subtitle: "Today",
    icon: MessageCircle,
    trend: null as null | { value: string; direction: "up" | "down" },
  },
  {
    title: "Completion Rate",
    value: "--",
    subtitle: "vs last week",
    icon: Activity,
    trend: null as null | { value: string; direction: "up" | "down" },
  },
  {
    title: "Avg Response Time",
    value: "--",
    subtitle: "vs last week",
    icon: Clock,
    trend: null as null | { value: string; direction: "up" | "down" },
  },
]

// TODO: fetch from API
const conversationData: { date: string; voice: number; whatsapp: number; chatbot: number }[] = []

// TODO: fetch from API
const funnelData: { stage: string; count: number; percent: number; fill: string }[] = []

type Channel = "Voice" | "WhatsApp" | "Chatbot"

interface RecentConversation {
  id: string
  contact: string
  agent: string
  channel: Channel
  stateReached: string
  timeAgo: string
}

// TODO: fetch from API
const recentConversations: RecentConversation[] = []

// TODO: fetch from API
const topAgents: {
  name: string
  conversations: number
  completionRate: number
  channels: Channel[]
}[] = []

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const channelConfig: Record<Channel, { color: string; icon: React.ElementType }> = {
  Voice: { color: "bg-blue-500/15 text-blue-700 dark:text-blue-400", icon: Phone },
  WhatsApp: { color: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400", icon: MessageCircle },
  Chatbot: { color: "bg-purple-500/15 text-purple-700 dark:text-purple-400", icon: Globe },
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
    <div className="rounded-lg border bg-card px-3 py-2 text-sm shadow-md">
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
  payload?: Array<{ payload: (typeof funnelData)[number] }>
}) {
  if (!active || !payload?.length) return null
  const data = payload[0].payload
  return (
    <div className="rounded-lg border bg-card px-3 py-2 text-sm shadow-md">
      <p className="font-medium text-card-foreground">{data.stage}</p>
      <p className="text-muted-foreground">
        {data.count.toLocaleString()} conversations ({data.percent}%)
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  return (
    <div className="p-6 space-y-6">
      {/* ---------------------------------------------------------------- */}
      {/* Page Header                                                      */}
      {/* ---------------------------------------------------------------- */}
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Organisation-wide overview for today, 4 Apr 2026
          </p>
        </div>
        <Badge variant="secondary" className="w-fit text-xs">
          Last 7 days
        </Badge>
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* KPI Cards                                                        */}
      {/* ---------------------------------------------------------------- */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {kpiCards.map((kpi) => {
          const Icon = kpi.icon
          return (
            <Card key={kpi.title}>
              <CardHeader className="flex flex-row items-center justify-between pb-0">
                <CardDescription className="text-sm font-medium">
                  {kpi.title}
                </CardDescription>
                <Icon className="size-4 text-muted-foreground" />
              </CardHeader>
              <CardContent className="pt-0">
                <div className="text-2xl font-bold">{kpi.value}</div>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  {kpi.trend && (
                    <span
                      className={`inline-flex items-center gap-0.5 font-medium ${
                        kpi.trend.direction === "up"
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-red-600 dark:text-red-400"
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
        <Card className="lg:col-span-4">
          <CardHeader>
            <CardTitle>Conversations Over Time</CardTitle>
            <CardDescription>
              Daily breakdown by channel (last 7 days)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={conversationData}
                  margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="gradVoice" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="oklch(0.55 0.2 260)" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="oklch(0.55 0.2 260)" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="gradWhatsApp" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="oklch(0.55 0.17 155)" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="oklch(0.55 0.17 155)" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="gradChatbot" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="oklch(0.65 0.15 300)" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="oklch(0.65 0.15 300)" stopOpacity={0.02} />
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
                    stroke="oklch(0.55 0.2 260)"
                    fill="url(#gradVoice)"
                    strokeWidth={2}
                  />
                  <Area
                    type="monotone"
                    dataKey="whatsapp"
                    name="WhatsApp"
                    stackId="1"
                    stroke="oklch(0.55 0.17 155)"
                    fill="url(#gradWhatsApp)"
                    strokeWidth={2}
                  />
                  <Area
                    type="monotone"
                    dataKey="chatbot"
                    name="Chatbot"
                    stackId="1"
                    stroke="oklch(0.65 0.15 300)"
                    fill="url(#gradChatbot)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Funnel chart */}
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Conversation Funnel</CardTitle>
            <CardDescription>
              Stage progression and drop-off rates
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
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
        <Card className="lg:col-span-3">
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
        <Card className="lg:col-span-2">
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
