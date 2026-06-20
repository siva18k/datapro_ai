import type { AgentFlowGraph, AgentFlowGraphEdge } from "../types";

export type FlowPoint = { x: number; y: number };
export type CardSide = "right" | "left" | "top" | "bottom";

export const EDGE_PAD = 8;
/** Distance from the card edge before turning. */
export const ROUTE_LANE = 32;
/** Corner rounding radius for orthogonal link paths. */
export const CORNER_RADIUS = 8;
const SIDE_SPREAD = 20;

const SIDE_ORDER: CardSide[] = ["right", "bottom", "top", "left"];

export type EdgeSideAssignment = {
  fromSide: CardSide;
  toSide: CardSide;
  fromSlot: number;
  toSlot: number;
  fromSlotTotal: number;
  toSlotTotal: number;
};

type RelativeNode = ReturnType<typeof relativeRect>;

export function relativeRect(rect: DOMRect, container: DOMRect) {
  return {
    left: rect.left - container.left,
    top: rect.top - container.top,
    right: rect.right - container.left,
    bottom: rect.bottom - container.top,
    cx: rect.left + rect.width / 2 - container.left,
    cy: rect.top + rect.height / 2 - container.top,
  };
}

export function edgeKey(from: string, to: string): string {
  return `${from}::${to}`;
}

/** Side of `from` that best faces `to`. */
export function sideToward(from: RelativeNode, to: RelativeNode): CardSide {
  const dx = to.cx - from.cx;
  const dy = to.cy - from.cy;
  if (Math.abs(dx) > Math.abs(dy)) {
    return dx > 0 ? "right" : "left";
  }
  return dy > 0 ? "bottom" : "top";
}

export function defaultOutputSide(column: 0 | 1): CardSide {
  return column === 0 ? "right" : "left";
}

function sidesAfter(preferred: CardSide): CardSide[] {
  const start = SIDE_ORDER.indexOf(preferred);
  return [...SIDE_ORDER.slice(start + 1), ...SIDE_ORDER.slice(0, start + 1)];
}

/** Pick the preferred side, or the next free side on the card. */
export function pickFreeSide(preferred: CardSide, used: Set<CardSide>): CardSide {
  if (!used.has(preferred)) return preferred;
  for (const side of sidesAfter(preferred)) {
    if (!used.has(side)) return side;
  }
  return preferred;
}

function slotOffset(slot: number, total: number): number {
  if (total <= 1) return 0;
  return (slot - (total - 1) / 2) * SIDE_SPREAD;
}

export function anchorOnSide(
  node: RelativeNode,
  side: CardSide,
  slot = 0,
  slotTotal = 1,
): FlowPoint {
  const offset = slotOffset(slot, slotTotal);
  switch (side) {
    case "right":
      return { x: node.right + EDGE_PAD, y: node.cy + offset };
    case "left":
      return { x: node.left - EDGE_PAD, y: node.cy + offset };
    case "top":
      return { x: node.cx + offset, y: node.top - EDGE_PAD };
    case "bottom":
      return { x: node.cx + offset, y: node.bottom + EDGE_PAD };
  }
}

function outwardDelta(side: CardSide): FlowPoint {
  switch (side) {
    case "right":
      return { x: ROUTE_LANE, y: 0 };
    case "left":
      return { x: -ROUTE_LANE, y: 0 };
    case "top":
      return { x: 0, y: -ROUTE_LANE };
    case "bottom":
      return { x: 0, y: ROUTE_LANE };
  }
}

function isHorizontalSide(side: CardSide): boolean {
  return side === "left" || side === "right";
}

function dist(a: FlowPoint, b: FlowPoint): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

function pointToward(from: FlowPoint, to: FlowPoint, amount: number): FlowPoint {
  const length = dist(from, to);
  if (length <= amount) return { ...to };
  const t = amount / length;
  return {
    x: from.x + (to.x - from.x) * t,
    y: from.y + (to.y - from.y) * t,
  };
}

/** Drop points that sit on the same horizontal or vertical line as their neighbors. */
function simplifyWaypoints(points: FlowPoint[]): FlowPoint[] {
  if (points.length <= 2) return points;

  const simplified = [points[0]];
  for (let i = 1; i < points.length - 1; i += 1) {
    const prev = simplified[simplified.length - 1];
    const curr = points[i];
    const next = points[i + 1];
    const colinearH = Math.abs(prev.y - curr.y) < 0.5 && Math.abs(curr.y - next.y) < 0.5;
    const colinearV = Math.abs(prev.x - curr.x) < 0.5 && Math.abs(curr.x - next.x) < 0.5;
    if (!colinearH && !colinearV) simplified.push(curr);
  }
  simplified.push(points[points.length - 1]);
  return simplified;
}

/** Build an SVG path with slightly rounded orthogonal corners. */
export function roundedOrthogonalPath(points: FlowPoint[], radius = CORNER_RADIUS): string {
  const waypoints = simplifyWaypoints(points);
  if (waypoints.length < 2) return "";
  if (waypoints.length === 2) {
    const [a, b] = waypoints;
    return `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
  }

  let path = `M ${waypoints[0].x} ${waypoints[0].y}`;
  let cursor = waypoints[0];

  for (let i = 1; i < waypoints.length - 1; i += 1) {
    const corner = waypoints[i];
    const next = waypoints[i + 1];
    const r = Math.min(radius, dist(cursor, corner) / 2, dist(corner, next) / 2);

    if (r < 1) {
      path += ` L ${corner.x} ${corner.y}`;
      cursor = corner;
      continue;
    }

    const before = pointToward(corner, cursor, r);
    const after = pointToward(corner, next, r);
    path += ` L ${before.x} ${before.y}`;
    path += ` Q ${corner.x} ${corner.y} ${after.x} ${after.y}`;
    cursor = after;
  }

  const last = waypoints[waypoints.length - 1];
  path += ` L ${last.x} ${last.y}`;
  return path;
}

function connectionWaypoints(
  start: FlowPoint,
  end: FlowPoint,
  fromSide: CardSide,
  toSide: CardSide,
): FlowPoint[] {
  const outDelta = outwardDelta(fromSide);
  const inDelta = outwardDelta(toSide);
  const out = { x: start.x + outDelta.x, y: start.y + outDelta.y };
  const approach = { x: end.x + inDelta.x, y: end.y + inDelta.y };

  if (isHorizontalSide(fromSide) && isHorizontalSide(toSide)) {
    const midX = (out.x + approach.x) / 2;
    return [start, out, { x: midX, y: out.y }, { x: midX, y: approach.y }, end];
  }
  if (!isHorizontalSide(fromSide) && !isHorizontalSide(toSide)) {
    const midY = (out.y + approach.y) / 2;
    return [start, out, { x: out.x, y: midY }, { x: approach.x, y: midY }, end];
  }
  if (isHorizontalSide(fromSide)) {
    return [start, out, { x: approach.x, y: out.y }, end];
  }
  return [start, out, { x: out.x, y: approach.y }, end];
}

/** Orthogonal path between two side anchors. */
export function steppedConnectionPath(
  start: FlowPoint,
  end: FlowPoint,
  fromSide: CardSide,
  toSide: CardSide,
): string {
  return roundedOrthogonalPath(connectionWaypoints(start, end, fromSide, toSide));
}

export function previewConnectionPath(
  start: FlowPoint,
  end: FlowPoint,
  fromSide: CardSide,
): string {
  const outDelta = outwardDelta(fromSide);
  const out = { x: start.x + outDelta.x, y: start.y + outDelta.y };

  if (isHorizontalSide(fromSide)) {
    return roundedOrthogonalPath([start, out, { x: out.x, y: end.y }, end]);
  }
  return roundedOrthogonalPath([start, out, { x: end.x, y: out.y }, end]);
}

type SideUsage = Map<CardSide, number>;

function bumpSideUsage(usage: SideUsage, side: CardSide): { slot: number; total: number } {
  const slot = usage.get(side) ?? 0;
  usage.set(side, slot + 1);
  return { slot, total: slot + 1 };
}

function refreshSideTotals(assignments: Map<string, EdgeSideAssignment>, edges: AgentFlowGraphEdge[]) {
  const fromTotals = new Map<string, Map<CardSide, number>>();
  const toTotals = new Map<string, Map<CardSide, number>>();

  for (const edge of edges) {
    const key = edgeKey(edge.from, edge.to);
    const assignment = assignments.get(key);
    if (!assignment) continue;

    const fromMap = fromTotals.get(edge.from) ?? new Map<CardSide, number>();
    fromMap.set(assignment.fromSide, (fromMap.get(assignment.fromSide) ?? 0) + 1);
    fromTotals.set(edge.from, fromMap);

    const toMap = toTotals.get(edge.to) ?? new Map<CardSide, number>();
    toMap.set(assignment.toSide, (toMap.get(assignment.toSide) ?? 0) + 1);
    toTotals.set(edge.to, toMap);
  }

  for (const edge of edges) {
    const key = edgeKey(edge.from, edge.to);
    const assignment = assignments.get(key);
    if (!assignment) continue;

    assignment.fromSlotTotal = fromTotals.get(edge.from)?.get(assignment.fromSide) ?? 1;
    assignment.toSlotTotal = toTotals.get(edge.to)?.get(assignment.toSide) ?? 1;
  }
}

/** Assign a distinct card side per connection when possible. */
export function computeEdgeSideAssignments(
  graph: AgentFlowGraph,
  getNodeRect: (nodeId: string) => DOMRect | null,
  containerRect: DOMRect,
): Map<string, EdgeSideAssignment> {
  const assignments = new Map<string, EdgeSideAssignment>();
  const outgoingUsed = new Map<string, Set<CardSide>>();
  const incomingUsed = new Map<string, Set<CardSide>>();
  const outgoingSlots = new Map<string, SideUsage>();
  const incomingSlots = new Map<string, SideUsage>();

  for (const edge of graph.edges) {
    const fromRect = getNodeRect(edge.from);
    const toRect = getNodeRect(edge.to);
    if (!fromRect || !toRect) continue;

    const from = relativeRect(fromRect, containerRect);
    const to = relativeRect(toRect, containerRect);

    const preferredFrom = sideToward(from, to);
    const preferredTo = sideToward(to, from);

    const fromUsed = outgoingUsed.get(edge.from) ?? new Set<CardSide>();
    const toUsed = incomingUsed.get(edge.to) ?? new Set<CardSide>();

    const fromSide = pickFreeSide(preferredFrom, fromUsed);
    const toSide = pickFreeSide(preferredTo, toUsed);

    fromUsed.add(fromSide);
    toUsed.add(toSide);
    outgoingUsed.set(edge.from, fromUsed);
    incomingUsed.set(edge.to, toUsed);

    const fromSlotUsage = outgoingSlots.get(edge.from) ?? new Map<CardSide, number>();
    const toSlotUsage = incomingSlots.get(edge.to) ?? new Map<CardSide, number>();
    const fromSlotInfo = bumpSideUsage(fromSlotUsage, fromSide);
    const toSlotInfo = bumpSideUsage(toSlotUsage, toSide);
    outgoingSlots.set(edge.from, fromSlotUsage);
    incomingSlots.set(edge.to, toSlotUsage);

    assignments.set(edgeKey(edge.from, edge.to), {
      fromSide,
      toSide,
      fromSlot: fromSlotInfo.slot,
      toSlot: toSlotInfo.slot,
      fromSlotTotal: fromSlotInfo.total,
      toSlotTotal: toSlotInfo.total,
    });
  }

  refreshSideTotals(assignments, graph.edges);
  return assignments;
}

const NEW_CONNECTION_SIDES: Record<0 | 1, CardSide[]> = {
  0: ["right", "bottom"],
  1: ["left", "bottom"],
};

function preferredNewConnectionSides(column: 0 | 1, incomingSides: Set<CardSide>): CardSide[] {
  const base = NEW_CONNECTION_SIDES[column];
  // When links arrive from above, prefer routing new links downward.
  if (incomingSides.has("top")) {
    return column === 0 ? ["bottom", "right"] : ["bottom", "left"];
  }
  return base;
}

/** Side for the drag-to-connect handle — only sensible free output sides. */
export function nextOutputSide(
  nodeId: string,
  column: 0 | 1,
  edges: AgentFlowGraphEdge[],
  assignments: Map<string, EdgeSideAssignment>,
): CardSide | null {
  const used = new Set<CardSide>();
  const incomingSides = new Set<CardSide>();
  for (const edge of edges) {
    if (edge.from === nodeId) {
      const assignment = assignments.get(edgeKey(edge.from, edge.to));
      if (assignment) used.add(assignment.fromSide);
    }
    if (edge.to === nodeId) {
      const assignment = assignments.get(edgeKey(edge.from, edge.to));
      if (assignment) incomingSides.add(assignment.toSide);
    }
  }
  for (const side of preferredNewConnectionSides(column, incomingSides)) {
    if (!used.has(side)) return side;
  }
  return null;
}

export function connectionAnchorsForEdge(
  fromRect: DOMRect,
  toRect: DOMRect,
  containerRect: DOMRect,
  assignment: EdgeSideAssignment,
): { start: FlowPoint; end: FlowPoint } {
  const from = relativeRect(fromRect, containerRect);
  const to = relativeRect(toRect, containerRect);
  return {
    start: anchorOnSide(from, assignment.fromSide, assignment.fromSlot, assignment.fromSlotTotal),
    end: anchorOnSide(to, assignment.toSide, assignment.toSlot, assignment.toSlotTotal),
  };
}

export function outputAnchorOnSide(
  nodeRect: DOMRect,
  containerRect: DOMRect,
  side: CardSide,
): FlowPoint {
  const node = relativeRect(nodeRect, containerRect);
  return anchorOnSide(node, side);
}
