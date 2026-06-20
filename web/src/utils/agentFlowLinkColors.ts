export const FLOW_LINK_COLOR_COUNT = 8;

export function flowLinkEdgeKey(from: string, to: string): string {
  return `${from}::${to}`;
}

/** One distinct palette slot per edge (by order in the graph). */
export function flowLinkColorIndex(edgeOrder: number): number {
  return edgeOrder % FLOW_LINK_COLOR_COUNT;
}

export function flowLinkColorClass(index: number): string {
  return `agent-flow-connection-path--c-${index % FLOW_LINK_COLOR_COUNT}`;
}

export function flowLinkConnectionItemClass(index: number): string {
  return `agent-flow-step-connection-item--c-${index % FLOW_LINK_COLOR_COUNT}`;
}

export function flowLinkDotClass(index: number): string {
  return `agent-flow-step-connection-dot--c-${index % FLOW_LINK_COLOR_COUNT}`;
}
