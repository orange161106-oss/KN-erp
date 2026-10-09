import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../auth/context';
import { canPerform } from '../../core/rbac';
import DataTable, { type ColumnDef } from '../../components/DataTable';
import Toolbar from '../../components/Toolbar';

export interface RequirementRecord {
  id: string;
  plant: string;
  process: string;
  consumable_code: string;
  description: string;
  unit: string;
  required_qty: string;
  stock_qty: string;
  shortage_qty: string;
  po_pending_qty: string;
  status: 'Normal' | 'Low' | 'Critical shortage' | string;
  remarks: string | null;
  msl: string;
  planning_period?: string;
  revision?: string;
}

export default function Requirements() {
  const { user } = useAuth();

  // RBAC checks
  const isAdmin = Boolean(user?.is_super_admin || user?.roles.includes('ADMIN'));
  const canRead = Boolean(isAdmin || user?.requirements_read || canPerform(user, 'requirements', 'read'));
  const canExport = Boolean(canRead || canPerform(user, 'requirements', 'export'));
  const canRecalculate = Boolean(isAdmin || user?.requirements_update || canPerform(user, 'requirements', 'update'));

  // Data state
  const [records, setRecords] = useState<RequirementRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Selection state
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set());
  const [selectedCell, setSelectedCell] = useState<{ rowId: string; colKey: keyof RequirementRecord & string } | null>(null);
  const [selectedAuditRow, setSelectedAuditRow] = useState<RequirementRecord | null>(null);

  // Filters state
  const [searchQuery, setSearchQuery] = useState('');
  const [plantFilter, setPlantFilter] = useState('');
  const [consumableFilter, setConsumableFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [versions, setVersions] = useState<Array<{ id: string; planning_period: string; revision_label: string; status: string }>>([]);
  const [selectedVersion, setSelectedVersion] = useState('');
  useEffect(() => {
    void apiClient.get<typeof versions>('/api/v1/prd/planning-versions').then(data => {
      setVersions(data); setSelectedVersion(data[0]?.id || '');
    }).catch(e => setStatusMessage({ type: 'error', text: e.message }));
  }, []);

  // Load records
  const loadRecords = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append('search', searchQuery);
      if (plantFilter) params.append('plant', plantFilter);
      if (consumableFilter) params.append('consumable', consumableFilter);
      if (statusFilter) params.append('status', statusFilter);
      const q = params.toString();
      const data = await apiClient.get<RequirementRecord[]>(`/api/v1/requirements/workspace/records${q ? `?${q}` : ''}`);

      setRecords(data);
      setSelectedRowIds(new Set());
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to fetch requirements data.',
      });
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, plantFilter, consumableFilter, statusFilter]);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  // Recalculate
  const handleRecalculate = async () => {
    setIsRecalculating(true);
    setStatusMessage(null);
    try {
      if (!selectedVersion) throw new Error('Import and validate a planning revision before calculation.');
      await apiClient.post('/api/v1/requirements/calculate', { planning_version_id: selectedVersion });
      await loadRecords();
      setSelectedRowIds(new Set());
      setStatusMessage({
        type: 'info',
        text: 'Calculation completed. Review configuration errors and results before Super Admin approval.',
      });
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Recalculation failed.',
      });
    } finally {
      setIsRecalculating(false);
    }
  };

  // Export Excel
  const handleExport = (mode: 'ALL' | 'FILTERED' | 'SELECTED') => {
    let url = '/api/v1/requirements/workspace/export';
    const params = new URLSearchParams();

    if (mode === 'SELECTED') {
      Array.from(selectedRowIds).forEach(id => params.append('record_ids', id));
    } else if (mode === 'FILTERED') {
      if (searchQuery) params.append('search', searchQuery);
      if (plantFilter) params.append('plant', plantFilter);
      if (consumableFilter) params.append('consumable', consumableFilter);
      if (statusFilter) params.append('status', statusFilter);
    }

    const queryString = params.toString();
    if (queryString) url += `?${queryString}`;
    window.open(url, '_blank');
  };

  // Filter options
  const uniquePlants = useMemo(() => {
    const set = new Set<string>();
    records.forEach(r => { if (r.plant) set.add(r.plant); });
    return Array.from(set).sort();
  }, [records]);

  const uniqueConsumables = useMemo(() => {
    const set = new Set<string>();
    records.forEach(r => { if (r.consumable_code) set.add(r.consumable_code); });
    return Array.from(set).sort();
  }, [records]);

  // Filtered records
  const filteredRecords = useMemo(() => {
    return records.filter(r => {
      if (plantFilter && r.plant !== plantFilter) return false;
      if (consumableFilter && r.consumable_code !== consumableFilter) return false;
      if (statusFilter && r.status !== statusFilter) return false;
      if (!searchQuery) return true;
      const q = searchQuery.toLowerCase();
      return (
        r.consumable_code.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        r.process.toLowerCase().includes(q) ||
        r.plant.toLowerCase().includes(q) ||
        (r.remarks && r.remarks.toLowerCase().includes(q))
      );
    });
  }, [records, plantFilter, consumableFilter, statusFilter, searchQuery]);

  // Summary counts
  const summary = useMemo(() => {
    let critical = 0;
    let low = 0;
    let normal = 0;
    records.forEach(r => {
      if (r.status === 'Critical shortage') critical++;
      else if (r.status === 'Low') low++;
      else normal++;
    });
    return { critical, low, normal, total: records.length };
  }, [records]);

  // Column definitions
  const columns: ColumnDef<RequirementRecord>[] = useMemo(
    () => [
      { key: 'planning_period', label: 'Period', width: 'w-28', align: 'left' },
      { key: 'revision', label: 'Revision', width: 'w-24', align: 'left' },
      {
        key: 'plant',
        label: 'Plant',
        width: 'w-24',
        align: 'left',
        isSticky: true,
      },
      {
        key: 'process',
        label: 'Process',
        width: 'w-28',
        align: 'left',
        isSticky: true,
      },
      {
        key: 'consumable_code',
        label: 'Consumable / Item ID',
        width: 'w-44',
        align: 'left',
        render: val => <span className="font-mono font-bold text-blue-900">{val}</span>,
      },
      {
        key: 'description',
        label: 'Description',
        width: 'w-64',
        align: 'left',
      },
      {
        key: 'unit',
        label: 'Unit',
        width: 'w-16',
        align: 'center',
      },
      {
        key: 'required_qty',
        label: 'Required Qty',
        width: 'w-28',
        align: 'right',
        render: val => <span className="font-mono font-bold text-gray-900">{val}</span>,
      },
      {
        key: 'stock_qty',
        label: 'Stock Qty',
        width: 'w-28',
        align: 'right',
        render: val => <span className="font-mono text-gray-800">{val}</span>,
      },
      {
        key: 'shortage_qty',
        label: 'Shortage Qty',
        width: 'w-28',
        align: 'right',
        render: val => {
          const num = parseFloat(val) || 0;
          return (
            <span
              className={`font-mono font-bold ${
                num > 0 ? 'text-red-600 bg-red-100/80 px-1.5 py-0.5 rounded' : 'text-gray-400'
              }`}
            >
              {val}
            </span>
          );
        },
      },
      {
        key: 'po_pending_qty',
        label: 'PO Pending Qty',
        width: 'w-28',
        align: 'right',
        render: val => <span className="font-mono text-gray-600">{val}</span>,
      },
      {
        key: 'status',
        label: 'Status',
        width: 'w-36',
        align: 'center',
        render: val => {
          if (val === 'Critical shortage') {
            return (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-800 border border-red-300 animate-pulse">
                CRITICAL SHORTAGE
              </span>
            );
          }
          if (val === 'Low') {
            return (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
                LOW STOCK
              </span>
            );
          }
          return (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
              NORMAL
            </span>
          );
        },
      },
      {
        key: 'remarks',
        label: 'Remarks',
        width: 'w-52',
        align: 'left',
      },
      {
        key: 'id' as any,
        label: 'Audit Trail',
        width: 'w-32',
        align: 'center',
        render: (_val, row) => (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setSelectedAuditRow(row);
            }}
            className="px-2 py-0.5 rounded text-2xs font-semibold bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-200 transition-colors shadow-2xs"
          >
            🔍 Audit Trail
          </button>
        ),
      },
    ],
    []
  );

  return (
    <div className="flex flex-col h-full space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 tracking-tight">Consumable Requirements Workspace</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Stored results from validated planning revisions and configured consumption rules. Review dated inventory projections separately.
          </p>
        </div>

        {/* Quick status summary cards */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-3 py-1 bg-white border border-gray-200 rounded text-xs shadow-2xs">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
            <span className="font-semibold text-red-700">{summary.critical}</span>
            <span className="text-gray-500">Critical</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1 bg-white border border-gray-200 rounded text-xs shadow-2xs">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
            <span className="font-semibold text-amber-700">{summary.low}</span>
            <span className="text-gray-500">Low</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1 bg-white border border-gray-200 rounded text-xs shadow-2xs">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
            <span className="font-semibold text-emerald-700">{summary.normal}</span>
            <span className="text-gray-500">Normal</span>
          </div>
        </div>
      </div>

      {statusMessage && (
        <div
          className={`px-3 py-2 rounded text-xs font-medium border flex items-center justify-between ${
            statusMessage.type === 'error'
              ? 'bg-red-50 text-red-800 border-red-200'
              : statusMessage.type === 'success'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : 'bg-blue-50 text-blue-800 border-blue-200'
          }`}
        >
          <div className="flex items-center gap-2">
            <span>{statusMessage.type === 'error' ? '⚠️' : '✓'}</span>
            <span>{statusMessage.text}</span>
          </div>
          <button onClick={() => setStatusMessage(null)} className="text-gray-400 hover:text-gray-600 font-bold">
            ×
          </button>
        </div>
      )}

      {/* Workspace Table Panel */}
      <div className="flex gap-3 items-center">
        <label>Planning revision <select value={selectedVersion} onChange={e => setSelectedVersion(e.target.value)}>
          <option value="">Select a validated planning revision</option>
          {versions.map(v => <option key={v.id} value={v.id}>{v.planning_period} · {v.revision_label} · {v.status}</option>)}
        </select></label>
        {user?.is_super_admin && <button disabled={!selectedVersion || isRecalculating} onClick={() => {
          void apiClient.post(`/api/v1/requirements/planning-versions/${selectedVersion}/approve`, {}).then(() => {
            setStatusMessage({ type: 'success', text: 'Calculated revision approved. No purchase order was created.' });
          }).catch(e => setStatusMessage({ type: 'error', text: e.message }));
        }}>Approve calculated revision</button>}
        <p className="text-xs">The table shows the latest revision for each period. Older revision evidence remains in planning history.</p>
      </div>
      <div className="flex-1 min-h-0 bg-white border border-gray-300 rounded shadow-xs flex flex-col overflow-hidden">
        {/* Toolbar */}
        <Toolbar
          canImport={false}
          canCreate={false}
          canUpdate={false}
          canDelete={false}
          canExport={canExport}
          onExport={handleExport}
          selectedCount={selectedRowIds.size}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          searchPlaceholder="🔍 Search item, description, process..."
          extraActions={
            canRecalculate ? (
              <button
                type="button"
                onClick={handleRecalculate}
                disabled={isRecalculating}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-white bg-brand-navy rounded shadow-xs hover:bg-opacity-90 active:bg-opacity-100 disabled:opacity-50 transition-colors"
              >
                {isRecalculating ? (
                  <>
                    <div className="animate-spin h-3 w-3 border-2 border-white border-t-transparent rounded-full" />
                    <span>Recalculating…</span>
                  </>
                ) : (
                  <>
                    <span>⚡</span>
                    <span>Recalculate</span>
                  </>
                )}
              </button>
            ) : null
          }
          filters={[
            {
              key: 'plant',
              label: 'Plant',
              value: plantFilter,
              onChange: setPlantFilter,
              options: [
                { value: '', label: 'All Plants' },
                ...uniquePlants.map(p => ({ value: p, label: p })),
              ],
            },
            {
              key: 'consumable',
              label: 'Consumable',
              value: consumableFilter,
              onChange: setConsumableFilter,
              options: [
                { value: '', label: 'All Consumables' },
                ...uniqueConsumables.map(c => ({ value: c, label: c })),
              ],
            },
            {
              key: 'status',
              label: 'Status',
              value: statusFilter,
              onChange: setStatusFilter,
              options: [
                { value: '', label: 'All Statuses' },
                { value: 'Critical shortage', label: 'Critical shortage' },
                { value: 'Low', label: 'Low Stock' },
                { value: 'Normal', label: 'Normal' },
              ],
            },
          ]}
        />

        {/* Data Grid */}
        <div className="flex-1 min-h-0">
          <DataTable
            columns={columns}
            data={filteredRecords}
            selectedIds={selectedRowIds}
            onSelectionChange={setSelectedRowIds}
            isLoading={isLoading}
            emptyMessage="No consumable requirements found. Click 'Recalculate' to compute from the latest PRD plan."
            canCreate={false}
            selectedCell={selectedCell}
            onSelectCell={setSelectedCell}
            getRowClassName={row => {
              if (row.status === 'Critical shortage') return 'bg-red-50/70 hover:bg-red-100/70 font-medium';
              if (row.status === 'Low') return 'bg-amber-50/60 hover:bg-amber-100/60';
              return '';
            }}
          />
        </div>
      </div>

      {/* Audit & Formula Explanation Modal */}
      {selectedAuditRow && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-lg shadow-xl border border-gray-200 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between bg-gray-50/70">
              <div>
                <h3 className="text-base font-bold text-gray-900">
                  Consumable Requirement Calculation Audit
                </h3>
                <p className="text-xs text-gray-500">
                  Deterministic KNL Formula Traceability & Net Available Supply Netting
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedAuditRow(null)}
                className="text-gray-400 hover:text-gray-600 font-bold text-lg p-1"
              >
                ✕
              </button>
            </div>

            <div className="p-6 space-y-5 text-xs text-gray-700">
              {/* Item Card */}
              <div className="p-4 bg-indigo-50/60 rounded-md border border-indigo-100 flex justify-between items-start">
                <div>
                  <span className="text-2xs font-bold uppercase tracking-wider text-indigo-700">
                    Consumable / Item ID
                  </span>
                  <div className="text-base font-bold text-indigo-950 mt-0.5">
                    {selectedAuditRow.consumable_code}
                  </div>
                  <div className="text-xs text-gray-600 mt-0.5">{selectedAuditRow.description}</div>
                </div>
                <div className="text-right space-y-1">
                  <div className="text-xs font-semibold text-gray-800">
                    Plant: <span className="font-bold text-indigo-900">{selectedAuditRow.plant}</span>
                  </div>
                  <div className="text-xs text-gray-600">
                    Process: <span className="font-semibold text-gray-800">{selectedAuditRow.process}</span>
                  </div>
                  <div className="text-2xs text-gray-500">
                    Unit: <span className="font-bold">{selectedAuditRow.unit}</span>
                  </div>
                </div>
              </div>

              {/* Numerical Metrics Matrix */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div className="p-3 bg-gray-50 border border-gray-200 rounded">
                  <div className="text-2xs font-semibold text-gray-500 uppercase">1. Gross Requirement</div>
                  <div className="text-base font-bold text-gray-900 mt-1">
                    {selectedAuditRow.required_qty} <span className="text-2xs font-normal text-gray-500">{selectedAuditRow.unit}</span>
                  </div>
                  <div className="text-3xs text-gray-400 mt-0.5">PRD Plan Qty × Consumption Norm</div>
                </div>

                <div className="p-3 bg-gray-50 border border-gray-200 rounded">
                  <div className="text-2xs font-semibold text-gray-500 uppercase">2. Current Stock</div>
                  <div className="text-base font-bold text-gray-900 mt-1">
                    {selectedAuditRow.stock_qty} <span className="text-2xs font-normal text-gray-500">{selectedAuditRow.unit}</span>
                  </div>
                  <div className="text-3xs text-gray-400 mt-0.5">Physical closing stock on hand</div>
                </div>

                <div className="p-3 bg-gray-50 border border-gray-200 rounded">
                  <div className="text-2xs font-semibold text-gray-500 uppercase">3. Confirmed Incoming PO</div>
                  <div className="text-base font-bold text-blue-700 mt-1">
                    {selectedAuditRow.po_pending_qty} <span className="text-2xs font-normal text-gray-500">{selectedAuditRow.unit}</span>
                  </div>
                  <div className="text-3xs text-gray-400 mt-0.5">On order (not yet received)</div>
                </div>

                <div className="p-3 bg-blue-50/70 border border-blue-200 rounded">
                  <div className="text-2xs font-semibold text-blue-800 uppercase">4. Available Supply</div>
                  <div className="text-base font-bold text-blue-900 mt-1">
                    {(parseFloat(selectedAuditRow.stock_qty) + parseFloat(selectedAuditRow.po_pending_qty)).toFixed(4)}{' '}
                    <span className="text-2xs font-normal text-gray-500">{selectedAuditRow.unit}</span>
                  </div>
                  <div className="text-3xs text-blue-600 mt-0.5">Current Stock + Confirmed PO</div>
                </div>

                <div className="p-3 bg-amber-50/70 border border-amber-200 rounded">
                  <div className="text-2xs font-semibold text-amber-800 uppercase">5. Min Stock Level (MSL)</div>
                  <div className="text-base font-bold text-amber-900 mt-1">
                    {selectedAuditRow.msl} <span className="text-2xs font-normal text-gray-500">{selectedAuditRow.unit}</span>
                  </div>
                  <div className="text-3xs text-amber-600 mt-0.5">Safety cover per stock policy</div>
                </div>

                <div className={`p-3 border rounded ${
                  selectedAuditRow.status === 'Critical shortage'
                    ? 'bg-red-50/80 border-red-200'
                    : selectedAuditRow.status === 'Low'
                    ? 'bg-amber-50/80 border-amber-200'
                    : 'bg-emerald-50/80 border-emerald-200'
                }`}>
                  <div className="text-2xs font-semibold uppercase">6. Net Shortage</div>
                  <div className={`text-base font-bold mt-1 ${
                    selectedAuditRow.status === 'Critical shortage'
                      ? 'text-red-700'
                      : selectedAuditRow.status === 'Low'
                      ? 'text-amber-700'
                      : 'text-emerald-700'
                  }`}>
                    {selectedAuditRow.shortage_qty} <span className="text-2xs font-normal text-gray-500">{selectedAuditRow.unit}</span>
                  </div>
                  <div className="text-3xs text-gray-500 mt-0.5">Status: {selectedAuditRow.status}</div>
                </div>
              </div>

              {/* Traceability Audit Trail */}
              <div className="border border-gray-200 rounded p-4 bg-gray-50 space-y-2.5">
                <div className="font-bold text-gray-800 uppercase tracking-wide text-2xs">
                  End-to-End Calculation Flow:
                </div>
                <div className="text-xs space-y-1 font-mono text-gray-600 bg-white p-3 rounded border border-gray-200">
                  <div>• PRD Plan Production Qty × Approved Consumption Norm = Gross Requirement ({selectedAuditRow.required_qty})</div>
                  <div>• Available Supply = Current Stock ({selectedAuditRow.stock_qty}) + Incoming PO ({selectedAuditRow.po_pending_qty})</div>
                  <div>• Net Purchase Need = max(0, Gross Requirement - Available Supply)</div>
                  <div>• Shortage Status: {selectedAuditRow.remarks || 'Sufficient stock on hand'}</div>
                </div>
              </div>
            </div>

            <div className="px-6 py-3 border-t border-gray-200 bg-gray-50 flex justify-end">
              <button
                type="button"
                onClick={() => setSelectedAuditRow(null)}
                className="px-4 py-1.5 bg-gray-200 hover:bg-gray-300 text-gray-800 rounded font-medium text-xs"
              >
                Close Audit View
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
