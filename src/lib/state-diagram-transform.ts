/**
 * Transformers between the React Flow shape used in the wizard UI and the
 * flat shape the backend `StateDiagramSave` / `StateDiagramResponse`
 * schemas expect (see `backend/app/schemas/state.py`).
 *
 * The wizard's editor stores rich React Flow nodes/edges with arbitrary
 * `data` objects and visual styling. The backend stores a normalized
 * State / Transition pair with first-class fields for the runtime
 * orchestrator (`name`, `instructions`, `is_initial`, `is_terminal`,
 * `condition`, `priority`). UI-only fields (max turns, node colour,
 * edge styling) are round-tripped through the `metadata` blob so a
 * load → edit → save cycle preserves them.
 *
 * `max_turns` is read by `prompt_builder._build_state_section` —
 * keep that key in sync if you rename it here.
 *
 * ---------------------------------------------------------------------------
 * TODO — outstanding state-diagram work (Phase 2+)
 * ---------------------------------------------------------------------------
 * Phase 1 (this commit) wires save/load round-tripping. The diagram now
 * persists, but the runtime state machine still doesn't actually move
 * because the wizard cannot author the fields the orchestrator reads.
 * Remaining work, in order:
 *
 * Phase 2 — make transitions actually fire
 *   - step-state-diagram.tsx: add edge selection + a side panel for editing
 *     `data.condition`, `data.description`, `data.priority` on the selected
 *     edge. Without `condition`, orchestrator.py:469 skips the transition
 *     entirely, so the state machine never moves. Update toBackend/fromBackend
 *     to read/write these fields (already plumbed in StateEdgeData).
 *   - step-state-diagram.tsx: add an `instructions` textarea on the node
 *     panel. prompt_builder._build_state_section injects this into the
 *     system prompt as a "### State Instructions" block — currently always
 *     empty because there's no editor.
 *   - backend/app/services/prompt_builder.py:339: flip the priority sort
 *     direction so it matches orchestrator.py:460 (lower = higher precedence).
 *     Today the system prompt lists transitions in the opposite order from
 *     the order they're evaluated in. Pick one convention.
 *
 * Phase 3 — UX cleanup
 *   - step-state-diagram.tsx: drop the hardcoded insurance-funnel
 *     INITIAL_NODES / INITIAL_EDGES (or extract behind a "Load template"
 *     button). New agents should start with a single empty start state.
 *   - step-state-diagram.tsx: sync to parent on every edit, not just on
 *     onMoveEnd — currently a label edit followed by Next loses the change
 *     unless the user pans the canvas first.
 *   - wizard-shell.tsx handleSave: client-side preflight before the
 *     Promise.all (exactly one start state, all edge endpoints exist) so
 *     validation errors don't land mid-batch after other resources have
 *     already been written.
 *   - wizard-shell.tsx isStepComplete(4): currently always returns true.
 *     Should require either zero nodes (stateless) or exactly one start.
 *
 * Phase 4 — cost / latency polish (optional)
 *   - backend/app/services/llm_client.py:23: EVAL_MODEL is currently
 *     Sonnet despite the comment claiming it's "lightweight". Switch to
 *     Haiku — each turn fires N evaluator calls (one per outgoing
 *     transition with a non-empty condition).
 */

import type { Edge, Node } from "@xyflow/react";

// ---------------------------------------------------------------------------
// Wizard-side types (shared with step-state-diagram.tsx)
// ---------------------------------------------------------------------------

export type StateNodeType = "start" | "normal" | "terminal" | "branch";

export interface StateNodeData {
  label: string;
  description: string;
  instructions: string;
  maxTurns: number;
  nodeType: StateNodeType;
  [key: string]: unknown;
}

export interface StateEdgeData {
  condition: string;
  description: string;
  priority: number;
  [key: string]: unknown;
}

export type WizardStateNode = Node<StateNodeData>;
export type WizardStateEdge = Edge<StateEdgeData>;

export interface WizardStateDiagram {
  nodes: WizardStateNode[];
  edges: WizardStateEdge[];
}

// ---------------------------------------------------------------------------
// Backend wire format (mirrors backend/app/schemas/state.py)
// ---------------------------------------------------------------------------

export interface BackendStateNode {
  id: string;
  name: string;
  description: string | null;
  instructions: string | null;
  is_initial: boolean;
  is_terminal: boolean;
  position_x: number | null;
  position_y: number | null;
  metadata: Record<string, unknown> | null;
}

export interface BackendTransitionEdge {
  id: string;
  from_state_id: string;
  to_state_id: string;
  condition: string | null;
  description: string | null;
  priority: number;
  metadata: Record<string, unknown> | null;
}

export interface BackendStateDiagram {
  nodes: BackendStateNode[];
  edges: BackendTransitionEdge[];
}

/**
 * Shape returned by GET /agents/{id}/states. Same as the save payload but
 * with server-assigned UUIDs and timestamps. The transformer treats both
 * shapes uniformly — only the fields it cares about are read.
 */
export interface BackendStateDiagramResponse {
  nodes: Array<
    BackendStateNode & {
      agent_id?: string;
      created_at?: string;
      updated_at?: string;
    }
  >;
  edges: Array<
    BackendTransitionEdge & {
      agent_id?: string;
      created_at?: string;
    }
  >;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DEFAULT_MAX_TURNS = 5;

function emptyToNull(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  const trimmed = value.trim();
  return trimmed.length === 0 ? null : trimmed;
}

function deriveNodeType(
  isInitial: boolean,
  isTerminal: boolean,
  metaNodeType: unknown,
): StateNodeType {
  if (isInitial) return "start";
  if (isTerminal) return "terminal";
  if (metaNodeType === "branch") return "branch";
  return "normal";
}

// ---------------------------------------------------------------------------
// toBackend — wizard form state → backend save payload
// ---------------------------------------------------------------------------

export function toBackend(diagram: WizardStateDiagram): BackendStateDiagram {
  const nodes: BackendStateNode[] = diagram.nodes.map((n) => {
    const data = n.data;
    const nodeType = data?.nodeType ?? "normal";
    return {
      id: n.id,
      name: data?.label?.trim() || "Untitled",
      description: emptyToNull(data?.description),
      instructions: emptyToNull(data?.instructions),
      is_initial: nodeType === "start",
      is_terminal: nodeType === "terminal",
      position_x: Math.round(n.position?.x ?? 0),
      position_y: Math.round(n.position?.y ?? 0),
      metadata: {
        max_turns:
          typeof data?.maxTurns === "number" ? data.maxTurns : DEFAULT_MAX_TURNS,
        node_type: nodeType,
      },
    };
  });

  const edges: BackendTransitionEdge[] = diagram.edges.map((e) => {
    const data = (e.data ?? {}) as Partial<StateEdgeData>;
    return {
      id: e.id,
      from_state_id: e.source,
      to_state_id: e.target,
      condition: emptyToNull(data.condition),
      description: emptyToNull(data.description),
      priority: typeof data.priority === "number" ? data.priority : 0,
      metadata: {
        // Preserve React Flow visual properties so a round-trip doesn't
        // strip the user's styling. These are opaque to the runtime.
        ui_label: e.label ?? null,
        ui_type: e.type ?? null,
        ui_style: (e.style as Record<string, unknown> | undefined) ?? null,
        ui_label_style:
          (e.labelStyle as Record<string, unknown> | undefined) ?? null,
        ui_label_bg_style:
          (e.labelBgStyle as Record<string, unknown> | undefined) ?? null,
        ui_marker_end:
          (e.markerEnd as Record<string, unknown> | undefined) ?? null,
      },
    };
  });

  return { nodes, edges };
}

// ---------------------------------------------------------------------------
// fromBackend — backend GET response → wizard form state
// ---------------------------------------------------------------------------

export function fromBackend(
  diagram: BackendStateDiagramResponse | BackendStateDiagram,
): WizardStateDiagram {
  const nodes: WizardStateNode[] = (diagram.nodes ?? []).map((n) => {
    const meta = (n.metadata ?? {}) as {
      max_turns?: unknown;
      node_type?: unknown;
    };
    const nodeType = deriveNodeType(n.is_initial, n.is_terminal, meta.node_type);
    const maxTurns =
      typeof meta.max_turns === "number" ? meta.max_turns : DEFAULT_MAX_TURNS;

    return {
      id: String(n.id),
      type: "stateNode",
      position: {
        x: n.position_x ?? 0,
        y: n.position_y ?? 0,
      },
      data: {
        label: n.name,
        description: n.description ?? "",
        instructions: n.instructions ?? "",
        maxTurns,
        nodeType,
      },
    };
  });

  const edges: WizardStateEdge[] = (diagram.edges ?? []).map((e) => {
    const meta = (e.metadata ?? {}) as {
      ui_label?: unknown;
      ui_type?: unknown;
      ui_style?: unknown;
      ui_label_style?: unknown;
      ui_label_bg_style?: unknown;
      ui_marker_end?: unknown;
    };

    return {
      id: String(e.id),
      source: String(e.from_state_id),
      target: String(e.to_state_id),
      // Fall back to the condition text as the visible label so loaded
      // diagrams aren't blank when the user never set a custom label.
      label:
        (typeof meta.ui_label === "string" ? meta.ui_label : null) ??
        e.condition ??
        undefined,
      type: typeof meta.ui_type === "string" ? meta.ui_type : "smoothstep",
      style:
        (meta.ui_style as WizardStateEdge["style"]) ?? { strokeWidth: 2 },
      labelStyle:
        (meta.ui_label_style as WizardStateEdge["labelStyle"]) ?? {
          fontSize: 10,
          fontWeight: 500,
        },
      labelBgStyle:
        (meta.ui_label_bg_style as WizardStateEdge["labelBgStyle"]) ?? {
          fillOpacity: 0.8,
        },
      markerEnd:
        (meta.ui_marker_end as WizardStateEdge["markerEnd"]) ?? undefined,
      data: {
        condition: e.condition ?? "",
        description: e.description ?? "",
        priority: e.priority ?? 0,
      },
    };
  });

  return { nodes, edges };
}
