import { useEffect, useState } from "react";

function useStandaloneTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const stored = localStorage.getItem("datapro-theme");
    if (stored === "light" || stored === "dark") return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("datapro-theme", theme);
  }, [theme]);

  return { theme, toggle: () => setTheme((t) => (t === "dark" ? "light" : "dark")) };
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2
      className="about-section-heading"
      style={{ color: "var(--color-text)", borderBottom: "1px solid var(--color-border)" }}
    >
      {children}
    </h2>
  );
}

function FeatureCard({
  icon,
  title,
  tagline,
  example,
  outcome,
}: {
  icon: string;
  title: string;
  tagline: string;
  example: string;
  outcome: string;
}) {
  return (
    <article
      className="about-feature-card"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
      }}
    >
      <div className="about-feature-card-header">
        <span className="about-feature-icon" aria-hidden>
          {icon}
        </span>
        <div>
          <h3 style={{ color: "var(--color-text)" }}>{title}</h3>
          <p style={{ color: "var(--color-text-muted)" }}>{tagline}</p>
        </div>
      </div>
      <div
        className="about-example-block"
        style={{
          background: "var(--color-surface-subtle)",
          border: "1px solid var(--color-border-light)",
        }}
      >
        <p className="about-example-label" style={{ color: "var(--color-text-faint)" }}>
          Example
        </p>
        <p className="about-example-text" style={{ color: "var(--color-text)" }}>
          {example}
        </p>
      </div>
      <p className="about-outcome" style={{ color: "var(--color-text-muted)" }}>
        {outcome}
      </p>
    </article>
  );
}

function Pillar({
  icon,
  title,
  body,
}: {
  icon: string;
  title: string;
  body: string;
}) {
  return (
    <div
      className="about-pillar"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
      }}
    >
      <span className="about-pillar-icon" aria-hidden>
        {icon}
      </span>
      <h3 style={{ color: "var(--color-text)" }}>{title}</h3>
      <p style={{ color: "var(--color-text-muted)" }}>{body}</p>
    </div>
  );
}

export function AboutPage() {
  const { theme, toggle } = useStandaloneTheme();

  return (
    <div className="about-page" style={{ background: "var(--color-bg)", minHeight: "100vh", color: "var(--color-text)" }}>
      <div className="about-page-shell">
      <header
        style={{ background: "var(--color-surface)", borderBottom: "1px solid var(--color-border)" }}
        className="about-header sticky top-0 z-20"
      >
        <div className="flex items-center gap-3">
          <span className="app-brand-gradient font-bold text-xl">DATA</span>
          <span style={{ color: "var(--color-text-muted)" }} className="text-xl font-light">
            Pro
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={toggle}
            type="button"
            style={{ color: "var(--color-text-muted)", background: "var(--color-surface-subtle)" }}
            className="rounded-lg px-3 py-1.5 text-xs font-medium hover:opacity-80 transition-opacity"
          >
            {theme === "dark" ? "☀ Light" : "☾ Dark"}
          </button>
          <button
            onClick={() => window.close()}
            type="button"
            style={{ color: "var(--color-text-muted)" }}
            className="rounded-lg px-3 py-1.5 text-xs font-medium hover:opacity-70 transition-opacity"
          >
            ✕ Close
          </button>
        </div>
      </header>

      {/* Hero */}
      <section
        className="about-hero"
        style={{ background: "var(--color-surface)", borderBottom: "1px solid var(--color-border)" }}
      >
        <p className="about-eyebrow" style={{ color: "var(--color-primary-text)" }}>
          Your AI data analytics platform
        </p>
        <h1 className="about-hero-title">
          Turn your data into answers — with <span className="app-brand-gradient">your</span> AI and{" "}
          <span className="app-brand-gradient">your</span> infrastructure
        </h1>
        <p className="about-hero-sub" style={{ color: "var(--color-text-muted)" }}>
          DATA Pro helps teams build a private analytics experience on top of their own databases, documents, and tools.
          Bring your LLM API key, connect your vector store, catalog what your data means — then ask questions, build
          dashboards, and automate research with agents.
        </p>
        <div className="about-hero-tags">
          {["Your API key", "Your Postgres + vectors", "Your live data", "Your domain knowledge"].map((tag) => (
            <span
              key={tag}
              className="about-tag"
              style={{
                background: "var(--color-primary-soft)",
                color: "var(--color-primary-text)",
                border: "1px solid var(--color-border-light)",
              }}
            >
              {tag}
            </span>
          ))}
        </div>
      </section>

      <div className="about-content py-12">
        {/* Why DATA Pro */}
        <SectionHeading>Built for teams who want control</SectionHeading>
        <p className="about-lead" style={{ color: "var(--color-text-muted)" }}>
          Most analytics copilots lock you into their cloud, their models, and their data copy. DATA Pro is the opposite:
          you run the platform, you choose the AI provider, and your data stays where it already lives.
        </p>

        <div className="about-pillars">
          <Pillar
            icon="🔑"
            title="Your AI provider"
            body="Connect OpenAI, Claude, Gemini, Mistral, OpenRouter, or a local model. Your API keys stay in your environment — not ours."
          />
          <Pillar
            icon="🗄"
            title="Your vector database"
            body="Store embeddings and catalog knowledge in your own Postgres with pgvector. Re-ingest when definitions change; search stays under your control."
          />
          <Pillar
            icon="📊"
            title="Your source systems"
            body="Point domains at live warehouses, file stores, and document libraries. Answers come from real data and real policies — not a static demo dataset."
          />
          <Pillar
            icon="🔌"
            title="Your tools & workflows"
            body="Extend with MCP servers, custom agents, and multi-step flows. Wire email, KPI checks, and external APIs into repeatable analytics automation."
          />
        </div>

        {/* Simple journey */}
        <SectionHeading>From catalog to insight in three moves</SectionHeading>
        <ol className="about-steps">
          {[
            {
              title: "Catalog your world",
              body: "Group data into domains — Finance, HR, Operations — and describe what each dataset means in plain language. Upload policies and reports for document search.",
            },
            {
              title: "Ask and visualize",
              body: "Use Ask for conversational answers and Analytics for dashboards. The platform routes each question to the right domain and blends live queries with document context.",
            },
            {
              title: "Automate with agents",
              body: "Create agents for recurring checks and reports. Chain them in Agent Flows when one insight should trigger the next — parallel reviews, merged summaries, stakeholder emails.",
            },
          ].map((step, i) => (
            <li key={step.title} className="about-step">
              <span
                className="about-step-num"
                style={{ background: "var(--color-primary)", color: "#fff" }}
              >
                {i + 1}
              </span>
              <div>
                <h3 style={{ color: "var(--color-text)" }}>{step.title}</h3>
                <p style={{ color: "var(--color-text-muted)" }}>{step.body}</p>
              </div>
            </li>
          ))}
        </ol>

        {/* Feature examples */}
        <SectionHeading>See it in action</SectionHeading>
        <p className="about-lead" style={{ color: "var(--color-text-muted)" }}>
          Four ways teams use DATA Pro every day — each grounded in the catalog you configure.
        </p>

        <div className="about-features">
          <FeatureCard
            icon="💬"
            title="Ask"
            tagline="Natural-language Q&A across domains"
            example={`"How many enterprise accounts renewed in Q1, and what does our renewal policy say about grace periods?"`}
            outcome="Ask picks the Sales domain, queries live account data, pulls the relevant policy document, and returns a clear answer with sources — no SQL required from the user."
          />
          <FeatureCard
            icon="📈"
            title="Analytics"
            tagline="Dashboards from a single prompt"
            example={`"Show monthly revenue by region for the last six months, with a trend line and top-five accounts table."`}
            outcome="Analytics generates charts and summary widgets from your connected database, ready to refine in conversation or present fullscreen to stakeholders."
          />
          <FeatureCard
            icon="🤖"
            title="Agents"
            tagline="Repeatable research and reporting"
            example={`An agent named "Weekly Revenue Review" checks KPIs against targets, builds an HTML report with charts, and emails the finance lead every Monday.`}
            outcome="Agents combine instructions, domain scope, and optional tools so routine analysis runs the same way every time — like a dedicated analyst who never forgets the playbook."
          />
          <FeatureCard
            icon="🔀"
            title="Agent Flows"
            tagline="Multi-step automation with branching"
            example={`Step 1: KPI checker flags underperforming regions → Step 2 & 3 run in parallel (deep-dive analyst + policy reviewer) → Step 4 merges findings into one executive brief.`}
            outcome="Agent Flows connect agents in a visual graph. Pass context downstream, run steps in parallel, and deliver one coordinated outcome from several specialized agents."
          />
        </div>

        {/* Who it's for */}
        <SectionHeading>Who it's for</SectionHeading>
        <div
          className="about-audience"
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
          }}
        >
          <ul style={{ color: "var(--color-text-muted)" }}>
            <li>
              <strong style={{ color: "var(--color-text)" }}>Data & analytics teams</strong> who want self-serve Q&A without
              rebuilding a copilot from scratch
            </li>
            <li>
              <strong style={{ color: "var(--color-text)" }}>Platform engineers</strong> who need BYOK AI, private vector
              search, and MCP extensibility
            </li>
            <li>
              <strong style={{ color: "var(--color-text)" }}>Business operators</strong> who live in spreadsheets and
              policies and want trustworthy answers in plain English
            </li>
            <li>
              <strong style={{ color: "var(--color-text)" }}>Leaders</strong> who want automated weekly briefs, KPI
              monitoring, and audit-friendly reporting
            </li>
          </ul>
        </div>

        {/* CTA */}
        <section
          className="about-cta"
          style={{
            background: "var(--color-surface-subtle)",
            border: "1px solid var(--color-border)",
          }}
        >
          <h2 style={{ color: "var(--color-text)" }}>Start with your data. Scale with your stack.</h2>
          <p style={{ color: "var(--color-text-muted)" }}>
            Connect your catalog, add your API key, and ask your first question in minutes. DATA Pro grows with the domains,
            agents, and integrations you define — not a vendor roadmap.
          </p>
          <button
            type="button"
            onClick={() => window.close()}
            className="about-cta-btn"
            style={{
              background: "var(--color-primary)",
              color: "#fff",
            }}
          >
            Back to DATA Pro
          </button>
        </section>

        <footer className="about-footer" style={{ color: "var(--color-text-faint)", borderTop: "1px solid var(--color-border)" }}>
          <span className="app-brand-gradient font-bold">DATA Pro</span>
          <span> — Your AI data analytics platform</span>
        </footer>
      </div>
      </div>
    </div>
  );
}
