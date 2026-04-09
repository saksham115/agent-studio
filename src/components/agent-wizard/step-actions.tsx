"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  CardAction,
  CardFooter,
} from "@/components/ui/card";
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
  GlobeIcon,
  SearchIcon,
  CheckCircle2Icon,
} from "lucide-react";

export type ActionType = "api_call" | "data_lookup";

export interface ActionParam {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

export interface AgentAction {
  id: string;
  name: string;
  description: string;
  action_type: ActionType;
  parameters: ActionParam[];
  config: Record<string, unknown>;
  requires_confirmation: boolean;
}

interface StepActionsData {
  actions: AgentAction[];
}

interface StepActionsProps {
  data: StepActionsData;
  onChange: (data: StepActionsData) => void;
}

const TYPE_CONFIG: Record<
  ActionType,
  { label: string; color: string; icon: React.ReactNode }
> = {
  api_call: {
    label: "API Call",
    color:
      "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/20",
    icon: <GlobeIcon className="size-4" />,
  },
  data_lookup: {
    label: "Data Lookup",
    color: "bg-chart-2/10 text-chart-2 border-chart-2/20",
    icon: <SearchIcon className="size-4" />,
  },
};

const PARAM_TYPES = ["string", "number", "boolean", "object", "array"] as const;

export function StepActions({ data, onChange }: StepActionsProps) {
  const [editing, setEditing] = useState<AgentAction | null>(null);
  const [configText, setConfigText] = useState("");
  const [configError, setConfigError] = useState<string | null>(null);

  function openEdit(action: AgentAction) {
    setEditing({
      ...action,
      parameters: action.parameters.map((p) => ({ ...p })),
    });
    setConfigText(JSON.stringify(action.config ?? {}, null, 2));
    setConfigError(null);
  }

  function commitEdit() {
    if (!editing) return;
    let parsedConfig: Record<string, unknown>;
    try {
      const raw = configText.trim() ? JSON.parse(configText) : {};
      if (typeof raw !== "object" || Array.isArray(raw) || raw === null) {
        throw new Error("Config must be a JSON object");
      }
      parsedConfig = raw as Record<string, unknown>;
    } catch (err) {
      setConfigError(err instanceof Error ? err.message : "Invalid JSON");
      return;
    }
    onChange({
      ...data,
      actions: data.actions.map((a) =>
        a.id === editing.id ? { ...editing, config: parsedConfig } : a
      ),
    });
    setEditing(null);
  }

  function toggleConfirmation(actionId: string) {
    onChange({
      ...data,
      actions: data.actions.map((a) =>
        a.id === actionId
          ? { ...a, requires_confirmation: !a.requires_confirmation }
          : a
      ),
    });
  }

  function removeAction(actionId: string) {
    onChange({
      ...data,
      actions: data.actions.filter((a) => a.id !== actionId),
    });
  }

  function addAction() {
    const newAction: AgentAction = {
      id: `action-${Date.now()}`,
      name: "New Action",
      description: "Describe what this action does",
      action_type: "api_call",
      parameters: [],
      config: {},
      requires_confirmation: true,
    };
    onChange({
      ...data,
      actions: [...data.actions, newAction],
    });
    openEdit(newAction);
  }

  function addParam() {
    if (!editing) return;
    setEditing({
      ...editing,
      parameters: [
        ...editing.parameters,
        { name: "", type: "string", required: false, description: "" },
      ],
    });
  }

  function updateParam(index: number, updates: Partial<ActionParam>) {
    if (!editing) return;
    setEditing({
      ...editing,
      parameters: editing.parameters.map((p, i) =>
        i === index ? { ...p, ...updates } : p
      ),
    });
  }

  function removeParam(index: number) {
    if (!editing) return;
    setEditing({
      ...editing,
      parameters: editing.parameters.filter((_, i) => i !== index),
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold">Actions</h2>
          <p className="text-sm text-muted-foreground">
            Define the actions your agent can perform during conversations, such
            as calling APIs, looking up data, or handing off to a human.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={addAction}>
          <PlusIcon className="size-3.5" />
          Add Action
        </Button>
      </div>

      {data.actions.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-12 text-center">
          <div className="flex size-12 items-center justify-center rounded-full bg-muted">
            <CheckCircle2Icon className="size-6 text-muted-foreground/50" />
          </div>
          <div>
            <p className="text-sm font-medium">No actions configured</p>
            <p className="text-xs text-muted-foreground">
              Add actions to let your agent perform tasks like calling external
              APIs, looking up records, or escalating to a human agent.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={addAction}>
            <PlusIcon className="size-3.5" />
            Add Your First Action
          </Button>
        </div>
      )}

      <div className="grid gap-4">
        {data.actions.map((action) => {
          const typeConfig = TYPE_CONFIG[action.action_type];
          return (
            <Card key={action.id}>
              <CardHeader>
                <div className="flex items-start gap-3">
                  <div
                    className={`flex size-10 items-center justify-center rounded-lg border ${typeConfig.color}`}
                  >
                    {typeConfig.icon}
                  </div>
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <CardTitle>{action.name}</CardTitle>
                      <span
                        className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${typeConfig.color}`}
                      >
                        {typeConfig.label}
                      </span>
                    </div>
                    <CardDescription>{action.description}</CardDescription>
                  </div>
                </div>
                <CardAction>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-muted-foreground"
                      onClick={() => openEdit(action)}
                    >
                      <PencilIcon className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => removeAction(action.id)}
                    >
                      <Trash2Icon className="size-3.5" />
                    </Button>
                  </div>
                </CardAction>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div>
                    <Label className="text-xs text-muted-foreground mb-2">
                      Parameters
                    </Label>
                    {action.parameters.length === 0 ? (
                      <p className="text-xs text-muted-foreground/70 italic">
                        No parameters defined
                      </p>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {action.parameters.map((param, idx) => (
                          <div
                            key={`${param.name}-${idx}`}
                            className="inline-flex items-center gap-1.5 rounded-md border bg-muted/50 px-2.5 py-1"
                          >
                            <span className="text-xs font-mono font-medium">
                              {param.name || "(unnamed)"}
                            </span>
                            <span className="text-[10px] text-muted-foreground">
                              {param.type}
                            </span>
                            {param.required && (
                              <span className="text-[10px] text-red-500">*</span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
              <CardFooter className="justify-between">
                <div className="flex items-center gap-2">
                  <Switch
                    size="sm"
                    checked={action.requires_confirmation}
                    onCheckedChange={() => toggleConfirmation(action.id)}
                  />
                  <Label className="text-xs text-muted-foreground">
                    Require confirmation before execution
                  </Label>
                </div>
              </CardFooter>
            </Card>
          );
        })}
      </div>

      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) {
            setEditing(null);
            setConfigError(null);
          }
        }}
      >
        <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit Action</DialogTitle>
            <DialogDescription>
              Configure the action&apos;s name, type, parameters, and execution
              config.
            </DialogDescription>
          </DialogHeader>

          {editing && (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="action-name">Name</Label>
                <Input
                  id="action-name"
                  value={editing.name}
                  onChange={(e) =>
                    setEditing({ ...editing, name: e.target.value })
                  }
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="action-description">Description</Label>
                <Textarea
                  id="action-description"
                  value={editing.description}
                  onChange={(e) =>
                    setEditing({ ...editing, description: e.target.value })
                  }
                  rows={2}
                />
              </div>

              <div className="space-y-2">
                <Label>Type</Label>
                <Select
                  value={editing.action_type}
                  onValueChange={(val) =>
                    setEditing({
                      ...editing,
                      action_type: val as ActionType,
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(TYPE_CONFIG) as ActionType[]).map((t) => (
                      <SelectItem key={t} value={t}>
                        {TYPE_CONFIG[t].label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label>Parameters</Label>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={addParam}
                  >
                    <PlusIcon className="size-3" />
                    Add
                  </Button>
                </div>
                {editing.parameters.length === 0 && (
                  <p className="text-xs text-muted-foreground italic">
                    No parameters
                  </p>
                )}
                <div className="space-y-2">
                  {editing.parameters.map((param, idx) => (
                    <div
                      key={idx}
                      className="rounded-md border bg-muted/30 p-2 space-y-2"
                    >
                      <div className="flex items-center gap-2">
                        <Input
                          placeholder="param_name"
                          value={param.name}
                          onChange={(e) =>
                            updateParam(idx, { name: e.target.value })
                          }
                          className="flex-1 h-8 text-xs font-mono"
                        />
                        <Select
                          value={param.type}
                          onValueChange={(val) =>
                            updateParam(idx, { type: val ?? "string" })
                          }
                        >
                          <SelectTrigger size="sm" className="w-[100px]">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {PARAM_TYPES.map((t) => (
                              <SelectItem key={t} value={t}>
                                {t}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <div className="flex items-center gap-1">
                          <Switch
                            size="sm"
                            checked={param.required}
                            onCheckedChange={(checked) =>
                              updateParam(idx, { required: !!checked })
                            }
                          />
                          <span className="text-[10px] text-muted-foreground">
                            req
                          </span>
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-xs"
                          className="text-muted-foreground hover:text-destructive"
                          onClick={() => removeParam(idx)}
                        >
                          <Trash2Icon className="size-3" />
                        </Button>
                      </div>
                      <Input
                        placeholder="Description"
                        value={param.description}
                        onChange={(e) =>
                          updateParam(idx, { description: e.target.value })
                        }
                        className="h-7 text-xs"
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="action-config">Config (JSON)</Label>
                <Textarea
                  id="action-config"
                  value={configText}
                  onChange={(e) => {
                    setConfigText(e.target.value);
                    setConfigError(null);
                  }}
                  rows={6}
                  className="font-mono text-xs"
                  placeholder='{"url": "https://...", "method": "POST"}'
                />
                {configError && (
                  <p className="text-xs text-red-600 dark:text-red-400">
                    {configError}
                  </p>
                )}
                <p className="text-[10px] text-muted-foreground">
                  Type-specific keys (e.g., url, method, headers for api_call;
                  endpoint, query_template for data_lookup).
                </p>
              </div>

              <div className="flex items-center gap-2">
                <Switch
                  size="sm"
                  checked={editing.requires_confirmation}
                  onCheckedChange={(checked) =>
                    setEditing({
                      ...editing,
                      requires_confirmation: !!checked,
                    })
                  }
                />
                <Label className="text-xs text-muted-foreground">
                  Require confirmation before execution
                </Label>
              </div>
            </div>
          )}

          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>
              Cancel
            </DialogClose>
            <Button onClick={commitEdit}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
