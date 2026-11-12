import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { apiClient, ApiError } from '../../api/client';
import DataTable, { type ColumnDef } from '../../components/DataTable';
import Toolbar from '../../components/Toolbar';
import type { MonthlyPlanMetadata } from '../requirements/Requirements';
import { useAuth } from '../auth/context';
import { mdViewColumns, normalViewColumns } from './purchaseViews';

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
  master_unit?: string | null;
  requested_purchase_qty?: string | null;
  requested_purchase_unit?: string | null;
  purchase_notes?: string | null;
  draft_version?: number;
  required_qty: string;
  stock_qty: string | null;
  po_pending_qty: string | null;
  shortage_qty: string | null;
  system_recommended_qty: string | null;
  calculation_basis?: string | null;
  stock_period?: string | null;
  minimum_stock_level?: string | null;
  minimum_order_qty?: string | null;
  unit_rate?: string | null;
  purchase_value?: string | null;
  category?: string | null;
  type_of_material?: string | null;
  output_unit?: string | null;
  max_stock_level?: string | null;
  lead_time_days?: number | null;
  opening_qty?: string | null;
  opening_value?: string | null;
  receipt_qty?: string | null;
  receipt_value?: string | null;
  issue_qty?: string | null;
  closing_value?: string | null;
  md_sources: Array<{ part_number?: string | null; part_name?: string | null; production_order_part?: string | null;
    process_name?: string | null; part_thickness?: string | null; process_count?: number | null;
    production_qty?: string | null; required_qty?: string | null }>;
  calculation_details?: string | null;
  input_issues?: string[];
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
  notice?: string | null;
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

export default function PurchaseWorkspace({ canCreate, onOpenRequirements }: {
  canCreate: boolean;
  onOpenRequirements?: (period: string) => void;
}) {
  const { user } = useAuth();
  const canEditMaster = Boolean(user?.is_super_admin || user?.is_superuser || user?.roles.includes('ADMIN') || user?.masters_update || user?.permissions.includes('masters.consumables.write'));
  const [selectedMonth, setSelectedMonth] = useState(10);
  const [selectedYear, setSelectedYear] = useState(2026);
  const [records, setRecords] = useState<PurchaseWorkspaceRecord[]>([]);
  const [purchaseView, setPurchaseView] = useState<'normal' | 'md'>('normal');
  const [showNormalSheetColumns, setShowNormalSheetColumns] = useState(false);
  const recordsRef = useRef<PurchaseWorkspaceRecord[]>([]);
  const originalsRef = useRef(new Map<string, PurchaseWorkspaceRecord>());
  const dirtyRef = useRef(false);
  const [originalRecords, setOriginalRecords] = useState(new Map<string, PurchaseWorkspaceRecord>());
  const [isSaving, setIsSaving] = useState(false);
  const pendingSave = useRef(false);
  const [planMetadata, setPlanMetadata] = useState<MonthlyPlanMetadata | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const isCentralPlan = planMetadata?.source_workflow === 'BASIC_CENTRAL_V1';
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set());
  const [selectedCell, setSelectedCell] = useState<{ rowId: string; colKey: keyof PurchaseWorkspaceRecord & string } | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const settledSearch = useDebouncedValue(searchQuery);
  const loadGeneration = useRef(0);
  const [statusFilter, setStatusFilter] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const pendingExport = useRef(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
  const editableKeys = ['consumable_name', 'master_unit', 'requested_purchase_qty', 'purchase_notes'] as const;
  const acceptRecords = useCallback((rows: PurchaseWorkspaceRecord[]) => {
    const baseline = new Map(rows.map(row => [row.id, { ...row }]));
    recordsRef.current = rows;
    originalsRef.current = baseline;
    dirtyRef.current = false;
    setRecords(rows);
    setOriginalRecords(baseline);
  }, []);
  const unsavedCount = records.filter(row => editableKeys.some(key => String(row[key] ?? '').trim() !== String(originalRecords.get(row.id)?.[key] ?? '').trim())).length;
  const handleCellChange = (id: string, key: keyof PurchaseWorkspaceRecord & string, value: string) => {
    if (!canCreate || isSaving || !editableKeys.some(item => item === key) || (['consumable_name', 'master_unit'].includes(key) && !canEditMaster)) return;
    ++loadGeneration.current;
    const next = recordsRef.current.map(row => row.id === id ? { ...row, [key]: value,
      ...(key === 'requested_purchase_qty' ? { requested_purchase_unit: row.unit } : {}) } : row);
    recordsRef.current = next;
    dirtyRef.current = next.some(row => editableKeys.some(field => String(row[field] ?? '').trim() !== String(originalsRef.current.get(row.id)?.[field] ?? '').trim()));
    setIsLoading(false);
    setRecords(next);
  };
  const saveEdits = async () => {
    if (!canCreate || pendingSave.current) return;
    const edits = recordsRef.current.flatMap(row => {
      const before = originalsRef.current.get(row.id);
      const changes = Object.fromEntries(editableKeys.filter(key => String(row[key] ?? '').trim() !== String(before?.[key] ?? '').trim())
        .map(key => [key, row[key] === '' ? null : row[key]]));
      return Object.keys(changes).length ? [{ record_id: row.id, expected_draft_version: before?.draft_version ?? 0,
        expected_name: before?.consumable_name ?? '', expected_master_unit: before?.master_unit ?? '', ...changes }] : [];
    });
    if (!edits.length) return;
    pendingSave.current = true;
    setIsSaving(true); setMessage(null);
    try {
      const response = await apiClient.post<PurchaseWorkspaceResponse>(`/api/v1/purchasing/workspace/save?month=${selectedMonth}&year=${selectedYear}`,
        { edits, reason: 'Reviewed cell/row edits in Purchase Plan.' });
      acceptRecords(response.records); setPlanMetadata(response.plan_metadata); setNotice(response.notice ?? null);
      setMessage({ type: 'success', text: 'Purchase Plan changes saved. Requested quantities remain proposals for review.' });
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Could not save Purchase Plan changes.' });
      throw error;
    } finally { pendingSave.current = false; setIsSaving(false); }
  };
  const saveQuietly = async () => { try { await saveEdits(); } catch { /* The error is displayed above the grid. */ } };

  const loadWorkspace = useCallback(async () => {
    if (dirtyRef.current) return;
    const generation=++loadGeneration.current;
    setIsLoading(true);
    try {
      const params = new URLSearchParams({
        month: String(selectedMonth),
        year: String(selectedYear),
      });
      if (settledSearch) params.set('search', settledSearch);
      if (statusFilter) params.set('status', statusFilter);
      params.set('view', purchaseView);
      const data = await apiClient.get<PurchaseWorkspaceResponse>(`/api/v1/purchasing/workspace?${params}`);
      if(generation!==loadGeneration.current)return;
      acceptRecords(data.records);
      setPlanMetadata(data.plan_metadata);
      setNotice(data.notice ?? null);
      setSelectedRowIds(new Set());
      setMessage(null);
    } catch (error) {
      if(generation!==loadGeneration.current)return;
      setMessage({
        type: 'error',
        text: error instanceof ApiError ? error.message : 'Failed to load purchase workspace.',
      });
    } finally {
      if(generation===loadGeneration.current)setIsLoading(false);
    }
  }, [selectedMonth, selectedYear, settledSearch, statusFilter, purchaseView, acceptRecords]);

  useEffect(() => {
    void loadWorkspace();
    return ()=>{++loadGeneration.current;};
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
      acceptRecords(res.records);
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

  const exportRows = async (mode: 'ALL' | 'FILTERED' | 'SELECTED') => {
    if (pendingExport.current) return;
    let url = `/api/v1/purchasing/workspace/export?month=${selectedMonth}&year=${selectedYear}&view=${purchaseView}`;
    const params = new URLSearchParams();
    if (mode === 'SELECTED') {
      Array.from(selectedRowIds).forEach(id => params.append('record_ids', id));
    } else if (mode === 'FILTERED') {
      if (searchQuery) params.set('search', searchQuery);
      if (statusFilter) params.set('status', statusFilter);
    }
    const q = params.toString();
    if (q) url += `&${q}`;
    pendingExport.current = true;
    setIsExporting(true);
    setMessage(null);
    try {
      const blob = await apiClient.getBlob(url);
      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `${purchaseView === 'md' ? 'purchase_md_view' : 'purchase_recommendations'}_${selectedYear}_${String(selectedMonth).padStart(2, '0')}.xlsx`;
      document.body.appendChild(link);
      try { link.click(); }
      finally { link.remove(); URL.revokeObjectURL(downloadUrl); }
      setMessage({type:'success',text:'Excel download started.'});
    } catch (error) {
      setMessage({type:'error',text:error instanceof Error ? error.message : 'Could not export the Purchase Plan. Please try again.'});
    } finally {
      pendingExport.current = false;
      setIsExporting(false);
    }
  };

  const summary = useMemo(() => {
    const ready = records.filter(row => row.status === 'READY_FOR_APPROVAL').length;
    const submitted = records.filter(row => row.status === 'SUBMITTED').length;
    const blocked = records.filter(row => row.status.endsWith('REQUIRED')).length;
    return { ready, submitted, blocked, total: records.length };
  }, [records]);

  const baseColumns: ColumnDef<PurchaseWorkspaceRecord>[] = [
    {
      key: 'consumable_code',
      label: 'Consumable Item ID',
      width: 170,
      minWidth: 130,
      isSticky: true,
      render: value => <span className="font-mono font-bold text-blue-900">{value}</span>,
    },
    {
      key: 'consumable_name',
      label: 'Consumable Name',
      width: 240,
      minWidth: 160,
      isSticky: true,
      render: value => <span className="font-semibold text-gray-900 truncate block">{value}</span>,
    },
    { key: 'unit', label: 'Calculation Unit', width: 110, minWidth: 60, align: 'center' },
    { key: 'master_unit', label: 'Stock Unit (Master)', width: 130, minWidth: 90 },
    { key: 'required_qty', label: 'Requirement Qty', width: 140, minWidth: 100, align: 'right' },
    { key: 'minimum_stock_level', label: 'MSL', width: 110, minWidth: 80, align: 'right', render: value => value ?? 'Unavailable' },
    { key: 'minimum_order_qty', label: 'MOQ', width: 110, minWidth: 80, align: 'right', render: value => value ?? 'Unavailable' },
    { key: 'stock_qty', label: isCentralPlan ? 'Stock Qty (see basis)' : 'Stock Qty', width: 160, minWidth: 80, align: 'right', render: value => value ?? 'Unavailable' },
    { key: 'po_pending_qty', label: isCentralPlan ? 'Incoming (assessment only)' : 'PO Pending Qty', width: 150, minWidth: 90, align: 'right',
      render: (value, row) => row.calculation_basis === 'KNL_MONTHLY_V1' ? 'Not used' : value ?? 'Unavailable' },
    {
      key: 'shortage_qty',
      label: isCentralPlan ? 'Raw Purchase Need' : 'Net Shortage',
      width: 130,
      minWidth: 90,
      align: 'right',
      render: value => <span className="font-mono font-bold text-red-700">{value ?? 'Unavailable'}</span>,
    },
    {
      key: 'system_recommended_qty',
      label: 'System Recommended Qty',
      width: 180,
      minWidth: 120,
      align: 'right',
      render: value => <span className="font-mono font-bold text-indigo-950">{value ?? 'Unavailable'}</span>,
    },
    { key: 'unit_rate', label: 'Unit Rate (Master)', width: 130, minWidth: 90, align: 'right', render: value => value ?? 'Unavailable' },
    { key: 'purchase_value', label: 'Purchase Value', width: 160, minWidth: 110, align: 'right', render: value => value ?? 'Unavailable' },
    { key: 'requested_purchase_qty', label: 'Requested Purchase Qty', type: 'number', width: 180, minWidth: 140,
      render: (value, row) => value == null || value === '' ? '—' : `${value} ${row.requested_purchase_unit || row.unit}` },
    { key: 'supplier_code', label: 'Supplier Code', width: 130, minWidth: 90 },
    { key: 'supplier_name', label: 'Supplier Name', width: 180, minWidth: 120 },
    {
      key: 'status',
      label: 'Workspace Status',
      width: 160,
      minWidth: 110,
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
      width: 130,
      minWidth: 90,
      align: 'center',
      render: value => <span className="font-mono text-xs text-gray-700">{value || '-'}</span>,
    },
    { key: 'source_row_count', label: 'Requirement Rows', width: 130, minWidth: 90, align: 'center' },
    { key: 'stock_period', label: 'Stock Period', width: 130, minWidth: 100, render: value => value || 'See saved assessment' },
    { key: 'calculation_basis', label: 'Calculation Basis', width: 160, minWidth: 120, render: value => value || 'Legacy monthly' },
    { key: 'remarks', label: 'Planning Details', width: 220, minWidth: 140 },
    { key: 'purchase_notes', label: 'Remarks', width: 220, minWidth: 140 },
  ];
  const columns = baseColumns.map(col => ({ ...col, isEditable: editableKeys.some(key => key === col.key)
    && (!['consumable_name', 'master_unit'].includes(col.key) || canEditMaster) }));
  const normalFields = normalViewColumns(selectedMonth, selectedYear);
  const normalData = records.map((row, index) => Object.assign({}, row,
    Object.fromEntries(normalFields.map((definition, fieldIndex) => [`normal_${fieldIndex}`, definition.value(row, undefined, index)]))));
  const normalOriginals = new Map(normalData.map((row, index) => [row.id, Object.assign({}, originalRecords.get(row.id) ?? row,
    Object.fromEntries(normalFields.map((definition, fieldIndex) => [`normal_${fieldIndex}`, definition.value(originalRecords.get(row.id) ?? row, undefined, index)])))]));
  const normalColumns: ColumnDef<PurchaseWorkspaceRecord>[] = [
    ...columns,
    ...(showNormalSheetColumns ? normalFields.map((definition, index) => ({ key: `normal_${index}` as keyof PurchaseWorkspaceRecord & string,
      label: definition.label, width: index === 3 ? 250 : 145, minWidth: 100, isEditable: false }))
      : []),
  ];
  const mdFields = mdViewColumns(selectedMonth, selectedYear, planMetadata?.revision_label ?? 'R1');
  const mdRows = records.flatMap(row => (row.md_sources?.length ? row.md_sources : [undefined]).map((source, sourceIndex) => ({ row, source, sourceIndex })));

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-2 overflow-hidden">
      {/* Compact Controls & Summary Bar (Section 9A) */}
      <div className="bg-white border border-gray-200 rounded-lg p-2 flex flex-wrap items-center justify-between gap-2 shadow-2xs flex-shrink-0">
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs font-semibold text-gray-700 flex items-center">
            Month:
            <select
              aria-label="Planning Month"
              value={selectedMonth}
              disabled={isSubmitting || isSaving || unsavedCount > 0}
              onChange={e => { setRecords([]); setPlanMetadata(null); setNotice(null); setSelectedRowIds(new Set()); setSelectedMonth(Number(e.target.value)); }}
              className="ml-1.5 px-2 py-1 text-xs border border-gray-300 rounded bg-white text-gray-800 font-medium"
            >
              {MONTH_NAMES.map((month, idx) => <option key={month} value={idx + 1}>{month}</option>)}
            </select>
          </label>
          <label className="text-xs font-semibold text-gray-700 flex items-center">
            Year:
            <select
              aria-label="Planning Year"
              value={selectedYear}
              disabled={isSubmitting || isSaving || unsavedCount > 0}
              onChange={e => { setRecords([]); setPlanMetadata(null); setNotice(null); setSelectedRowIds(new Set()); setSelectedYear(Number(e.target.value)); }}
              className="ml-1.5 px-2 py-1 text-xs border border-gray-300 rounded bg-white text-gray-800 font-medium"
            >
              {[2024, 2025, 2026, 2027, 2028, 2029, 2030].map(year => <option key={year}>{year}</option>)}
            </select>
          </label>
          <button
            type="button"
            onClick={() => void loadWorkspace()}
            disabled={isLoading || isSaving || unsavedCount > 0}
            className="px-2.5 py-1 bg-gray-100 hover:bg-gray-200 text-gray-800 border border-gray-300 rounded font-semibold text-xs transition-colors"
          >
            {isLoading ? 'Loading…' : 'Load Plan'}
          </button>
          <div role="group" aria-label="Purchase view" className="ml-2 inline-flex overflow-hidden rounded border border-gray-300 text-xs">
            {(['normal', 'md'] as const).map(view => <button key={view} type="button"
              disabled={isLoading || isSaving || unsavedCount > 0}
              aria-pressed={purchaseView === view}
              onClick={() => { if (view !== purchaseView) { setSelectedRowIds(new Set()); setSelectedCell(null); setPurchaseView(view); } }}
              className={`px-3 py-1 font-semibold ${purchaseView === view ? 'bg-brand-navy text-white' : 'bg-white text-gray-700 hover:bg-gray-50'}`}>
              {view === 'normal' ? 'Normal view' : 'MD view'}
            </button>)}
          </div>
          {purchaseView === 'normal' && <button type="button" onClick={() => setShowNormalSheetColumns(value => !value)}
            className="rounded border border-gray-300 bg-white px-2 py-1 text-xs font-semibold text-gray-700">
            {showNormalSheetColumns ? 'Hide' : 'Show'} Normal sheet columns
          </button>}

          <div className="hidden sm:flex items-center gap-1.5 text-[11px] ml-2 border-l border-gray-200 pl-2">
            <span className="px-1.5 py-0.5 bg-gray-50 border rounded text-gray-600">Rev: <strong>{planMetadata?.revision_label ?? 'R0'}</strong></span>
            <span className="px-1.5 py-0.5 bg-gray-50 border rounded text-gray-600">Total: <strong>{summary.total}</strong></span>
            <span className="px-1.5 py-0.5 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded">Ready: <strong>{summary.ready}</strong></span>
            <span className="px-1.5 py-0.5 bg-blue-50 border border-blue-200 text-blue-800 rounded">Submitted: <strong>{summary.submitted}</strong></span>
            <span className="px-1.5 py-0.5 bg-amber-50 border border-amber-200 text-amber-800 rounded">Blocked: <strong>{summary.blocked}</strong></span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {canCreate && (
            <button
              type="button"
              onClick={() => void submitSelected()}
              disabled={isSubmitting || isSaving || unsavedCount > 0 || readySelectedIds.length === 0}
              className="px-3 py-1 bg-brand-navy hover:bg-opacity-90 disabled:opacity-50 text-white rounded font-semibold text-xs shadow-2xs transition-colors"
            >
              {isSubmitting ? 'Submitting...' : `Submit to Approval${readySelectedIds.length ? ` (${readySelectedIds.length})` : ''}`}
            </button>
          )}
          <button
            type="button"
            onClick={() => void exportRows(selectedRowIds.size ? 'SELECTED' : 'ALL')}
            disabled={isExporting}
            className="px-2.5 py-1 bg-white hover:bg-gray-50 border border-gray-300 text-gray-800 rounded font-semibold text-xs shadow-2xs transition-colors"
          >
            {isExporting ? 'Exporting…' : 'Export Excel'}
          </button>
          <button
            type="button"
            onClick={() => void exportRows('FILTERED')}
            disabled={isExporting}
            className="px-2.5 py-1 bg-white hover:bg-gray-50 border border-gray-300 text-gray-800 rounded font-semibold text-xs shadow-2xs transition-colors"
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

      {notice && (
        <div role="status" className="flex shrink-0 flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <p className="min-w-0 flex-1">{notice}</p>
          {onOpenRequirements && planMetadata?.plan_id && (
            <button type="button" className="rounded border border-amber-300 bg-white px-3 py-1.5 font-semibold"
              onClick={() => onOpenRequirements(planMetadata.planning_period)}>
              {planMetadata.status === 'APPROVED' ? 'View requirements' : 'Review central requirements'}
            </button>
          )}
        </div>
      )}

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded border border-gray-300 bg-white shadow-xs">
        <p className="shrink-0 border-b bg-blue-50 px-3 py-1 text-xs text-blue-900">
          {purchaseView === 'md' ? 'MD view follows the 76-column management layout; product/process lines come from saved requirements. Switch to Normal view to edit purchase proposals.'
            : 'Normal view keeps the editable plan. Show Normal sheet columns to inspect the 23-column monthly layout; Excel export follows that layout.'}
        </p>
        {canCreate && <p className="shrink-0 border-b bg-white px-3 py-1.5 text-xs text-gray-600">Edit requested purchase quantities and remarks here. Name and stock-unit edits update Product Master; existing stock-history unit restrictions apply. Calculation and approval quantities stay protected.</p>}
        {unsavedCount > 0 && <div className="shrink-0 border-b px-3 py-1 text-xs text-amber-900">
          Save changes before loading another period.{' '}
          <button type="button" disabled={isSaving} className="underline" onClick={() => {
            acceptRecords(Array.from(originalsRef.current.values()));
            void loadWorkspace();
          }}>Discard changes and reload</button>
        </div>}
        <Toolbar
          canImport={false}
          canCreate={false}
          canUpdate={canCreate}
          onSave={saveQuietly}
          isSaving={isSaving}
          unsavedCount={unsavedCount}
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
                { value: 'REQUIREMENT_REVIEW_REQUIRED', label: 'Requirement Review Required' },
                { value: 'ASSESSMENT_REQUIRED', label: 'Inventory / Supplier Assessment Required' },
                { value: 'MONTHLY_INPUTS_REQUIRED', label: 'Monthly Stock / MSL / MOQ Required' },
                { value: 'NO_PURCHASE_REQUIRED', label: 'No Purchase Required' },
              ],
            },
          ]}
        />
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          {purchaseView === 'normal' ? <DataTable
            virtualize
            columns={normalColumns}
            data={normalData}
            originalData={normalOriginals}
            onCellChange={handleCellChange}
            onSave={saveQuietly}
            onSaveRow={async (id, changes) => { Object.entries(changes).forEach(([key,value]) => handleCellChange(id, key as keyof PurchaseWorkspaceRecord & string, String(value ?? ''))); await saveEdits(); }}
            selectedIds={selectedRowIds}
            onSelectionChange={setSelectedRowIds}
            selectedCell={selectedCell}
            onSelectCell={setSelectedCell}
            isLoading={isLoading}
            canCreate={false}
            canUpdate={canCreate && !isSaving && !isSubmitting}
            canDelete={false}
            storageKey="knl_purchase_workspace_grid"
            onExport={exportRows}
            emptyMessage={notice ? (searchQuery || statusFilter ? 'No consumables match the current filters. Clear the search or status filter to see this plan.' : notice) : `No purchase recommendations found for ${MONTH_NAMES[selectedMonth - 1]} ${selectedYear}. Recalculate or import requirements first.`}
            getRowClassName={row => {
              if (row.status === 'READY_FOR_APPROVAL') return 'bg-emerald-50/60 hover:bg-emerald-100/60';
              if (row.status.endsWith('REQUIRED')) return 'bg-amber-50/60 hover:bg-amber-100/60';
              return '';
            }}
          /> : <div className="min-h-0 flex-1 overflow-auto" aria-label="MD purchase view">
            <table className="w-max min-w-full border-collapse text-xs">
              <thead className="sticky top-0 z-10 bg-[#f4ecda] text-left text-[#3b211c]">
                <tr>{mdFields.map((column, index) => <th key={index} className="min-w-32 max-w-64 whitespace-normal border border-gray-300 px-2 py-2">{column.label}</th>)}</tr>
              </thead>
              <tbody>{mdRows.map(({ row, source, sourceIndex }, rowIndex) => <tr key={`${row.id}:${rowIndex}`} className="even:bg-gray-50">
                {mdFields.map((column, colIndex) => {
                  const value = sourceIndex > 0 && colIndex >= 29 ? '—' : column.value(row, source, rowIndex);
                  return <td key={colIndex} className="max-w-64 truncate border border-gray-200 px-2 py-1.5" title={value}>{value}</td>;
                })}
              </tr>)}</tbody>
            </table>
            {!mdRows.length && <p className="p-6 text-center text-gray-600">No purchase plan records for this period.</p>}
          </div>}
        </div>
      </div>
    </div>
  );
}
