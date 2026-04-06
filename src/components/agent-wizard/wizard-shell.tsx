"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  UserIcon,
  DatabaseIcon,
  ZapIcon,
  GitBranchIcon,
  RadioIcon,
  ShieldIcon,
  CheckIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
  SaveIcon,
  Loader2Icon,
} from "lucide-react";
import { StepIdentity } from "./step-identity";
import { StepKnowledgeBase } from "./step-knowledge-base";
import { StepActions } from "./step-actions";
import { StepStateDiagram } from "./step-state-diagram";
import { StepChannels } from "./step-channels";
import { StepGuardrails } from "./step-guardrails";
import {
  agentApi,
  kbApi,
  actionApi,
  stateApi,
  channelApi,
  guardrailApi,
} from "@/lib/api";

const STEPS = [
  { id: 1, title: "Identity & Prompt", icon: UserIcon },
  { id: 2, title: "Knowledge Base", icon: DatabaseIcon },
  { id: 3, title: "Actions", icon: ZapIcon },
  { id: 4, title: "State Diagram", icon: GitBranchIcon },
  { id: 5, title: "Channels", icon: RadioIcon },
  { id: 6, title: "Guardrails", icon: ShieldIcon },
] as const;

interface WizardFormData {
  identity: {
    agentName: string;
    personaName: string;
    customer: string;
    systemPrompt: string;
    languages: string[];
    tone: string;
  };
  knowledgeBase: {
    documents: {
      id: string;
      name: string;
      type: "PDF" | "DOCX" | "CSV";
      category: string;
      status: "processing" | "ready";
      size: string;
    }[];
    structuredSources: {
      id: string;
      name: string;
      type: "API" | "Database" | "Static JSON";
      description: string;
      status: "connected" | "disconnected" | "pending";
    }[];
  };
  actions: {
    actions: {
      id: string;
      name: string;
      description: string;
      type: "db_update" | "link_generation" | "doc_fetch" | "api_call" | "notification";
      parameters: {
        name: string;
        type: string;
        required: boolean;
        description: string;
      }[];
      requireConfirmation: boolean;
    }[];
  };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  stateDiagram: {
    nodes: any[];
    edges: any[];
  };
  channels: {
    voice: {
      enabled: boolean;
      config: {
        phoneNumber: string;
        greetingMessage: string;
        ttsVoice: string;
        workingHoursStart: string;
        workingHoursEnd: string;
        transferNumber: string;
        callTimeout: string;
        consentMessage: boolean;
      };
    };
    whatsapp: {
      enabled: boolean;
      config: {
        provider: string;
        phoneNumber: string;
        welcomeMessage: string;
        sessionTimeout: string;
        mediaImages: boolean;
        mediaDocuments: boolean;
        mediaVoiceNotes: boolean;
        languageDetection: boolean;
        gupshupApiKey: string;
        gupshupAppName: string;
        metaPhoneNumberId: string;
        metaBusinessAccountId: string;
        metaAccessToken: string;
        metaAppSecret: string;
        metaVerifyToken: string;
      };
    };
    chatbot: {
      enabled: boolean;
      config: {
        welcomeMessage: string;
        sessionTimeout: string;
        rateLimit: string;
        ipAllowlist: string;
        corsOrigins: string;
      };
    };
  };
  guardrails: {
    guardrails: {
      id: string;
      name: string;
      rule: string;
      category: "compliance" | "pii" | "topic_boundary" | "safety" | "anti_misselling" | "custom";
      severity: "block" | "warn" | "log";
      enabled: boolean;
    }[];
  };
}

const INITIAL_FORM_DATA: WizardFormData = {
  identity: {
    agentName: "",
    personaName: "",
    customer: "",
    systemPrompt: "",
    languages: [],
    tone: "",
  },
  knowledgeBase: {
    documents: [],
    structuredSources: [],
  },
  actions: {
    actions: [],
  },
  stateDiagram: {
    nodes: [],
    edges: [],
  },
  channels: {
    voice: {
      enabled: false,
      config: {
        phoneNumber: "",
        greetingMessage: "",
        ttsVoice: "female_hindi",
        workingHoursStart: "09:00",
        workingHoursEnd: "18:00",
        transferNumber: "",
        callTimeout: "300",
        consentMessage: true,
      },
    },
    whatsapp: {
      enabled: false,
      config: {
        provider: "gupshup",
        phoneNumber: "",
        welcomeMessage: "",
        sessionTimeout: "30",
        mediaImages: true,
        mediaDocuments: true,
        mediaVoiceNotes: false,
        languageDetection: true,
        gupshupApiKey: "",
        gupshupAppName: "",
        metaPhoneNumberId: "",
        metaBusinessAccountId: "",
        metaAccessToken: "",
        metaAppSecret: "",
        metaVerifyToken: "",
      },
    },
    chatbot: {
      enabled: false,
      config: {
        welcomeMessage: "",
        sessionTimeout: "15",
        rateLimit: "30",
        ipAllowlist: "",
        corsOrigins: "",
      },
    },
  },
  guardrails: {
    guardrails: [],
  },
};

function isStepComplete(step: number, formData: WizardFormData): boolean {
  switch (step) {
    case 1:
      return (
        formData.identity.agentName.trim().length > 0 &&
        formData.identity.personaName.trim().length > 0 &&
        formData.identity.customer.length > 0
      );
    case 2:
      return (
        formData.knowledgeBase.documents.length > 0 ||
        formData.knowledgeBase.structuredSources.length > 0
      );
    case 3:
      return formData.actions.actions.length > 0;
    case 4:
      return true;
    case 5:
      return (
        formData.channels.voice.enabled ||
        formData.channels.whatsapp.enabled ||
        formData.channels.chatbot.enabled
      );
    case 6:
      return formData.guardrails.guardrails.filter((g) => g.enabled).length > 0;
    default:
      return false;
  }
}

export function WizardShell({ agentId: initialAgentId }: { agentId?: string } = {}) {
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState<WizardFormData>(INITIAL_FORM_DATA);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAgentId, setSavedAgentId] = useState<string | null>(initialAgentId ?? null);
  const [loadingAgent, setLoadingAgent] = useState(!!initialAgentId);
  const router = useRouter();

  // Load existing agent data when editing
  useEffect(() => {
    if (!initialAgentId) return;

    async function loadAgent() {
      try {
        const [agent, channelsRes] = await Promise.all([
          agentApi.get(initialAgentId!),
          channelApi.list(initialAgentId!).catch(() => ({ items: [] })),
        ]);

        const channels = channelsRes?.items ?? [];

        // Build channels form state from saved channel data
        const channelsState = { ...INITIAL_FORM_DATA.channels };
        for (const ch of channels) {
          const type = ch.channel_type as "voice" | "whatsapp" | "chatbot";
          if (channelsState[type]) {
            channelsState[type] = {
              enabled: true,
              config: { ...channelsState[type].config, ...(ch.config || {}) },
            };
          }
        }

        setFormData((prev) => ({
          ...prev,
          identity: {
            agentName: agent.name || "",
            personaName: agent.persona || "",
            customer: "",
            systemPrompt: agent.system_prompt || "",
            languages: agent.languages || [],
            tone: "",
          },
          channels: channelsState,
        }));
      } catch (err) {
        console.error("Failed to load agent for editing:", err);
      } finally {
        setLoadingAgent(false);
      }
    }

    loadAgent();
  }, [initialAgentId]);

  function goToStep(step: number) {
    if (step >= 1 && step <= 6) {
      setCurrentStep(step);
    }
  }

  async function handleSave(isDraft = true) {
    setSaving(true);
    setSaveError(null);

    try {
      // Build channels list from enabled channels
      const enabledChannels: ("voice" | "whatsapp" | "chatbot")[] = [];
      if (formData.channels.voice.enabled) enabledChannels.push("voice");
      if (formData.channels.whatsapp.enabled) enabledChannels.push("whatsapp");
      if (formData.channels.chatbot.enabled) enabledChannels.push("chatbot");

      // Create or update the agent
      let agentId = savedAgentId;
      const agentPayload = {
        name: formData.identity.agentName,
        persona: formData.identity.personaName,
        customer: formData.identity.customer,
        system_prompt: formData.identity.systemPrompt,
        languages: formData.identity.languages,
        tone: formData.identity.tone,
        channels: enabledChannels,
      };

      if (agentId) {
        await agentApi.update(agentId, agentPayload);
      } else {
        const created = await agentApi.create(agentPayload);
        agentId = created.id;
        setSavedAgentId(agentId);
      }

      // Save remaining configuration in parallel (best-effort)
      const savePromises: Promise<any>[] = [];

      // Save actions
      if (formData.actions.actions.length > 0) {
        for (const action of formData.actions.actions) {
          savePromises.push(
            actionApi.create(agentId, {
              name: action.name,
              description: action.description,
              type: action.type,
              parameters: action.parameters,
              requireConfirmation: action.requireConfirmation,
            })
          );
        }
      }

      // Save state diagram
      if (formData.stateDiagram.nodes.length > 0) {
        savePromises.push(
          stateApi.save(agentId, formData.stateDiagram)
        );
      }

      // Save channel configurations
      for (const [channelType, channelData] of Object.entries(formData.channels)) {
        if (channelData.enabled) {
          savePromises.push(
            channelApi.update(agentId, channelType, channelData.config)
          );
        }
      }

      // Save guardrails
      if (formData.guardrails.guardrails.length > 0) {
        savePromises.push(
          guardrailApi.bulkUpdate(agentId, formData.guardrails.guardrails)
        );
      }

      // Wait for all saves
      const results = await Promise.allSettled(savePromises);
      const failures = results.filter((r) => r.status === "rejected");
      if (failures.length > 0) {
        console.warn(`${failures.length} sub-resource save(s) failed:`, failures);
      }

      // Redirect to the agent detail page
      router.push(`/agents/${agentId}`);
    } catch (err: any) {
      console.error("Failed to save agent:", err);
      setSaveError(err.message || "Failed to save agent");
    } finally {
      setSaving(false);
    }
  }

  function renderStep() {
    switch (currentStep) {
      case 1:
        return (
          <StepIdentity
            data={formData.identity}
            onChange={(identity) => setFormData({ ...formData, identity })}
          />
        );
      case 2:
        return (
          <StepKnowledgeBase
            data={formData.knowledgeBase}
            onChange={(knowledgeBase) =>
              setFormData({ ...formData, knowledgeBase })
            }
          />
        );
      case 3:
        return (
          <StepActions
            data={formData.actions}
            onChange={(actions) => setFormData({ ...formData, actions })}
          />
        );
      case 4:
        return (
          <StepStateDiagram
            data={formData.stateDiagram}
            onChange={(stateDiagram) =>
              setFormData({ ...formData, stateDiagram })
            }
          />
        );
      case 5:
        return (
          <StepChannels
            data={formData.channels}
            onChange={(channels) => setFormData({ ...formData, channels })}
          />
        );
      case 6:
        return (
          <StepGuardrails
            data={formData.guardrails}
            onChange={(guardrails) => setFormData({ ...formData, guardrails })}
          />
        );
      default:
        return null;
    }
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b px-6 py-3">
        <div>
          <h1 className="text-lg font-semibold">{initialAgentId ? "Edit Agent" : "Create New Agent"}</h1>
          <p className="text-xs text-muted-foreground">
            Step {currentStep} of 6 — {STEPS[currentStep - 1].title}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {saveError && (
            <span className="text-xs text-red-600 dark:text-red-400 mr-2">
              {saveError}
            </span>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleSave(true)}
            disabled={saving}
          >
            {saving ? (
              <Loader2Icon className="size-3.5 animate-spin" />
            ) : (
              <SaveIcon className="size-3.5" />
            )}
            {saving ? "Saving..." : "Save Draft"}
          </Button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Desktop Sidebar Stepper */}
        <aside className="hidden w-[260px] shrink-0 border-r bg-muted/20 p-4 lg:block">
          <nav className="space-y-1">
            {STEPS.map((step) => {
              const Icon = step.icon;
              const isActive = currentStep === step.id;
              const isComplete = isStepComplete(step.id, formData);
              const isPast = step.id < currentStep;

              return (
                <button
                  key={step.id}
                  onClick={() => goToStep(step.id)}
                  className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                    isActive
                      ? "bg-primary/10 text-primary"
                      : isPast || isComplete
                      ? "text-foreground hover:bg-muted"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
                >
                  <div
                    className={`flex size-8 shrink-0 items-center justify-center rounded-lg text-xs font-semibold transition-colors ${
                      isActive
                        ? "bg-primary text-primary-foreground"
                        : isComplete
                        ? "bg-primary/80 text-primary-foreground"
                        : "bg-muted text-muted-foreground group-hover:bg-muted-foreground/10"
                    }`}
                  >
                    {isComplete && !isActive ? (
                      <CheckIcon className="size-4" />
                    ) : (
                      <Icon className="size-4" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div
                      className={`text-sm font-medium ${
                        isActive ? "text-primary" : ""
                      }`}
                    >
                      {step.title}
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      Step {step.id}
                    </div>
                  </div>
                  {isComplete && !isActive && (
                    <CheckIcon className="size-3.5 shrink-0 text-primary" />
                  )}
                </button>
              );
            })}
          </nav>

          <div className="mt-6 rounded-lg border bg-card p-3">
            <div className="mb-2 text-xs font-medium">Progress</div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all duration-300"
                style={{
                  width: `${
                    (STEPS.filter((s) => isStepComplete(s.id, formData))
                      .length /
                      6) *
                    100
                  }%`,
                }}
              />
            </div>
            <div className="mt-1.5 text-[11px] text-muted-foreground">
              {STEPS.filter((s) => isStepComplete(s.id, formData)).length} of 6
              steps complete
            </div>
          </div>
        </aside>

        {/* Content Area */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Mobile Horizontal Stepper */}
          <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-b px-4 py-2 lg:hidden">
            {STEPS.map((step) => {
              const Icon = step.icon;
              const isActive = currentStep === step.id;
              const isComplete = isStepComplete(step.id, formData);

              return (
                <button
                  key={step.id}
                  onClick={() => goToStep(step.id)}
                  className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : isComplete
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-muted"
                  }`}
                >
                  {isComplete && !isActive ? (
                    <CheckIcon className="size-3" />
                  ) : (
                    <Icon className="size-3" />
                  )}
                  <span className="hidden sm:inline">{step.title}</span>
                  <span className="sm:hidden">{step.id}</span>
                </button>
              );
            })}
          </div>
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-4xl p-6">{renderStep()}</div>
          </div>

          {/* Bottom Bar */}
          <div className="flex shrink-0 items-center justify-between border-t bg-muted/20 px-6 py-3">
            <Button
              variant="outline"
              size="sm"
              disabled={currentStep === 1}
              onClick={() => goToStep(currentStep - 1)}
            >
              <ArrowLeftIcon className="size-3.5" />
              Back
            </Button>

            <div className="flex items-center gap-1.5">
              {STEPS.map((step) => (
                <button
                  key={step.id}
                  onClick={() => goToStep(step.id)}
                  className={`size-2 rounded-full transition-colors ${
                    currentStep === step.id
                      ? "bg-primary"
                      : isStepComplete(step.id, formData)
                      ? "bg-primary/80"
                      : "bg-muted-foreground/30"
                  }`}
                  aria-label={`Go to step ${step.id}`}
                />
              ))}
            </div>

            <div className="flex items-center gap-2">
              {currentStep === 6 ? (
                <Button
                  size="sm"
                  onClick={() => handleSave(false)}
                  disabled={saving}
                >
                  {saving ? (
                    <Loader2Icon className="size-3.5 animate-spin" />
                  ) : (
                    <SaveIcon className="size-3.5" />
                  )}
                  {saving ? "Saving..." : "Save Agent"}
                </Button>
              ) : (
                <Button
                  size="sm"
                  onClick={() => goToStep(currentStep + 1)}
                >
                  Next
                  <ArrowRightIcon className="size-3.5" />
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
