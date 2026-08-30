import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  computeEdgeSideAssignments,
  nextOutputSide,
  type CardSide,
} from "../utils/agentFlowConnectionGeometry";
import { AgentFlowConnectionLines } from "./AgentFlowConnectionLines";
import type { Agent, AgentFlowGraph, AgentFlowGraphNode } from "../types";
import {
  addEdge,
  incomingTargets,
  nodeKind,
  nodeLabel,
  outgoingTargets,
  repositionNode,
  removeEdge,
  removeNode,
  updateEdgeHandoff,
  updateNode,
} from "../utils/agentFlowGraph";
import {
  flowLinkColorIndex,
  flowLinkConnectionItemClass,
  flowLinkDotClass,
  flowLinkEdgeKey,
} from "../utils/agentFlowLinkColors";

type AgentFlowGraphCanvasProps = {
  graph: AgentFlowGraph;
  agentById: Map<string, Agent>;
  dragOverColumn: 0 | 1 | null;
  onGraphChange: (graph: AgentFlowGraph) => void;
  onDragOverColumn: (column: 0 | 1 | null) => void;
  onDropAgent: (agent: Agent, column: 0 | 1) => void;
  onDropTask?: (column: 0 | 1) => void;
};

type LinkPreview = {
  fromId: string;
  fromSide: CardSide;
  x: number;
  y: number;
};

type CardDropTarget = {
  nodeId: string;
  placement: "before" | "after";
};

function columnFromClientX(container: HTMLElement, clientX: number): 0 | 1 {
  const rect = container.getBoundingClientRect();
  return clientX < rect.left + rect.width / 2 ? 0 : 1;
}

function columnFromPointer(event: React.DragEvent<HTMLElement>): 0 | 1 {
  return columnFromClientX(event.currentTarget, event.clientX);
}

function pointerInContainer(container: HTMLElement, clientX: number, clientY: number) {
  const rect = container.getBoundingClientRect();
  return { x: clientX - rect.left, y: clientY - rect.top };
}

function nodeIdFromElement(element: Element | null): string | null {
  if (!element) return null;
  const card = element.closest("[data-flow-node-id]");
  return card?.getAttribute("data-flow-node-id") ?? null;
}

export function AgentFlowGraphCanvas({
  graph,
  agentById,
  dragOverColumn,
  onGraphChange,
  onDragOverColumn,
  onDropAgent,
  onDropTask,
}: AgentFlowGraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef<Map<string, HTMLLIElement>>(new Map());
  const [linkPreview, setLinkPreview] = useState<LinkPreview | null>(null);
  const [linkTargetId, setLinkTargetId] = useState<string | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);
  const linkingFromRef = useRef<string | null>(null);
  const linkingFromSideRef = useRef<CardSide>("right");
  const [cardDragId, setCardDragId] = useState<string | null>(null);
  const [cardDropTarget, setCardDropTarget] = useState<CardDropTarget | null>(null);
  const [cardDragColumn, setCardDragColumn] = useState<0 | 1 | null>(null);
  const cardDragRef = useRef<string | null>(null);
  const cardDropTargetRef = useRef<CardDropTarget | null>(null);
  const cardDragColumnRef = useRef<0 | 1 | null>(null);

  const nodeIndex = new Map(graph.nodes.map((node, index) => [node.id, index]));

  const setNodeRef = useCallback((nodeId: string) => {
    return (element: HTMLLIElement | null) => {
      if (element) nodeRefs.current.set(nodeId, element);
      else nodeRefs.current.delete(nodeId);
    };
  }, []);

  const startCardDrag = (nodeId: string, event: React.PointerEvent<HTMLElement>) => {
    if (linkingFromRef.current || cardDragRef.current) return;
    if ((event.target as HTMLElement).closest(".icon-btn, input, textarea, button")) return;
    event.preventDefault();
    event.stopPropagation();
    cardDragRef.current = nodeId;
    setCardDragId(nodeId);
    setCardDropTarget(null);
    cardDropTargetRef.current = null;
    const container = containerRef.current;
    if (container) {
      const column = columnFromClientX(container, event.clientX);
      setCardDragColumn(column);
      cardDragColumnRef.current = column;
    }
  };

  const finishCardDrag = useCallback(
    (clientX: number, _clientY: number) => {
      const nodeId = cardDragRef.current;
      cardDragRef.current = null;
      setCardDragId(null);
      const dropTarget = cardDropTargetRef.current;
      setCardDropTarget(null);
      cardDropTargetRef.current = null;
      setCardDragColumn(null);
      cardDragColumnRef.current = null;

      if (!nodeId) return;

      const container = containerRef.current;
      if (!container) return;

      const column = columnFromClientX(container, clientX);
      if (dropTarget && dropTarget.nodeId !== nodeId) {
        const targetNode = graph.nodes.find((node) => node.id === dropTarget.nodeId);
        onGraphChange(
          repositionNode(graph, nodeId, {
            column: targetNode?.column ?? column,
            targetId: dropTarget.nodeId,
            placement: dropTarget.placement,
          }),
        );
      } else {
        onGraphChange(repositionNode(graph, nodeId, { column, placement: "append" }));
      }
    },
    [graph, onGraphChange],
  );

  useEffect(() => {
    if (!cardDragId) return;

    const onPointerMove = (event: PointerEvent) => {
      const container = containerRef.current;
      if (!container || !cardDragRef.current) return;

      const column = columnFromClientX(container, event.clientX);
      setCardDragColumn(column);
      cardDragColumnRef.current = column;

      const hoveredEl = document.elementFromPoint(event.clientX, event.clientY);
      const cardEl = hoveredEl?.closest("[data-flow-node-id]");
      const hoveredId = cardEl?.getAttribute("data-flow-node-id") ?? null;

      if (hoveredId && hoveredId !== cardDragRef.current && cardEl) {
        const rect = cardEl.getBoundingClientRect();
        const placement: CardDropTarget["placement"] =
          event.clientY < rect.top + rect.height / 2 ? "before" : "after";
        const target = { nodeId: hoveredId, placement };
        setCardDropTarget(target);
        cardDropTargetRef.current = target;
      } else {
        setCardDropTarget(null);
        cardDropTargetRef.current = null;
      }
    };

    const onPointerUp = (event: PointerEvent) => {
      finishCardDrag(event.clientX, event.clientY);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [cardDragId, finishCardDrag]);

  const startLinkDrag = (fromId: string, fromSide: CardSide, event: React.PointerEvent<HTMLButtonElement>) => {
    if (cardDragRef.current) return;
    event.preventDefault();
    event.stopPropagation();
    linkingFromRef.current = fromId;
    linkingFromSideRef.current = fromSide;
    setLinkError(null);
    const container = containerRef.current;
    if (!container) return;
    const point = pointerInContainer(container, event.clientX, event.clientY);
    setLinkPreview({ fromId, fromSide, ...point });
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const finishLinkDrag = useCallback(
    (clientX: number, clientY: number) => {
      const fromId = linkingFromRef.current;
      linkingFromRef.current = null;
      setLinkPreview(null);
      setLinkTargetId(null);

      if (!fromId) return;

      const targetId = nodeIdFromElement(document.elementFromPoint(clientX, clientY));
      if (!targetId || targetId === fromId) return;

      const result = addEdge(graph, fromId, targetId);
      if (result.error) {
        setLinkError(result.error);
        return;
      }
      setLinkError(null);
      onGraphChange(result.graph);
    },
    [graph, onGraphChange],
  );

  useEffect(() => {
    if (!linkPreview) return;

    const onPointerMove = (event: PointerEvent) => {
      const container = containerRef.current;
      if (!container || !linkingFromRef.current) return;
      const point = pointerInContainer(container, event.clientX, event.clientY);
      setLinkPreview({ fromId: linkingFromRef.current, fromSide: linkingFromSideRef.current, ...point });
      const hovered = nodeIdFromElement(document.elementFromPoint(event.clientX, event.clientY));
      setLinkTargetId(hovered && hovered !== linkingFromRef.current ? hovered : null);
    };

    const onPointerUp = (event: PointerEvent) => {
      finishLinkDrag(event.clientX, event.clientY);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [linkPreview, finishLinkDrag]);

  const handleDragOver = (event: React.DragEvent<HTMLElement>) => {
    if (linkingFromRef.current || cardDragRef.current) return;
    event.preventDefault();
    onDragOverColumn(columnFromPointer(event));
  };

  const handleDrop = (event: React.DragEvent<HTMLElement>) => {
    if (linkingFromRef.current || cardDragRef.current) return;
    event.preventDefault();
    const column = columnFromPointer(event);
    onDragOverColumn(null);
    const agentId = event.dataTransfer.getData("application/x-agent-id");
    if (agentId) {
      const agent = agentById.get(agentId);
      if (agent) onDropAgent(agent, column);
      return;
    }
    if (event.dataTransfer.getData("application/x-flow-task") === "1") {
      onDropTask?.(column);
    }
  };

  const handleRemoveEdge = useCallback(
    (from: string, to: string) => {
      setLinkError(null);
      onGraphChange(removeEdge(graph, from, to));
    },
    [graph, onGraphChange],
  );

  const edgeColorIndexMap = useMemo(() => {
    const map = new Map<string, number>();
    graph.edges.forEach((edge, index) => {
      map.set(flowLinkEdgeKey(edge.from, edge.to), flowLinkColorIndex(index));
    });
    return map;
  }, [graph.edges]);

  const containerRect = containerRef.current?.getBoundingClientRect();
  const edgeSideAssignments = containerRect
    ? computeEdgeSideAssignments(
        graph,
        (nodeId) => nodeRefs.current.get(nodeId)?.getBoundingClientRect() ?? null,
        containerRect,
      )
    : new Map();

  const renderNode = (node: AgentFlowGraphNode) => {
    const index = nodeIndex.get(node.id) ?? 0;
    const isTask = nodeKind(node) === "task";
    const agent = node.agent_id ? agentById.get(node.agent_id) : undefined;
    const label = isTask
      ? (node.title || "").trim() || "Custom step"
      : node.agent_name || agent?.name || "Unknown agent";
    const slug = isTask ? "" : node.agent_slug || agent?.slug || "";
    const outgoing = outgoingTargets(graph, node.id);
    const incoming = incomingTargets(graph, node.id);
    const column = node.column ?? 0;
    const isLinkTarget = linkTargetId === node.id;
    const isDragging = cardDragId === node.id;
    const dropBefore = cardDropTarget?.nodeId === node.id && cardDropTarget.placement === "before";
    const dropAfter = cardDropTarget?.nodeId === node.id && cardDropTarget.placement === "after";
    const newLinkSide = nextOutputSide(node.id, column, graph.edges, edgeSideAssignments);

    return (
      <li
        key={node.id}
        ref={setNodeRef(node.id)}
        data-flow-node-id={node.id}
        className={`agent-flow-step-card agent-flow-step-card--col-${column}${
          isTask ? " agent-flow-step-card--task" : ""
        }${
          isLinkTarget ? " agent-flow-step-card--link-target" : ""
        }${isDragging ? " agent-flow-step-card--dragging" : ""}${
          dropBefore ? " agent-flow-step-card--drop-before" : ""
        }${dropAfter ? " agent-flow-step-card--drop-after" : ""}`}
      >
        {newLinkSide != null && (
          <button
            type="button"
            className={`agent-flow-link-handle agent-flow-link-handle--out-${newLinkSide}`}
            aria-label={`Drag to connect from ${label}`}
            title="Drag to another step to connect"
            onPointerDown={(event) => startLinkDrag(node.id, newLinkSide, event)}
          />
        )}

        <div
          className="agent-flow-step-header agent-flow-step-header--draggable"
          onPointerDown={(event) => startCardDrag(node.id, event)}
          title="Drag to move"
        >
          <span className="agent-flow-step-index">{index + 1}</span>
          <div className="min-w-0 flex-1">
            {isTask ? (
              <>
                <span className="agent-flow-step-kind">Custom</span>
                <input
                  className="input agent-flow-step-title-input"
                  value={node.title ?? ""}
                  placeholder="Step name (e.g. Top 5)"
                  onPointerDown={(event) => event.stopPropagation()}
                  onChange={(e) => onGraphChange(updateNode(graph, node.id, { title: e.target.value }))}
                />
              </>
            ) : (
              <>
                <p className="font-medium">{label}</p>
                {slug && (
                  <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                    @{slug}
                  </p>
                )}
              </>
            )}
          </div>
          <button
            type="button"
            className="icon-btn"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => onGraphChange(removeNode(graph, node.id))}
            aria-label="Remove step"
            title="Remove"
          >
            ×
          </button>
        </div>

        {isTask && (
          <textarea
            className="input agent-flow-step-task-input mt-2 w-full resize-y text-xs"
            rows={3}
            value={node.instructions ?? ""}
            placeholder="What should this step do with the previous result? e.g. Pick the top 5 most expensive items and build an HTML table and chart."
            onPointerDown={(event) => event.stopPropagation()}
            onChange={(e) => onGraphChange(updateNode(graph, node.id, { instructions: e.target.value }))}
          />
        )}

        {(outgoing.length > 0 || incoming.length > 0) && (
          <div className="agent-flow-step-connections">
            {outgoing.length > 0 && (
              <>
                <p className="agent-flow-step-connections-label">Outgoing links</p>
                <ul className="agent-flow-step-connection-list">
                  {outgoing.map((edge) => {
                    const target = graph.nodes.find((candidate) => candidate.id === edge.to);
                    if (!target) return null;
                    const targetIndex = nodeIndex.get(target.id) ?? 0;
                    const colorIndex = edgeColorIndexMap.get(flowLinkEdgeKey(node.id, edge.to)) ?? 0;
                    return (
                      <li
                        key={edge.to}
                        className={`agent-flow-step-connection-item ${flowLinkConnectionItemClass(colorIndex)}`}
                      >
                        <div className="agent-flow-step-connection-row">
                          <span className="agent-flow-step-connection-label text-xs font-medium">
                            <span
                              className={`agent-flow-step-connection-dot ${flowLinkDotClass(colorIndex)}`}
                              aria-hidden
                            />
                            → {nodeLabel(target, targetIndex)}
                          </span>
                          <button
                            type="button"
                            className="agent-flow-link-remove btn-ghost btn-sm"
                            aria-label={`Remove link to ${nodeLabel(target, targetIndex)}`}
                            onClick={() => handleRemoveEdge(node.id, edge.to)}
                          >
                            Remove
                          </button>
                        </div>
                        <input
                          className="input mt-1 w-full text-xs"
                          value={edge.handoff ?? ""}
                          placeholder={`What should ${nodeLabel(target, targetIndex)} receive?`}
                          onChange={(e) =>
                            onGraphChange(updateEdgeHandoff(graph, node.id, edge.to, e.target.value))
                          }
                        />
                      </li>
                    );
                  })}
                </ul>
              </>
            )}
            {incoming.length > 0 && (
              <>
                <p className={`agent-flow-step-connections-label${outgoing.length > 0 ? " mt-3" : ""}`}>
                  Incoming links
                </p>
                <ul className="agent-flow-step-connection-list">
                  {incoming.map((edge) => {
                    const source = graph.nodes.find((candidate) => candidate.id === edge.from);
                    if (!source) return null;
                    const sourceIndex = nodeIndex.get(source.id) ?? 0;
                    const colorIndex = edgeColorIndexMap.get(flowLinkEdgeKey(edge.from, node.id)) ?? 0;
                    return (
                      <li
                        key={edge.from}
                        className={`agent-flow-step-connection-item ${flowLinkConnectionItemClass(colorIndex)}`}
                      >
                        <div className="agent-flow-step-connection-row">
                          <span className="agent-flow-step-connection-label text-xs font-medium">
                            <span
                              className={`agent-flow-step-connection-dot ${flowLinkDotClass(colorIndex)}`}
                              aria-hidden
                            />
                            ← {nodeLabel(source, sourceIndex)}
                          </span>
                          <button
                            type="button"
                            className="agent-flow-link-remove btn-ghost btn-sm"
                            aria-label={`Remove link from ${nodeLabel(source, sourceIndex)}`}
                            onClick={() => handleRemoveEdge(edge.from, node.id)}
                          >
                            Remove
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </>
            )}
          </div>
        )}
      </li>
    );
  };

  return (
    <div
      ref={containerRef}
      className={`agent-flow-steps-grid${
        dragOverColumn != null ? ` agent-flow-steps-grid--drag-over agent-flow-steps-grid--col-${dragOverColumn}` : ""
      }${cardDragColumn != null ? ` agent-flow-steps-grid--drag-over agent-flow-steps-grid--col-${cardDragColumn}` : ""}${
        linkPreview ? " agent-flow-steps-grid--linking" : ""
      }${cardDragId ? " agent-flow-steps-grid--moving" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={() => onDragOverColumn(null)}
      onDrop={handleDrop}
    >
      {graph.nodes.length > 0 && (
        <AgentFlowConnectionLines
          graph={graph}
          containerRef={containerRef}
          nodeRefs={nodeRefs}
          linkPreview={linkPreview}
          onRemoveEdge={handleRemoveEdge}
        />
      )}
      {graph.nodes.length === 0 ? (
        <p className="agent-flow-steps-grid-empty">
          Drop agents or a Custom step here — left half is column 1, right half is column 2
        </p>
      ) : (
        <>
          <p className="agent-flow-link-hint">
            Drag a card header to move it. Drag the{" "}
            <span className="agent-flow-link-hint-handle" aria-hidden /> to add a link. Colored dots mark
            connection points. Click a line or use <strong>Remove</strong> on a card to delete a link.
          </p>
          <ul className="agent-flow-steps-list">{graph.nodes.map(renderNode)}</ul>
        </>
      )}
      {linkError && <p className="agent-flow-link-error">{linkError}</p>}
    </div>
  );
}
