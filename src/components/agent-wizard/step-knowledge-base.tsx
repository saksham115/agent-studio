"use client";

import { useState, useCallback, useRef } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
  UploadCloudIcon,
  FileTextIcon,
  TableIcon,
  Trash2Icon,
  PlusIcon,
  DatabaseIcon,
  GlobeIcon,
  FileJsonIcon,
  PencilIcon,
  CheckCircle2Icon,
  LoaderIcon,
  CircleXIcon,
  CircleDotDashedIcon,
} from "lucide-react";

export interface UploadedDocument {
  id: string;
  name: string;
  type: "PDF" | "TXT" | "CSV";
  category: string;
  status: "pending" | "processing" | "ready" | "failed";
  size: number;
  backendId?: string;
  errorMessage?: string;
}

interface StructuredSource {
  id: string;
  name: string;
  type: "API" | "Database" | "Static JSON";
  description: string;
  status: "connected" | "disconnected" | "pending";
}

export interface StepKnowledgeBaseData {
  documents: UploadedDocument[];
  structuredSources: StructuredSource[];
}

interface StepKnowledgeBaseProps {
  data: StepKnowledgeBaseData;
  onChange: (data: StepKnowledgeBaseData) => void;
  onFileAdded?: (tempId: string, file: File) => void;
  onFileRemoved?: (tempId: string) => void;
}

const ALLOWED_EXTENSIONS = new Set(["pdf", "txt", "csv"]);
const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB

const CATEGORIES = [
  "Product Brochure",
  "FAQ",
  "Policy Terms",
  "Claim Process",
];

const FILE_TYPE_ICONS: Record<string, React.ReactNode> = {
  PDF: <FileTextIcon className="size-4 text-destructive" />,
  TXT: <FileTextIcon className="size-4 text-chart-2" />,
  CSV: <TableIcon className="size-4 text-primary" />,
};

const SOURCE_TYPE_ICONS: Record<string, React.ReactNode> = {
  API: <GlobeIcon className="size-4 text-chart-4" />,
  Database: <DatabaseIcon className="size-4 text-chart-2" />,
  "Static JSON": <FileJsonIcon className="size-4 text-chart-3" />,
};

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function typeBadgeVariant(type: string) {
  switch (type) {
    case "PDF":
      return "bg-destructive/10 text-destructive";
    case "TXT":
      return "bg-chart-2/10 text-chart-2";
    case "CSV":
      return "bg-primary/10 text-primary";
    case "API":
      return "bg-chart-4/10 text-chart-4";
    case "Database":
      return "bg-chart-2/10 text-chart-2";
    case "Static JSON":
      return "bg-chart-3/10 text-chart-3";
    default:
      return "";
  }
}

function statusBadge(status: string) {
  switch (status) {
    case "ready":
    case "connected":
      return (
        <span className="inline-flex items-center gap-1 text-xs text-primary">
          <CheckCircle2Icon className="size-3" />
          {status === "ready" ? "Ready" : "Connected"}
        </span>
      );
    case "processing":
      return (
        <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
          <LoaderIcon className="size-3 animate-spin" />
          Processing
        </span>
      );
    case "pending":
      return (
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <CircleDotDashedIcon className="size-3" />
          Pending upload
        </span>
      );
    case "failed":
      return (
        <span className="inline-flex items-center gap-1 text-xs text-destructive">
          <CircleXIcon className="size-3" />
          Failed
        </span>
      );
    case "disconnected":
      return (
        <span className="inline-flex items-center gap-1 text-xs text-red-500">
          <span className="size-2 rounded-full bg-red-500" />
          Disconnected
        </span>
      );
    default:
      return null;
  }
}

export function StepKnowledgeBase({
  data,
  onChange,
  onFileAdded,
  onFileRemoved,
}: StepKnowledgeBaseProps) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function processFiles(files: File[]) {
    const newDocs: UploadedDocument[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const ext = file.name.split(".").pop()?.toLowerCase() || "";

      if (!ALLOWED_EXTENSIONS.has(ext)) {
        toast.error(`"${file.name}" rejected — only PDF, TXT, and CSV files are supported.`);
        continue;
      }

      if (file.size > MAX_FILE_SIZE) {
        toast.error(`"${file.name}" is too large (${formatFileSize(file.size)}). Maximum is 50 MB.`);
        continue;
      }

      const tempId = `doc-${Date.now()}-${i}`;
      const fileType = ext.toUpperCase() as UploadedDocument["type"];

      newDocs.push({
        id: tempId,
        name: file.name,
        type: fileType,
        category: "Product Brochure",
        status: "pending",
        size: file.size,
      });

      onFileAdded?.(tempId, file);
    }

    if (newDocs.length > 0) {
      onChange({
        ...data,
        documents: [...data.documents, ...newDocs],
      });
    }
  }

  function updateDocCategory(docId: string, category: string) {
    onChange({
      ...data,
      documents: data.documents.map((d) =>
        d.id === docId ? { ...d, category } : d
      ),
    });
  }

  function removeDocument(docId: string) {
    onFileRemoved?.(docId);
    onChange({
      ...data,
      documents: data.documents.filter((d) => d.id !== docId),
    });
  }

  function removeSource(sourceId: string) {
    onChange({
      ...data,
      structuredSources: data.structuredSources.filter(
        (s) => s.id !== sourceId
      ),
    });
  }

  function addSampleSource() {
    const newSource: StructuredSource = {
      id: `src-${Date.now()}`,
      name: "New Data Source",
      type: "API",
      description: "Configure this data source endpoint",
      status: "pending",
    };
    onChange({
      ...data,
      structuredSources: [...data.structuredSources, newSource],
    });
  }

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const files = Array.from(e.dataTransfer.files);
      if (files.length > 0) {
        processFiles(files);
      }
    },
    [data, onChange, onFileAdded]
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        processFiles(Array.from(e.target.files));
        e.target.value = "";
      }
    },
    [data, onChange, onFileAdded]
  );

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-lg font-semibold">Knowledge Base</h2>
        <p className="text-sm text-muted-foreground">
          Configure the data sources your agent will use to answer customer
          queries.
        </p>
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold">Unstructured Sources</h3>
            <p className="text-xs text-muted-foreground">
              Upload documents like product brochures, FAQs, and policy
              documents.
            </p>
          </div>
          <Badge variant="secondary">{data.documents.length} files</Badge>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.txt,.csv"
          className="hidden"
          onChange={handleFileSelect}
        />

        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 transition-colors ${
            isDragging
              ? "border-primary bg-primary/5"
              : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50"
          }`}
        >
          <div className="flex size-12 items-center justify-center rounded-full bg-muted">
            <UploadCloudIcon className="size-6 text-muted-foreground" />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium">
              Drag & drop files here, or click to browse
            </p>
            <p className="text-xs text-muted-foreground">
              Supports PDF, TXT, CSV (max 50 MB per file)
            </p>
          </div>
        </div>

        {data.documents.length > 0 && (
          <div className="space-y-2">
            {data.documents.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center gap-3 rounded-lg border bg-card p-3 transition-colors hover:bg-muted/30"
              >
                <div className="flex size-9 items-center justify-center rounded-md bg-muted">
                  {FILE_TYPE_ICONS[doc.type]}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">
                      {doc.name}
                    </span>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${typeBadgeVariant(
                        doc.type
                      )}`}
                    >
                      {doc.type}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {formatFileSize(doc.size)}
                  </span>
                </div>
                <Select
                  value={doc.category}
                  onValueChange={(val) => updateDocCategory(doc.id, val ?? "")}
                >
                  <SelectTrigger className="w-[160px]" size="sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIES.map((cat) => (
                      <SelectItem key={cat} value={cat}>
                        {cat}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <div className="flex items-center gap-2">
                  {statusBadge(doc.status)}
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => removeDocument(doc.id)}
                    className="text-muted-foreground hover:text-destructive"
                  >
                    <Trash2Icon className="size-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="h-px bg-border" />

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold">Structured Sources</h3>
            <p className="text-xs text-muted-foreground">
              Connect APIs, databases, or upload structured data for real-time
              lookups.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={addSampleSource}>
            <PlusIcon className="size-3.5" />
            Add Source
          </Button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {data.structuredSources.map((source) => (
            <Card key={source.id} size="sm">
              <CardHeader>
                <div className="flex items-start gap-3">
                  <div className="flex size-9 items-center justify-center rounded-md bg-muted">
                    {SOURCE_TYPE_ICONS[source.type]}
                  </div>
                  <div className="flex-1 min-w-0 space-y-1">
                    <CardTitle className="text-sm">{source.name}</CardTitle>
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${typeBadgeVariant(
                          source.type
                        )}`}
                      >
                        {source.type}
                      </span>
                      {statusBadge(source.status)}
                    </div>
                  </div>
                </div>
                <CardAction>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      className="text-muted-foreground"
                    >
                      <PencilIcon className="size-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => removeSource(source.id)}
                    >
                      <Trash2Icon className="size-3" />
                    </Button>
                  </div>
                </CardAction>
              </CardHeader>
              <CardContent>
                <CardDescription>{source.description}</CardDescription>
              </CardContent>
            </Card>
          ))}

          {data.structuredSources.length === 0 && (
            <div className="col-span-full flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-8 text-center">
              <DatabaseIcon className="size-8 text-muted-foreground/50" />
              <p className="text-sm text-muted-foreground">
                No structured sources configured yet.
              </p>
              <Button variant="outline" size="sm" onClick={addSampleSource}>
                <PlusIcon className="size-3.5" />
                Add Your First Source
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
