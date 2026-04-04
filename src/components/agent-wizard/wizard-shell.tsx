"use client";

import { useState } from "react";
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
} from "lucide-react";
import { StepIdentity } from "./step-identity";
import { StepKnowledgeBase } from "./step-knowledge-base";
import { StepActions } from "./step-actions";
import { StepStateDiagram } from "./step-state-diagram";
import { StepChannels } from "./step-channels";
import { StepGuardrails } from "./step-guardrails";

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
    languages: ["English", "Hindi"],
    tone: "conversational",
  },
  knowledgeBase: {
    documents: [
      {
        id: "doc-1",
        name: "HDFC_Ergo_Health_Brochure_2026.pdf",
        type: "PDF",
        category: "Product Brochure",
        status: "ready",
        size: "4.2 MB",
      },
      {
        id: "doc-2",
        name: "Health_Insurance_FAQ.docx",
        type: "DOCX",
        category: "FAQ",
        status: "processing",
        size: "1.8 MB",
      },
    ],
    structuredSources: [
      {
        id: "src-1",
        name: "Premium Calculator API",
        type: "API",
        description:
          "REST API endpoint that returns premium quotes based on age, sum insured, and plan type. Connected to the customer's product catalog.",
        status: "connected",
      },
    ],
  },
  actions: {
    actions: [
      {
        id: "action-1",
        name: "Generate Payment Link",
        description:
          "Generate a Razorpay payment link for the selected insurance plan and send it to the customer via WhatsApp or SMS.",
        type: "link_generation",
        parameters: [
          {
            name: "plan_id",
            type: "string",
            required: true,
            description: "Selected insurance plan identifier",
          },
          {
            name: "premium_amount",
            type: "number",
            required: true,
            description: "Premium amount in INR",
          },
          {
            name: "customer_name",
            type: "string",
            required: true,
            description: "Customer full name",
          },
          {
            name: "customer_phone",
            type: "string",
            required: true,
            description: "Customer mobile number",
          },
        ],
        requireConfirmation: true,
      },
      {
        id: "action-2",
        name: "Update Lead Status",
        description:
          "Update the lead status in the CRM system to track the customer's progress through the sales funnel.",
        type: "db_update",
        parameters: [
          {
            name: "lead_id",
            type: "string",
            required: true,
            description: "CRM lead identifier",
          },
          {
            name: "status",
            type: "enum",
            required: true,
            description: "New status: interested, quoted, converted, lost",
          },
          {
            name: "notes",
            type: "string",
            required: false,
            description: "Agent notes about the interaction",
          },
        ],
        requireConfirmation: false,
      },
      {
        id: "action-3",
        name: "Send Policy Document",
        description:
          "Fetch the policy brochure or terms document from the document store and send it to the customer.",
        type: "doc_fetch",
        parameters: [
          {
            name: "document_type",
            type: "enum",
            required: true,
            description: "Type: brochure, terms, claim_form, proposal",
          },
          {
            name: "plan_id",
            type: "string",
            required: true,
            description: "Insurance plan identifier",
          },
        ],
        requireConfirmation: true,
      },
    ],
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
    guardrails: [
      {
        id: "guard-1",
        name: "IRDAI Compliance",
        rule: "Always mention cooling-off period and free-look period when discussing policy purchase",
        category: "compliance",
        severity: "block",
        enabled: true,
      },
      {
        id: "guard-2",
        name: "PII Protection",
        rule: "Never repeat full Aadhaar or PAN number back to the customer",
        category: "pii",
        severity: "block",
        enabled: true,
      },
      {
        id: "guard-3",
        name: "Topic Boundary",
        rule: "Only discuss insurance products available in the knowledge base",
        category: "topic_boundary",
        severity: "warn",
        enabled: true,
      },
      {
        id: "guard-4",
        name: "Anti-Misselling",
        rule: "Never guarantee returns on ULIP or investment-linked products",
        category: "safety",
        severity: "block",
        enabled: true,
      },
      {
        id: "guard-5",
        name: "Escalation Trigger",
        rule: "Escalate to human agent when customer explicitly requests or shows frustration",
        category: "safety",
        severity: "warn",
        enabled: true,
      },
      {
        id: "guard-6",
        name: "Consent Required",
        rule: "Collect explicit consent before storing personal information",
        category: "compliance",
        severity: "block",
        enabled: true,
      },
    ],
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

export function WizardShell() {
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState<WizardFormData>(INITIAL_FORM_DATA);

  function goToStep(step: number) {
    if (step >= 1 && step <= 6) {
      setCurrentStep(step);
    }
  }

  function handleSave() {
    // In production this would POST to the API
    console.log("Saving agent configuration:", formData);
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
          <h1 className="text-lg font-semibold">Create New Agent</h1>
          <p className="text-xs text-muted-foreground">
            Step {currentStep} of 6 — {STEPS[currentStep - 1].title}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleSave}>
            <SaveIcon className="size-3.5" />
            Save Draft
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
                        ? "bg-emerald-600 text-white dark:bg-emerald-700"
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
                    <CheckIcon className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
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
                      ? "bg-emerald-600/10 text-emerald-600 dark:text-emerald-400"
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
          <ScrollArea className="flex-1">
            <div className="mx-auto max-w-4xl p-6">{renderStep()}</div>
          </ScrollArea>

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
                      ? "bg-emerald-600 dark:bg-emerald-500"
                      : "bg-muted-foreground/30"
                  }`}
                  aria-label={`Go to step ${step.id}`}
                />
              ))}
            </div>

            <div className="flex items-center gap-2">
              {currentStep === 6 ? (
                <Button size="sm" onClick={handleSave}>
                  <SaveIcon className="size-3.5" />
                  Save Agent
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
