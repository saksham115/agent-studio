"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
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
  PlusIcon,
  Trash2Icon,
  PencilIcon,
  LinkIcon,
  DatabaseIcon,
  FileOutputIcon,
  GlobeIcon,
  BellIcon,
  CheckCircle2Icon,
} from "lucide-react";

interface ActionParam {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

interface AgentAction {
  id: string;
  name: string;
  description: string;
  type: "db_update" | "link_generation" | "doc_fetch" | "api_call" | "notification";
  parameters: ActionParam[];
  requireConfirmation: boolean;
}

interface StepActionsData {
  actions: AgentAction[];
}

interface StepActionsProps {
  data: StepActionsData;
  onChange: (data: StepActionsData) => void;
}

const TYPE_CONFIG: Record<
  AgentAction["type"],
  { label: string; color: string; icon: React.ReactNode }
> = {
  db_update: {
    label: "DB Update",
    color: "bg-chart-2/10 text-chart-2 border-chart-2/20",
    icon: <DatabaseIcon className="size-4" />,
  },
  link_generation: {
    label: "Link Gen",
    color: "bg-chart-4/10 text-chart-4 border-chart-4/20",
    icon: <LinkIcon className="size-4" />,
  },
  doc_fetch: {
    label: "Doc Fetch",
    color: "bg-primary/10 text-primary border-primary/20",
    icon: <FileOutputIcon className="size-4" />,
  },
  api_call: {
    label: "API Call",
    color: "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/20",
    icon: <GlobeIcon className="size-4" />,
  },
  notification: {
    label: "Notification",
    color: "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-500/20",
    icon: <BellIcon className="size-4" />,
  },
};

export function StepActions({ data, onChange }: StepActionsProps) {
  function toggleConfirmation(actionId: string) {
    onChange({
      ...data,
      actions: data.actions.map((a) =>
        a.id === actionId
          ? { ...a, requireConfirmation: !a.requireConfirmation }
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
      type: "api_call",
      parameters: [
        {
          name: "param1",
          type: "string",
          required: true,
          description: "Parameter description",
        },
      ],
      requireConfirmation: true,
    };
    onChange({
      ...data,
      actions: [...data.actions, newAction],
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold">Actions</h2>
          <p className="text-sm text-muted-foreground">
            Define the actions your agent can perform during conversations, such
            as generating links, updating records, or fetching documents.
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
              Add actions to let your agent perform tasks like generating payment
              links or updating CRM records.
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
          const typeConfig = TYPE_CONFIG[action.type];
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
                    <div className="flex flex-wrap gap-2">
                      {action.parameters.map((param) => (
                        <div
                          key={param.name}
                          className="inline-flex items-center gap-1.5 rounded-md border bg-muted/50 px-2.5 py-1"
                        >
                          <span className="text-xs font-mono font-medium">
                            {param.name}
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
                  </div>
                </div>
              </CardContent>
              <CardFooter className="justify-between">
                <div className="flex items-center gap-2">
                  <Switch
                    size="sm"
                    checked={action.requireConfirmation}
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
    </div>
  );
}
