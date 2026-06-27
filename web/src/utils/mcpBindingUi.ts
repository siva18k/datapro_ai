export function bindingCapabilityName(item: { capability_name?: string; name: string }): string {
  return item.capability_name ?? item.name;
}

export function isLocalPromptBinding(item: { capability_name?: string; name: string; prompt_kind?: string }): boolean {
  if (item.prompt_kind === "local") return true;
  return bindingCapabilityName(item).startsWith("local:");
}
