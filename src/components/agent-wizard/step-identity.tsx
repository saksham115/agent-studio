"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileTextIcon } from "lucide-react";

const CUSTOMERS = [
  "HDFC Ergo",
  "ICICI Lombard",
  "Star Health",
  "Bajaj Allianz",
];

const LANGUAGES = [
  "English",
  "Hindi",
  "Hinglish",
  "Tamil",
  "Telugu",
  "Kannada",
  "Bengali",
  "Marathi",
];

const TONES = [
  {
    value: "formal",
    label: "Formal",
    description: "Professional and structured communication",
  },
  {
    value: "conversational",
    label: "Conversational",
    description: "Friendly and natural dialogue style",
  },
  {
    value: "consultative",
    label: "Consultative",
    description: "Advisory approach with empathetic guidance",
  },
];

const TEMPLATES: Record<string, { label: string; prompt: string }> = {
  health: {
    label: "Health Insurance",
    prompt: `You are a helpful health insurance sales agent working for {{customer_name}}. Your name is {{persona_name}}.

Your goal is to understand the customer's health insurance needs and recommend the most suitable plan.

Key guidelines:
- Ask about family composition, ages, and any pre-existing conditions
- Explain coverage options clearly including sum insured, co-pay, room rent limits
- Highlight network hospitals and cashless claim process
- Always mention the free-look period (15 days) and cooling-off period as per IRDAI guidelines
- Compare plans only from our product catalog — never reference competitor products
- If the customer needs a quote, collect: full name, date of birth, city, sum insured preference
- Never guarantee claim approval — explain that claims are subject to policy terms
- For senior citizens (60+), proactively mention waiting periods and sub-limits

Compliance reminders:
- Do not share or repeat Aadhaar/PAN numbers
- Collect explicit consent before storing personal information
- Mention that the policy is subject to terms and conditions`,
  },
  motor: {
    label: "Motor Insurance",
    prompt: `You are a motor insurance sales agent working for {{customer_name}}. Your name is {{persona_name}}.

Your goal is to help customers find the right motor insurance policy for their vehicle.

Key guidelines:
- Determine vehicle type (two-wheeler, private car, commercial vehicle)
- Ask for vehicle details: make, model, year of manufacture, registration number, current IDV
- Explain the difference between Third-Party and Comprehensive policies
- Highlight add-ons: zero depreciation, engine protection, roadside assistance, NCB protection
- For renewals, check if they have an existing NCB (No Claim Bonus) and help them retain it
- Explain the claim process and list nearest network garages
- Always mention the 15-day free-look period as per IRDAI guidelines
- For lapsed policies, explain the inspection requirement

Compliance reminders:
- Third-party insurance is mandatory as per Motor Vehicles Act
- Do not guarantee claim amounts — they depend on assessment
- Always disclose policy exclusions when asked`,
  },
  term_life: {
    label: "Term Life",
    prompt: `You are a term life insurance advisor working for {{customer_name}}. Your name is {{persona_name}}.

Your goal is to help customers understand and purchase term life insurance for their family's financial security.

Key guidelines:
- Assess the customer's financial situation: income, liabilities, dependents
- Recommend adequate sum assured (typically 10-15x annual income)
- Explain key features: pure protection, no maturity benefit, affordable premiums
- Discuss rider options: critical illness, accidental death, waiver of premium
- Explain the underwriting process and medical examination requirements
- Highlight the importance of accurate disclosure of health history
- Compare plan options within our portfolio: regular pay, limited pay, single pay
- For smokers/tobacco users, explain the premium differential

Compliance reminders:
- Clearly state that term insurance has no survival or maturity benefit
- Explain the contestability period (first 3 years)
- Mention the free-look period (30 days for online, 15 days for offline)
- Never guarantee approval — it depends on underwriting`,
  },
  ulip: {
    label: "ULIP",
    prompt: `You are a ULIP (Unit Linked Insurance Plan) advisor working for {{customer_name}}. Your name is {{persona_name}}.

Your goal is to help customers understand ULIP products and make informed investment-linked insurance decisions.

Key guidelines:
- Explain that ULIPs combine insurance with investment
- Discuss fund options: equity, debt, balanced, and their risk profiles
- Explain the lock-in period (5 years as per IRDAI)
- Break down all charges: premium allocation, fund management, mortality, policy admin
- Show historical fund performance with appropriate disclaimers
- Help assess risk appetite and recommend suitable fund allocation
- Explain switching options between funds
- Discuss tax benefits under Section 80C and Section 10(10D)

Compliance reminders:
- NEVER guarantee returns — ULIPs are subject to market risk
- Always disclose all charges upfront
- Clearly state that past performance does not guarantee future returns
- Mention the free-look period (15 days)
- Explain that the insurance component is secondary to the investment component
- Follow IRDAI guidelines on benefit illustration (optimistic and conservative scenarios)`,
  },
};

interface StepIdentityData {
  agentName: string;
  personaName: string;
  customer: string;
  systemPrompt: string;
  languages: string[];
  tone: string;
}

interface StepIdentityProps {
  data: StepIdentityData;
  onChange: (data: StepIdentityData) => void;
}

export function StepIdentity({ data, onChange }: StepIdentityProps) {
  const [showTemplates, setShowTemplates] = useState(false);

  function updateField<K extends keyof StepIdentityData>(
    field: K,
    value: StepIdentityData[K]
  ) {
    onChange({ ...data, [field]: value });
  }

  function toggleLanguage(lang: string) {
    const current = data.languages;
    const updated = current.includes(lang)
      ? current.filter((l) => l !== lang)
      : [...current, lang];
    updateField("languages", updated);
  }

  function insertTemplate(key: string) {
    const template = TEMPLATES[key];
    if (template) {
      updateField("systemPrompt", template.prompt);
      setShowTemplates(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Identity & Prompt</h2>
        <p className="text-sm text-muted-foreground">
          Define your agent&apos;s identity, personality, and core instructions.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="agent-name">Agent Name</Label>
          <Input
            id="agent-name"
            placeholder="e.g., Health Sales Bot v2"
            value={data.agentName}
            onChange={(e) => updateField("agentName", e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Internal label for identifying this agent in the dashboard.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="persona-name">Persona Name</Label>
          <Input
            id="persona-name"
            placeholder="e.g., Priya, Rahul, Advisor"
            value={data.personaName}
            onChange={(e) => updateField("personaName", e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            What should the agent call itself when speaking to customers?
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="customer">Customer</Label>
        <Select
          value={data.customer}
          onValueChange={(val) => updateField("customer", val ?? "")}
        >
          <SelectTrigger id="customer" className="w-full">
            <SelectValue placeholder="Select a customer" />
          </SelectTrigger>
          <SelectContent>
            {CUSTOMERS.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          The insurance company this agent is being built for.
        </p>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="system-prompt">System Prompt</Label>
          <div className="relative">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowTemplates(!showTemplates)}
            >
              <FileTextIcon className="size-3.5" />
              Insert Template
            </Button>
            {showTemplates && (
              <div className="absolute right-0 top-full z-50 mt-1 w-56 rounded-lg border bg-popover p-1 shadow-lg ring-1 ring-foreground/10">
                {Object.entries(TEMPLATES).map(([key, tpl]) => (
                  <button
                    key={key}
                    className="flex w-full items-center rounded-md px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
                    onClick={() => insertTemplate(key)}
                  >
                    {tpl.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <Textarea
          id="system-prompt"
          placeholder={`You are a helpful insurance sales agent working for {{customer_name}}. Your name is {{persona_name}}.\n\nYour goal is to understand the customer's needs and recommend the most suitable insurance plan.\n\nKey guidelines:\n- Ask about the customer's requirements\n- Explain coverage options clearly\n- Always mention the free-look period as per IRDAI guidelines\n- Never guarantee claim approval\n- Collect explicit consent before storing personal information`}
          className="min-h-[240px] font-mono text-xs"
          value={data.systemPrompt}
          onChange={(e) => updateField("systemPrompt", e.target.value)}
        />
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            Core instructions that define your agent&apos;s behavior. Use{" "}
            {"{{customer_name}}"} and {"{{persona_name}}"} as dynamic
            placeholders.
          </p>
          <span className="text-xs text-muted-foreground">
            {data.systemPrompt.length} characters
          </span>
        </div>
      </div>

      <div className="space-y-3">
        <Label>Languages</Label>
        <p className="text-xs text-muted-foreground">
          Select the languages this agent should support.
        </p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {LANGUAGES.map((lang) => (
            <label
              key={lang}
              className="flex cursor-pointer items-center gap-2 rounded-lg border border-input px-3 py-2 text-sm transition-colors hover:bg-accent has-[:checked]:border-primary has-[:checked]:bg-primary/5"
            >
              <Checkbox
                checked={data.languages.includes(lang)}
                onCheckedChange={() => toggleLanguage(lang)}
              />
              {lang}
            </label>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        <Label>Tone</Label>
        <p className="text-xs text-muted-foreground">
          Choose the communication style for your agent.
        </p>
        <RadioGroup
          value={data.tone}
          onValueChange={(val) => updateField("tone", val ?? "")}
          className="grid gap-3 sm:grid-cols-3"
        >
          {TONES.map((t) => (
            <label
              key={t.value}
              className="flex cursor-pointer items-start gap-3 rounded-lg border border-input px-4 py-3 transition-colors hover:bg-accent has-[:checked]:border-primary has-[:checked]:bg-primary/5"
            >
              <RadioGroupItem value={t.value} className="mt-0.5" />
              <div className="space-y-1">
                <span className="text-sm font-medium">{t.label}</span>
                <p className="text-xs text-muted-foreground">
                  {t.description}
                </p>
              </div>
            </label>
          ))}
        </RadioGroup>
      </div>

      {(data.agentName || data.personaName || data.customer) && (
        <Card size="sm" className="bg-muted/30">
          <CardHeader className="border-b">
            <CardTitle className="text-sm">Preview</CardTitle>
            <CardDescription>How this agent will appear</CardDescription>
          </CardHeader>
          <CardContent className="pt-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">
                {data.agentName || "Untitled Agent"}
              </span>
              {data.personaName && (
                <Badge variant="secondary">{data.personaName}</Badge>
              )}
              {data.customer && (
                <Badge variant="outline">{data.customer}</Badge>
              )}
              {data.tone && (
                <Badge variant="outline" className="capitalize">
                  {data.tone}
                </Badge>
              )}
              {data.languages.length > 0 && (
                <span className="text-muted-foreground">
                  {data.languages.join(", ")}
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
