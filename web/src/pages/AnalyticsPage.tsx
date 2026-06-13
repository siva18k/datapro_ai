import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { AnalyticsDashboard } from "../components/AnalyticsDashboard";
import { AnalyticsPanel } from "../components/AnalyticsPanel";
import { DomainScopePromptOptions } from "../components/DomainScopePromptOptions";
import { PageHeader } from "../components/PageHeader";
import { useSetSidebarContent } from "../context/SidebarContext";
import { api } from "../api/client";
import type { AnalyticsResponse } from "../types";

export function AnalyticsPage() {
  const [prompt, setPrompt] = useState("");
  const [selectedDomains, setSelectedDomains] = useState<string[]>([]);
  const [dashboard, setDashboard] = useState<AnalyticsResponse | null>(null);
  const [activityStatus, setActivityStatus] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const previewRef = useRef<HTMLDivElement>(null);

  const sidebarPanel = useMemo(
    () => (
      <AnalyticsPanel
        selectedDomains={selectedDomains}
        onSelectedDomainsChange={setSelectedDomains}
      />
    ),
    [selectedDomains],
  );
  useSetSidebarContent(sidebarPanel);

  useEffect(() => {
    const onChange = () => setIsFullscreen(document.fullscreenElement === previewRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggleFullscreen = async () => {
    const el = previewRef.current;
    if (!el) return;
    try {
      if (document.fullscreenElement === el) {
        await document.exitFullscreen();
      } else {
        await el.requestFullscreen();
      }
    } catch {
      /* browser may block without user gesture */
    }
  };

  const run = useMutation({
    mutationFn: (text: string) =>
      api.analyticsStream(
        {
          prompt: text,
          domain_overrides: selectedDomains.length ? selectedDomains : undefined,
        },
        (message) => setActivityStatus(message),
      ),
    onSettled: () => setActivityStatus(null),
    onSuccess: (res) => setDashboard(res),
  });

  const submit = () => {
    const text = prompt.trim();
    if (!text || run.isPending) return;
    setDashboard(null);
    run.mutate(text);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="analytics-page">
      <div className="shrink-0">
        <PageHeader
          title="Analytics"
          description="Dashboards from catalog data"
        />
      </div>

      <div className="card mb-4 shrink-0 md:hidden">
        <AnalyticsPanel
          selectedDomains={selectedDomains}
          onSelectedDomainsChange={setSelectedDomains}
        />
      </div>

      <div className="card analytics-shell mb-0 flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="analytics-prompt-bar shrink-0 border-b">
          <div className="analytics-prompt-row">
            <textarea
              className="ask-prompt analytics-prompt min-h-0 flex-1"
              rows={2}
              placeholder="Describe a dashboard… e.g. revenue by country"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={run.isPending}
            />
            <button type="button" className="btn shrink-0" disabled={run.isPending || !prompt.trim()} onClick={submit}>
              {run.isPending ? "Building…" : "Run"}
            </button>
            {dashboard && (
              <button
                type="button"
                className="btn btn-secondary shrink-0"
                disabled={run.isPending}
                onClick={() => setDashboard(null)}
              >
                Clear
              </button>
            )}
          </div>
          <div className="ask-composer-options">
            <DomainScopePromptOptions
              selectedSlugs={selectedDomains}
              onChange={setSelectedDomains}
            />
          </div>
          {run.isError && <p className="alert-error mt-2">{String(run.error)}</p>}
        </div>

        <div ref={previewRef} className="analytics-preview min-h-0 flex-1 overflow-y-auto">
          <AnalyticsDashboard
            data={dashboard}
            isRunning={run.isPending}
            activityStatus={activityStatus}
            isFullscreen={isFullscreen}
            onToggleFullscreen={dashboard ? toggleFullscreen : undefined}
          />
        </div>
      </div>
    </div>
  );
}
