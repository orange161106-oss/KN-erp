import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient, ApiError } from '../../api/client';
import DataTable, { type ColumnDef, type HeaderGroupDef } from '../../components/DataTable';
import Toolbar from '../../components/Toolbar';
import type { MonthlyPlanMetadata } from '../requirements/Requirements';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export interface PurchaseWorkspaceRecord {
  id: string;
  planning_period: string;
  planning_month: number;
  planning_year: number;
  plan_id: string | null;
  revision: string;
  consumable_id: string | null;
  consumable_code: string;
  consumable_name: string;
  supplier_id: string | null;
  supplier_code: string | null;
  supplier_name: string | null;
  unit: string;
  required_qty: string;
  stock_qty: string;
  po_pending_qty: string;
  shortage_qty: string;
  system_recommended_qty: string;
  approval_status: string | null;
  approval_id: string | null;
  status: string;
  remarks: string | null;
  source_row_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

interface PurchaseWorkspaceResponse {
  plan_metadata: MonthlyPlanMetadata;
  records: PurchaseWorkspaceRecord[];
}

function formatDisplayDate(dateStr?: string | null): string {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return date.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function statusClass(status: string): string {
  if (status === 'READY_FOR_APPROVAL') return 'bg-emerald-50 text-emerald-800 border-emerald-200';
  if (status === 'SUBMITTED') return 'bg-blue-50 text-blue-800 border-blue-200';
  if (status === 'NO_PURCHASE_REQUIRED') return 'bg-gray-50 text-gray-700 border-gray-200';
  return 'bg-amber-50 text-amber-800 border-amber-200';
}

export default function PurchaseWorkspace({ canCreate }: { canCreate: boolean }) {
  const [selectedMonth, setSelectedMonth] = useState(10);
  const [selectedYear, setSelectedYear] = useState(2026);
  const [records, setRecords] = useState<PurchaseWorkspaceRecord[]>([]);
  const [planMetadata, setPlanMetadata] = useState<MonthlyPlanMetadata | null>(null);
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set());
  const [selectedCell, setSelectedCell] = useState<{ rowId: string; colKey: keyof PurchaseWorkspaceRecord & string } | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  const loadWorkspace = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams({
        month: String(selectedMonth),
        year: String(selectedYear),
      });
      if (searchQuery) params.set('search', searchQuery);
      if (statusFilter) params.set('status', statusFilter);
      const data = await apiClient.get<PurchaseWorkspaceResponse>(`/api/v1/purchasing/workspace?${params}`);
      setRecords(data.records);
      setPlanMetadata(data.plan_metadata);
      setSelectedRowIds(new Set());
      setMessage(null);
    } catch (error) {
      setMessage({
        type: 'error',
        text: error instanceof ApiError ? error.message : 'Failed to load purchase workspace.',
      });
    } finally {
      setIsLoading(false);
    }
  }, [selectedMonth, selectedYear, searchQuery, statusFilter]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  const readySelectedIds = useMemo(
    () => Array.from(selectedRowIds).filter(id => records.find(row => row.id === id)?.status === 'READY_FOR_APPROVAL'),
    [records, selectedRowIds]
  );

  const submitSelected = async () => {
    if (!readySelectedIds.length) return;
    const reason = window.prompt('Reason for approval queue submission:', 'Submitted from monthly Purchase workspace.');
    if (reason === null) return;
    setIsSubmitting(true);
    setMessage(null);
    try {
      const res = await apiClient.post<{
        message: string;
        submitted_count: number;
        skipped_count: number;
        records: PurchaseWorkspaceRecord[];
        plan_metadata: MonthlyPlanMetadata;
      }>(`/api/v1/purchasing/workspace/submit?month=${selectedMonth}&year=${selectedYear}`, {
        record_ids: readySelectedIds,
        reason: reason.trim() || null,
      });
      setRecords(res.records);
      setPlanMetadata(res.plan_metadata);
      setSelectedRowIds(new Set());
      setMessage({ type: 'success', text: res.message });
    } catch (error) {
      setMessage({
        type: 'error',
        text: error instanceof ApiError ? error.message : 'Failed to submit recommendations.',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const exportRows = (mode: 'ALL' | 'FILTERED' | 'SELECTED') => {
    let url = `/api/v1/purchasing/workspace/export?month=${selectedMonth}&year=${selectedYear}`;
    const params = new URLSearchParams();
    if (mode === 'SELECTED') {
      Array.from(selectedRowIds).forEach(id => params.append('record_ids', id));
    } else if (mode === 'FILTERED') {
      if (searchQuery) params.set('search', searchQuery);
      if (statusFilter) params.set('status', statusFilter);
    }
    const q = params.toString();
    if (q) url += `&${q}`;
    window.open(url, '_blank');
  };

  const summary = useMemo(() => {
    const ready = records.filter(row => row.status === 'READY_FOR_APPROVAL').length;
    const submitted = records.filter(row => row.status === 'SUBMITTED').length;
    const blocked = records.filter(row => row.status.endsWith('REQUIRED')).length;
    return { ready, submitted, blocked, total: records.length };
  }, [records]);

  const headerGroups: HeaderGroupDef[] = [
    {
      label: 'CONSUMABLE',
      colSpan: 3,
      className: 'p-1 text-center font-bold text-white uppercase tracking-wider text-[11px] border-r border-ink-text/20 bg-brand-navy select-none',
    },
    {
      label: 'PURCHASE QUANTITY',
      colSpan: 5,
      className: 'p-1 text-center font-bold text-white uppercase tracking-wider text-[11px] border-r border-ink-text/20 bg-brand-steel select-none',
    },
    {
      label: 'APPROVAL STATUS',
      colSpan: 4,
      className: 'p-1 text-center font-bold text-white uppercase tracking-wider text-[11px] border-r border-ink-text/20 bg-brand-navy select-none',
    },
  ];

  const columns: ColumnDef<PurchaseWorkspaceRecord>[] = [
    {
      key: 'consumable_code',
      label: 'Consumable Item ID',
      width: 'w-40',
      isSticky: true,
      render: value => <span className="font-mono font-bold text-blue-900">{value}</span>,
    },
    {
      key: 'consumable_name',
      label: 'Consumable Name',
      width: 'w-56',
      isSticky: true,
      render: value => <span className="font-semibold text-gray-900 truncate block">{value}</span>,
    },
    { key: 'unit', label: 'Unit', width: 'w-16', align: 'center' },
    { key: 'required_qty', label: 'Requirement Qty', width: 'w-32', align: 'right' },
    { key: 'stock_qty', label: 'Stock Qty', width: 'w-28', align: 'right' },
    { key: 'po_pending_qty', label: 'PO Pending Qty', width: 'w-32', align: 'right' },
    {
      key: 'shortage_qty',
      label: 'Net Shortage',
      width: 'w-32',
      align: 'right',
      render: value => <span className="font-mono font-bold text-red-700">{value}</span>,
    },
    {
      key: 'system_recommended_qty',
      label: 'System Recommended Qty',
      width: 'w-40',
      align: 'right',
      render: value => <span className="font-mono font-bold text-indigo-950">{value}</span>,
    },
    { key: 'supplier_code', label: 'Supplier Code', width: 'w-32' },
    { key: 'supplier_name', label: 'Supplier Name', width: 'w-44' },
    {
      key: 'status',
      label: 'Workspace Status',
      width: 'w-44',
      align: 'center',
      render: value => (
        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${statusClass(String(value))}`}>
          {String(value).replaceAll('_', ' ')}
        </span>
      ),
    },
    {
      key: 'approval_status',
      label: 'Approval Queue',
      width: 'w-32',
      align: 'center',
      render: value => <span className="font-mono text-xs text-gray-700">{value || '-'}</span>,
    },
    { key: 'source_row_count', label: 'Requirement Rows', width: 'w-28', align: 'center' },
    { key: 'remarks', label: 'Remarks', width: 'w-64' },
  ];

  return (
    <div className="flex flex-col h-full space-y-3">
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-3 bg-white p-3 rounded border border-gray-200 shadow-2xs">
        <div>
          <h1 className="text-lg font-bold text-gray-900 tracking-tight">Purchase</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Monthly purchase recommendations from approved requirement shortages.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="px-2 py-1 bg-gray-50 border rounded">Revision: <strong>{planMetadata?.revision_label ?? 'R0'}</strong></span>
          <span className="px-2 py-1 bg-gray-50 border rounded">Records: <strong>{summary.total}</strong></span>
          <span className="px-2 py-1 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded">Ready: <strong>{summary.ready}</strong></span>
          <span className="px-2 py-1 bg-blue-50 border border-blue-200 text-blue-800 rounded">Submitted: <strong>{summary.submitted}</strong></span>
          <span className="px-2 py-1 bg-amber-50 border border-amber-200 text-amber-800 rounded">Blocked: <strong>{summary.blocked}</strong></span>
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded p-2 flex flex-wrap items-center justify-between gap-3 shadow-2xs">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs font-bold text-gray-700">
            Planning Month:
            <select
              aria-label="Planning Month"
              value={selectedMonth}
              onChange={e => setSelectedMonth(Number(e.target.value))}
              className="ml-2 px-2.5 py-1 text-xs border border-gray-300 rounded bg-white text-gray-800 font-medium"
            >
              {MONTH_NAMES.map((month, idx) => <option key={month} value={idx + 1}>{month}</option>)}
            </select>
          </label>
          <label className="text-xs font-bold text-gray-700">
            Planning Year:
            <select
              aria-label="Planning Year"
              value={selectedYear}
              onChange={e => setSelectedYear(Number(e.target.value))}
              className="ml-2 px-2.5 py-1 text-xs border border-gray-300 rounded bg-white text-gray-800 font-medium"
            >
              {[2024, 2025, 2026, 2027, 2028, 2029, 2030].map(year => <option key={year}>{year}</option>)}
            </select>
          </label>
          <button
            type="button"
            onClick={() => void loadWorkspace()}
            disabled={isLoading}
            className="px-3 py-1 bg-gray-100 hover:bg-gray-200 text-gray-800 border border-gray-300 rounded font-semibold text-xs"
          >
            Load Purchase Plan
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canCreate && (
            <button
              type="button"
              onClick={() => void submitSelected()}
              disabled={isSubmitting || readySelectedIds.length === 0}
              className="px-3 py-1 bg-brand-navy hover:bg-opacity-90 disabled:opacity-50 text-white rounded font-semibold text-xs shadow-2xs"
            >
              {isSubmitting ? 'Submitting...' : `Submit to Approval${readySelectedIds.length ? ` (${readySelectedIds.length})` : ''}`}
            </button>
          )}
          <button
            type="button"
            onClick={() => exportRows(selectedRowIds.size ? 'SELECTED' : 'ALL')}
            className="px-3 py-1 bg-white hover:bg-gray-50 border border-gray-300 text-gray-800 rounded font-semibold text-xs shadow-2xs"
          >
            Export Excel
          </button>
          <button
            type="button"
            onClick={() => exportRows('FILTERED')}
            className="px-3 py-1 bg-white hover:bg-gray-50 border border-gray-300 text-gray-800 rounded font-semibold text-xs shadow-2xs"
          >
            Export Filtered
          </button>
        </div>
      </div>

      {planMetadata && (
        <div className="px-3 py-2 bg-white border border-gray-200 rounded text-xs text-gray-600">
          Plan {planMetadata.has_plan ? 'loaded' : 'not found'} for {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
          {' '}| Created: {formatDisplayDate(planMetadata.created_at)}
          {' '}| Updated: {formatDisplayDate(planMetadata.updated_at)}
          {planMetadata.source_filename ? ` | Source: ${planMetadata.source_filename}` : ''}
        </div>
      )}

      {message && (
        <div className={`px-3 py-2 rounded text-xs font-medium border ${
          message.type === 'error' ? 'bg-red-50 text-red-800 border-red-200'
            : message.type === 'success' ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
            : 'bg-blue-50 text-blue-800 border-blue-200'
        }`}>
          {message.text}
        </div>
      )}

      <div className="flex-1 min-h-0 bg-white border border-gray-300 rounded shadow-xs flex flex-col overflow-hidden">
        <Toolbar
          canImport={false}
          canCreate={false}
          canUpdate={false}
          canDelete={false}
          canExport={false}
          selectedCount={selectedRowIds.size}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          searchPlaceholder="Search consumable or supplier..."
          filters={[
            {
              key: 'status',
              label: 'Status',
              value: statusFilter,
              onChange: setStatusFilter,
              options: [
                { value: '', label: 'All Statuses' },
                { value: 'READY_FOR_APPROVAL', label: 'Ready for Approval' },
                { value: 'SUBMITTED', label: 'Submitted' },
                { value: 'SUPPLIER_REQUIRED', label: 'Supplier Required' },
                { value: 'MASTER_REQUIRED', label: 'Master Required' },
                { value: 'NO_PURCHASE_REQUIRED', label: 'No Purchase Required' },
              ],
            },
          ]}
        />
        <div className="flex-1 min-h-0">
          <DataTable
            columns={columns}
            headerGroups={headerGroups}
            data={records}
            selectedIds={selectedRowIds}
            onSelectionChange={setSelectedRowIds}
            selectedCell={selectedCell}
            onSelectCell={setSelectedCell}
            isLoading={isLoading}
            canCreate={false}
            emptyMessage={`No purchase recommendations found for ${MONTH_NAMES[selectedMonth - 1]} ${selectedYear}. Recalculate or import requirements first.`}
            getRowClassName={row => {
              if (row.status === 'READY_FOR_APPROVAL') return 'bg-emerald-50/60 hover:bg-emerald-100/60';
              if (row.status.endsWith('REQUIRED')) return 'bg-amber-50/60 hover:bg-amber-100/60';
              return '';
            }}
          />
        </div>
      </div>
    </div>
  );
}
