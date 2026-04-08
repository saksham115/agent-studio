"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from "@/components/ui/dialog";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  CardAction,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  PlusIcon,
  Trash2Icon,
  PencilIcon,
  SparklesIcon,
  ShieldCheckIcon,
  ShieldAlertIcon,
  ShieldIcon,
} from "lucide-react";

interface Guardrail {
  id: string;
  name: string;
  rule: string;
  category: "compliance" | "pii" | "topic_boundary" | "safety" | "anti_misselling" | "custom";
  severity: "block" | "warn" | "log";
  enabled: boolean;
}

interface StepGuardrailsData {
  guardrails: Guardrail[];
}

interface StepGuardrailsProps {
  data: StepGuardrailsData;
  onChange: (data: StepGuardrailsData) => void;
}

const CATEGORY_CONFIG: Record<
  Guardrail["category"],
  { label: string; color: string; icon: React.ReactNode }
> = {
  compliance: {
    label: "Compliance",
    color: "bg-chart-2/10 text-chart-2 border-chart-2/20",
    icon: <ShieldCheckIcon className="size-4" />,
  },
  pii: {
    label: "PII",
    color: "bg-destructive/10 text-destructive border-destructive/20",
    icon: <ShieldAlertIcon className="size-4" />,
  },
  topic_boundary: {
    label: "Topic Boundary",
    color: "bg-chart-3/10 text-chart-3 border-chart-3/20",
    icon: <ShieldIcon className="size-4" />,
  },
  safety: {
    label: "Safety",
    color: "bg-primary/10 text-primary border-primary/20",
    icon: <ShieldCheckIcon className="size-4" />,
  },
  anti_misselling: {
    label: "Anti-Misselling",
    color: "bg-warning/10 text-warning border-warning/20",
    icon: <ShieldAlertIcon className="size-4" />,
  },
  custom: {
    label: "Custom",
    color: "bg-muted text-muted-foreground border-border",
    icon: <ShieldIcon className="size-4" />,
  },
};

const SEVERITY_CONFIG: Record<
  Guardrail["severity"],
  { label: string; color: string }
> = {
  block: {
    label: "Block",
    color: "bg-destructive/10 text-destructive",
  },
  warn: {
    label: "Warn",
    color: "bg-warning/10 text-warning",
  },
  log: {
    label: "Log",
    color: "bg-chart-2/10 text-chart-2",
  },
};

export function StepGuardrails({ data, onChange }: StepGuardrailsProps) {
  const [editingGuardrail, setEditingGuardrail] = useState<Guardrail | null>(null);

  function updateGuardrail(id: string, updates: Partial<Guardrail>) {
    onChange({
      ...data,
      guardrails: data.guardrails.map((g) =>
        g.id === id ? { ...g, ...updates } : g
      ),
    });
  }

  function removeGuardrail(id: string) {
    onChange({
      ...data,
      guardrails: data.guardrails.filter((g) => g.id !== id),
    });
  }

  function addCustomRule() {
    const newRule: Guardrail = {
      id: `guard-${Date.now()}`,
      name: "New Custom Rule",
      rule: "Define the guardrail rule text here",
      category: "custom",
      severity: "warn",
      enabled: true,
    };
    onChange({
      ...data,
      guardrails: [...data.guardrails, newRule],
    });
    setEditingGuardrail({ ...newRule });
  }

  function autoGenerate() {
    const autoRules: Guardrail[] = [
      {
        id: "auto-1",
        name: "IRDAI Compliance",
        rule: "Always mention cooling-off period and free-look period when discussing policy purchase",
        category: "compliance",
        severity: "block",
        enabled: true,
      },
      {
        id: "auto-2",
        name: "PII Protection",
        rule: "Never repeat full Aadhaar or PAN number back to the customer",
        category: "pii",
        severity: "block",
        enabled: true,
      },
      {
        id: "auto-3",
        name: "Topic Boundary",
        rule: "Only discuss insurance products available in the knowledge base",
        category: "topic_boundary",
        severity: "warn",
        enabled: true,
      },
      {
        id: "auto-4",
        name: "Anti-Misselling",
        rule: "Never guarantee returns on ULIP or investment-linked products",
        category: "safety",
        severity: "block",
        enabled: true,
      },
      {
        id: "auto-5",
        name: "Escalation Trigger",
        rule: "Escalate to human agent when customer explicitly requests or shows frustration",
        category: "safety",
        severity: "warn",
        enabled: true,
      },
      {
        id: "auto-6",
        name: "Consent Required",
        rule: "Collect explicit consent before storing personal information",
        category: "compliance",
        severity: "block",
        enabled: true,
      },
    ];
    onChange({ ...data, guardrails: autoRules });
  }

  const enabledCount = data.guardrails.filter((g) => g.enabled).length;
  const blockCount = data.guardrails.filter(
    (g) => g.enabled && g.severity === "block"
  ).length;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold">Guardrails</h2>
          <p className="text-sm text-muted-foreground">
            Define safety rules and compliance boundaries for your agent. These
            rules are enforced during every conversation.
          </p>
        </div>
        <Button variant="default" size="sm" onClick={autoGenerate}>
          <SparklesIcon className="size-3.5" />
          Auto-generate
        </Button>
      </div>

      {data.guardrails.length > 0 && (
        <div className="flex gap-3">
          <div className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2">
            <span className="text-2xl font-bold">{enabledCount}</span>
            <div className="text-xs text-muted-foreground">
              <div>Active</div>
              <div>Rules</div>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-lg border bg-red-500/5 px-3 py-2">
            <span className="text-2xl font-bold text-red-600 dark:text-red-400">
              {blockCount}
            </span>
            <div className="text-xs text-muted-foreground">
              <div>Blocking</div>
              <div>Rules</div>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-lg border bg-amber-500/5 px-3 py-2">
            <span className="text-2xl font-bold text-amber-600 dark:text-amber-400">
              {data.guardrails.filter(
                (g) => g.enabled && g.severity === "warn"
              ).length}
            </span>
            <div className="text-xs text-muted-foreground">
              <div>Warning</div>
              <div>Rules</div>
            </div>
          </div>
        </div>
      )}

      {data.guardrails.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-dashed p-12 text-center">
          <div className="flex size-14 items-center justify-center rounded-full bg-muted">
            <ShieldIcon className="size-7 text-muted-foreground/50" />
          </div>
          <div>
            <p className="text-sm font-medium">No guardrails configured</p>
            <p className="text-xs text-muted-foreground">
              Add safety rules to ensure your agent stays compliant and
              on-topic. Use auto-generate to create rules based on your agent
              configuration.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="default" size="sm" onClick={autoGenerate}>
              <SparklesIcon className="size-3.5" />
              Auto-generate Rules
            </Button>
            <Button variant="outline" size="sm" onClick={addCustomRule}>
              <PlusIcon className="size-3.5" />
              Add Custom Rule
            </Button>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {data.guardrails.map((guardrail) => {
          const catConfig = CATEGORY_CONFIG[guardrail.category];
          const sevConfig = SEVERITY_CONFIG[guardrail.severity];

          return (
            <Card
              key={guardrail.id}
              className={!guardrail.enabled ? "opacity-60" : ""}
            >
              <CardHeader>
                <div className="flex items-start gap-3">
                  <div
                    className={`flex size-9 items-center justify-center rounded-lg border ${catConfig.color}`}
                  >
                    {catConfig.icon}
                  </div>
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <CardTitle className="text-sm">
                        {guardrail.name}
                      </CardTitle>
                      <span
                        className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${catConfig.color}`}
                      >
                        {catConfig.label}
                      </span>
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${sevConfig.color}`}
                      >
                        {sevConfig.label}
                      </span>
                    </div>
                    <CardDescription className="text-xs leading-relaxed">
                      {guardrail.rule}
                    </CardDescription>
                  </div>
                </div>
                <CardAction>
                  <div className="flex items-center gap-2">
                    <Switch
                      size="sm"
                      checked={guardrail.enabled}
                      onCheckedChange={(checked) =>
                        updateGuardrail(guardrail.id, { enabled: !!checked })
                      }
                    />
                    <Select
                      value={guardrail.severity}
                      onValueChange={(val) =>
                        updateGuardrail(guardrail.id, {
                          severity: val as Guardrail["severity"],
                        })
                      }
                    >
                      <SelectTrigger size="sm" className="w-[80px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="block">Block</SelectItem>
                        <SelectItem value="warn">Warn</SelectItem>
                        <SelectItem value="log">Log</SelectItem>
                      </SelectContent>
                    </Select>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      className="text-muted-foreground"
                      onClick={() => setEditingGuardrail({ ...guardrail })}
                    >
                      <PencilIcon className="size-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => removeGuardrail(guardrail.id)}
                    >
                      <Trash2Icon className="size-3" />
                    </Button>
                  </div>
                </CardAction>
              </CardHeader>
            </Card>
          );
        })}
      </div>

      {data.guardrails.length > 0 && (
        <Button variant="outline" size="sm" onClick={addCustomRule}>
          <PlusIcon className="size-3.5" />
          Add Custom Rule
        </Button>
      )}

      <Dialog
        open={editingGuardrail !== null}
        onOpenChange={(open) => {
          if (!open) setEditingGuardrail(null);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit Guardrail</DialogTitle>
            <DialogDescription>
              Modify the guardrail name, category, and rule text.
            </DialogDescription>
          </DialogHeader>

          {editingGuardrail && (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="guardrail-name">Name</Label>
                <Input
                  id="guardrail-name"
                  value={editingGuardrail.name}
                  onChange={(e) =>
                    setEditingGuardrail({
                      ...editingGuardrail,
                      name: e.target.value,
                    })
                  }
                />
              </div>

              <div className="space-y-2">
                <Label>Category</Label>
                <Select
                  value={editingGuardrail.category}
                  onValueChange={(val) =>
                    setEditingGuardrail({
                      ...editingGuardrail,
                      category: val as Guardrail["category"],
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="compliance">Compliance</SelectItem>
                    <SelectItem value="pii">PII</SelectItem>
                    <SelectItem value="topic_boundary">Topic Boundary</SelectItem>
                    <SelectItem value="safety">Safety</SelectItem>
                    <SelectItem value="anti_misselling">Anti-Misselling</SelectItem>
                    <SelectItem value="custom">Custom</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="guardrail-rule">Rule</Label>
                <Textarea
                  id="guardrail-rule"
                  value={editingGuardrail.rule}
                  onChange={(e) =>
                    setEditingGuardrail({
                      ...editingGuardrail,
                      rule: e.target.value,
                    })
                  }
                  rows={3}
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>
              Cancel
            </DialogClose>
            <Button
              onClick={() => {
                if (editingGuardrail) {
                  updateGuardrail(editingGuardrail.id, {
                    name: editingGuardrail.name,
                    rule: editingGuardrail.rule,
                    category: editingGuardrail.category,
                  });
                  setEditingGuardrail(null);
                }
              }}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
