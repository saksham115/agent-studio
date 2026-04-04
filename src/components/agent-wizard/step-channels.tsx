"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  PhoneIcon,
  MessageCircleIcon,
  GlobeIcon,
  ChevronDownIcon,
  ChevronUpIcon,
} from "lucide-react";

interface VoiceConfig {
  phoneNumber: string;
  greetingMessage: string;
  ttsVoice: string;
  workingHoursStart: string;
  workingHoursEnd: string;
  transferNumber: string;
  callTimeout: string;
  consentMessage: boolean;
}

interface WhatsAppConfig {
  provider: string;
  phoneNumber: string;
  welcomeMessage: string;
  sessionTimeout: string;
  mediaImages: boolean;
  mediaDocuments: boolean;
  mediaVoiceNotes: boolean;
  languageDetection: boolean;
}

interface ChatbotConfig {
  welcomeMessage: string;
  sessionTimeout: string;
  rateLimit: string;
  ipAllowlist: string;
  corsOrigins: string;
}

interface StepChannelsData {
  voice: { enabled: boolean; config: VoiceConfig };
  whatsapp: { enabled: boolean; config: WhatsAppConfig };
  chatbot: { enabled: boolean; config: ChatbotConfig };
}

interface StepChannelsProps {
  data: StepChannelsData;
  onChange: (data: StepChannelsData) => void;
}

export function StepChannels({ data, onChange }: StepChannelsProps) {
  function toggleChannel(channel: "voice" | "whatsapp" | "chatbot") {
    onChange({
      ...data,
      [channel]: {
        ...data[channel],
        enabled: !data[channel].enabled,
      },
    });
  }

  function updateVoiceConfig(updates: Partial<VoiceConfig>) {
    onChange({
      ...data,
      voice: {
        ...data.voice,
        config: { ...data.voice.config, ...updates },
      },
    });
  }

  function updateWhatsAppConfig(updates: Partial<WhatsAppConfig>) {
    onChange({
      ...data,
      whatsapp: {
        ...data.whatsapp,
        config: { ...data.whatsapp.config, ...updates },
      },
    });
  }

  function updateChatbotConfig(updates: Partial<ChatbotConfig>) {
    onChange({
      ...data,
      chatbot: {
        ...data.chatbot,
        config: { ...data.chatbot.config, ...updates },
      },
    });
  }

  const enabledCount = [data.voice.enabled, data.whatsapp.enabled, data.chatbot.enabled].filter(Boolean).length;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold">Channels</h2>
          <p className="text-sm text-muted-foreground">
            Configure how customers can interact with your agent. Enable one or
            more channels.
          </p>
        </div>
        <Badge variant="secondary">
          {enabledCount} of 3 enabled
        </Badge>
      </div>

      <div className="space-y-4">
        {/* Voice Channel */}
        <Card className={data.voice.enabled ? "ring-1 ring-primary/30" : ""}>
          <CardHeader className="border-b cursor-pointer" onClick={() => toggleChannel("voice")}>
            <div className="flex items-center gap-3">
              <div
                className={`flex size-10 items-center justify-center rounded-lg ${
                  data.voice.enabled
                    ? "bg-primary/10 text-primary"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                <PhoneIcon className="size-5" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <CardTitle>Voice</CardTitle>
                  {data.voice.enabled && (
                    <Badge variant="secondary" className="text-[10px]">
                      Active
                    </Badge>
                  )}
                </div>
                <CardDescription>
                  Inbound and outbound phone calls with TTS and STT
                </CardDescription>
              </div>
              <div className="flex items-center gap-3">
                <Switch
                  checked={data.voice.enabled}
                  onCheckedChange={() => toggleChannel("voice")}
                  onClick={(e) => e.stopPropagation()}
                />
                {data.voice.enabled ? (
                  <ChevronUpIcon className="size-4 text-muted-foreground" />
                ) : (
                  <ChevronDownIcon className="size-4 text-muted-foreground" />
                )}
              </div>
            </div>
          </CardHeader>

          {data.voice.enabled && (
            <CardContent className="pt-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="voice-phone">Phone Number</Label>
                  <Input
                    id="voice-phone"
                    placeholder="+91 98765 43210"
                    value={data.voice.config.phoneNumber}
                    onChange={(e) =>
                      updateVoiceConfig({ phoneNumber: e.target.value })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    The number customers will call or receive calls from.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="voice-tts">TTS Voice</Label>
                  <Select
                    value={data.voice.config.ttsVoice}
                    onValueChange={(val) =>
                      updateVoiceConfig({ ttsVoice: val ?? "" })
                    }
                  >
                    <SelectTrigger id="voice-tts" className="w-full">
                      <SelectValue placeholder="Select a voice" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="male_hindi">Male Hindi</SelectItem>
                      <SelectItem value="female_hindi">Female Hindi</SelectItem>
                      <SelectItem value="male_english">Male English</SelectItem>
                      <SelectItem value="female_english">Female English</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    Text-to-speech voice for the agent.
                  </p>
                </div>

                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="voice-greeting">Greeting Message</Label>
                  <Textarea
                    id="voice-greeting"
                    placeholder="Namaste! Thank you for calling. I am your insurance advisor. How can I help you today?"
                    value={data.voice.config.greetingMessage}
                    onChange={(e) =>
                      updateVoiceConfig({ greetingMessage: e.target.value })
                    }
                    className="min-h-[80px]"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="voice-hours-start">Working Hours Start</Label>
                  <Input
                    id="voice-hours-start"
                    type="time"
                    value={data.voice.config.workingHoursStart}
                    onChange={(e) =>
                      updateVoiceConfig({ workingHoursStart: e.target.value })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="voice-hours-end">Working Hours End</Label>
                  <Input
                    id="voice-hours-end"
                    type="time"
                    value={data.voice.config.workingHoursEnd}
                    onChange={(e) =>
                      updateVoiceConfig({ workingHoursEnd: e.target.value })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="voice-transfer">Transfer Number</Label>
                  <Input
                    id="voice-transfer"
                    placeholder="+91 98765 43211"
                    value={data.voice.config.transferNumber}
                    onChange={(e) =>
                      updateVoiceConfig({ transferNumber: e.target.value })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Number to transfer to when escalating to a human agent.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="voice-timeout">Call Timeout (seconds)</Label>
                  <Input
                    id="voice-timeout"
                    type="number"
                    placeholder="300"
                    value={data.voice.config.callTimeout}
                    onChange={(e) =>
                      updateVoiceConfig({ callTimeout: e.target.value })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Maximum call duration before auto-disconnect.
                  </p>
                </div>

                <div className="flex items-center justify-between rounded-lg border p-3 sm:col-span-2">
                  <div>
                    <Label>Consent Message</Label>
                    <p className="text-xs text-muted-foreground">
                      Play a recording consent message at the start of the call.
                    </p>
                  </div>
                  <Switch
                    checked={data.voice.config.consentMessage}
                    onCheckedChange={(checked) =>
                      updateVoiceConfig({ consentMessage: !!checked })
                    }
                  />
                </div>
              </div>
            </CardContent>
          )}
        </Card>

        {/* WhatsApp Channel */}
        <Card className={data.whatsapp.enabled ? "ring-1 ring-primary/30" : ""}>
          <CardHeader className="border-b cursor-pointer" onClick={() => toggleChannel("whatsapp")}>
            <div className="flex items-center gap-3">
              <div
                className={`flex size-10 items-center justify-center rounded-lg ${
                  data.whatsapp.enabled
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                <MessageCircleIcon className="size-5" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <CardTitle>WhatsApp</CardTitle>
                  {data.whatsapp.enabled && (
                    <Badge variant="secondary" className="text-[10px]">
                      Active
                    </Badge>
                  )}
                </div>
                <CardDescription>
                  WhatsApp Business API messaging with rich media support
                </CardDescription>
              </div>
              <div className="flex items-center gap-3">
                <Switch
                  checked={data.whatsapp.enabled}
                  onCheckedChange={() => toggleChannel("whatsapp")}
                  onClick={(e) => e.stopPropagation()}
                />
                {data.whatsapp.enabled ? (
                  <ChevronUpIcon className="size-4 text-muted-foreground" />
                ) : (
                  <ChevronDownIcon className="size-4 text-muted-foreground" />
                )}
              </div>
            </div>
          </CardHeader>

          {data.whatsapp.enabled && (
            <CardContent className="pt-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="wa-provider">BSP Provider</Label>
                  <Select
                    value={data.whatsapp.config.provider}
                    onValueChange={(val) =>
                      updateWhatsAppConfig({ provider: val ?? "" })
                    }
                  >
                    <SelectTrigger id="wa-provider" className="w-full">
                      <SelectValue placeholder="Select provider" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="gupshup">Gupshup</SelectItem>
                      <SelectItem value="meta_cloud">Meta Cloud API</SelectItem>
                      <SelectItem value="twilio">Twilio</SelectItem>
                      <SelectItem value="wati">Wati</SelectItem>
                      <SelectItem value="valuefirst">ValueFirst</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    WhatsApp Business Solution Provider.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="wa-phone">Phone Number</Label>
                  <Input
                    id="wa-phone"
                    placeholder="+91 98765 43210"
                    value={data.whatsapp.config.phoneNumber}
                    onChange={(e) =>
                      updateWhatsAppConfig({ phoneNumber: e.target.value })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    WhatsApp Business number registered with the BSP.
                  </p>
                </div>

                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="wa-welcome">Welcome Message</Label>
                  <Textarea
                    id="wa-welcome"
                    placeholder="Hello! I'm your insurance advisor. I can help you find the right insurance plan. How can I assist you today?"
                    value={data.whatsapp.config.welcomeMessage}
                    onChange={(e) =>
                      updateWhatsAppConfig({ welcomeMessage: e.target.value })
                    }
                    className="min-h-[80px]"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="wa-session">Session Timeout (minutes)</Label>
                  <Input
                    id="wa-session"
                    type="number"
                    placeholder="30"
                    value={data.whatsapp.config.sessionTimeout}
                    onChange={(e) =>
                      updateWhatsAppConfig({ sessionTimeout: e.target.value })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Conversation resets after this idle period.
                  </p>
                </div>

                <div className="space-y-3">
                  <Label>Media Support</Label>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between rounded-md border px-3 py-2">
                      <span className="text-sm">Images</span>
                      <Switch
                        size="sm"
                        checked={data.whatsapp.config.mediaImages}
                        onCheckedChange={(checked) =>
                          updateWhatsAppConfig({ mediaImages: !!checked })
                        }
                      />
                    </div>
                    <div className="flex items-center justify-between rounded-md border px-3 py-2">
                      <span className="text-sm">Documents</span>
                      <Switch
                        size="sm"
                        checked={data.whatsapp.config.mediaDocuments}
                        onCheckedChange={(checked) =>
                          updateWhatsAppConfig({ mediaDocuments: !!checked })
                        }
                      />
                    </div>
                    <div className="flex items-center justify-between rounded-md border px-3 py-2">
                      <span className="text-sm">Voice Notes</span>
                      <Switch
                        size="sm"
                        checked={data.whatsapp.config.mediaVoiceNotes}
                        onCheckedChange={(checked) =>
                          updateWhatsAppConfig({ mediaVoiceNotes: !!checked })
                        }
                      />
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between rounded-lg border p-3 sm:col-span-2">
                  <div>
                    <Label>Language Detection</Label>
                    <p className="text-xs text-muted-foreground">
                      Automatically detect customer&apos;s language and respond
                      accordingly.
                    </p>
                  </div>
                  <Switch
                    checked={data.whatsapp.config.languageDetection}
                    onCheckedChange={(checked) =>
                      updateWhatsAppConfig({ languageDetection: !!checked })
                    }
                  />
                </div>
              </div>
            </CardContent>
          )}
        </Card>

        {/* Chatbot Channel */}
        <Card className={data.chatbot.enabled ? "ring-1 ring-primary/30" : ""}>
          <CardHeader className="border-b cursor-pointer" onClick={() => toggleChannel("chatbot")}>
            <div className="flex items-center gap-3">
              <div
                className={`flex size-10 items-center justify-center rounded-lg ${
                  data.chatbot.enabled
                    ? "bg-violet-500/10 text-violet-600 dark:text-violet-400"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                <GlobeIcon className="size-5" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <CardTitle>Chatbot</CardTitle>
                  {data.chatbot.enabled && (
                    <Badge variant="secondary" className="text-[10px]">
                      Active
                    </Badge>
                  )}
                </div>
                <CardDescription>
                  Embeddable web chatbot via authenticated API endpoints
                </CardDescription>
              </div>
              <div className="flex items-center gap-3">
                <Switch
                  checked={data.chatbot.enabled}
                  onCheckedChange={() => toggleChannel("chatbot")}
                  onClick={(e) => e.stopPropagation()}
                />
                {data.chatbot.enabled ? (
                  <ChevronUpIcon className="size-4 text-muted-foreground" />
                ) : (
                  <ChevronDownIcon className="size-4 text-muted-foreground" />
                )}
              </div>
            </div>
          </CardHeader>

          {data.chatbot.enabled && (
            <CardContent className="pt-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="chat-welcome">Welcome Message</Label>
                  <Textarea
                    id="chat-welcome"
                    placeholder="Welcome! I'm here to help you find the perfect insurance plan. What are you looking for?"
                    value={data.chatbot.config.welcomeMessage}
                    onChange={(e) =>
                      updateChatbotConfig({ welcomeMessage: e.target.value })
                    }
                    className="min-h-[80px]"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="chat-session">Session Timeout (minutes)</Label>
                  <Input
                    id="chat-session"
                    type="number"
                    placeholder="15"
                    value={data.chatbot.config.sessionTimeout}
                    onChange={(e) =>
                      updateChatbotConfig({ sessionTimeout: e.target.value })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Session expires after this idle period.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="chat-rate">Rate Limit (req/min)</Label>
                  <Input
                    id="chat-rate"
                    type="number"
                    placeholder="30"
                    value={data.chatbot.config.rateLimit}
                    onChange={(e) =>
                      updateChatbotConfig({ rateLimit: e.target.value })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Maximum requests per minute per session.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="chat-ip">IP Allowlist</Label>
                  <Textarea
                    id="chat-ip"
                    placeholder={"192.168.1.0/24\n10.0.0.0/8\n203.0.113.50"}
                    value={data.chatbot.config.ipAllowlist}
                    onChange={(e) =>
                      updateChatbotConfig({ ipAllowlist: e.target.value })
                    }
                    className="min-h-[80px] font-mono text-xs"
                  />
                  <p className="text-xs text-muted-foreground">
                    One IP or CIDR range per line. Leave empty to allow all.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="chat-cors">CORS Origins</Label>
                  <Textarea
                    id="chat-cors"
                    placeholder={"https://www.example.com\nhttps://app.example.com"}
                    value={data.chatbot.config.corsOrigins}
                    onChange={(e) =>
                      updateChatbotConfig({ corsOrigins: e.target.value })
                    }
                    className="min-h-[80px] font-mono text-xs"
                  />
                  <p className="text-xs text-muted-foreground">
                    Allowed origins for cross-origin requests. One URL per line.
                  </p>
                </div>
              </div>
            </CardContent>
          )}
        </Card>
      </div>
    </div>
  );
}
