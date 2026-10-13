import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  ArrowDownToLine,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileSpreadsheet,
  Filter,
  Layers,
  RefreshCw,
  Save,
  Search,
  Sliders,
  Sparkles,
  Upload,
  X,
} from 'lucide-react';
import DataTable, { type ColumnDef } from '../../components/DataTable';
import { apiClient, getAccessToken, getApiBaseUrl } from '../../api/client';
import { useAuth } from '../auth/context';
import { canPerform } from '../../core/rbac';

export interface StockParameterRecord {
  id: string;
  item_id: string;
  consumable_id: string | null;
  category: string | null;
  type_of_material: string | null;
  description: string | null;
  min_stock_level: number | string | null;
  max_stock_level: number | string | null;
  min_order_qty: number | string | null;
  lead_time_days: number | null;
  edited_after_import: boolean;
  source_row: number;
  resolution_applied?: string | null;
  resolved_by_name?: string | null;
  resolved_at?: string | null;
  resolution_note?: string | null;
  category_count?: number;
  has_conflicting_limits?: boolean;
}

export interface StockManagementMetadata {
  has_parameters: boolean;
  batch_id: string | null;
  month: number;
  year: number;
  effective_date: string;
  source_filename: string | null;
  status: string | null;
  created_at: string | null;
  created_by_name: string | null;
  updated_at: string | null;
  updated_by_name: string | null;
  row_count: number;
  skipped_rows?: Array<Record<string, any>>;
  resolutions_applied?: Array<Record<string, any>>;
}

export interface StockManagementSummary {
  item_count: number;
  missing_limits_count: number;
  min_exceeds_max_count: number;
  multi_category_items_count?: number;
  ambiguous_limits_items_count?: number;
  skipped_rows_count?: number;
  resolved_rows_count?: number;
}

export interface StockManagementResponse {
  metadata: StockManagementMetadata;
  summary: StockManagementSummary;
  records: StockParameterRecord[];
}

export interface ComparisonSummary {
  has_previous_month: boolean;
  previous_month_label: string | null;
  new_items_count: number;
  removed_items_count: number;
  changed_items_count: number;
  changes_sample: Array<{
    item_id: string;
    description?: string;
    type?: 'NEW' | 'REMOVED' | 'CHANGED';
    field?: string;
    old_value?: any;
    new_value?: any;
    min_old?: string | null;
    min_new?: string | null;
    max_old?: string | null;
    max_new?: string | null;
  }>;
}

export interface RowContentSnapshot {
  row?: number;
  item_id?: string | null;
  category?: string | null;
  type_of_material?: string | null;
  description?: string | null;
  min_stock_level?: string | number | null;
  max_stock_level?: string | number | null;
  min_order_qty?: string | number | null;
  lead_time_days?: string | number | null;
}

export interface PossibleMatchHint {
  item_id: string;
  description?: string | null;
  category?: string | null;
  type_of_material?: string | null;
  source: 'UPLOAD_ROW' | 'CONSUMABLE_MASTER' | string;
  source_row?: number | null;
  min_stock_level?: string | null;
  max_stock_level?: string | null;
  min_order_qty?: string | null;
  lead_time_days?: number | null;
}

export interface RowIssue {
  row: number;
  column: string;
  description: string;
  severity: 'ERROR' | 'WARNING';
  code?: string | null;
  item_id?: string | null;
  suggested_action?: string | null;
  row_content?: RowContentSnapshot | null;
  conflicting_row?: number | null;
  conflicting_row_content?: RowContentSnapshot | null;
  possible_matches?: PossibleMatchHint[];
  resolvable?: boolean;
  allowed_actions?: string[];
  default_action?: string | null;
}

export interface ConsumableOption {
  item_id: string;
  name: string;
  category?: string;
  type_of_material?: string;
}

export interface RowResolutionInput {
  row: number;
  action: string;
  assigned_item_id?: string;
  note?: string;
}

export interface StockParameterPreviewResponse {
  month: number;
  year: number;
  effective_date: string;
  detected_title: string | null;
  source_filename: string;
  file_token: string;
  uniqueness_mode?: string;
  is_existing_batch: boolean;
  existing_batch_filename: string | null;
  errors: RowIssue[];
  warnings: RowIssue[];
  issue_counts_by_code?: Record<string, number>;
  unknown_items: string[];
  consumable_options?: ConsumableOption[];
  comparison: ComparisonSummary;
  total_rows: number;
  unresolved_blocking_count?: number;
  lines_preview: StockParameterRecord[];
  can_confirm: boolean;
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const ISSUE_CODE_LABELS: Record<string, string> = {
  INCOMPLETE_LINE: 'Incomplete Line',
  MISSING_ITEM_ID: 'Missing Item Id',
  UNKNOWN_ITEM_ID: 'Unknown Item Id',
  SAME_CATEGORY_CONFLICT: 'Conflicting Limits',
  EXACT_DUPLICATE: 'Exact Duplicate',
  MULTI_CATEGORY_ITEM: 'Multi-Category Item',
  MIN_EXCEEDS_MAX: 'Min > Max Violation',
  EMPTY_LIMIT: 'Empty Limit Field',
  MASTER_CATEGORY_DIFF: 'Category Differs from Master',
  MASTER_TYPE_DIFF: 'Type Differs from Master',
  LARGE_LIMIT_CHANGE: 'Large Limit Change',
};

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

function formatQty(val?: number | string | null): string {
  if (val === null || val === undefined || val === '') return '—';
  const num = typeof val === 'number' ? val : parseFloat(val);
  if (isNaN(num)) return String(val);
  return num.toLocaleString('en-IN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 4,
  });
}

export default function StockManagementWorkspace() {
  const { user } = useAuth();
  const now = new Date();
  const [selectedMonth, setSelectedMonth] = useState<number>(now.getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState<number>(now.getFullYear());
  const [searchQuery, setSearchQuery] = useState('');
  const [multiCategoryOnly, setMultiCategoryOnly] = useState(false);

  const [records, setRecords] = useState<StockParameterRecord[]>([]);
  const [originalRecords, setOriginalRecords] = useState<Map<string, StockParameterRecord>>(new Map());
  const [metadata, setMetadata] = useState<StockManagementMetadata | null>(null);
  const [summary, setSummary] = useState<StockManagementSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Dirty state tracking for inline edits
  const [dirtyMap, setDirtyMap] = useState<Map<string, Partial<StockParameterRecord>>>(new Map());
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  // Selected row IDs
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Upload modal state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [previewData, setPreviewData] = useState<StockParameterPreviewResponse | null>(null);
  const [replaceConfirmed, setReplaceConfirmed] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [showComparisonDetails, setShowComparisonDetails] = useState(false);

  // Issue filter & row resolutions inside the upload modal
  const [issueTypeFilter, setIssueTypeFilter] = useState<string>('ALL');
  const [resolutions, setResolutions] = useState<Record<number, RowResolutionInput>>({});

  const canUpload = user ? canPerform(user, 'inventory', 'import') || canPerform(user, 'inventory', 'create') : false;
  const canEdit = user ? canPerform(user, 'inventory', 'update') || canPerform(user, 'inventory', 'create') : false;

  const loadData = useCallback(async () => {
    if (!selectedMonth || !selectedYear) return;
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const params = new URLSearchParams({
        month: String(selectedMonth),
        year: String(selectedYear),
      });
      if (searchQuery) params.set('search', searchQuery);
      if (multiCategoryOnly) params.set('multi_category_only', 'true');

      const res = await apiClient.get<StockManagementResponse>(
        `/api/v1/inventory/management?${params.toString()}`
      );
      setRecords(res.records || []);
      const orig = new Map<string, StockParameterRecord>();
      (res.records || []).forEach(r => orig.set(r.id, { ...r }));
      setOriginalRecords(orig);
      setMetadata(res.metadata);
      setSummary(res.summary);
      setDirtyMap(new Map());
      setSelectedIds(new Set());
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load stock parameters.');
      setRecords([]);
      setOriginalRecords(new Map());
      setMetadata(null);
      setSummary(null);
    } finally {
      setIsLoading(false);
    }
  }, [selectedMonth, selectedYear, searchQuery, multiCategoryOnly]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle cell edit
  const handleCellChange = useCallback(
    (rowId: string, colKey: string, value: string) => {
      setRecords(prev =>
        prev.map(row => {
          if (row.id !== rowId) return row;
          let parsedVal: any = value;
          if (colKey === 'lead_time_days') {
            parsedVal = value === '' ? null : parseInt(value, 10);
            if (isNaN(parsedVal)) parsedVal = null;
          } else {
            parsedVal = value === '' ? null : parseFloat(value);
            if (isNaN(parsedVal)) parsedVal = null;
          }
          return { ...row, [colKey]: parsedVal };
        })
      );

      setDirtyMap(prev => {
        const next = new Map(prev);
        const existing = next.get(rowId) || {};
        let parsedVal: any = value;
        if (colKey === 'lead_time_days') {
          parsedVal = value === '' ? null : parseInt(value, 10);
          if (isNaN(parsedVal)) parsedVal = null;
        } else {
          parsedVal = value === '' ? null : parseFloat(value);
          if (isNaN(parsedVal)) parsedVal = null;
        }
        next.set(rowId, { ...existing, [colKey]: parsedVal });
        return next;
      });
    },
    []
  );

  // Save batch updates (Ctrl+S)
  const handleSave = useCallback(async () => {
    if (dirtyMap.size === 0) return;
    setSaveStatus('saving');
    try {
      const updates = Array.from(dirtyMap.entries()).map(([id, changes]) => ({
        id,
        min_stock_level: changes.min_stock_level,
        max_stock_level: changes.max_stock_level,
        min_order_qty: changes.min_order_qty,
        lead_time_days: changes.lead_time_days,
      }));

      await apiClient.patch('/api/v1/inventory/management/batch-update', {
        month: selectedMonth,
        year: selectedYear,
        updates,
      });

      setSaveStatus('saved');
      setDirtyMap(new Map());
      await loadData();
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch (err: any) {
      setSaveStatus('error');
      alert(`Save failed: ${err.message}`);
    }
  }, [dirtyMap, selectedMonth, selectedYear, loadData]);

  // Global Ctrl+S key listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleSave]);

  // Export Stock Management
  const handleExport = async () => {
    try {
      const token = getAccessToken();
      const url = `${getApiBaseUrl()}/api/v1/inventory/management/export?month=${selectedMonth}&year=${selectedYear}`;
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error('Download failed');
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `Stock_Management_${MONTH_NAMES[selectedMonth - 1]}_${selectedYear}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(blobUrl);
    } catch (err: any) {
      alert(`Export failed: ${err.message}`);
    }
  };

  // Download Import Summary (.xlsx) with skipped & resolved rows
  const handleDownloadImportSummary = async () => {
    try {
      const token = getAccessToken();
      const url = `${getApiBaseUrl()}/api/v1/inventory/management/import-summary?month=${selectedMonth}&year=${selectedYear}`;
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error('Failed to download import summary');
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `Import_Summary_${MONTH_NAMES[selectedMonth - 1]}_${selectedYear}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(blobUrl);
    } catch (err: any) {
      alert(`Download failed: ${err.message}`);
    }
  };

  // Download Preview Error Report (.xlsx)
  const handleDownloadErrorReport = async () => {
    if (!previewData?.file_token) return;
    try {
      const token = getAccessToken();
      const url = `${getApiBaseUrl()}/api/v1/inventory/management/preview-errors?file_token=${encodeURIComponent(
        previewData.file_token
      )}`;
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error('Failed to download error report');
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `Error_Report_${previewData.source_filename || 'stock_management.xlsx'}`;
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
    setIssueTypeFilter('ALL');
    setResolutions({});

    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('month', selectedMonth.toString());
      formData.append('year', selectedYear.toString());

      const res = await apiClient.postFormData<StockParameterPreviewResponse>(
        '/api/v1/inventory/management/preview',
        formData
      );
      setPreviewData(res);

      // Initialize default actions for warnings that have default_action (EXACT_DUPLICATE -> KEEP_FIRST, MULTI_CATEGORY_ITEM -> KEEP_BOTH)
      // Blocking errors NEVER get auto-resolved — user must choose explicitly.
      const initialRes: Record<number, RowResolutionInput> = {};
      for (const w of res.warnings || []) {
        if (w.resolvable && w.default_action) {
          initialRes[w.row] = {
            row: w.row,
            action: w.default_action,
          };
        }
      }
      setResolutions(initialRes);
    } catch (err: any) {
      setUploadError(err.message || 'Validation failed. Check your file format.');
    } finally {
      setIsPreviewing(false);
    }
  };

  // Fast lookup set of valid Consumable Master Item Ids
  const validConsumableCodes = useMemo(() => {
    const s = new Set<string>();
    (previewData?.consumable_options || []).forEach(c => {
      if (c.item_id) s.add(c.item_id.trim().toUpperCase());
    });
    return s;
  }, [previewData?.consumable_options]);

  // Update a row resolution in dialog state
  const handleSetRowResolution = useCallback(
    (row: number, action: string, assigned_item_id?: string) => {
      setResolutions(prev => {
        const next = { ...prev };
        if (!action) {
          delete next[row];
        } else {
          next[row] = {
            row,
            action,
            assigned_item_id:
              assigned_item_id !== undefined
                ? assigned_item_id
                : prev[row]?.assigned_item_id || '',
          };
        }
        return next;
      });
    },
    []
  );

  // Check if a blocking error row has a complete, valid resolution selected
  const isBlockingIssueResolved = useCallback(
    (issue: RowIssue): boolean => {
      if (issue.resolvable === false) return false;
      const res = resolutions[issue.row];
      if (!res || !res.action) return false;
      if (res.action === 'ASSIGN_ITEM_ID') {
        const cleaned = (res.assigned_item_id || '').trim().toUpperCase();
        if (!cleaned) return false;
        if (validConsumableCodes.size > 0 && !validConsumableCodes.has(cleaned)) {
          return false;
        }
      }
      return true;
    },
    [resolutions, validConsumableCodes]
  );

  // Count remaining unresolved blocking errors
  const unresolvedBlockingErrorsCount = useMemo(() => {
    if (!previewData) return 0;
    return (previewData.errors || []).filter(err => !isBlockingIssueResolved(err)).length;
  }, [previewData, isBlockingIssueResolved]);

  const canConfirmImport = useMemo(() => {
    if (!previewData) return false;
    if (unresolvedBlockingErrorsCount > 0) return false;
    if (previewData.is_existing_batch && !replaceConfirmed) return false;
    return true;
  }, [previewData, unresolvedBlockingErrorsCount, replaceConfirmed]);

  // All resolvable problem rows (all blocking errors + duplicate/multi-category warnings)
  const resolvableIssues = useMemo(() => {
    if (!previewData) return [];
    const list: RowIssue[] = [];
    const seenRowCode = new Set<string>();
    for (const err of previewData.errors || []) {
      const key = `${err.row}:${err.code || 'ERR'}`;
      if (!seenRowCode.has(key)) {
        seenRowCode.add(key);
        list.push(err);
      }
    }
    for (const warn of previewData.warnings || []) {
      if (warn.resolvable || warn.code === 'EXACT_DUPLICATE' || warn.code === 'MULTI_CATEGORY_ITEM') {
        const key = `${warn.row}:${warn.code || 'WARN'}`;
        if (!seenRowCode.has(key)) {
          seenRowCode.add(key);
          list.push(warn);
        }
      }
    }
    return list.sort((a, b) => {
      if (a.severity !== b.severity) return a.severity === 'ERROR' ? -1 : 1;
      return a.row - b.row;
    });
  }, [previewData]);

  // All issues for the filterable log
  const allPreviewIssues = useMemo(() => {
    if (!previewData) return [];
    return [...(previewData.errors || []), ...(previewData.warnings || [])];
  }, [previewData]);

  const issueCountsByType = useMemo(() => {
    const counts: Record<string, number> = { ALL: allPreviewIssues.length };
    for (const iss of allPreviewIssues) {
      const key = iss.code || iss.severity;
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  }, [allPreviewIssues]);

  const filteredIssues = useMemo(() => {
    if (issueTypeFilter === 'ALL') return allPreviewIssues;
    if (issueTypeFilter === 'ERROR') return allPreviewIssues.filter(i => i.severity === 'ERROR');
    return allPreviewIssues.filter(i => (i.code || i.severity) === issueTypeFilter);
  }, [allPreviewIssues, issueTypeFilter]);

  // Confirm Upload
  const handleConfirmUpload = async () => {
    if (!previewData || !canConfirmImport) return;
    setIsConfirming(true);
    setUploadError(null);

    try {
      const resolutionPayload = Object.values(resolutions);
      await apiClient.post<StockManagementResponse>('/api/v1/inventory/management/confirm', {
        file_token: previewData.file_token,
        month: selectedMonth,
        year: selectedYear,
        replace_confirmed: replaceConfirmed,
        resolutions: resolutionPayload,
      });
      setShowUploadModal(false);
      setUploadFile(null);
      setPreviewData(null);
      setResolutions({});
      await loadData();
    } catch (err: any) {
      setUploadError(err.message || 'Failed to save parameters.');
    } finally {
      setIsConfirming(false);
    }
  };

  // Discard changes
  const handleDiscard = () => {
    if (dirtyMap.size === 0) return;
    if (window.confirm('Discard all unsaved edits?')) {
      const origList: StockParameterRecord[] = [];
      originalRecords.forEach(r => origList.push({ ...r }));
      setRecords(origList);
      setDirtyMap(new Map());
    }
  };

  // Columns definition (8 exact KNL columns + multi-category & resolution indicators)
  const columns: ColumnDef<StockParameterRecord>[] = useMemo(
    () => [
      {
        key: 'category',
        label: 'Category',
        width: 170,
        render: (val, row) => (
          <div className="flex items-center gap-1.5">
            <span className="truncate" title={val || ''}>{val || '—'}</span>
            {(row.category_count || 1) > 1 && (
              <span
                title={
                  row.has_conflicting_limits
                    ? `Item ${row.item_id} appears in ${row.category_count} categories with DIFFERENT stock limits`
                    : `Item ${row.item_id} appears in ${row.category_count} categories with identical limits`
                }
                className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold shrink-0 ${
                  row.has_conflicting_limits
                    ? 'bg-amber-100 text-amber-800 border border-amber-300'
                    : 'bg-blue-50 text-blue-700 border border-blue-200'
                }`}
              >
                <Layers className="w-2.5 h-2.5" />
                {row.category_count} cats
              </span>
            )}
          </div>
        ),
      },
      {
        key: 'type_of_material',
        label: 'Type of Material',
        width: 160,
        render: val => <span>{val || '—'}</span>,
      },
      {
        key: 'item_id',
        label: 'Item Id',
        width: 150,
        isSticky: true,
        render: (val, row) => (
          <div className="flex items-center gap-1.5 font-medium">
            <span>{val}</span>
            {row.edited_after_import && (
              <span
                title="Edited after upload"
                className="w-1.5 h-1.5 rounded-full bg-blue-500"
              />
            )}
            {row.resolution_applied && row.resolution_applied !== 'NONE' && (
              <span
                title={`${row.resolution_note || row.resolution_applied}${
                  row.resolved_by_name ? ` by ${row.resolved_by_name}` : ''
                }`}
                className="px-1 py-0.2 rounded text-[9px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200"
              >
                {row.resolution_applied === 'ASSIGNED_ITEM_ID'
                  ? 'Assigned ID'
                  : row.resolution_applied === 'KEPT_FIRST'
                  ? 'Kept 1st'
                  : row.resolution_applied === 'KEPT_SECOND'
                  ? 'Kept 2nd'
                  : 'Multi-Cat'}
              </span>
            )}
          </div>
        ),
      },
      {
        key: 'description',
        label: 'Description',
        width: 260,
        render: val => <span className="truncate block" title={val || ''}>{val || '—'}</span>,
      },
      {
        key: 'min_stock_level',
        label: 'Min. Stock Level',
        width: 140,
        align: 'right',
        type: 'number',
        isEditable: canEdit,
        render: (val, row) => {
          const isInvalid =
            row.min_stock_level !== null &&
            row.max_stock_level !== null &&
            Number(row.min_stock_level) > Number(row.max_stock_level);
          return (
            <span
              className={isInvalid ? 'text-red-700 font-bold bg-red-50 px-1 rounded' : ''}
              title={isInvalid ? 'Min Stock Level cannot exceed Max Stock Level' : undefined}
            >
              {formatQty(val)}
            </span>
          );
        },
      },
      {
        key: 'max_stock_level',
        label: 'Max. Stock Level',
        width: 140,
        align: 'right',
        type: 'number',
        isEditable: canEdit,
        render: val => <span>{formatQty(val)}</span>,
      },
      {
        key: 'min_order_qty',
        label: 'Min Order Qty',
        width: 130,
        align: 'right',
        type: 'number',
        isEditable: canEdit,
        render: val => <span>{formatQty(val)}</span>,
      },
      {
        key: 'lead_time_days',
        label: 'Lead Time in Days',
        width: 140,
        align: 'right',
        type: 'number',
        isEditable: canEdit,
        render: val => <span>{val !== null && val !== undefined ? `${val} d` : '—'}</span>,
      },
    ],
    [canEdit]
  );

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* 1. Header & Top-Right Persisted Metadata */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-4 rounded-xl border border-stone-200 shadow-xs">
        <div>
          <div className="flex items-center gap-2">
            <Sliders className="w-5 h-5 text-erp-orange" />
            <h1 className="text-lg font-bold text-erp-chocolate tracking-tight">
              Stock Management
            </h1>
            <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-erp-vanilla text-erp-chocolate border border-erp-dark-vanilla/40">
              {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
            </span>
          </div>
          <p className="text-xs text-stone-500 mt-0.5">
            Stock control parameters (MSL, Max Level, MOQ, Lead Time in days). Editable directly or imported monthly.
          </p>
        </div>

        {/* Persisted Metadata in top-right corner */}
        <div className="text-right text-xs text-stone-600 bg-stone-50 px-3 py-2 rounded-lg border border-stone-200 space-y-0.5">
          {metadata && metadata.has_parameters ? (
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
            <div className="text-stone-400 italic">No parameters uploaded for selected month</div>
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

          {/* Upload Button */}
          <button
            type="button"
            onClick={() => {
              setShowUploadModal(true);
              setUploadFile(null);
              setPreviewData(null);
              setUploadError(null);
              setResolutions({});
            }}
            disabled={!canUpload || !selectedMonth || !selectedYear || isLoading}
            className="flex items-center gap-1.5 text-xs font-semibold bg-erp-orange text-white px-3 py-1.5 rounded-lg shadow-xs hover:bg-erp-orange/90 disabled:opacity-50 transition-colors"
            title={canUpload ? 'Upload stock management parameters spreadsheet' : 'Permission required'}
          >
            <Upload className="w-3.5 h-3.5" />
            Upload parameters
          </button>

          {/* Save Edits (Ctrl+S) */}
          {canEdit && (
            <button
              type="button"
              onClick={handleSave}
              disabled={dirtyMap.size === 0 || saveStatus === 'saving'}
              className="flex items-center gap-1.5 text-xs font-semibold bg-emerald-600 text-white px-3 py-1.5 rounded-lg shadow-xs hover:bg-emerald-700 disabled:opacity-50 transition-colors"
              title="Save changes (Ctrl+S)"
            >
              <Save className="w-3.5 h-3.5" />
              <span>Save</span>
              {dirtyMap.size > 0 && (
                <span className="px-1.5 py-0.2 bg-white/20 rounded-full text-[10px]">
                  {dirtyMap.size}
                </span>
              )}
            </button>
          )}

          {/* Discard Edits */}
          {dirtyMap.size > 0 && (
            <button
              type="button"
              onClick={handleDiscard}
              className="text-xs text-stone-600 hover:text-stone-800 px-2 py-1.5 underline"
            >
              Discard edits
            </button>
          )}

          {/* Multi-Category Filter Toggle */}
          {metadata?.has_parameters && (summary?.multi_category_items_count || 0) > 0 && (
            <button
              type="button"
              onClick={() => setMultiCategoryOnly(prev => !prev)}
              className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
                multiCategoryOnly
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-stone-700 border-stone-300 hover:bg-stone-50'
              }`}
              title="Filter items that appear under multiple categories"
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Multi-category ({summary?.multi_category_items_count})</span>
            </button>
          )}

          {/* Export to Excel */}
          <button
            type="button"
            onClick={handleExport}
            disabled={!metadata?.has_parameters || records.length === 0}
            className="flex items-center gap-1.5 text-xs font-medium border border-stone-300 bg-white hover:bg-stone-50 text-stone-700 px-3 py-1.5 rounded-lg disabled:opacity-50 transition-colors"
          >
            <ArrowDownToLine className="w-3.5 h-3.5 text-stone-600" />
            Export Excel
          </button>

          {/* Import Summary (.xlsx) with Skipped & Resolved Rows */}
          {metadata?.has_parameters && (
            <button
              type="button"
              onClick={handleDownloadImportSummary}
              className="flex items-center gap-1.5 text-xs font-medium border border-stone-300 bg-white hover:bg-stone-50 text-stone-700 px-3 py-1.5 rounded-lg transition-colors"
              title="Download Import Summary (.xlsx) including skipped and resolved rows"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-700" />
              <span>Import Summary</span>
              {(summary?.skipped_rows_count || 0) > 0 && (
                <span className="px-1.5 py-0.2 rounded-full bg-amber-100 text-amber-800 text-[10px] font-bold">
                  {summary?.skipped_rows_count} skipped
                </span>
              )}
            </button>
          )}

          {/* Refresh */}
          <button
            type="button"
            onClick={() => loadData()}
            disabled={isLoading}
            className="p-1.5 border border-stone-300 rounded-lg hover:bg-stone-50 text-stone-600 disabled:opacity-50 transition-colors"
            title="Refresh parameters"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Search Filter */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-stone-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search items or category..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="text-xs pl-8 pr-3 py-1.5 border border-stone-300 rounded-lg w-56 focus:outline-none focus:ring-1 focus:ring-erp-orange"
          />
        </div>
      </div>

      {/* 3. Summary Strip */}
      {summary && metadata?.has_parameters && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="bg-white p-3 rounded-xl border border-stone-200 shadow-xs">
            <span className="text-[11px] font-semibold text-stone-500 uppercase">Parameter Lines</span>
            <p className="text-base font-bold text-stone-800">{summary.item_count}</p>
          </div>
          <div className="bg-white p-3 rounded-xl border border-stone-200 shadow-xs">
            <span className="text-[11px] font-semibold text-blue-700 uppercase">Multi-Category Items</span>
            <p className="text-base font-bold text-stone-800">
              {summary.multi_category_items_count || 0} items
              {(summary.ambiguous_limits_items_count || 0) > 0 && (
                <span className="ml-1.5 text-xs font-semibold text-amber-700">
                  ({summary.ambiguous_limits_items_count} diff limits)
                </span>
              )}
            </p>
          </div>
          <div className="bg-white p-3 rounded-xl border border-stone-200 shadow-xs">
            <span className="text-[11px] font-semibold text-amber-700 uppercase">Missing Limits</span>
            <p className="text-base font-bold text-stone-800">{summary.missing_limits_count} items</p>
          </div>
          <div className="bg-white p-3 rounded-xl border border-stone-200 shadow-xs">
            <span className="text-[11px] font-semibold text-red-700 uppercase">Min &gt; Max Violations</span>
            <p
              className={`text-base font-bold ${
                summary.min_exceeds_max_count > 0 ? 'text-red-700' : 'text-emerald-600'
              }`}
            >
              {summary.min_exceeds_max_count}
            </p>
          </div>
          <div className="bg-white p-3 rounded-xl border border-stone-200 shadow-xs">
            <span className="text-[11px] font-semibold text-stone-500 uppercase">Unsaved Edits</span>
            <p
              className={`text-base font-bold ${
                dirtyMap.size > 0 ? 'text-erp-orange' : 'text-stone-400'
              }`}
            >
              {dirtyMap.size} items
            </p>
          </div>
        </div>
      )}

      {/* Error alert if load failed */}
      {errorMsg && (
        <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* 4. Table Area */}
      <div className="flex-1 min-h-0 bg-white rounded-xl border border-stone-200 shadow-xs overflow-hidden flex flex-col">
        <DataTable
          columns={columns}
          data={records}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          isLoading={isLoading}
          onCellChange={handleCellChange}
          onSave={handleSave}
          saveStatus={saveStatus}
          emptyMessage={
            metadata?.has_parameters
              ? 'No parameters match your search.'
              : `No stock parameters recorded for ${MONTH_NAMES[selectedMonth - 1]} ${selectedYear}. Upload parameters spreadsheet above.`
          }
          storageKey="knl_stock_management_grid"
          canCreate={false}
          canUpdate={canEdit}
          canDelete={false}
        />
      </div>

      {/* 5. Upload, Validation & Interactive Resolution Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-[10000] bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-5xl w-full p-6 shadow-2xl border border-stone-200 flex flex-col max-h-[92vh]">
            <div className="flex items-center justify-between pb-3 border-b border-stone-200">
              <div className="flex items-center gap-2">
                <Sliders className="w-5 h-5 text-erp-orange" />
                <h3 className="text-base font-bold text-erp-chocolate">
                  Upload Stock Management Parameters
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

            <div className="py-4 space-y-4 overflow-y-auto flex-1 pr-1">
              {/* Target Month Banner */}
              <div className="p-3 bg-erp-vanilla/60 border border-erp-dark-vanilla/40 rounded-xl text-xs text-erp-chocolate flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="font-semibold">Target Period:</span>{' '}
                  {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
                  <p className="text-[11px] text-stone-500 mt-0.5">
                    The uploaded parameters will govern stock levels and reorder policies for this month.
                  </p>
                </div>
                {previewData?.file_token && allPreviewIssues.length > 0 && (
                  <button
                    type="button"
                    onClick={handleDownloadErrorReport}
                    className="flex items-center gap-1.5 text-xs font-semibold bg-white border border-stone-300 text-stone-800 px-3 py-1.5 rounded-lg hover:bg-stone-50 shadow-2xs"
                  >
                    <ArrowDownToLine className="w-3.5 h-3.5 text-red-700" />
                    Download Error Report (.xlsx)
                  </button>
                )}
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
                    setResolutions({});
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
                        Preview & Compare
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

              {/* Preview Results, Interactive Resolution Table & Detailed Issue Log */}
              {previewData && (
                <div className="space-y-4 pt-1">
                  {/* Datalist of Consumable Master items for Assign Item Id */}
                  <datalist id="consumable-master-options">
                    {(previewData.consumable_options || []).map(opt => (
                      <option key={opt.item_id} value={opt.item_id}>
                        {opt.name} {opt.category ? `(${opt.category})` : ''}
                      </option>
                    ))}
                  </datalist>

                  {/* Basic Stats */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 text-xs">
                    <div className="p-2.5 bg-stone-50 rounded-xl border border-stone-200">
                      <span className="text-[10px] uppercase font-semibold text-stone-500 block">
                        Detected Sheet Title
                      </span>
                      <span className="font-bold text-stone-800 truncate block">
                        {previewData.detected_title || 'Stock Management'}
                      </span>
                    </div>
                    <div className="p-2.5 bg-stone-50 rounded-xl border border-stone-200">
                      <span className="text-[10px] uppercase font-semibold text-stone-500 block">
                        Total Rows in File
                      </span>
                      <span className="font-bold text-stone-800">{previewData.total_rows}</span>
                    </div>
                    <div
                      className={`p-2.5 rounded-xl border ${
                        unresolvedBlockingErrorsCount > 0
                          ? 'bg-red-50 border-red-200 text-red-900'
                          : 'bg-emerald-50 border-emerald-200 text-emerald-900'
                      }`}
                    >
                      <span className="text-[10px] uppercase font-semibold block">
                        Blocking Problems
                      </span>
                      <span className="font-bold">
                        {unresolvedBlockingErrorsCount} unresolved (of {previewData.errors.length})
                      </span>
                    </div>
                    <div className="p-2.5 bg-amber-50/70 rounded-xl border border-amber-200 text-amber-900">
                      <span className="text-[10px] uppercase font-semibold block">
                        Warnings &amp; Notices
                      </span>
                      <span className="font-bold">{previewData.warnings.length}</span>
                    </div>
                  </div>

                  {/* Changes since last month summary */}
                  {previewData.comparison.has_previous_month && (
                    <div className="p-3 bg-blue-50 border border-blue-200 rounded-xl space-y-2 text-xs text-blue-900">
                      <div className="flex items-center justify-between">
                        <span className="font-bold">
                          Changes since last month ({previewData.comparison.previous_month_label}):
                        </span>
                        {previewData.comparison.changes_sample.length > 0 && (
                          <button
                            type="button"
                            onClick={() => setShowComparisonDetails(prev => !prev)}
                            className="text-[11px] font-semibold text-blue-700 underline flex items-center gap-0.5"
                          >
                            {showComparisonDetails ? 'Hide details' : 'View sample changes'}
                            {showComparisonDetails ? (
                              <ChevronDown className="w-3 h-3" />
                            ) : (
                              <ChevronRight className="w-3 h-3" />
                            )}
                          </button>
                        )}
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-center pt-1">
                        <div className="bg-white p-1.5 rounded border border-blue-200">
                          <span className="block text-[10px] text-stone-500 uppercase">New Items</span>
                          <span className="font-bold text-emerald-700">
                            {previewData.comparison.new_items_count}
                          </span>
                        </div>
                        <div className="bg-white p-1.5 rounded border border-blue-200">
                          <span className="block text-[10px] text-stone-500 uppercase">Removed Items</span>
                          <span className="font-bold text-stone-600">
                            {previewData.comparison.removed_items_count}
                          </span>
                        </div>
                        <div className="bg-white p-1.5 rounded border border-blue-200">
                          <span className="block text-[10px] text-stone-500 uppercase">Changed Limits</span>
                          <span className="font-bold text-amber-700">
                            {previewData.comparison.changed_items_count}
                          </span>
                        </div>
                      </div>

                      {showComparisonDetails && previewData.comparison.changes_sample.length > 0 && (
                        <div className="max-h-28 overflow-y-auto space-y-1 pt-1">
                          {previewData.comparison.changes_sample.map((ch, idx) => (
                            <div
                              key={idx}
                              className="bg-white p-1.5 rounded border border-blue-100 text-[11px] text-stone-700"
                            >
                              <span className="font-semibold">{ch.item_id}:</span>{' '}
                              {ch.min_old !== undefined || ch.max_old !== undefined ? (
                                <span className="text-amber-800">
                                  Min: {ch.min_old ?? '—'} &rarr; {ch.min_new ?? '—'} | Max:{' '}
                                  {ch.max_old ?? '—'} &rarr; {ch.max_new ?? '—'}
                                </span>
                              ) : (
                                <span className="text-amber-800">
                                  {ch.field}: {String(ch.old_value)} &rarr; {String(ch.new_value)}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* INTERACTIVE RESOLUTION TABLE FOR PROBLEM ROWS */}
                  {resolvableIssues.length > 0 && (
                    <div className="border border-stone-300 rounded-xl overflow-hidden bg-white shadow-2xs">
                      <div className="bg-stone-100 px-3.5 py-2.5 border-b border-stone-200 flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <AlertTriangle className="w-4 h-4 text-erp-orange" />
                          <span className="text-xs font-bold text-stone-800">
                            Problem Rows &amp; Duplicate Resolution ({resolvableIssues.length})
                          </span>
                        </div>
                        <span className="text-[11px] text-stone-600">
                          Resolve every blocking row below to enable <strong>Confirm &amp; Save Parameters</strong>.
                        </span>
                      </div>

                      <div className="overflow-x-auto max-h-80 overflow-y-auto">
                        <table className="w-full text-left border-collapse text-xs">
                          <thead className="bg-stone-50 text-stone-600 sticky top-0 z-10 border-b border-stone-200">
                            <tr>
                              <th className="py-2 px-2.5 font-semibold w-16">Row</th>
                              <th className="py-2 px-2.5 font-semibold w-36">Problem Type</th>
                              <th className="py-2 px-2.5 font-semibold">Row Content &amp; Conflict Details</th>
                              <th className="py-2 px-2.5 font-semibold w-64">Resolution Action</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-stone-200">
                            {resolvableIssues.map(issue => {
                              const rc = issue.row_content || {};
                              const crc = issue.conflicting_row_content;
                              const currentRes = resolutions[issue.row];
                              const isBlocking = issue.severity === 'ERROR';
                              const isResolved = isBlocking ? isBlockingIssueResolved(issue) : Boolean(currentRes?.action);
                              const code = issue.code || issue.severity;

                              return (
                                <tr
                                  key={`${issue.row}-${code}`}
                                  className={
                                    isBlocking && !isResolved
                                      ? 'bg-red-50/50'
                                      : isResolved
                                      ? 'bg-emerald-50/30'
                                      : 'bg-amber-50/30'
                                  }
                                >
                                  <td className="py-2.5 px-2.5 align-top font-bold text-stone-800">
                                    #{issue.row}
                                    {issue.conflicting_row && (
                                      <div className="text-[10px] font-normal text-stone-500 mt-0.5">
                                        vs #{issue.conflicting_row}
                                      </div>
                                    )}
                                  </td>

                                  <td className="py-2.5 px-2.5 align-top">
                                    <span
                                      className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                                        isBlocking
                                          ? 'bg-red-100 text-red-800 border border-red-200'
                                          : 'bg-amber-100 text-amber-800 border border-amber-200'
                                      }`}
                                    >
                                      {ISSUE_CODE_LABELS[code] || code}
                                    </span>
                                    <div className="text-[10px] mt-1 font-medium">
                                      {isBlocking ? (
                                        isResolved ? (
                                          <span className="text-emerald-700 flex items-center gap-0.5">
                                            <CheckCircle2 className="w-3 h-3" /> Resolved
                                          </span>
                                        ) : (
                                          <span className="text-red-700">Blocking — Action required</span>
                                        )
                                      ) : (
                                        <span className="text-amber-700">Warning — Review</span>
                                      )}
                                    </div>
                                  </td>

                                  <td className="py-2.5 px-2.5 align-top space-y-1.5">
                                    <div className="font-medium text-stone-800">{issue.description}</div>

                                    {/* Row Content Pill */}
                                    <div className="p-2 rounded bg-white border border-stone-200 text-[11px] text-stone-700 space-y-1">
                                      <div>
                                        <span className="font-semibold text-stone-900">Row {issue.row}:</span>{' '}
                                        <span className="font-mono font-semibold text-erp-chocolate">
                                          {rc.item_id || '(Empty Item Id)'}
                                        </span>{' '}
                                        | Cat: <span className="font-medium">{rc.category || '—'}</span> | Type:{' '}
                                        <span>{rc.type_of_material || '—'}</span> | Desc:{' '}
                                        <span className="italic">{rc.description || '—'}</span>
                                      </div>
                                      <div className="text-stone-600">
                                        Limits &rarr; Min: <strong>{rc.min_stock_level ?? '—'}</strong>, Max:{' '}
                                        <strong>{rc.max_stock_level ?? '—'}</strong>, MOQ:{' '}
                                        <strong>{rc.min_order_qty ?? '—'}</strong>, Lead:{' '}
                                        <strong>{rc.lead_time_days ?? '—'} d</strong>
                                      </div>
                                    </div>

                                    {/* Side-by-side Conflicting Row Content */}
                                    {issue.conflicting_row && crc && (
                                      <div className="p-2 rounded bg-stone-50 border border-stone-300 text-[11px] text-stone-700 space-y-1">
                                        <div>
                                          <span className="font-semibold text-stone-900">
                                            Earlier Row {issue.conflicting_row}:
                                          </span>{' '}
                                          <span className="font-mono font-semibold">{crc.item_id}</span> | Cat:{' '}
                                          <span className="font-medium">{crc.category || '—'}</span> | Type:{' '}
                                          <span>{crc.type_of_material || '—'}</span> | Desc:{' '}
                                          <span className="italic">{crc.description || '—'}</span>
                                        </div>
                                        <div className="text-stone-600">
                                          Limits &rarr; Min: <strong>{crc.min_stock_level ?? '—'}</strong>, Max:{' '}
                                          <strong>{crc.max_stock_level ?? '—'}</strong>, MOQ:{' '}
                                          <strong>{crc.min_order_qty ?? '—'}</strong>, Lead:{' '}
                                          <strong>{crc.lead_time_days ?? '—'} d</strong>
                                        </div>
                                      </div>
                                    )}

                                    {/* Possible Matches Hints (Never auto-assigned) */}
                                    {issue.possible_matches && issue.possible_matches.length > 0 && (
                                      <div className="p-2 rounded bg-blue-50/80 border border-blue-200 text-[11px] text-blue-950 space-y-1">
                                        <div className="font-semibold flex items-center gap-1 text-blue-800">
                                          <Sparkles className="w-3.5 h-3.5" />
                                          Possible match by description (hint only — not auto-applied):
                                        </div>
                                        {issue.possible_matches.map((m, mIdx) => (
                                          <div
                                            key={mIdx}
                                            className="flex flex-wrap items-center justify-between gap-2 bg-white px-2 py-1 rounded border border-blue-100"
                                          >
                                            <div>
                                              <span className="font-mono font-bold text-blue-900">{m.item_id}</span>
                                              {m.source_row ? ` (Row ${m.source_row})` : ' (Consumable Master)'} — Cat:{' '}
                                              <span className="font-medium">{m.category || '—'}</span>
                                              {m.min_stock_level !== null && m.min_stock_level !== undefined && (
                                                <span className="text-stone-600">
                                                  {' '}
                                                  | Min: {m.min_stock_level}, Max: {m.max_stock_level}, MOQ:{' '}
                                                  {m.min_order_qty}, Lead: {m.lead_time_days}d
                                                </span>
                                              )}
                                            </div>
                                            <button
                                              type="button"
                                              onClick={() =>
                                                handleSetRowResolution(issue.row, 'ASSIGN_ITEM_ID', m.item_id)
                                              }
                                              className="px-2 py-0.5 bg-blue-600 text-white rounded text-[10px] font-semibold hover:bg-blue-700 shrink-0"
                                            >
                                              Use {m.item_id}
                                            </button>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                  </td>

                                  <td className="py-2.5 px-2.5 align-top space-y-2">
                                    <select
                                      value={currentRes?.action || ''}
                                      onChange={e => handleSetRowResolution(issue.row, e.target.value)}
                                      className={`w-full text-xs border rounded-lg px-2 py-1.5 font-medium focus:outline-none focus:ring-1 focus:ring-erp-orange ${
                                        isBlocking && !isResolved
                                          ? 'border-red-300 bg-white text-red-900'
                                          : 'border-stone-300 bg-white text-stone-800'
                                      }`}
                                    >
                                      <option value="">-- Choose action --</option>
                                      {(issue.allowed_actions || []).includes('KEEP_FIRST') && (
                                        <option value="KEEP_FIRST">
                                          Keep first (Row {issue.conflicting_row}), skip Row {issue.row}
                                        </option>
                                      )}
                                      {(issue.allowed_actions || []).includes('KEEP_SECOND') && (
                                        <option value="KEEP_SECOND">
                                          Keep this (Row {issue.row}), replace Row {issue.conflicting_row}
                                        </option>
                                      )}
                                      {(issue.allowed_actions || []).includes('KEEP_BOTH') && (
                                        <option value="KEEP_BOTH">
                                          Keep both rows (separate categories)
                                        </option>
                                      )}
                                      {(issue.allowed_actions || []).includes('ASSIGN_ITEM_ID') && (
                                        <option value="ASSIGN_ITEM_ID">
                                          Assign Item Id from Consumable Master
                                        </option>
                                      )}
                                      {(issue.allowed_actions || []).includes('SKIP_ROW') && (
                                        <option value="SKIP_ROW">
                                          Skip this row (do not import)
                                        </option>
                                      )}
                                    </select>

                                    {currentRes?.action === 'ASSIGN_ITEM_ID' && (
                                      <div className="space-y-1">
                                        <input
                                          type="text"
                                          list="consumable-master-options"
                                          placeholder="Type or pick Item Id (e.g. ABA100009QC)"
                                          value={currentRes.assigned_item_id || ''}
                                          onChange={e =>
                                            handleSetRowResolution(
                                              issue.row,
                                              'ASSIGN_ITEM_ID',
                                              e.target.value
                                            )
                                          }
                                          className="w-full text-xs font-mono border border-stone-300 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-erp-orange"
                                        />
                                        {currentRes.assigned_item_id && (
                                          <div className="text-[10px]">
                                            {validConsumableCodes.size === 0 ||
                                            validConsumableCodes.has(
                                              currentRes.assigned_item_id.trim().toUpperCase()
                                            ) ? (
                                              <span className="text-emerald-700 font-semibold">
                                                ✓ Valid Consumable Master Item Id
                                              </span>
                                            ) : (
                                              <span className="text-red-600 font-semibold">
                                                ✕ Item Id not found in Consumable Master
                                              </span>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    )}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* ALL ERRORS & WARNINGS SCROLLABLE FILTERABLE LIST */}
                  {allPreviewIssues.length > 0 && (
                    <div className="p-3 bg-stone-50 border border-stone-200 rounded-xl space-y-2.5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-xs font-bold text-stone-800 flex items-center gap-1.5">
                          <Filter className="w-3.5 h-3.5 text-stone-600" />
                          Validation Log ({filteredIssues.length} of {allPreviewIssues.length})
                        </span>

                        {/* Filter Pills by Issue Type */}
                        <div className="flex flex-wrap items-center gap-1">
                          {Object.entries(issueCountsByType).map(([codeKey, cnt]) => (
                            <button
                              key={codeKey}
                              type="button"
                              onClick={() => setIssueTypeFilter(codeKey)}
                              className={`px-2 py-0.5 rounded-full text-[10px] font-semibold transition-colors ${
                                issueTypeFilter === codeKey
                                  ? 'bg-erp-chocolate text-white'
                                  : 'bg-white text-stone-700 border border-stone-300 hover:bg-stone-100'
                              }`}
                            >
                              {codeKey === 'ALL' ? 'All' : ISSUE_CODE_LABELS[codeKey] || codeKey} ({cnt})
                            </button>
                          ))}
                        </div>
                      </div>

                      <div className="max-h-40 overflow-y-auto space-y-1 text-xs">
                        {filteredIssues.map((iss, i) => (
                          <div
                            key={i}
                            className={`p-2 rounded border flex items-start justify-between gap-2 ${
                              iss.severity === 'ERROR'
                                ? 'bg-red-50/80 border-red-200 text-red-900'
                                : 'bg-white border-stone-200 text-stone-700'
                            }`}
                          >
                            <div>
                              <span className="font-bold">Row {iss.row}:</span> {iss.description}
                              {iss.suggested_action && (
                                <span className="block text-[11px] text-stone-500 mt-0.5">
                                  Suggested: {iss.suggested_action}
                                </span>
                              )}
                            </div>
                            <span
                              className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase shrink-0 ${
                                iss.severity === 'ERROR'
                                  ? 'bg-red-100 text-red-800'
                                  : 'bg-amber-100 text-amber-800'
                              }`}
                            >
                              {iss.code || iss.severity}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Existing Batch Replacement Confirmation */}
                  {previewData.is_existing_batch && (
                    <div className="p-3 bg-amber-50 border border-amber-300 rounded-xl space-y-2">
                      <p className="text-xs text-amber-800 font-medium">
                        Active parameters for {MONTH_NAMES[selectedMonth - 1]} {selectedYear} already exist.
                        Uploading will supersede the previous parameters for this month.
                      </p>
                      <label className="flex items-center gap-2 text-xs font-semibold text-stone-800 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={replaceConfirmed}
                          onChange={e => setReplaceConfirmed(e.target.checked)}
                          className="rounded text-erp-orange focus:ring-erp-orange"
                        />
                        <span>I confirm replacing existing parameters for this month</span>
                      </label>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            {previewData && (
              <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-stone-200">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setPreviewData(null);
                      setResolutions({});
                    }}
                    className="text-xs font-medium text-stone-600 hover:text-stone-800 px-3 py-1.5 border border-stone-300 rounded-lg"
                  >
                    Choose another file
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowUploadModal(false);
                      setUploadFile(null);
                      setPreviewData(null);
                      setResolutions({});
                    }}
                    className="text-xs font-medium text-red-700 hover:text-red-900 px-3 py-1.5"
                  >
                    Cancel upload
                  </button>
                </div>

                <div className="flex items-center gap-3">
                  {unresolvedBlockingErrorsCount > 0 ? (
                    <span className="text-xs font-semibold text-red-700">
                      {unresolvedBlockingErrorsCount} blocking row(s) require resolution above
                    </span>
                  ) : (
                    <span className="text-xs font-semibold text-emerald-700">
                      All blocking issues resolved — ready to save
                    </span>
                  )}

                  <button
                    type="button"
                    onClick={handleConfirmUpload}
                    disabled={!canConfirmImport || isConfirming}
                    className="flex items-center gap-2 text-xs font-semibold bg-emerald-600 text-white px-4 py-2 rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-colors shadow-xs"
                  >
                    {isConfirming ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        Saving parameters...
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Confirm &amp; Save Parameters
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
