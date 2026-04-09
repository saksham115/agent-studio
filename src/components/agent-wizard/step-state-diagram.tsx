"use client";

import { useState, useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type NodeTypes,
  type NodeProps,
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  MarkerType,
  Handle,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  PlusIcon,
  LayoutIcon,
  XIcon,
  MaximizeIcon,
  MinimizeIcon,
} from "lucide-react";
import type {
  StateNodeData,
  WizardStateDiagram,
  WizardStateEdge,
  WizardStateNode,
} from "@/lib/state-diagram-transform";

type StateNode = WizardStateNode;

const HEADER_COLORS: Record<string, string> = {
  start: "bg-primary dark:bg-primary/90",
  normal: "bg-chart-2 dark:bg-chart-2/90",
  terminal: "bg-destructive dark:bg-destructive/90",
  branch: "bg-chart-3 dark:bg-chart-3/90",
};

const BORDER_COLORS: Record<string, string> = {
  start: "border-primary/30",
  normal: "border-chart-2/30",
  terminal: "border-destructive/30",
  branch: "border-chart-3/30",
};

function CustomNode({ data, selected }: NodeProps<StateNode>) {
  const headerColor = HEADER_COLORS[data.nodeType] || HEADER_COLORS.normal;
  const borderColor = BORDER_COLORS[data.nodeType] || BORDER_COLORS.normal;

  return (
    <div
      className={`min-w-[180px] max-w-[220px] rounded-lg border-2 bg-card shadow-md transition-shadow ${borderColor} ${
        selected ? "shadow-lg ring-2 ring-primary/50" : ""
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!size-2.5 !border-2 !border-background !bg-muted-foreground"
      />
      <div
        className={`rounded-t-[6px] px-3 py-1.5 text-xs font-semibold text-white ${headerColor}`}
      >
        {data.label}
      </div>
      <div className="space-y-1.5 p-3">
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {data.description}
        </p>
        <div className="flex items-center justify-between">
          <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            Max {data.maxTurns} turns
          </span>
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${
              data.nodeType === "start"
                ? "bg-primary/10 text-primary"
                : data.nodeType === "terminal"
                ? "bg-destructive/10 text-destructive"
                : data.nodeType === "branch"
                ? "bg-chart-3/10 text-chart-3"
                : "bg-chart-2/10 text-chart-2"
            }`}
          >
            {data.nodeType}
          </span>
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!size-2.5 !border-2 !border-background !bg-muted-foreground"
      />
    </div>
  );
}

const INITIAL_NODES: StateNode[] = [
  {
    id: "greeting",
    type: "stateNode",
    position: { x: 400, y: 0 },
    data: {
      label: "Greeting",
      description: "Welcome the customer and introduce the agent",
      instructions: "",
      maxTurns: 2,
      nodeType: "start",
    },
  },
  {
    id: "need-discovery",
    type: "stateNode",
    position: { x: 400, y: 140 },
    data: {
      label: "Need Discovery",
      description: "Understand customer requirements, family details, and budget",
      instructions: "",
      maxTurns: 8,
      nodeType: "normal",
    },
  },
  {
    id: "product-pitch",
    type: "stateNode",
    position: { x: 400, y: 280 },
    data: {
      label: "Product Pitch",
      description: "Present suitable insurance products from the knowledge base",
      instructions: "",
      maxTurns: 6,
      nodeType: "normal",
    },
  },
  {
    id: "objection-handling",
    type: "stateNode",
    position: { x: 400, y: 420 },
    data: {
      label: "Objection Handling",
      description: "Address customer concerns about pricing, coverage, or terms",
      instructions: "",
      maxTurns: 10,
      nodeType: "normal",
    },
  },
  {
    id: "quote-generation",
    type: "stateNode",
    position: { x: 400, y: 560 },
    data: {
      label: "Quote Generation",
      description: "Generate premium quote and share payment link",
      instructions: "",
      maxTurns: 4,
      nodeType: "normal",
    },
  },
  {
    id: "document-collection",
    type: "stateNode",
    position: { x: 400, y: 700 },
    data: {
      label: "Document Collection",
      description: "Collect KYC documents: Aadhaar, PAN, photos, medical reports",
      instructions: "",
      maxTurns: 6,
      nodeType: "normal",
    },
  },
  {
    id: "closure",
    type: "stateNode",
    position: { x: 400, y: 840 },
    data: {
      label: "Closure",
      description: "Confirm policy issuance and provide next steps",
      instructions: "",
      maxTurns: 3,
      nodeType: "terminal",
    },
  },
  {
    id: "follow-up",
    type: "stateNode",
    position: { x: 700, y: 420 },
    data: {
      label: "Follow-up",
      description: "Schedule callback or send information for later decision",
      instructions: "",
      maxTurns: 4,
      nodeType: "branch",
    },
  },
  {
    id: "escalation",
    type: "stateNode",
    position: { x: 100, y: 420 },
    data: {
      label: "Escalation",
      description: "Transfer to human agent when requested or frustration detected",
      instructions: "",
      maxTurns: 2,
      nodeType: "terminal",
    },
  },
];

const INITIAL_EDGES: WizardStateEdge[] = [
  {
    id: "e-greeting-need",
    source: "greeting",
    target: "need-discovery",
    label: "Customer responds",
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { strokeWidth: 2 },
    labelStyle: { fontSize: 10, fontWeight: 500 },
    labelBgStyle: { fillOpacity: 0.8 },
  },
  {
    id: "e-need-pitch",
    source: "need-discovery",
    target: "product-pitch",
    label: "Needs identified",
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { strokeWidth: 2 },
    labelStyle: { fontSize: 10, fontWeight: 500 },
    labelBgStyle: { fillOpacity: 0.8 },
  },
  {
    id: "e-pitch-objection",
    source: "product-pitch",
    target: "objection-handling",
    label: "Customer has concerns",
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { strokeWidth: 2 },
    labelStyle: { fontSize: 10, fontWeight: 500 },
    labelBgStyle: { fillOpacity: 0.8 },
  },
  {
    id: "e-pitch-quote",
    source: "product-pitch",
    target: "quote-generation",
    label: "Ready for quote",
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { strokeWidth: 2, strokeDasharray: "5 5" },
    labelStyle: { fontSize: 10, fontWeight: 500 },
    labelBgStyle: { fillOpacity: 0.8 },
  },
  {
    id: "e-objection-quote",
    source: "objection-handling",
    target: "quote-generation",
    label: "Objections resolved",
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { strokeWidth: 2 },
    labelStyle: { fontSize: 10, fontWeight: 500 },
    labelBgStyle: { fillOpacity: 0.8 },
  },
  {
    id: "e-objection-followup",
    source: "objection-handling",
    target: "follow-up",
    label: "Needs time to decide",
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { strokeWidth: 2 },
    labelStyle: { fontSize: 10, fontWeight: 500 },
    labelBgStyle: { fillOpacity: 0.8 },
  },
  {
    id: "e-quote-docs",
    source: "quote-generation",
    target: "document-collection",
    label: "Quote accepted",
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { strokeWidth: 2 },
    labelStyle: { fontSize: 10, fontWeight: 500 },
    labelBgStyle: { fillOpacity: 0.8 },
  },
  {
    id: "e-docs-closure",
    source: "document-collection",
    target: "closure",
    label: "Documents verified",
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { strokeWidth: 2 },
    labelStyle: { fontSize: 10, fontWeight: 500 },
    labelBgStyle: { fillOpacity: 0.8 },
  },
  {
    id: "e-any-escalation",
    source: "need-discovery",
    target: "escalation",
    label: "Escalation request",
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { strokeWidth: 2, strokeDasharray: "5 5" },
    labelStyle: { fontSize: 10, fontWeight: 500 },
    labelBgStyle: { fillOpacity: 0.8 },
  },
  {
    id: "e-pitch-escalation",
    source: "product-pitch",
    target: "escalation",
    label: "Frustrated",
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { strokeWidth: 2, strokeDasharray: "5 5" },
    labelStyle: { fontSize: 10, fontWeight: 500 },
    labelBgStyle: { fillOpacity: 0.8 },
  },
];

interface StepStateDiagramProps {
  data: WizardStateDiagram;
  onChange: (data: WizardStateDiagram) => void;
}

export function StepStateDiagram({ data, onChange }: StepStateDiagramProps) {
  const initialNodes = data.nodes.length > 0 ? data.nodes : INITIAL_NODES;
  const initialEdges = data.edges.length > 0 ? data.edges : INITIAL_EDGES;

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedNode, setSelectedNode] = useState<StateNode | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);

  const nodeTypes: NodeTypes = useMemo(
    () => ({
      stateNode: CustomNode,
    }),
    []
  );

  const onConnect = useCallback(
    (params: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...params,
            type: "smoothstep",
            markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
            style: { strokeWidth: 2 },
            label: "Transition",
            labelStyle: { fontSize: 10, fontWeight: 500 },
            labelBgStyle: { fillOpacity: 0.8 },
          },
          eds
        )
      );
    },
    [setEdges]
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: StateNode) => {
      setSelectedNode(node);
      setPanelOpen(true);
    },
    []
  );

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  function addState() {
    const newNode: StateNode = {
      id: `state-${Date.now()}`,
      type: "stateNode",
      position: { x: 250 + Math.random() * 200, y: 200 + Math.random() * 200 },
      data: {
        label: "New State",
        description: "Describe this state",
        instructions: "",
        maxTurns: 5,
        nodeType: "normal",
      },
    };
    setNodes((nds) => [...nds, newNode]);
  }

  function autoLayout() {
    const sortedNodeIds = [
      "greeting",
      "need-discovery",
      "product-pitch",
      "objection-handling",
      "quote-generation",
      "document-collection",
      "closure",
    ];
    const branchNodes = nodes.filter(
      (n) => !sortedNodeIds.includes(n.id)
    );

    const updated = nodes.map((node) => {
      const mainIdx = sortedNodeIds.indexOf(node.id);
      if (mainIdx !== -1) {
        return {
          ...node,
          position: { x: 400, y: mainIdx * 140 },
        };
      }
      const branchIdx = branchNodes.indexOf(node);
      if (node.id === "follow-up") {
        return { ...node, position: { x: 700, y: 420 } };
      }
      if (node.id === "escalation") {
        return { ...node, position: { x: 100, y: 420 } };
      }
      return {
        ...node,
        position: {
          x: 750,
          y: 140 + branchIdx * 140,
        },
      };
    });

    setNodes(updated);
  }

  function updateSelectedNode(updates: Partial<StateNodeData>) {
    if (!selectedNode) return;
    setNodes((nds) =>
      nds.map((n) =>
        n.id === selectedNode.id
          ? { ...n, data: { ...n.data, ...updates } }
          : n
      )
    );
    setSelectedNode({
      ...selectedNode,
      data: { ...selectedNode.data, ...updates },
    });
  }

  function syncToParent() {
    onChange({ nodes, edges });
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">State Diagram</h2>
        <p className="text-sm text-muted-foreground">
          Define the sales lifecycle states and transitions your agent will
          follow.
        </p>
      </div>

      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={addState}>
          <PlusIcon className="size-3.5" />
          Add State
        </Button>
        <Button variant="outline" size="sm" onClick={autoLayout}>
          <LayoutIcon className="size-3.5" />
          Auto-layout
        </Button>
        <div className="flex-1" />
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="size-2.5 rounded-full bg-primary" /> Start
          </span>
          <span className="flex items-center gap-1">
            <span className="size-2.5 rounded-full bg-chart-2" /> Normal
          </span>
          <span className="flex items-center gap-1">
            <span className="size-2.5 rounded-full bg-chart-3" /> Branch
          </span>
          <span className="flex items-center gap-1">
            <span className="size-2.5 rounded-full bg-destructive" /> Terminal
          </span>
        </div>
      </div>

      <div className="relative flex rounded-lg border bg-muted/20 overflow-hidden" style={{ height: 560 }}>
        <div className={`flex-1 transition-all ${panelOpen && selectedNode ? "mr-[320px]" : ""}`}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.3}
            maxZoom={1.5}
            onMoveEnd={() => syncToParent()}
            proOptions={{ hideAttribution: true }}
            className="bg-background"
          >
            <Background gap={20} size={1} />
            <Controls
              showInteractive={false}
              className="!rounded-lg !border !bg-card !shadow-sm [&>button]:!rounded-md [&>button]:!border-none [&>button]:!bg-transparent [&>button]:!text-muted-foreground [&>button:hover]:!bg-muted"
            />
          </ReactFlow>
        </div>

        {selectedNode && panelOpen && (
          <div className="absolute right-0 top-0 h-full w-[320px] border-l bg-card shadow-lg overflow-y-auto">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <h3 className="text-sm font-semibold">State Properties</h3>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon-xs"
                  onClick={() => setPanelOpen(false)}
                >
                  <MinimizeIcon className="size-3" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  onClick={() => setSelectedNode(null)}
                >
                  <XIcon className="size-3" />
                </Button>
              </div>
            </div>
            <div className="space-y-4 p-4">
              <div className="space-y-2">
                <Label className="text-xs">State Name</Label>
                <Input
                  value={selectedNode.data.label}
                  onChange={(e) =>
                    updateSelectedNode({ label: e.target.value })
                  }
                />
              </div>

              <div className="space-y-2">
                <Label className="text-xs">Description</Label>
                <Textarea
                  value={selectedNode.data.description}
                  onChange={(e) =>
                    updateSelectedNode({ description: e.target.value })
                  }
                  className="min-h-[80px]"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-xs">Max Turns</Label>
                <Input
                  type="number"
                  min={1}
                  max={50}
                  value={selectedNode.data.maxTurns}
                  onChange={(e) =>
                    updateSelectedNode({
                      maxTurns: parseInt(e.target.value, 10) || 1,
                    })
                  }
                />
                <p className="text-[11px] text-muted-foreground">
                  Maximum conversation turns before auto-transitioning.
                </p>
              </div>

              <div className="space-y-2">
                <Label className="text-xs">Node Type</Label>
                <div className="grid grid-cols-2 gap-2">
                  {(
                    ["start", "normal", "branch", "terminal"] as const
                  ).map((t) => (
                    <button
                      key={t}
                      onClick={() => updateSelectedNode({ nodeType: t })}
                      className={`flex items-center gap-2 rounded-md border px-3 py-2 text-xs capitalize transition-colors ${
                        selectedNode.data.nodeType === t
                          ? "border-primary bg-primary/10 font-medium"
                          : "hover:bg-muted"
                      }`}
                    >
                      <span
                        className={`size-2 rounded-full ${
                          t === "start"
                            ? "bg-primary"
                            : t === "terminal"
                            ? "bg-destructive"
                            : t === "branch"
                            ? "bg-chart-3"
                            : "bg-chart-2"
                        }`}
                      />
                      {t}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-xs">Connected Edges</Label>
                <div className="space-y-1">
                  {edges
                    .filter(
                      (e) =>
                        e.source === selectedNode.id ||
                        e.target === selectedNode.id
                    )
                    .map((edge) => (
                      <div
                        key={edge.id}
                        className="flex items-center gap-2 rounded-md border bg-muted/50 px-2.5 py-1.5 text-xs"
                      >
                        <span className="font-medium">
                          {edge.source === selectedNode.id ? "Out" : "In"}
                        </span>
                        <span className="text-muted-foreground">
                          {edge.source === selectedNode.id
                            ? `to ${
                                nodes.find((n) => n.id === edge.target)?.data
                                  .label || edge.target
                              }`
                            : `from ${
                                nodes.find((n) => n.id === edge.source)?.data
                                  .label || edge.source
                              }`}
                        </span>
                        {edge.label && (
                          <Badge variant="secondary" className="ml-auto text-[10px]">
                            {String(edge.label)}
                          </Badge>
                        )}
                      </div>
                    ))}
                  {edges.filter(
                    (e) =>
                      e.source === selectedNode.id ||
                      e.target === selectedNode.id
                  ).length === 0 && (
                    <p className="text-xs text-muted-foreground">
                      No connections yet. Drag from a handle to connect.
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {!panelOpen && selectedNode && (
          <Button
            variant="outline"
            size="icon-sm"
            className="absolute right-3 top-3 z-10"
            onClick={() => setPanelOpen(true)}
          >
            <MaximizeIcon className="size-3" />
          </Button>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        Click a state to edit its properties. Drag between handles to create
        transitions. Use the toolbar to add states or re-arrange the layout.
      </p>
    </div>
  );
}
