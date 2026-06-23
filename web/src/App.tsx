import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ApiConnectionProvider } from "./context/ApiConnectionContext";
import { SidebarProvider } from "./context/SidebarContext";
import { ThemeProvider } from "./context/ThemeContext";
import { AgentsPage } from "./pages/AgentsPage";
import { AgentFlowsPage } from "./pages/AgentFlowsPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { AboutPage } from "./pages/AboutPage";
import { AskDebugPage } from "./pages/AskDebugPage";
import { AskPage } from "./pages/AskPage";
import { CatalogPage } from "./pages/CatalogPage";
import { McpPage } from "./pages/McpPage";
import { RagPage } from "./pages/RagPage";
import { SettingsPage } from "./pages/SettingsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: false,
      refetchOnWindowFocus: (query) => query.state.status !== "error",
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ApiConnectionProvider>
      <ThemeProvider>
      <BrowserRouter>
        <SidebarProvider>
        <Routes>
          <Route path="ask/debug" element={<AskDebugPage />} />
          <Route path="about" element={<AboutPage />} />
          <Route element={<Layout />}>
            <Route index element={<CatalogPage />} />
            <Route path="ask" element={<AskPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="agents" element={<AgentsPage />} />
            <Route path="agent-flows" element={<AgentFlowsPage />} />
            <Route path="rag" element={<RagPage />} />
            <Route path="mcp" element={<McpPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
        </SidebarProvider>
      </BrowserRouter>
      </ThemeProvider>
      </ApiConnectionProvider>
    </QueryClientProvider>
  );
}
