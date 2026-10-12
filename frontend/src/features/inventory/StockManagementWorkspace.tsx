import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  ArrowDownToLine,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Save,
  Search,
  Sliders,
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
}

export interface StockManagementSummary {
  item_count: number;
  missing_limits_count: number;
  min_exceeds_max_count: number;
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
    description: string;
    type: 'NEW' | 'REMOVED' | 'CHANGED';
    field?: string;
    old_value?: any;
    new_value?: any;
  }>;
}

export interface RowIssue {
  row: number;
  column: string;
  description: string;
  severity: 'ERROR' | 'WARNING';
}

export interface StockParameterPreviewResponse {
  month: number;
  year: number;
  effective_date: string;
  detected_title: string | null;
  source_filename: string;
  file_token: string;
  is_existing_batch: boolean;
  existing_batch_filename: string | null;
  errors: RowIssue[];
  warnings: RowIssue[];
  unknown_items: string[];
  comparison: ComparisonSummary;
  total_rows: number;
  lines_preview: StockParameterRecord[];
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

function formatQty(val?: number | string | null): string {
  if (val === null || val === undefined || val === '') return '—';
  const num = typeof val === 'number' ? val : parseFloat(val);
  if (isNaN(num)) return '—';
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

  const canUpload = user ? canPerform(user, 'inventory', 'import') || canPerform(user, 'inventory', 'create') : false;
  const canEdit = user ? canPerform(user, 'inventory', 'update') || canPerform(user, 'inventory', 'create') : false;

  const loadData = useCallback(async () => {
    if (!selectedMonth || !selectedYear) return;
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const res = await apiClient.get<StockManagementResponse>(
        `/api/v1/inventory/management?month=${selectedMonth}&year=${selectedYear}${
          searchQuery ? `&search=${encodeURIComponent(searchQuery)}` : ''
        }`
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
  }, [selectedMonth, selectedYear, searchQuery]);

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
      formData.append('month', selectedMonth.toString());
      formData.append('year', selectedYear.toString());

      const res = await apiClient.postFormData<StockParameterPreviewResponse>(
        '/api/v1/inventory/management/preview',
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
      await apiClient.post<StockManagementResponse>('/api/v1/inventory/management/confirm', {
        file_token: previewData.file_token,
        month: selectedMonth,
        year: selectedYear,
        replace_confirmed: replaceConfirmed,
      });
      setShowUploadModal(false);
      setUploadFile(null);
      setPreviewData(null);
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

  // Columns definition (8 exact KNL columns)
  const columns: ColumnDef<StockParameterRecord>[] = useMemo(
    () => [
      {
        key: 'category',
        label: 'Category',
        width: 140,
        render: val => <span>{val || '—'}</span>,
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
        width: 130,
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
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-white p-3 rounded-xl border border-stone-200 shadow-xs">
            <span className="text-[11px] font-semibold text-stone-500 uppercase">Items Configured</span>
            <p className="text-base font-bold text-stone-800">{summary.item_count}</p>
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

      {/* 5. Upload & Preview Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-[10000] bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl border border-stone-200 flex flex-col max-h-[90vh]">
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

            <div className="py-4 space-y-4 overflow-y-auto flex-1">
              {/* Target Month Banner */}
              <div className="p-3 bg-erp-vanilla/60 border border-erp-dark-vanilla/40 rounded-xl text-xs text-erp-chocolate">
                <span className="font-semibold">Target Period:</span>{' '}
                {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
                <p className="text-[11px] text-stone-500 mt-0.5">
                  The uploaded parameters will govern stock levels and reorder policies for this month.
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

              {/* Preview Results & Comparison */}
              {previewData && (
                <div className="space-y-3 pt-2">
                  {/* Basic Stats */}
                  <div className="p-3 bg-stone-50 rounded-xl border border-stone-200 text-xs space-y-1">
                    <div className="flex justify-between">
                      <span className="text-stone-600">Detected Sheet Title:</span>
                      <span className="font-semibold text-stone-800">
                        {previewData.detected_title || 'Stock Management'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-stone-600">Total Items in File:</span>
                      <span className="font-semibold text-stone-800">{previewData.total_rows}</span>
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
                        <div className="max-h-32 overflow-y-auto space-y-1 pt-1">
                          {previewData.comparison.changes_sample.map((ch, idx) => (
                            <div
                              key={idx}
                              className="bg-white p-1.5 rounded border border-blue-100 text-[11px] text-stone-700"
                            >
                              <span className="font-semibold">{ch.item_id}:</span>{' '}
                              {ch.type === 'NEW' && <span className="text-emerald-700">New Item added</span>}
                              {ch.type === 'REMOVED' && <span className="text-stone-500">Item omitted</span>}
                              {ch.type === 'CHANGED' && (
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

                  {/* Blocking Errors Display */}
                  {previewData.errors.length > 0 && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-xl space-y-2">
                      <span className="text-xs font-bold text-red-800 flex items-center gap-1.5">
                        <AlertCircle className="w-4 h-4" />
                        {previewData.errors.length} Blocking Errors Detected
                      </span>
                      <div className="max-h-36 overflow-y-auto space-y-1 text-xs text-red-700">
                        {previewData.errors.map((err, i) => (
                          <div key={i} className="bg-white/80 p-1.5 rounded border border-red-200">
                            <span className="font-semibold">Row {err.row}:</span> {err.description}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Existing Batch Replacement Confirmation */}
                  {previewData.is_existing_batch && previewData.can_confirm && (
                    <div className="p-3 bg-amber-50 border border-amber-300 rounded-xl space-y-2">
                      <p className="text-xs text-amber-800 font-medium">
                        ⚠️ Active parameters for {MONTH_NAMES[selectedMonth - 1]} {selectedYear} already exist.
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
                      Saving parameters...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Confirm & Save Parameters
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
