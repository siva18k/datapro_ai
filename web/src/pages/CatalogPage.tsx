import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ApiConnectingPanel } from "../components/ApiConnectingPanel";
import { ApiOfflinePanel } from "../components/ApiOfflinePanel";
import { CatalogDomainsPanel } from "../components/CatalogDomainsPanel";
import { DomainMcpBindingsPanel } from "../components/DomainMcpBindingsPanel";
import { AddDatasetForm } from "../components/AddDatasetForm";
import { DatasetPanel } from "../components/DatasetPanel";
import { EditableName } from "../components/EditableName";
import { PageHeader } from "../components/PageHeader";
import { useApiPageState } from "../context/ApiConnectionContext";
import { useSetSidebarContent } from "../context/SidebarContext";
import { api } from "../api/client";
import { CONNECTOR_LABELS, type Dataset } from "../types";

export function CatalogPage() {
  const qc = useQueryClient();
  const { apiOnline, showConnecting, showOffline, connectingTitle } = useApiPageState();
  const [domainId, setDomainId] = useState<string | null>(null);
  const [openDatasetId, setOpenDatasetId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [newDomainName, setNewDomainName] = useState("");
  const [showAddDomain, setShowAddDomain] = useState(false);

  const { data: domains, isLoading: domainsLoading } = useQuery({
    queryKey: ["domains"],
    queryFn: api.listDomains,
    enabled: apiOnline,
  });

  const { data: stats } = useQuery({
    queryKey: ["stats"],
    queryFn: api.stats,
    enabled: apiOnline,
  });

  const activeDomainId = domainId ?? domains?.[0]?.id ?? null;
  const activeDomain = domains?.find((d) => d.id === activeDomainId);

  const { data: datasets, isLoading: datasetsLoading } = useQuery({
    queryKey: ["datasets", activeDomainId],
    queryFn: () => api.listDatasets(activeDomainId!),
    enabled: !!activeDomainId,
  });

  const [openInitialTab, setOpenInitialTab] = useState<"data" | "definition" | undefined>(undefined);

  const createDomain = useMutation({
    mutationFn: (name: string) => api.createDomain(name),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["domains"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      setDomainId(d.id);
      setShowAddDomain(false);
      setNewDomainName("");
    },
  });

  const updateDomainName = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => api.updateDomain(id, { name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["domains"] }),
  });

  const deleteDataset = useMutation({
    mutationFn: (id: string) => api.deleteDataset(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["datasets", activeDomainId] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      if (openDatasetId === id) setOpenDatasetId(null);
    },
  });

  const updateDatasetName = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => api.updateDataset(id, { name }),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      qc.invalidateQueries({ queryKey: ["rag", id] });
      qc.invalidateQueries({ queryKey: ["summary", id] });
    },
  });

  const createDatasetHandled = (datasetId: string) => {
    setOpenDatasetId(datasetId);
    setOpenInitialTab("data");
    setShowAdd(false);
    window.setTimeout(() => setOpenInitialTab(undefined), 0);
  };

  const selectDomain = (id: string) => {
    setDomainId(id);
    setOpenDatasetId(null);
  };

  const deleteDomain = useMutation({
    mutationFn: (id: string) => api.deleteDomain(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["domains"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      if (domainId === id || activeDomainId === id) {
        setDomainId(null);
        setOpenDatasetId(null);
      }
    },
    onError: (err) => {
      window.alert(String(err));
    },
  });

  const requestRemoveDomain = (domain: { id: string; name: string }) => {
    if (domain.id === activeDomainId && datasets?.length) {
      window.alert(
        `Delete all ${datasets.length} dataset(s) in «${domain.name}» before removing this domain.`,
      );
      return;
    }
    if (
      !window.confirm(
        `Remove domain «${domain.name}»? This cannot be undone. All datasets must be deleted first.`,
      )
    ) {
      return;
    }
    deleteDomain.mutate(domain.id);
  };

  const canRemoveActiveDomain = !datasetsLoading && (datasets?.length ?? 0) === 0;

  const domainsPanelProps = {
    domains,
    loading: domainsLoading,
    activeDomainId,
    onSelectDomain: selectDomain,
    showAddDomain,
    onShowAddDomain: setShowAddDomain,
    newDomainName,
    onNewDomainNameChange: setNewDomainName,
    onCreateDomain: () => createDomain.mutate(newDomainName.trim()),
    creating: createDomain.isPending,
    onDeleteDomain: requestRemoveDomain,
    deletingDomainId: deleteDomain.isPending ? deleteDomain.variables ?? null : null,
  };

  const sidebarPanel = useMemo(
    () => <CatalogDomainsPanel {...domainsPanelProps} />,
    [
      domains,
      domainsLoading,
      activeDomainId,
      showAddDomain,
      newDomainName,
      createDomain.isPending,
      deleteDomain.isPending,
      deleteDomain.variables,
      datasets?.length,
      datasetsLoading,
    ],
  );
  useSetSidebarContent(sidebarPanel);

  if (showConnecting) {
    return (
      <div>
        <PageHeader title="Data Catalog" description="Datasets by domain" />
        <ApiConnectingPanel title={connectingTitle} />
      </div>
    );
  }

  if (showOffline) {
    return (
      <div>
        <PageHeader
          title="Data Catalog"
          description="Datasets by domain"
        />
        <ApiOfflinePanel />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Data Catalog"
        description="Datasets by domain"
      >
        {stats && (
          <p className="text-sm text-zinc-500">
            <strong>{stats.domain_count}</strong> domains · <strong>{stats.dataset_count}</strong> datasets
          </p>
        )}
      </PageHeader>

      {/* Mobile: domains inline (desktop uses left sidebar) */}
      <div className="card mb-4 md:hidden">
        <CatalogDomainsPanel {...domainsPanelProps} />
      </div>

      {activeDomain ? (
        <div className="card catalog-domain-panel overflow-hidden">
          <div className="card-header">
            <div className="min-w-0 flex-1">
              <EditableName
                value={activeDomain.name}
                className="text-base font-semibold text-zinc-900"
                inputClassName="w-full max-w-sm text-base font-semibold"
                saving={updateDomainName.isPending}
                onSave={(name) => updateDomainName.mutate({ id: activeDomain.id, name })}
              />
              <p className="mt-1 text-sm text-zinc-500">
                {activeDomain.description || "Add a description in dataset settings"}
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={!canRemoveActiveDomain || deleteDomain.isPending}
                title={
                  canRemoveActiveDomain
                    ? "Remove this domain"
                    : "Delete all datasets in this domain before removing it"
                }
                onClick={() => requestRemoveDomain(activeDomain)}
              >
                {deleteDomain.isPending ? "Removing…" : "Remove domain"}
              </button>
              <button type="button" className="btn shrink-0" onClick={() => setShowAdd(!showAdd)}>
                + Add dataset
              </button>
            </div>
          </div>

          {deleteDomain.isError && activeDomainId === deleteDomain.variables && (
            <p className="alert-error mx-5 mt-3">{String(deleteDomain.error)}</p>
          )}

          <div className="catalog-domain-mcp-wrap">
            <DomainMcpBindingsPanel
              domainId={activeDomain.id}
              domainName={activeDomain.name}
              domainSlug={activeDomain.slug}
            />
          </div>

          {showAdd && activeDomainId && (
            <AddDatasetForm
              domainId={activeDomainId}
              onCreated={createDatasetHandled}
              onCancel={() => setShowAdd(false)}
            />
          )}

          <div className="catalog-domain-body">
            {datasetsLoading && <p className="px-5 py-4 text-sm text-zinc-500">Loading datasets…</p>}

            {!datasetsLoading && !datasets?.length && (
              <div className="px-5 py-10 text-center">
                <p className="text-sm text-zinc-500">No datasets in this domain yet.</p>
                <button type="button" className="btn btn-secondary mt-4" onClick={() => setShowAdd(true)}>
                  Add your first dataset
                </button>
              </div>
            )}

            {!!datasets?.length && (
              <div className="catalog-dataset-list">
                {datasets.map((ds) => (
                  <DatasetCard
                    key={ds.id}
                    dataset={ds}
                    open={openDatasetId === ds.id}
                    initialTab={openDatasetId === ds.id ? openInitialTab : undefined}
                    onToggle={() => {
                      if (openDatasetId === ds.id) {
                        setOpenDatasetId(null);
                        setOpenInitialTab(undefined);
                      } else {
                        setOpenDatasetId(ds.id);
                        setOpenInitialTab(undefined);
                      }
                    }}
                    onRename={(name) => updateDatasetName.mutate({ id: ds.id, name })}
                    renaming={updateDatasetName.isPending && updateDatasetName.variables?.id === ds.id}
                    onDelete={() => {
                      if (
                        !window.confirm(
                          `Delete dataset "${ds.name}"? This removes catalog metadata and ingested chunks for this dataset.`,
                        )
                      ) {
                        return;
                      }
                      deleteDataset.mutate(ds.id);
                    }}
                    deleting={deleteDataset.isPending && deleteDataset.variables === ds.id}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="card card-pad text-center text-sm text-zinc-500">Select or create a domain to get started.</div>
      )}
    </div>
  );
}

function DatasetCard({
  dataset,
  open,
  initialTab,
  onToggle,
  onRename,
  renaming,
  onDelete,
  deleting,
}: {
  dataset: Dataset;
  open: boolean;
  initialTab?: "data" | "definition";
  onToggle: () => void;
  onRename: (name: string) => void;
  renaming?: boolean;
  onDelete: () => void;
  deleting?: boolean;
}) {
  const { data: summary } = useQuery({
    queryKey: ["summary", dataset.id],
    queryFn: () => api.datasetSummary(dataset.id),
  });

  let meta = CONNECTOR_LABELS[dataset.connector] ?? dataset.connector;
  if (summary?.table_count != null) meta += ` · ${summary.table_count} tables`;
  else if (summary?.file_count != null) meta += ` · ${summary.file_count} files, ${summary.chunk_count ?? 0} chunks`;

  return (
    <div className={`catalog-dataset-card ${open ? "border-blue-400" : ""}`}>
      <div
        className="catalog-dataset-header flex cursor-pointer items-center gap-2 px-4 py-3"
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onToggle();
          }
        }}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        aria-label={`${open ? "Collapse" : "Expand"} dataset ${dataset.name}`}
      >
        <div className="min-w-0 flex-1">
          <div onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
            <EditableName
              value={dataset.name}
              className="font-medium text-zinc-900"
              inputClassName="w-full font-medium"
              saving={renaming}
              onSave={onRename}
            />
          </div>
          <p className="mt-0.5 truncate text-sm text-zinc-500">{meta}</p>
        </div>
        <span className="badge-muted badge shrink-0">{dataset.source_type}</span>
        <button
          type="button"
          className="btn-ghost btn-sm shrink-0 text-red-600 hover:bg-red-50"
          title="Delete dataset"
          disabled={deleting}
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
        >
          {deleting ? "…" : "Delete"}
        </button>
        <span className="shrink-0 px-2 text-zinc-400" aria-hidden="true">
          {open ? "▲" : "▼"}
        </span>
      </div>
      {open && (
        <div className="catalog-panel-divider">
          <DatasetPanel dataset={dataset} initialTab={initialTab} />
        </div>
      )}
    </div>
  );
}
