import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  ArrowDownToLine,
  CheckCircle2,
  FileSpreadsheet,
  RefreshCw,
  Search,
  Save,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import DataTable, { type ColumnDef, type HeaderGroupDef } from '../../components/DataTable';
import ConfirmDialog from '../../components/ConfirmDialog';
import { apiClient, getAccessToken, getApiBaseUrl } from '../../api/client';
import { useAuth } from '../auth/context';
import { stockEditValue, validatedStockValue, validatedStockText } from './stockEditing';
import { canPerform } from '../../core/rbac';

export interface StockStatementLine {
  id: string;
  item_id: string;
  consumable_id: string | null;
  item_class?: string;
  item_description: string | null;
  cust_part_no: string | null;
  unit: string | null;
  opening_qty: number | string | null;
  opening_value: number | string | null;
  receipt_qty: number | string | null;
  receipt_value: number | string | null;
  issue_qty: number | string | null;
  issue_value: number | string | null;
  closing_qty: number | string | null;
  closing_value: number | string | null;
  source_row: number;
  warning_codes: string[];
  diff_closing_qty: number | string | null;
  diff_closing_value: number | string | null;
}

export interface StockStatementMetadata {
  has_statement: boolean;
  batch_id: string | null;
  statement_month: number;
  statement_year: number;
  statement_date: string;
  source_filename: string | null;
  status: string | null;
  created_at: string | null;
  created_by_name: string | null;
  updated_at: string | null;
  updated_by_name: string | null;
  row_count: number;
  warning_count: number;
  consumable_count?: number;
  product_or_other_count?: number;
  unknown_count?: number;
}

export interface StockStatementSummary {
  item_count: number;
  consumable_count?: number;
  product_or_other_count?: number;
  unknown_count?: number;
  total_opening_value: number | string;
  total_receipt_value: number | string;
  total_issue_value: number | string;
  total_closing_value: number | string;
  warning_rows_count: number;
}

export interface StockStatementResponse {
  metadata: StockStatementMetadata;
  summary: StockStatementSummary;
  records: StockStatementLine[];
}

interface StatementDeleteTarget {
  batchId: string;
  month: number;
  year: number;
  rowCount: number;
  filename: string | null;
}

export interface RowIssue {
  row: number;
  column: string;
  description: string;
  severity: 'ERROR' | 'WARNING';
  code?: string;
  item_id?: string;
  item_class?: string;
}

export interface GroupedWarning {
  code: string;
  description: string;
  count: number;
  sample_rows: number[];
}

export interface StockStatementPreviewResponse {
  statement_month: number;
  statement_year: number;
  statement_date: string;
  detected_title: string | null;
  source_filename: string;
  file_token: string;
  is_existing_batch: boolean;
  existing_batch_filename: string | null;
  existing_batch_date: string | null;
  errors: RowIssue[];
  warnings: RowIssue[];
  grouped_warnings?: GroupedWarning[];
  unknown_items: string[];
  total_rows: number;
  warning_count: number;
  consumable_count?: number;
  product_or_other_count?: number;
  unknown_count?: number;
  lines_preview: StockStatementLine[];
  can_confirm: boolean;
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function formatIST(isoDateString?: string | null): string {
  if (!isoDateString) return '—';
  try {
    const d = new Date(isoDateString);
    return d.toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return isoDateString;
  }
}

function formatINR(val?: number | string | null): string {
  if (val === null || val === undefined || val === '') return '—';
  const num = typeof val === 'number' ? val : parseFloat(val);
  if (isNaN(num)) return '—';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
}

function formatQty(val?: number | string | null): string {
  if (val === null || val === undefined || val === '') return '—';
  const num = typeof val === 'number' ? val : parseFloat(val);
  if (isNaN(num)) return '—';
  return num.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });
}

export default function StockStatementWorkspace() {
  const { user } = useAuth();
  const now = new Date();
  // Default to previous month
  const initialMonth = now.getMonth() === 0 ? 12 : now.getMonth();
  const initialYear = now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear();

  const [selectedMonth, setSelectedMonth] = useState<number>(initialMonth);
  const [selectedYear, setSelectedYear] = useState<number>(initialYear);
  const [searchQuery, setSearchQuery] = useState('');
  const [warningsOnly, setWarningsOnly] = useState(false);
  const [itemClassFilter, setItemClassFilter] = useState<'CONSUMABLE' | 'ALL'>('CONSUMABLE');

  const [originalRecords, setOriginalRecords] = useState<Map<string, StockStatementLine>>(new Map());
  const [dirtyMap, setDirtyMap] = useState<Map<string, Partial<StockStatementLine>>>(new Map());
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [draftVersion, setDraftVersion] = useState(0);
  const [records, setRecords] = useState<StockStatementLine[]>([]);
  const [metadata, setMetadata] = useState<StockStatementMetadata | null>(null);
  const [summary, setSummary] = useState<StockStatementSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const loadRequestId = useRef(0);
  const [deleteTarget, setDeleteTarget] = useState<StatementDeleteTarget | null>(null);
  const [deleteReason, setDeleteReason] = useState('');
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const deleteInProgress = useRef(false);
  const saveInProgress = useRef(false);

  // Table selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Upload modal state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [previewData, setPreviewData] = useState<StockStatementPreviewResponse | null>(null);
  const [replaceConfirmed, setReplaceConfirmed] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const canUpload = user ? canPerform(user, 'inventory', 'import') || canPerform(user, 'inventory', 'create') : false;
  const canEdit = user ? canPerform(user, 'inventory', 'update') : false;
  const canDeleteStatement = user ? canPerform(user, 'inventory', 'delete') : false;
  const selectedStatementLoaded = Boolean(metadata?.has_statement && metadata.batch_id
    && metadata.statement_month === selectedMonth && metadata.statement_year === selectedYear);

  const loadData = useCallback(async () => {
    if (!selectedMonth || !selectedYear) return;
    const requestId = ++loadRequestId.current;
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const res = await apiClient.get<StockStatementResponse>(
        `/api/v1/inventory/statement?month=${selectedMonth}&year=${selectedYear}&item_class=${itemClassFilter}&has_warnings_only=${warningsOnly}${
          searchQuery ? `&search=${encodeURIComponent(searchQuery)}` : ''
        }`
      );
      if (requestId !== loadRequestId.current) return;
      setRecords(res.records || []);
      setOriginalRecords(new Map((res.records || []).map(row => [row.id, { ...row }])));
      setDirtyMap(new Map());
      setDraftVersion(prev => prev + 1);
      setMetadata(res.metadata);
      setSummary(res.summary);
      setSelectedIds(new Set());
    } catch (err: any) {
      if (requestId !== loadRequestId.current) return;
      setErrorMsg(err.message || 'Failed to load stock statement.');
      setRecords([]);
      setOriginalRecords(new Map());
      setDirtyMap(new Map());
      setMetadata(null);
      setSummary(null);
    } finally {
      if (requestId === loadRequestId.current) setIsLoading(false);
    }
  }, [selectedMonth, selectedYear, itemClassFilter, warningsOnly, searchQuery]);

  useEffect(() => {
    setSuccessMsg(null);
    loadData();
  }, [loadData]);

  const handleDeleteStatement = async () => {
    if (!deleteTarget || !canDeleteStatement || deleteInProgress.current) return;
    const reason = deleteReason.trim();
    if (!reason) { setDeleteError('Enter a reason for deleting this statement.'); return; }
    const target = deleteTarget;
    deleteInProgress.current = true;
    setIsDeleting(true);
    setDeleteError(null);
    ++loadRequestId.current;
    try {
      await apiClient.delete(`/api/v1/inventory/statement?month=${target.month}&year=${target.year}`, {
        batch_id: target.batchId,
        reason,
      });
      setRecords([]);
      setOriginalRecords(new Map());
      setDirtyMap(new Map());
      setMetadata(null);
      setSummary(null);
      setSelectedIds(new Set());
      setDeleteTarget(null);
      setSuccessMsg(`Deleted the ${MONTH_NAMES[target.month - 1]} ${target.year} stock statement.`);
      await loadData();
    } catch (err: unknown) {
      setDeleteError(err instanceof Error ? err.message : 'Failed to delete the statement.');
    } finally {
      deleteInProgress.current = false;
      setIsDeleting(false);
    }
  };

  const handleCellChange = useCallback((rowId: string, colKey: string, value: string) => {
    if (!canEdit || isDeleting || deleteTarget) return;
    setRecords(prev => prev.map(row => row.id === rowId ? { ...row, [colKey]: value } : row));
    setDirtyMap(prev => {
      const next = new Map(prev);
      const changes = { ...next.get(rowId) } as Record<string, unknown>;
      const original = originalRecords.get(rowId) as unknown as Record<string, unknown> | undefined;
      if (stockEditValue(original?.[colKey]) === value) delete changes[colKey];
      else changes[colKey] = value;
      if (Object.keys(changes).length) next.set(rowId, changes as Partial<StockStatementLine>);
      else next.delete(rowId);
      return next;
    });
  }, [canEdit, isDeleting, deleteTarget, originalRecords]);

  const handleSave = async () => {
    if (!canEdit || !metadata?.batch_id || !dirtyMap.size || deleteTarget || isDeleting || saveStatus === 'saving') return;
    if (saveInProgress.current) return;
    saveInProgress.current = true;
    setSaveStatus('saving');
    setErrorMsg(null);
    try {
      const updates = Array.from(dirtyMap.entries()).map(([id, changes]) => ({ id,
        ...Object.fromEntries(Object.entries(changes).map(([key, value]) => [key, key === 'item_description' ? validatedStockText(value) : validatedStockValue(value)])),
      }));
      await apiClient.patch('/api/v1/inventory/statement/batch-update', {
        month: selectedMonth, year: selectedYear, batch_id: metadata.batch_id, updates,
      });
      await loadData();
      setSaveStatus('saved');
      setSuccessMsg('Stock statement corrections saved with audit history.');
    } catch (err) {
      setSaveStatus('error');
      setErrorMsg(err instanceof Error ? err.message : 'Failed to save statement corrections.');
    } finally { saveInProgress.current = false; }
  };

  // Export Stock Statement
  const handleExport = async () => {
    try {
      const token = getAccessToken();
      const url = `${getApiBaseUrl()}/api/v1/inventory/statement/export?month=${selectedMonth}&year=${selectedYear}`;
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error('Download failed');
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `Stock_Statement_${MONTH_NAMES[selectedMonth - 1]}_${selectedYear}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(blobUrl);
    } catch (err: any) {
      alert(`Export failed: ${err.message}`);
    }
  };

  // Download Error Report
  const handleDownloadErrorReport = async (token: string) => {
    try {
      const authToken = getAccessToken();
      const url = `${getApiBaseUrl()}/api/v1/inventory/statement/preview-errors?file_token=${encodeURIComponent(token)}`;
      const res = await fetch(url, {
        headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
      });
      if (!res.ok) throw new Error('Failed to download error report.');
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `Stock_Statement_Validation_Report_${MONTH_NAMES[selectedMonth - 1]}_${selectedYear}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(blobUrl);
    } catch (err: any) {
      alert(`Error report download failed: ${err.message}`);
    }
  };

  // Preview Upload
  const handlePreviewUpload = async () => {
    if (!uploadFile) return;
    setIsPreviewing(true);
    setUploadError(null);
    setPreviewData(null);
    setReplaceConfirmed(false);

    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('statement_month', selectedMonth.toString());
      formData.append('statement_year', selectedYear.toString());

      const res = await apiClient.postFormData<StockStatementPreviewResponse>(
        '/api/v1/inventory/statement/preview',
        formData
      );
      setPreviewData(res);
    } catch (err: any) {
      setUploadError(err.message || 'Validation failed. Check your file format.');
    } finally {
      setIsPreviewing(false);
    }
  };

  // Confirm Upload
  const handleConfirmUpload = async () => {
    if (!previewData) return;
    setIsConfirming(true);
    setUploadError(null);

    try {
      await apiClient.post<StockStatementResponse>('/api/v1/inventory/statement/confirm', {
        file_token: previewData.file_token,
        statement_month: selectedMonth,
        statement_year: selectedYear,
        replace_confirmed: replaceConfirmed,
      });
      setShowUploadModal(false);
      setUploadFile(null);
      setPreviewData(null);
      await loadData();
    } catch (err: any) {
      setUploadError(err.message || 'Failed to save statement.');
    } finally {
      setIsConfirming(false);
    }
  };

  // Table Column Definitions
  const columns: ColumnDef<StockStatementLine>[] = useMemo(
    () => [
      {
        key: 'item_id',
        isEditable: false,
        label: 'Item Id',
        width: 130,
        isSticky: true,
        render: (val, row) => (
          <div className="flex items-center gap-1.5 font-medium">
            <span>{val}</span>
            {row.warning_codes && row.warning_codes.length > 0 && (
              <span
                title={row.warning_codes.join('; ')}
                className="inline-flex items-center text-amber-600 hover:text-amber-800 cursor-help"
              >
                <AlertTriangle className="w-3.5 h-3.5" />
              </span>
            )}
          </div>
        ),
      },
      {
        key: 'item_description',
        isEditable: canEdit,
        label: 'Item Description',
        width: 240,
        render: val => <span className="truncate block" title={val || ''}>{val || '—'}</span>,
      },
      {
        key: 'cust_part_no',
        isEditable: false,
        label: 'Cust. Part No.',
        width: 140,
        render: val => <span>{val || '—'}</span>,
      },
      {
        key: 'unit',
        isEditable: false,
        label: 'Unit',
        width: 80,
        align: 'center',
        render: val => <span className="font-semibold text-xs">{val || '—'}</span>,
      },
      {
        key: 'opening_qty',
        label: 'Opening Qty.',
        width: 120,
        align: 'right',
        render: val => <span>{formatQty(val)}</span>,
      },
      {
        key: 'opening_value',
        label: 'Opening Value',
        width: 140,
        align: 'right',
        render: val => <span>{formatINR(val)}</span>,
      },
      {
        key: 'receipt_qty',
        label: 'Receipt Qty.',
        width: 120,
        align: 'right',
        render: val => <span>{formatQty(val)}</span>,
      },
      {
        key: 'receipt_value',
        label: 'Receipt Value',
        width: 140,
        align: 'right',
        render: val => <span>{formatINR(val)}</span>,
      },
      {
        key: 'issue_qty',
        label: 'Issue Qty.',
        width: 120,
        align: 'right',
        render: val => <span>{formatQty(val)}</span>,
      },
      {
        key: 'issue_value',
        label: 'Issue Value',
        width: 140,
        align: 'right',
        render: val => <span>{formatINR(val)}</span>,
      },
      {
        key: 'closing_qty',
        label: 'Closing Qty.',
        width: 120,
        align: 'right',
        render: (val, row) => (
          <span
            className={row.diff_closing_qty ? 'font-semibold text-amber-700' : ''}
            title={row.diff_closing_qty ? `Diff: ${row.diff_closing_qty}` : undefined}
          >
            {formatQty(val)}
          </span>
        ),
      },
      {
        key: 'closing_value',
        label: 'Closing Value',
        width: 140,
        align: 'right',
        render: (val, row) => (
          <span
            className={row.diff_closing_value ? 'font-semibold text-amber-700' : ''}
            title={row.diff_closing_value ? `Diff: ₹ ${row.diff_closing_value}` : undefined}
          >
            {formatINR(val)}
          </span>
        ),
      },
      ...(itemClassFilter === 'ALL'
        ? [
            {
              key: 'item_class' as keyof StockStatementLine,
              isEditable: false,
              label: 'Class',
              width: 130,
              align: 'center' as const,
              render: (val: any) => {
                const cls = String(val || 'CONSUMABLE');
                const badgeColor =
                  cls === 'CONSUMABLE'
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : cls === 'PRODUCT_OR_OTHER'
                    ? 'bg-blue-50 text-blue-700 border-blue-200'
                    : 'bg-amber-50 text-amber-700 border-amber-200';
                return (
                  <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold border ${badgeColor}`}>
                    {cls}
                  </span>
                );
              },
            },
          ]
        : []),
    ],
    [itemClassFilter, canEdit]
  );

  // Grouped Header Bands
  const headerGroups: HeaderGroupDef[] = useMemo(
    () => [
      {
        label: 'IDENTIFICATION',
        colSpan: itemClassFilter === 'ALL' ? 5 : 4,
        className: 'bg-stone-100 text-stone-700',
      },
      { label: 'OPENING', colSpan: 2, className: 'bg-blue-50 text-blue-800' },
      { label: 'RECEIPTS', colSpan: 2, className: 'bg-emerald-50 text-emerald-800' },
      { label: 'ISSUES', colSpan: 2, className: 'bg-amber-50 text-amber-800' },
      { label: 'CLOSING', colSpan: 2, className: 'bg-purple-50 text-purple-800' },
    ],
    [itemClassFilter, canEdit]
  );

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* 1. Header & Top-Right Persisted Metadata */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-4 rounded-xl border border-stone-200 shadow-xs">
        <div>
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="w-5 h-5 text-erp-orange" />
            <h1 className="text-lg font-bold text-erp-chocolate tracking-tight">
              Stock Statement
            </h1>
            <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-erp-vanilla text-erp-chocolate border border-erp-dark-vanilla/40">
              {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
            </span>
          </div>
          <p className="text-xs text-stone-500 mt-0.5">
            Monthly consumable stock statement (Opening, Receipts, Issues, Closing). Authoritative source for purchase planning.
          </p>
        </div>

        {/* Persisted Metadata in top-right corner */}
        <div className="text-right text-xs text-stone-600 bg-stone-50 px-3 py-2 rounded-lg border border-stone-200 space-y-0.5">
          {metadata && metadata.has_statement ? (
            <>
              <div>
                <span className="font-semibold text-stone-700">Entered:</span>{' '}
                {metadata.created_by_name || 'System'} at {formatIST(metadata.created_at)}
              </div>
              <div>
                <span className="font-semibold text-stone-700">Last modified:</span>{' '}
                {metadata.updated_by_name || 'System'} at {formatIST(metadata.updated_at)}
              </div>
              {metadata.source_filename && (
                <div className="text-[11px] text-stone-500 truncate max-w-xs">
                  File: {metadata.source_filename}
                </div>
              )}
            </>
          ) : (
            <div className="text-stone-400 italic">No statement uploaded for selected month</div>
          )}
        </div>
      </div>

      {/* 2. Control Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white px-4 py-3 rounded-xl border border-stone-200 shadow-xs">
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Month Selector */}
          <div className="flex items-center gap-1.5">
            <label className="text-xs font-semibold text-stone-700">Month:</label>
            <select
              aria-label="Statement month"
              disabled={isDeleting || Boolean(deleteTarget) || dirtyMap.size > 0 || saveStatus === 'saving'}
              value={selectedMonth}
              onChange={e => setSelectedMonth(Number(e.target.value))}
              className="text-xs border border-stone-300 rounded-lg px-2.5 py-1.5 bg-white font-medium text-stone-800 focus:outline-none focus:ring-1 focus:ring-erp-orange"
            >
              {MONTH_NAMES.map((name, idx) => (
                <option key={name} value={idx + 1}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          {/* Year Selector */}
          <div className="flex items-center gap-1.5">
            <label className="text-xs font-semibold text-stone-700">Year:</label>
            <select
              aria-label="Statement year"
              disabled={isDeleting || Boolean(deleteTarget) || dirtyMap.size > 0 || saveStatus === 'saving'}
              value={selectedYear}
              onChange={e => setSelectedYear(Number(e.target.value))}
              className="text-xs border border-stone-300 rounded-lg px-2.5 py-1.5 bg-white font-medium text-stone-800 focus:outline-none focus:ring-1 focus:ring-erp-orange"
            >
              {[2024, 2025, 2026, 2027].map(yr => (
                <option key={yr} value={yr}>
                  {yr}
                </option>
              ))}
            </select>
          </div>

          <div className="h-5 w-px bg-stone-300 mx-1" />

          {/* Upload Button: Enabled only after selecting date */}
          <button
            type="button"
            onClick={() => {
              setShowUploadModal(true);
              setUploadFile(null);
              setPreviewData(null);
              setUploadError(null);
            }}
            disabled={!canUpload || !selectedMonth || !selectedYear || isLoading || isDeleting || dirtyMap.size > 0 || saveStatus === 'saving'}
            className="flex items-center gap-1.5 text-xs font-semibold bg-erp-orange text-white px-3 py-1.5 rounded-lg shadow-xs hover:bg-erp-orange/90 disabled:opacity-50 transition-colors"
            title={canUpload ? 'Upload monthly statement spreadsheet' : 'Permission required'}
          >
            <Upload className="w-3.5 h-3.5" />
            Upload statement
          </button>

          {canDeleteStatement && (
            <button
              type="button"
              onClick={() => {
                if (!selectedStatementLoaded || !metadata?.batch_id) return;
                setDeleteTarget({ batchId: metadata.batch_id, month: selectedMonth, year: selectedYear,
                  rowCount: metadata.row_count, filename: metadata.source_filename });
                setDeleteReason('');
                setDeleteError(null);
              }}
              disabled={!selectedStatementLoaded || isLoading || isDeleting || dirtyMap.size > 0 || saveStatus === 'saving'}
              className="flex items-center gap-1.5 text-xs font-semibold border border-red-300 text-red-700 bg-white px-3 py-1.5 rounded-lg hover:bg-red-50 disabled:opacity-50 transition-colors"
              title={`Delete the ${MONTH_NAMES[selectedMonth - 1]} ${selectedYear} statement`}
            >
              <Trash2 className="w-3.5 h-3.5" />
              Delete statement
            </button>
          )}

          {canEdit && <button type="button" onClick={() => { void handleSave(); }}
            disabled={!dirtyMap.size || saveStatus === 'saving' || isDeleting}
            className="flex items-center gap-1.5 text-xs font-semibold bg-emerald-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50">
            <Save className="w-3.5 h-3.5" />Save changes
          </button>}

          {dirtyMap.size > 0 && <button type="button" disabled={saveStatus === 'saving' || isDeleting}
            onClick={() => { setRecords(Array.from(originalRecords.values())); setDirtyMap(new Map()); setDraftVersion(prev => prev + 1); }}
            className="text-xs underline px-2">Discard edits</button>}
          {/* Export to Excel */}
          <button
            type="button"
            onClick={handleExport}
            disabled={!metadata?.has_statement || records.length === 0 || isDeleting}
            className="flex items-center gap-1.5 text-xs font-medium border border-stone-300 bg-white hover:bg-stone-50 text-stone-700 px-3 py-1.5 rounded-lg disabled:opacity-50 transition-colors"
          >
            <ArrowDownToLine className="w-3.5 h-3.5 text-stone-600" />
            Export Excel
          </button>

          {/* Refresh */}
          <button
            type="button"
            onClick={() => loadData()}
            disabled={isLoading || isDeleting || dirtyMap.size > 0 || saveStatus === 'saving'}
            className="p-1.5 border border-stone-300 rounded-lg hover:bg-stone-50 text-stone-600 disabled:opacity-50 transition-colors"
            title="Refresh statement"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Item Class Filter & Search & Warning Filters */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Item Class Toggle */}
          <div className="flex items-center bg-stone-100 p-0.5 rounded-lg border border-stone-200 text-xs">
            <button
              type="button"
              disabled={dirtyMap.size > 0 || saveStatus === 'saving'}
              onClick={() => setItemClassFilter('CONSUMABLE')}
              className={`px-2.5 py-1 rounded-md font-semibold transition-all ${
                itemClassFilter === 'CONSUMABLE'
                  ? 'bg-white text-stone-900 shadow-xs'
                  : 'text-stone-500 hover:text-stone-700'
              }`}
            >
              Consumables only ({metadata?.consumable_count ?? summary?.consumable_count ?? 0})
            </button>
            <button
              type="button"
              disabled={dirtyMap.size > 0 || saveStatus === 'saving'}
              onClick={() => setItemClassFilter('ALL')}
              className={`px-2.5 py-1 rounded-md font-semibold transition-all ${
                itemClassFilter === 'ALL'
                  ? 'bg-white text-stone-900 shadow-xs'
                  : 'text-stone-500 hover:text-stone-700'
              }`}
            >
              All items ({metadata?.row_count ?? 0})
            </button>
          </div>

          <div className="relative">
            <Search className="w-3.5 h-3.5 text-stone-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search items..."
              disabled={dirtyMap.size > 0 || saveStatus === 'saving'}
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="text-xs pl-8 pr-3 py-1.5 border border-stone-300 rounded-lg w-44 focus:outline-none focus:ring-1 focus:ring-erp-orange"
            />
          </div>

          <label className="flex items-center gap-1.5 text-xs text-stone-700 font-medium cursor-pointer select-none border border-stone-200 px-2.5 py-1.5 rounded-lg hover:bg-stone-50">
            <input
              type="checkbox"
              disabled={dirtyMap.size > 0 || saveStatus === 'saving'}
              checked={warningsOnly}
              onChange={e => setWarningsOnly(e.target.checked)}
              className="rounded text-erp-orange focus:ring-erp-orange"
            />
            <span>Warnings only</span>
            {summary && summary.warning_rows_count > 0 && (
              <span className="ml-1 px-1.5 py-0.2 text-[10px] font-bold rounded-full bg-amber-100 text-amber-800">
                {summary.warning_rows_count}
              </span>
            )}
          </label>
        </div>
      </div>

      {/* 3. Aggregated Summary Strip */}
      {summary && metadata?.has_statement && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <div className="bg-white p-3 rounded-xl border border-stone-200 shadow-xs">
            <span className="text-[11px] font-semibold text-stone-500 uppercase">Items</span>
            <p className="text-base font-bold text-stone-800">{summary.item_count}</p>
          </div>
          <div className="bg-white p-3 rounded-xl border border-stone-200 shadow-xs">
            <span className="text-[11px] font-semibold text-blue-700 uppercase">Opening Value</span>
            <p className="text-base font-bold text-stone-800">{formatINR(summary.total_opening_value)}</p>
          </div>
          <div className="bg-white p-3 rounded-xl border border-stone-200 shadow-xs">
            <span className="text-[11px] font-semibold text-emerald-700 uppercase">Receipt Value</span>
            <p className="text-base font-bold text-stone-800">{formatINR(summary.total_receipt_value)}</p>
          </div>
          <div className="bg-white p-3 rounded-xl border border-stone-200 shadow-xs">
            <span className="text-[11px] font-semibold text-amber-700 uppercase">Issue Value</span>
            <p className="text-base font-bold text-stone-800">{formatINR(summary.total_issue_value)}</p>
          </div>
          <div className="bg-white p-3 rounded-xl border border-stone-200 shadow-xs">
            <span className="text-[11px] font-semibold text-purple-700 uppercase">Closing Value</span>
            <p className="text-base font-bold text-stone-800">{formatINR(summary.total_closing_value)}</p>
          </div>
          <div className="bg-white p-3 rounded-xl border border-stone-200 shadow-xs">
            <span className="text-[11px] font-semibold text-stone-500 uppercase">Warnings</span>
            <p
              className={`text-base font-bold ${
                summary.warning_rows_count > 0 ? 'text-amber-600' : 'text-emerald-600'
              }`}
            >
              {summary.warning_rows_count} rows
            </p>
          </div>
        </div>
      )}

      {dirtyMap.size > 0 && <p className="text-xs text-amber-800">Unsaved edits: use Ctrl+Z to undo, then save or discard before changing the period or filters.</p>}
      {/* Error alert if load failed */}
      {successMsg && <div role="status" className="p-3 bg-green-50 border border-green-200 text-green-800 text-xs rounded-xl">{successMsg}</div>}
      {errorMsg && (
        <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* 4. Table Area */}
      <div className="flex-1 min-h-0 bg-white rounded-xl border border-stone-200 shadow-xs overflow-hidden flex flex-col">
        <DataTable
          key={`${metadata?.batch_id || `${selectedYear}-${selectedMonth}`}:${draftVersion}`}
          originalData={originalRecords}
          onCellChange={handleCellChange}
          onSave={handleSave}
          saveStatus={saveStatus}
          columns={columns}
          headerGroups={headerGroups}
          data={records}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          isLoading={isLoading}
          emptyMessage={
            metadata?.has_statement
              ? 'No records match your filter criteria.'
              : `No stock statement recorded for ${MONTH_NAMES[selectedMonth - 1]} ${selectedYear}. Use the upload button above to import the statement.`
          }
          storageKey="knl_stock_statement_grid"
          canCreate={false}
          canUpdate={canEdit && !isDeleting && !deleteTarget && saveStatus !== 'saving'}
          canDelete={false}
          getRowClassName={row =>
            row.warning_codes && row.warning_codes.length > 0
              ? 'bg-amber-50/50 hover:bg-amber-100/50'
              : ''
          }
        />
      </div>

      <ConfirmDialog
        isOpen={Boolean(deleteTarget)}
        title={`Delete ${deleteTarget ? `${MONTH_NAMES[deleteTarget.month - 1]} ${deleteTarget.year}` : ''} stock statement?`}
        message="This removes the entire selected month's statement from the active view and future purchase planning. Other months and years are unaffected. Upload and audit history are retained."
        confirmLabel="Delete statement"
        isDestructive
        isLoading={isDeleting}
        isConfirmDisabled={!deleteReason.trim()}
        onConfirm={() => { void handleDeleteStatement(); }}
        onCancel={() => { if (!isDeleting) setDeleteTarget(null); }}
        details={<div className="font-sans space-y-2">
          <p>{deleteTarget?.rowCount} rows in the complete statement, including rows hidden by filters.</p>
          {dirtyMap.size > 0 && <p>Unsaved edits will be discarded after deletion.</p>}
          {deleteTarget?.filename && <p>File: {deleteTarget.filename}</p>}
          <label className="block" htmlFor="statement-delete-reason">Reason for deletion</label>
          <textarea id="statement-delete-reason" autoFocus maxLength={1000} disabled={isDeleting}
            value={deleteReason} onChange={event => setDeleteReason(event.target.value)}
            className="w-full rounded border border-gray-300 p-2" rows={2} />
          {deleteError && <p role="alert" className="text-red-700">{deleteError}</p>}
        </div>}
      />

      {/* 5. Upload & Preview Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-[10000] bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl border border-stone-200 flex flex-col max-h-[90vh]">
            <div className="flex items-center justify-between pb-3 border-b border-stone-200">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5 text-erp-orange" />
                <h3 className="text-base font-bold text-erp-chocolate">
                  Upload Stock Statement
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowUploadModal(false)}
                className="text-stone-400 hover:text-stone-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="py-4 space-y-4 overflow-y-auto flex-1">
              {/* Target Month Confirmation Banner */}
              <div className="p-3 bg-erp-vanilla/60 border border-erp-dark-vanilla/40 rounded-xl text-xs text-erp-chocolate">
                <span className="font-semibold">Target Period:</span>{' '}
                {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
                <p className="text-[11px] text-stone-500 mt-0.5">
                  The uploaded statement will be recorded as the active stock snapshot for this month.
                </p>
              </div>

              {/* File Input */}
              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-stone-700">
                  Select Excel file (.xlsx):
                </label>
                <input
                  type="file"
                  accept=".xlsx"
                  onChange={e => {
                    setUploadFile(e.target.files?.[0] || null);
                    setPreviewData(null);
                    setUploadError(null);
                  }}
                  className="block w-full text-xs text-stone-700 border border-stone-300 rounded-lg file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-erp-vanilla file:text-erp-chocolate hover:file:bg-erp-vanilla/80 cursor-pointer"
                />
              </div>

              {/* Action: Validate and Preview */}
              {!previewData && (
                <div className="flex justify-end pt-2">
                  <button
                    type="button"
                    onClick={handlePreviewUpload}
                    disabled={!uploadFile || isPreviewing}
                    className="flex items-center gap-2 text-xs font-semibold bg-erp-orange text-white px-4 py-2 rounded-lg hover:bg-erp-orange/90 disabled:opacity-50 transition-colors shadow-xs"
                  >
                    {isPreviewing ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        Validating spreadsheet...
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Preview & Validate
                      </>
                    )}
                  </button>
                </div>
              )}

              {/* Error Alert */}
              {uploadError && (
                <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold">Validation Error:</span> {uploadError}
                  </div>
                </div>
              )}

              {/* Preview Results */}
              {previewData && (
                <div className="space-y-3 pt-2">
                  {/* Title / Row stats */}
                  <div className="p-3 bg-stone-50 rounded-xl border border-stone-200 text-xs space-y-2">
                    <div className="flex justify-between">
                      <span className="text-stone-600">Detected Sheet Title:</span>
                      <span className="font-semibold text-stone-800">
                        {previewData.detected_title || 'Stock Statement'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-stone-600">Total Rows Found:</span>
                      <span className="font-bold text-stone-800">{previewData.total_rows}</span>
                    </div>

                    {/* Breakdown by item class */}
                    <div className="grid grid-cols-3 gap-2 pt-1 border-t border-stone-200">
                      <div className="bg-emerald-50/70 border border-emerald-200 rounded-lg p-2 text-center">
                        <span className="text-[10px] font-semibold text-emerald-800 uppercase block">Consumables</span>
                        <span className="text-sm font-bold text-emerald-700">{previewData.consumable_count ?? 0}</span>
                      </div>
                      <div className="bg-blue-50/70 border border-blue-200 rounded-lg p-2 text-center">
                        <span className="text-[10px] font-semibold text-blue-800 uppercase block">Products / Other</span>
                        <span className="text-sm font-bold text-blue-700">{previewData.product_or_other_count ?? 0}</span>
                      </div>
                      <div className="bg-amber-50/70 border border-amber-200 rounded-lg p-2 text-center">
                        <span className="text-[10px] font-semibold text-amber-800 uppercase block">Unknown</span>
                        <span className="text-sm font-bold text-amber-700">{previewData.unknown_count ?? 0}</span>
                      </div>
                    </div>
                  </div>

                  {/* Blocking Errors Display */}
                  {previewData.errors.length > 0 && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-xl space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-red-800 flex items-center gap-1.5">
                          <AlertCircle className="w-4 h-4" />
                          {previewData.errors.length} Blocking Errors Detected
                        </span>
                        <button
                          type="button"
                          onClick={() => handleDownloadErrorReport(previewData.file_token)}
                          className="text-[11px] font-semibold text-red-700 underline hover:text-red-900"
                        >
                          Download Error Report (.xlsx)
                        </button>
                      </div>
                      <div className="max-h-36 overflow-y-auto space-y-1 text-xs text-red-700">
                        {previewData.errors.slice(0, 10).map((err, i) => (
                          <div key={i} className="bg-white/80 p-1.5 rounded border border-red-200">
                            <span className="font-semibold">Row {err.row}:</span> {err.description}
                          </div>
                        ))}
                        {previewData.errors.length > 10 && (
                          <p className="text-[11px] italic text-red-600">
                            ...and {previewData.errors.length - 10} more errors. Download the report for full details.
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Grouped Warnings Display (non-blocking) */}
                  {previewData.grouped_warnings && previewData.grouped_warnings.length > 0 && (
                    <div className="p-3 bg-amber-50/80 border border-amber-200 rounded-xl space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-amber-900 flex items-center gap-1.5">
                          <AlertTriangle className="w-4 h-4 text-amber-600" />
                          Validation Warnings Summary ({previewData.warning_count} total)
                        </span>
                        <button
                          type="button"
                          onClick={() => handleDownloadErrorReport(previewData.file_token)}
                          className="text-[11px] font-semibold text-amber-800 underline hover:text-amber-950"
                        >
                          Download Report (.xlsx)
                        </button>
                      </div>
                      <div className="max-h-48 overflow-y-auto rounded border border-amber-200 bg-white">
                        <table className="w-full text-left border-collapse text-[11px]">
                          <thead>
                            <tr className="bg-amber-100/60 text-amber-900 border-b border-amber-200">
                              <th className="p-1.5 font-semibold">Warning Code</th>
                              <th className="p-1.5 font-semibold text-right">Count</th>
                              <th className="p-1.5 font-semibold">Sample Rows</th>
                              <th className="p-1.5 font-semibold">Description</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-amber-100">
                            {previewData.grouped_warnings.map((gw, idx) => (
                              <tr key={idx} className="hover:bg-amber-50/50">
                                <td className="p-1.5 font-mono font-semibold text-amber-800">{gw.code}</td>
                                <td className="p-1.5 text-right font-bold text-stone-700">{gw.count}</td>
                                <td className="p-1.5 text-stone-600 font-mono text-[10px]">{gw.sample_rows.slice(0, 5).join(', ')}</td>
                                <td className="p-1.5 text-stone-600 max-w-xs truncate" title={gw.description}>{gw.description}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Existing Batch Replacement Confirmation */}
                  {previewData.is_existing_batch && previewData.can_confirm && (
                    <div className="p-3 bg-amber-50 border border-amber-300 rounded-xl space-y-2">
                      <p className="text-xs text-amber-800 font-medium">
                        ⚠️ An active stock statement for {MONTH_NAMES[selectedMonth - 1]} {selectedYear} already exists
                        (uploaded on {formatIST(previewData.existing_batch_date)}). Uploading will replace and supersede it.
                      </p>
                      <label className="flex items-center gap-2 text-xs font-semibold text-stone-800 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={replaceConfirmed}
                          onChange={e => setReplaceConfirmed(e.target.checked)}
                          className="rounded text-erp-orange focus:ring-erp-orange"
                        />
                        <span>I confirm replacing the previous stock statement</span>
                      </label>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            {previewData && (
              <div className="flex items-center justify-between pt-3 border-t border-stone-200">
                <button
                  type="button"
                  onClick={() => setPreviewData(null)}
                  className="text-xs font-medium text-stone-600 hover:text-stone-800 px-3 py-1.5"
                >
                  Choose another file
                </button>

                <button
                  type="button"
                  onClick={handleConfirmUpload}
                  disabled={
                    !previewData.can_confirm ||
                    (previewData.is_existing_batch && !replaceConfirmed) ||
                    isConfirming
                  }
                  className="flex items-center gap-2 text-xs font-semibold bg-emerald-600 text-white px-4 py-2 rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-colors shadow-xs"
                >
                  {isConfirming ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      Saving to database...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Confirm & Save Statement
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
