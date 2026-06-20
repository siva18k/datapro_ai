import { useCallback, useId, useLayoutEffect, useRef, useState } from "react";
import type { AgentFlowGraph } from "../types";
import {
  computeEdgeSideAssignments,
  connectionAnchorsForEdge,
  outputAnchorOnSide,
  previewConnectionPath,
  steppedConnectionPath,
  type CardSide,
  type FlowPoint,
} from "../utils/agentFlowConnectionGeometry";
import { flowLinkColorClass, flowLinkColorIndex } from "../utils/agentFlowLinkColors";

type EdgePath = {
  from: string;
  to: string;
  d: string;
  start: FlowPoint;
  end: FlowPoint;
  colorIndex: number;
  preview?: boolean;
};

type LinkPreview = {
  fromId: string;
  fromSide: CardSide;
  x: number;
  y: number;
};

type AgentFlowConnectionLinesProps = {
  graph: AgentFlowGraph;
  containerRef: React.RefObject<HTMLDivElement | null>;
  nodeRefs: React.RefObject<Map<string, HTMLLIElement>>;
  linkPreview?: LinkPreview | null;
  onRemoveEdge?: (from: string, to: string) => void;
};

export function AgentFlowConnectionLines({
  graph,
  containerRef,
  nodeRefs,
  linkPreview,
  onRemoveEdge,
}: AgentFlowConnectionLinesProps) {
  const markerId = useId().replace(/:/g, "");
  const [paths, setPaths] = useState<EdgePath[]>([]);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [hoveredEdge, setHoveredEdge] = useState<{ from: string; to: string } | null>(null);
  const observerRef = useRef<ResizeObserver | null>(null);

  const remeasure = useCallback(() => {
    const container = containerRef.current;
    if (!container) {
      setPaths([]);
      return;
    }

    const containerRect = container.getBoundingClientRect();
    const getNodeRect = (nodeId: string) => nodeRefs.current?.get(nodeId)?.getBoundingClientRect() ?? null;
    const sideAssignments = computeEdgeSideAssignments(graph, getNodeRect, containerRect);
    const nextPaths: EdgePath[] = [];

    for (let edgeIndex = 0; edgeIndex < graph.edges.length; edgeIndex += 1) {
      const edge = graph.edges[edgeIndex];
      const fromEl = nodeRefs.current?.get(edge.from);
      const toEl = nodeRefs.current?.get(edge.to);
      if (!fromEl || !toEl) continue;

      const assignment = sideAssignments.get(`${edge.from}::${edge.to}`);
      if (!assignment) continue;

      const anchors = connectionAnchorsForEdge(
        fromEl.getBoundingClientRect(),
        toEl.getBoundingClientRect(),
        containerRect,
        assignment,
      );
      nextPaths.push({
        from: edge.from,
        to: edge.to,
        colorIndex: flowLinkColorIndex(edgeIndex),
        start: anchors.start,
        end: anchors.end,
        d: steppedConnectionPath(anchors.start, anchors.end, assignment.fromSide, assignment.toSide),
      });
    }

    if (linkPreview) {
      const fromEl = nodeRefs.current?.get(linkPreview.fromId);
      if (fromEl) {
        const start = outputAnchorOnSide(
          fromEl.getBoundingClientRect(),
          containerRect,
          linkPreview.fromSide,
        );
        const end: FlowPoint = { x: linkPreview.x, y: linkPreview.y };
        nextPaths.push({
          from: linkPreview.fromId,
          to: "__preview__",
          colorIndex: 0,
          start,
          end,
          d: previewConnectionPath(start, end, linkPreview.fromSide),
          preview: true,
        });
      }
    }

    setDimensions({
      width: container.clientWidth,
      height: container.clientHeight,
    });
    setPaths(nextPaths);
  }, [containerRef, graph.edges, graph.nodes, linkPreview, nodeRefs]);

  useLayoutEffect(() => {
    let observer: ResizeObserver | null = null;

    const attach = () => {
      remeasure();
      observer?.disconnect();
      observer = new ResizeObserver(() => remeasure());
      observerRef.current = observer;

      const container = containerRef.current;
      if (container) observer.observe(container);
      nodeRefs.current?.forEach((node) => observer?.observe(node));
    };

    attach();
    const frame = requestAnimationFrame(attach);

    window.addEventListener("resize", remeasure);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener("resize", remeasure);
    };
  }, [containerRef, graph.nodes, graph.edges, linkPreview, nodeRefs, remeasure]);

  if (paths.length === 0 || dimensions.width === 0) return null;

  return (
    <svg
      className="agent-flow-connection-lines"
      width={dimensions.width}
      height={dimensions.height}
      viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
      aria-hidden={!onRemoveEdge}
    >
      <defs>
        <marker
          id={`agent-flow-arrow-${markerId}`}
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" className="agent-flow-connection-arrowhead" />
        </marker>
      </defs>
      {paths.map((path) => {
        if (path.preview) {
          return (
            <g key="preview">
              <circle
                cx={path.start.x}
                cy={path.start.y}
                r={5}
                className="agent-flow-connection-anchor agent-flow-connection-path--preview"
              />
              <path
                d={path.d}
                className="agent-flow-connection-path agent-flow-connection-path--preview"
                fill="none"
              />
            </g>
          );
        }

        const isHovered = hoveredEdge?.from === path.from && hoveredEdge?.to === path.to;
        const colorClass = flowLinkColorClass(path.colorIndex);
        return (
          <g key={`${path.from}::${path.to}`}>
            <path
              d={path.d}
              className="agent-flow-connection-hit"
              fill="none"
              onMouseEnter={() => setHoveredEdge({ from: path.from, to: path.to })}
              onMouseLeave={() => setHoveredEdge(null)}
              onClick={() => onRemoveEdge?.(path.from, path.to)}
            />
            <circle
              cx={path.start.x}
              cy={path.start.y}
              r={5}
              className={`agent-flow-connection-anchor ${colorClass}${
                isHovered ? " agent-flow-connection-anchor--hover" : ""
              }`}
            />
            <circle
              cx={path.end.x}
              cy={path.end.y}
              r={5}
              className={`agent-flow-connection-anchor ${colorClass}${
                isHovered ? " agent-flow-connection-anchor--hover" : ""
              }`}
            />
            <path
              d={path.d}
              className={`agent-flow-connection-path ${colorClass}${
                isHovered ? " agent-flow-connection-path--hover" : ""
              }`}
              markerEnd={`url(#agent-flow-arrow-${markerId})`}
              fill="none"
              pointerEvents="none"
            />
          </g>
        );
      })}
    </svg>
  );
}
