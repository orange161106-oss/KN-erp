import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { apiClient, fetchWithAuth } from '../../api/client';
import { useAuth } from '../auth/context';
import { canPerform } from '../../core/rbac';
import DataTable, { type ColumnDef, type HeaderGroupDef } from '../../components/DataTable';
import Toolbar from '../../components/Toolbar';
import MonthlyExcelUploadModal from './MonthlyExcelUploadModal';
import {
  FileSpreadsheet,
  UploadCloud,
  Download,
  Save,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
  Upload,
} from 'lucide-react';

export interface RequirementRecord {
  id: string;
  plan_id?: string | null;
  planning_period: string;
  planning_month?: number | null;
  planning_year?: number | null;
  revision?: string;
  // Group 1: Component
  part_name: string;
  part_number: string;
  // Group 2: Consumables
  consumable_code: string;
  consumable_name: string;
  process_name: string;
  part_thickness: string;
  process_count: number;
  production_order_qty: string;
  scheduled_consumable_qty: string;
  // Group 3: Operational fields
  plant: string;
  process: string;
  description: string;
  unit: string;
  required_qty: string;
  stock_qty: string;
  shortage_qty: string;
  po_pending_qty: string;
  msl: string;
  status: 'Normal' | 'Low' | 'Critical shortage' | 'Calculated' | 'Configuration required' | string;
  remarks: string | null;
  created_at?: string | null;
  updated_at?: string | null;

  // MRP GRN Tracking & Reconciliation Fields
  opening_stock?: number | string | null;
  grn_received_qty?: number | string | null;
  consumed_qty?: number | string | null;
  closing_stock?: number | string | null;
  gross_requirement?: number | string | null;
  net_order_requirement?: number | string | null;
  last_synced_at?: string | null;
  grn_source_file?: string | null;
  invoice_no?: string | null;
  grn_date?: string | null;
}

export interface MonthlyPlanMetadata {
  has_plan: boolean;
  plan_id?: string | null;
  planning_month?: number | null;
  planning_year?: number | null;
  planning_period: string;
  status: string;
  revision_label: string;
  source_filename?: string | null;
  created_at?: string | null;
  created_by?: string | null;
  created_by_name?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
  updated_by_name?: string | null;
  record_count: number;
  source_workflow?: string | null;
  issue_count?: number;
  grn_reconciled?: boolean;
  last_grn_synced_at?: string | null;
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

function formatDisplayDate(dateStr?: string | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleString(undefined, {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

export default function Requirements(_props: { defaultTab?: 'workspace' | 'mrp' } = {}) {
  const { user } = useAuth();

  // RBAC checks
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const canRead = Boolean(isSuperAdmin || user?.requirements_read || canPerform(user, 'requirements', 'read') || user?.permissions?.includes('requirements.read'));
  const canUpdate = Boolean(isSuperAdmin || user?.requirements_update || canPerform(user, 'requirements', 'update') || user?.permissions?.includes('requirements.calculate'));
  const canExport = Boolean(canRead || canPerform(user, 'requirements', 'export'));
  const canRecalculate = canUpdate;

  // Planning Period State (Month 1-12, Year)
  const [selectedMonth, setSelectedMonth] = useState<number>(10); // Default October
  const [selectedYear, setSelectedYear] = useState<number>(2026);  // Default 2026

  // Plan Metadata State
  const [planMetadata, setPlanMetadata] = useState<MonthlyPlanMetadata | null>(null);
  const productionBased = planMetadata?.source_workflow === 'BASIC_CENTRAL_V1';
  const canEditPlan = canUpdate && !productionBased;

  // Data records & inline editing state
  const [records, setRecords] = useState<RequirementRecord[]>([]);
  const [originalMap, setOriginalMap] = useState<Map<string, RequirementRecord>>(new Map());
  const [modifiedRecords, setModifiedRecords] = useState<Map<string, Partial<RequirementRecord>>>(new Map());

  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [isDownloadingIssues, setIsDownloadingIssues] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Selection & UI state
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set());
  const [selectedCell, setSelectedCell] = useState<{ rowId: string; colKey: keyof RequirementRecord & string } | null>(null);
  const [selectedAuditRow, setSelectedAuditRow] = useState<RequirementRecord | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);

  // MRP GRN Upload Modal State
  const [isGrnModalOpen, setIsGrnModalOpen] = useState(false);
  const [grnFile, setGrnFile] = useState<File | null>(null);
  const [grnTargetPlant, setGrnTargetPlant] = useState('Plant 1');
  const [isGrnUploading, setIsGrnUploading] = useState(false);
  const [grnError, setGrnError] = useState<string | null>(null);
  const grnFileInputRef = useRef<HTMLInputElement>(null);

  // Filter state
  const [searchQuery, setSearchQuery] = useState('');
  const settledSearch = useDebouncedValue(searchQuery);
  const loadGeneration = useRef(0);
  const [plantFilter, setPlantFilter] = useState('');
  const [consumableFilter, setConsumableFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // 2. Load Records for Period
  const loadRecords = useCallback(async () => {
    const generation=++loadGeneration.current;
    setIsLoading(true);
    setStatusMessage(null);
    try {
      const params = new URLSearchParams();
      params.append('month', String(selectedMonth));
      params.append('year', String(selectedYear));
      if (settledSearch) params.append('search', settledSearch);
      if (plantFilter) params.append('plant', plantFilter);
      if (consumableFilter) params.append('consumable', consumableFilter);
      if (statusFilter) params.append('status', statusFilter);

      const view = await apiClient.get<{records:RequirementRecord[];plan_metadata:MonthlyPlanMetadata}>(
        `/api/v1/requirements/workspace/view?${params.toString()}`,60000);
      if(generation!==loadGeneration.current)return;
      const data=view.records;
      setPlanMetadata(view.plan_metadata);

      setRecords(data);
      const orig = new Map<string, RequirementRecord>();
      data.forEach(r => orig.set(r.id, { ...r }));
      setOriginalMap(orig);
      setModifiedRecords(new Map());
      setSelectedRowIds(new Set());
      setStatusMessage(null);
    } catch (err) {
      if(generation!==loadGeneration.current)return;
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to fetch requirements data.',
      });
    } finally {
      if(generation===loadGeneration.current)setIsLoading(false);
    }
  }, [selectedMonth, selectedYear, settledSearch, plantFilter, consumableFilter, statusFilter]);

  useEffect(() => {
    void loadRecords();
    return () => {
      ++loadGeneration.current;
    };
  }, [loadRecords]);

  // Handle inline cell changes for permitted fields
  const handleCellChange = (rowId: string, colKey: keyof RequirementRecord & string, value: string) => {
    if (!canEditPlan) return;
    // Permitted fields: production_order_qty, part_thickness, process_count, remarks
    const permittedKeys = ['production_order_qty', 'part_thickness', 'process_count', 'remarks'];
    if (!permittedKeys.includes(colKey)) return;

    setRecords(prev =>
      prev.map(row => {
        if (row.id !== rowId) return row;
        const updated = { ...row, [colKey]: colKey === 'process_count' ? parseInt(value, 10) || 1 : value };
        return updated;
      })
    );

    setModifiedRecords(prev => {
      const next = new Map(prev);
      const existing = next.get(rowId) || {};
      next.set(rowId, {
        ...existing,
        [colKey]: colKey === 'process_count' ? parseInt(value, 10) || 1 : value,
      });
      return next;
    });
  };

  // Save modified changes transactionally
  const handleSaveChanges = async () => {
    if (modifiedRecords.size === 0) return;
    setIsSaving(true);
    setStatusMessage(null);

    try {
      const payloadRecords = Array.from(modifiedRecords.entries()).map(([id, changes]) => ({
        id,
        production_order_qty: changes.production_order_qty,
        part_thickness: changes.part_thickness,
        process_count: changes.process_count,
        remarks: changes.remarks,
      }));

      const res = await apiClient.put<{
        message: string;
        updated_count: number;
        records: RequirementRecord[];
        plan_metadata: MonthlyPlanMetadata;
      }>('/api/v1/requirements/workspace/records', { records: payloadRecords });

      setRecords(res.records);
      const orig = new Map<string, RequirementRecord>();
      res.records.forEach(r => orig.set(r.id, { ...r }));
      setOriginalMap(orig);
      setModifiedRecords(new Map());
      if (res.plan_metadata) setPlanMetadata(res.plan_metadata);

      setStatusMessage({
        type: 'success',
        text: `Changes saved successfully (${res.updated_count} record${res.updated_count > 1 ? 's' : ''} updated).`,
      });
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to save changes.',
      });
    } finally {
      setIsSaving(false);
    }
  };

  // Discard unsaved changes
  const handleDiscardChanges = () => {
    if (modifiedRecords.size === 0) return;
    setRecords(prev =>
      prev.map(r => {
        const orig = originalMap.get(r.id);
        return orig ? { ...orig } : r;
      })
    );
    setModifiedRecords(new Map());
    setStatusMessage({
      type: 'info',
      text: 'Unsaved changes discarded.',
    });
  };

  // Bulk / single delete rows
  const handleDeleteRows = async (ids: string[]) => {
    if (!ids || ids.length === 0) return;
    try {
      const res = await apiClient.post<{
        message: string;
        deleted_count: number;
        plan_metadata?: MonthlyPlanMetadata;
      }>('/api/v1/requirements/workspace/bulk-delete', { record_ids: ids });

      setRecords(prev => prev.filter(r => !ids.includes(r.id)));
      setOriginalMap(prev => {
        const next = new Map(prev);
        ids.forEach(id => next.delete(id));
        return next;
      });
      setModifiedRecords(prev => {
        const next = new Map(prev);
        ids.forEach(id => next.delete(id));
        return next;
      });
      setSelectedRowIds(prev => {
        const next = new Set(prev);
        ids.forEach(id => next.delete(id));
        return next;
      });
      if (res.plan_metadata) {
        setPlanMetadata(res.plan_metadata);
      }
      setStatusMessage({
        type: 'success',
        text: res.message || `Deleted ${ids.length} record(s) successfully.`,
      });
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to delete records.',
      });
      throw err;
    }
  };

  // Warn before leaving if unsaved changes exist
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (modifiedRecords.size > 0) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [modifiedRecords.size]);

  const handleMonthChange = (newMonth: number) => {
    if (modifiedRecords.size > 0) {
      if (!window.confirm('You have unsaved changes. Discard changes and change month?')) {
        return;
      }
      setModifiedRecords(new Map());
    }
    setSelectedMonth(newMonth);
  };

  const handleYearChange = (newYear: number) => {
    if (modifiedRecords.size > 0) {
      if (!window.confirm('You have unsaved changes. Discard changes and change year?')) {
        return;
      }
      setModifiedRecords(new Map());
    }
    setSelectedYear(newYear);
  };

  // Recalculate deterministic consumable requirements
  const handleRecalculate = async () => {
    setIsRecalculating(true);
    setStatusMessage(null);

    try {
      const res = await apiClient.post<{
        message: string;
        record_count: number;
        critical_shortages: number;
        low_stock: number;
        records: RequirementRecord[];
        plan_metadata: MonthlyPlanMetadata;
      }>(`/api/v1/requirements/workspace/recalculate?month=${selectedMonth}&year=${selectedYear}`, {});

      setRecords(res.records);
      const orig = new Map<string, RequirementRecord>();
      res.records.forEach(r => orig.set(r.id, { ...r }));
      setOriginalMap(orig);
      setModifiedRecords(new Map());
      if (res.plan_metadata) setPlanMetadata(res.plan_metadata);

      setStatusMessage({
        type: 'info',
        text: res.message || 'Recalculation completed using approved deterministic KNL consumption rules.',
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

  // Month-End GRN Ingestion and Overwrite Upsert
  const handleUploadMRPGRN = async () => {
    if (!grnFile) return;
    setIsGrnUploading(true);
    setGrnError(null);
    try {
      const formData = new FormData();
      formData.append('file', grnFile);
      formData.append('plant_id', grnTargetPlant);
      formData.append('planning_month', String(selectedMonth));
      formData.append('planning_year', String(selectedYear));

      const res = await apiClient.post<{
        status: string;
        updated_count: number;
        inserted_count: number;
        period: string;
      }>('/api/v1/mrp/upload-grn', formData);

      setStatusMessage({
        type: 'success',
        text: `GRN uploaded successfully for ${grnTargetPlant} (${res.period}): ${res.updated_count} record(s) updated, ${res.inserted_count} inserted.`,
      });

      setIsGrnModalOpen(false);
      setGrnFile(null);
      // Auto-refresh spreadsheet and metadata immediately without reload
      await loadRecords();
    } catch (err) {
      setGrnError(err instanceof Error ? err.message : 'Failed to ingest GRN file.');
    } finally {
      setIsGrnUploading(false);
    }
  };

  // Export Excel with authentication
  const handleExport = async (mode: 'ALL' | 'FILTERED' | 'SELECTED') => {
    let url = `/api/v1/requirements/workspace/export?month=${selectedMonth}&year=${selectedYear}`;
    const params = new URLSearchParams();

    if (mode === 'SELECTED') {
      Array.from(selectedRowIds).forEach(id => params.append('record_ids', id));
    } else if (mode === 'FILTERED') {
      if (searchQuery) params.append('search', searchQuery);
      if (plantFilter) params.append('plant', plantFilter);
      if (consumableFilter) params.append('consumable', consumableFilter);
      if (statusFilter) params.append('status', statusFilter);
    }

    const q = params.toString();
    if (q) url += `&${q}`;

    try {
      const res = await fetchWithAuth(url);
      if (!res.ok) throw new Error('Download failed');
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `consumable_requirements_${selectedYear}_${String(selectedMonth).padStart(2, '0')}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(blobUrl);
    } catch (err) {
      console.error('Export Excel error:', err);
      setStatusMessage({
        type: 'error',
        text: 'Failed to export requirements spreadsheet.',
      });
    }
  };

  // Download issues list CSV with authentication
  const handleDownloadIssues = async () => {
    setIsDownloadingIssues(true);
    try {
      const period = `${selectedYear}-${String(selectedMonth).padStart(2, '0')}`;
      const response = await fetchWithAuth(
        `/api/v1/requirements/workspace/issues/export?period=${period}`
      );
      if (!response.ok) {
        throw new Error(`Failed to export issues: ${response.statusText}`);
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `requirement_issues_${selectedYear}_${String(selectedMonth).padStart(2, '0')}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Export issues error:", error);
      setStatusMessage({
        type: 'error',
        text: 'Failed to download issues list',
      });
    } finally {
      setIsDownloadingIssues(false);
    }
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
        r.part_name.toLowerCase().includes(q) ||
        r.part_number.toLowerCase().includes(q) ||
        r.consumable_code.toLowerCase().includes(q) ||
        r.consumable_name.toLowerCase().includes(q) ||
        r.process_name.toLowerCase().includes(q) ||
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

  // Section 7A: Grouped Headers
  const headerGroups: HeaderGroupDef[] = useMemo(
    () => [
      {
        label: 'FOR COMPONENT',
        colSpan: 2,
        className: 'p-1 text-center font-bold text-white uppercase tracking-wider text-[11px] border-r border-ink-text/20 bg-brand-navy select-none',
      },
      {
        label: 'FOR CONSUMABLES',
        colSpan: 7,
        className: 'p-1 text-center font-bold text-white uppercase tracking-wider text-[11px] border-r border-ink-text/20 bg-brand-steel select-none',
      },
      {
        label: 'INVENTORY & OPERATIONAL STATUS',
        colSpan: 7,
        className: 'p-1 text-center font-bold text-white uppercase tracking-wider text-[11px] border-r border-ink-text/20 bg-brand-navy select-none',
      },
    ],
    []
  );

  // Section 7A: Fixed Column Definitions with explicit numeric pixel widths
  const columns: ColumnDef<RequirementRecord>[] = useMemo(
    () => [
      // --- Group 1: For Component (Frozen Left Columns) ---
      {
        key: 'part_name',
        label: 'Used For – Part Name',
        width: 200,
        minWidth: 150,
        align: 'left',
        isSticky: true,
        render: val => <span className="font-semibold text-gray-900 truncate block">{val}</span>,
      },
      {
        key: 'part_number',
        label: 'Used Part No. (Production Order)',
        width: 220,
        minWidth: 160,
        align: 'left',
        isSticky: true,
        render: val => <span className="font-mono text-gray-800 font-semibold">{val}</span>,
      },

      // --- Group 2: For Consumables ---
      {
        key: 'consumable_code',
        label: 'Consumable Item ID',
        width: 170,
        minWidth: 130,
        align: 'left',
        render: val => <span className="font-mono font-bold text-blue-900">{val}</span>,
      },
      {
        key: 'consumable_name',
        label: 'Consumable Name',
        width: 240,
        minWidth: 160,
        align: 'left',
        render: val => <span className="text-gray-900 truncate block">{val}</span>,
      },
      {
        key: 'process_name',
        label: 'Process Name',
        width: 160,
        minWidth: 110,
        align: 'left',
      },
      {
        key: 'part_thickness',
        label: 'Part Thickness (mm)',
        width: 140,
        minWidth: 100,
        align: 'right',
        type: 'number',
        isEditable: canUpdate,
        render: val => <span className="font-mono text-gray-800">{val}</span>,
      },
      {
        key: 'process_count',
        label: 'Number of Processes',
        width: 140,
        minWidth: 90,
        align: 'center',
        type: 'number',
        isEditable: canUpdate,
        render: val => <span className="font-mono font-semibold text-gray-800">{val}</span>,
      },
      {
        key: 'production_order_qty',
        label: 'Production Order for Selected Month',
        width: 200,
        minWidth: 140,
        align: 'right',
        type: 'number',
        isEditable: canUpdate,
        render: val => (
          <span className="font-mono font-bold text-gray-950 bg-gray-50/50 px-1 py-0.5 rounded">
            {val}
          </span>
        ),
      },
      {
        key: 'scheduled_consumable_qty',
        label: 'Scheduled Consumable Quantity for Selected Month',
        width: 220,
        minWidth: 150,
        align: 'right',
        type: 'number',
        isEditable: false,
        render: val => <span className="font-mono font-bold text-indigo-950">{val}</span>,
      },

      // --- Group 3: Inventory & Operational Status ---
      {
        key: 'unit',
        label: 'Unit',
        width: 80,
        minWidth: 60,
        align: 'center',
      },
      {
        key: 'stock_qty',
        label: 'Stock Qty',
        width: 120,
        minWidth: 80,
        align: 'right',
        render: val => <span className="font-mono text-gray-700">{val}</span>,
      },
      {
        key: 'grn_received_qty',
        label: 'GRN Received',
        width: 120,
        minWidth: 80,
        align: 'right',
        render: val => (
          <span className="font-mono text-emerald-700 font-semibold">
            {val != null && val !== '' ? String(val) : '—'}
          </span>
        ),
      },
      {
        key: 'shortage_qty',
        label: 'Shortage Qty',
        width: 120,
        minWidth: 80,
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
        key: 'status',
        label: 'Status',
        width: 150,
        minWidth: 110,
        align: 'center',
        render: val => {
          if (val === 'Critical shortage') {
            return (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-800 border border-red-300">
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
          if (val === 'Configuration required') {
            return (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 text-purple-800 border border-purple-300">
                RULE REVIEW
              </span>
            );
          }
          if (val === 'Calculated') {
            return (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 border border-blue-300">
                CALCULATED
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
        width: 220,
        minWidth: 140,
        align: 'left',
        isEditable: canUpdate,
      },
      {
        key: 'id' as any,
        label: 'Audit Trail',
        width: 100,
        minWidth: 80,
        align: 'center',
        render: (_val, row) => (
          <button
            type="button"
            onClick={e => {
              e.stopPropagation();
              setSelectedAuditRow(row);
            }}
            className="px-2 py-0.5 rounded text-2xs font-semibold bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-200 transition-colors shadow-2xs"
          >
            🔍 Audit
          </button>
        ),
      },
    ],
    [canUpdate]
  );

  return (
    <div className="flex flex-col h-full space-y-3 font-['Plus_Jakarta_Sans',sans-serif]">
      {productionBased && (
        <div className="rounded border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900">
          Production-based requirements calculated deterministically from Production order quantities (R0) and Consumption Norms (Sch).
        </div>
      )}
          {/* Top Banner: Module Purpose & Saved Plan Metadata Card */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-lg font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <span>Requirement</span>
            <span className="text-xs font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md border border-slate-200">
              Consumable Planning Module
            </span>
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Manage and recalculate monthly consumable requirements deterministically based on production planning data.
          </p>
        </div>

        {/* Section 6: Top-Right Saved Plan Metadata Card */}
        <div className="flex items-center gap-3">
          <div className="bg-white border border-slate-200 rounded-xl p-3 text-xs shadow-sm min-w-[280px]">
            {planMetadata?.has_plan ? (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between border-b border-slate-100 pb-1.5">
                  <span className="font-bold text-slate-900 text-xs">
                    Period: {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span className="px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded-md text-[10px] font-bold border border-blue-200">
                      {planMetadata.revision_label}
                    </span>
                    <span className="px-1.5 py-0.5 bg-emerald-50 text-emerald-700 rounded-md text-[10px] font-bold border border-emerald-200">
                      {planMetadata.status}
                    </span>
                  </div>
                </div>
                <div className="text-[11px] text-slate-500 flex justify-between">
                  <span>Created:</span>
                  <span className="font-semibold text-slate-700">
                    {formatDisplayDate(planMetadata.created_at)}
                    {planMetadata.created_by_name ? ` by ${planMetadata.created_by_name}` : ''}
                  </span>
                </div>
                <div className="text-[11px] text-slate-500 flex justify-between">
                  <span>Last Modified:</span>
                  <span className="font-semibold text-slate-700">
                    {planMetadata.updated_at
                      ? `${formatDisplayDate(planMetadata.updated_at)}${
                          planMetadata.updated_by_name ? ` by ${planMetadata.updated_by_name}` : ''
                        }`
                      : 'Not modified'}
                  </span>
                </div>
              </div>
            ) : (
              <div className="py-2 px-1 text-center text-slate-400 italic text-[11px]">
                No monthly requirement plan has been created.
              </div>
            )}
          </div>

          {/* Metric Badges */}
          <div className="hidden lg:flex items-center gap-2">
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs shadow-sm">
              <span className="w-2 h-2 rounded-full bg-rose-500" />
              <span className="font-bold text-rose-700">{summary.critical}</span>
              <span className="text-slate-400 text-2xs">Critical</span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs shadow-sm">
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              <span className="font-bold text-amber-700">{summary.low}</span>
              <span className="text-slate-400 text-2xs">Low</span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs shadow-sm">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="font-bold text-emerald-700">{summary.normal}</span>
              <span className="text-slate-400 text-2xs">Normal</span>
            </div>
          </div>
        </div>
      </div>

      {statusMessage && (
        <div
          className={`px-3.5 py-2.5 rounded-xl text-xs font-medium border flex items-center justify-between shadow-xs ${
            statusMessage.type === 'error'
              ? 'bg-rose-50 text-rose-800 border-rose-200'
              : statusMessage.type === 'success'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : 'bg-blue-50 text-blue-800 border-blue-200'
          }`}
        >
          <div className="flex items-center gap-2">
            <span>{statusMessage.type === 'error' ? '⚠️' : '✓'}</span>
            <span>{statusMessage.text}</span>
          </div>
          <button onClick={() => setStatusMessage(null)} className="text-slate-400 hover:text-slate-600 font-bold">
            ✕
          </button>
        </div>
      )}

      {/* Section 3: Prominent Planning-Period Selector & Action Toolbar */}
      <div className="bg-white border border-slate-200 rounded-xl p-3 flex flex-wrap items-center justify-between gap-3 shadow-sm">
        <div className="flex items-center gap-3">
          {/* Month Selector */}
          <div className="flex items-center gap-1.5">
            <label htmlFor="req-planning-month-select" className="text-xs font-bold text-slate-700">Planning Month:</label>
            <select
              id="req-planning-month-select"
              aria-label="Planning Month"
              value={selectedMonth}
              onChange={e => handleMonthChange(parseInt(e.target.value, 10))}
              className="px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg bg-white text-slate-800 font-medium focus:ring-1 focus:ring-slate-900"
            >
              {MONTH_NAMES.map((m, idx) => (
                <option key={idx + 1} value={idx + 1}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          {/* Year Selector */}
          <div className="flex items-center gap-1.5">
            <label htmlFor="req-planning-year-select" className="text-xs font-bold text-slate-700">Planning Year:</label>
            <select
              id="req-planning-year-select"
              aria-label="Planning Year"
              value={selectedYear}
              onChange={e => handleYearChange(parseInt(e.target.value, 10))}
              className="px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg bg-white text-slate-800 font-medium focus:ring-1 focus:ring-slate-900"
            >
              {[2024, 2025, 2026, 2027, 2028, 2029, 2030].map(y => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>

          <button
            type="button"
            onClick={() => void loadRecords()}
            disabled={isLoading}
            className="px-3 py-1.5 border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 rounded-lg font-semibold text-xs transition-colors shadow-sm flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5 text-slate-500" />
            <span>Load Requirements</span>
          </button>

          {/* Active GRN Reconciliation Badge */}
          {planMetadata?.grn_reconciled ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 shadow-2xs">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              <span>GRN Reconciled</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200 shadow-2xs">
              <AlertCircle className="w-3.5 h-3.5 text-amber-600" />
              <span>GRN Pending</span>
            </span>
          )}
        </div>

        {/* Primary Action Buttons */}
        <div className="flex items-center gap-2">
          {/* Upload Plan Button */}
          {canEditPlan && (
            <button
              type="button"
              onClick={() => setShowUploadModal(true)}
              className="border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 rounded-lg px-3 py-1.5 font-semibold text-xs shadow-sm transition-colors flex items-center gap-1.5"
            >
              <UploadCloud className="w-3.5 h-3.5 text-slate-600" />
              <span>Upload Plan</span>
            </button>
          )}

          {/* Upload GRN Button */}
          {canUpdate && (
            <button
              type="button"
              onClick={() => {
                setGrnFile(null);
                setGrnError(null);
                setIsGrnModalOpen(true);
              }}
              className="border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 rounded-lg px-3 py-1.5 font-semibold text-xs shadow-sm transition-colors flex items-center gap-1.5"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600" />
              <span>Upload GRN</span>
            </button>
          )}

          {/* Save Changes Button (Active when permitted cells are edited) */}
          {canEditPlan && (
            <button
              type="button"
              onClick={() => void handleSaveChanges()}
              disabled={isSaving || modifiedRecords.size === 0}
              className={`rounded-lg px-3 py-1.5 font-semibold text-xs shadow-sm transition-colors flex items-center gap-1.5 ${
                modifiedRecords.size > 0
                  ? 'bg-amber-600 hover:bg-amber-700 text-white animate-pulse'
                  : 'border border-slate-200 bg-slate-50 text-slate-400 cursor-not-allowed'
              }`}
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Saving…</span>
                </>
              ) : (
                <>
                  <Save className="w-3.5 h-3.5" />
                  <span>Save Changes {modifiedRecords.size > 0 ? `(${modifiedRecords.size})` : ''}</span>
                </>
              )}
            </button>
          )}

          {/* Recalculate MRP Button (Primary Action) */}
          {canRecalculate && (
            <button
              type="button"
              onClick={() => void handleRecalculate()}
              disabled={isRecalculating || isLoading || (!productionBased && records.length === 0) || (productionBased && planMetadata?.status === 'APPROVED')}
              className="border border-slate-300 bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white rounded-lg px-3.5 py-1.5 font-semibold text-xs shadow-sm transition-colors flex items-center gap-1.5"
            >
              {isRecalculating ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Recalculating…</span>
                </>
              ) : (
                <>
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Recalculate</span>
                </>
              )}
            </button>
          )}

          {/* Export Excel Button */}
          {canExport && (
            <div className="relative group">
              <button
                type="button"
                onClick={() => handleExport(selectedRowIds.size > 0 ? 'SELECTED' : 'ALL')}
                className="border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 rounded-lg px-3 py-1.5 font-semibold text-xs shadow-sm transition-colors flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5 text-slate-600" />
                <span>Export Excel ▾</span>
              </button>
              <div className="absolute right-0 top-full mt-1 w-40 bg-white border border-slate-200 rounded-xl shadow-lg py-1 z-30 hidden group-hover:block">
                <button
                  type="button"
                  onClick={() => handleExport('ALL')}
                  className="w-full text-left px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                >
                  Export All Rows
                </button>
                <button
                  type="button"
                  onClick={() => handleExport('FILTERED')}
                  className="w-full text-left px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                >
                  Export Filtered Rows
                </button>
                {selectedRowIds.size > 0 && (
                  <button
                    type="button"
                    onClick={() => handleExport('SELECTED')}
                    className="w-full text-left px-3 py-1.5 text-xs text-blue-700 font-semibold hover:bg-blue-50"
                  >
                    Export Selected ({selectedRowIds.size})
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Issues Alert Line */}
      {Boolean(planMetadata?.issue_count && planMetadata.issue_count > 0) && (
        <div className="flex items-center justify-between px-3 py-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-900 shadow-2xs">
          <div className="flex items-center gap-2">
            <span className="font-bold">⚠️ {planMetadata?.issue_count} issue{planMetadata?.issue_count === 1 ? '' : 's'}:</span>
            <span>missing norms or unmapped processes for planned parts in this period.</span>
          </div>
          <button
            type="button"
            onClick={handleDownloadIssues}
            disabled={isDownloadingIssues}
            className="px-2.5 py-1 bg-white hover:bg-amber-100 border border-amber-300 rounded font-semibold text-xs text-amber-900 transition-colors shadow-2xs flex items-center gap-1 cursor-pointer disabled:opacity-50"
          >
            <span>📥</span>
            <span>{isDownloadingIssues ? 'Downloading...' : 'Download issues list (CSV)'}</span>
          </button>
        </div>
      )}

      {/* Main Spreadsheet Grid Container */}
      <div className="flex-1 min-h-0 bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col overflow-hidden">
        {/* Toolbar for search and column filters */}
        <Toolbar
          canImport={false}
          canCreate={false}
          canUpdate={false}
          canDelete={false}
          canExport={false}
          selectedCount={selectedRowIds.size}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          searchPlaceholder="🔍 Search part name, part no, consumable ID, process..."
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
                { value: 'Calculated', label: 'Calculated' },
                { value: 'Configuration required', label: 'Rule Review Required' },
              ],
            },
          ]}
        />

        {/* Section 7 & 7A: Spreadsheet Table Grid with ALWAYS VISIBLE HEADERS */}
        <div className="flex-1 min-h-0">
          <DataTable
            virtualize
            columns={columns}
            headerGroups={headerGroups}
            data={filteredRecords}
            originalData={originalMap}
            selectedIds={selectedRowIds}
            onSelectionChange={setSelectedRowIds}
            onCellChange={handleCellChange}
            onSave={handleSaveChanges}
            onDeleteRows={handleDeleteRows}
            onDiscardChanges={handleDiscardChanges}
            isLoading={isLoading}
            emptyMessage={`No consumable requirements found for ${MONTH_NAMES[selectedMonth - 1]} ${selectedYear}. Click 'Upload Excel' to import a plan.`}
            canCreate={false}
            canUpdate={canEditPlan}
            canDelete={canEditPlan}
            selectedCell={selectedCell}
            onSelectCell={setSelectedCell}
            storageKey="knl_requirements_grid"
            saveStatus={isSaving ? 'saving' : modifiedRecords.size > 0 ? 'idle' : 'saved'}
            lastModifiedText={
              planMetadata?.updated_at
                ? `Modified ${formatDisplayDate(planMetadata.updated_at)}${planMetadata.updated_by_name ? ` by ${planMetadata.updated_by_name}` : ''}`
                : undefined
            }
            onExport={handleExport}
            getRowClassName={row => {
              if (row.status === 'Critical shortage') return 'bg-red-50/70 hover:bg-red-100/70 font-medium';
              if (row.status === 'Low') return 'bg-amber-50/60 hover:bg-amber-100/60';
              if (row.status === 'Configuration required') return 'bg-purple-50/60 hover:bg-purple-100/60';
              return '';
            }}
          />
        </div>
      </div>

      {/* Upload Excel Modal */}
      <MonthlyExcelUploadModal
        isOpen={showUploadModal}
        planningMonth={selectedMonth}
        planningYear={selectedYear}
        monthName={MONTH_NAMES[selectedMonth - 1]}
        onClose={() => setShowUploadModal(false)}
        onImportSuccess={msg => {
          setStatusMessage({ type: 'success', text: msg });
          void loadRecords();
        }}
      />

      {/* MRP Month-End GRN Upload Modal */}
      {isGrnModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-lg w-full overflow-hidden animate-in fade-in duration-150">
            {/* Header */}
            <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50/70">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-emerald-50 text-emerald-600 rounded-lg border border-emerald-100">
                  <FileSpreadsheet className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    Upload Store GRN (Goods Receipt Note)
                  </h3>
                  <p className="text-2xs text-slate-500">
                    Month-End Ingestion & Reconciliation
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsGrnModalOpen(false);
                  setGrnFile(null);
                  setGrnError(null);
                }}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-md transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Body */}
            <div className="p-5 space-y-4 text-xs">
              {/* Context Note */}
              <div className="bg-emerald-50/60 border border-emerald-100 rounded-lg p-3 text-[11px] text-emerald-900 space-y-1">
                <div className="font-semibold flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  <span>Month-End Overwrite Upsert Engine</span>
                </div>
                <p className="text-emerald-800">
                  Matches records by composite key <code className="font-mono font-semibold bg-emerald-100/70 px-1 py-0.5 rounded text-[10px]">(Plant, Month, Year, Consumable Code)</code>. Re-uploading overwrites existing GRN quantities deterministically, updating closing stock and net order requirements.
                </p>
              </div>

              {/* Target Plant & Period */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="mrp-grn-plant-select" className="block text-[11px] font-bold text-slate-700 mb-1">
                    Target Plant
                  </label>
                  <select
                    id="mrp-grn-plant-select"
                    value={grnTargetPlant}
                    onChange={e => setGrnTargetPlant(e.target.value)}
                    className="w-full px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg bg-white text-slate-800 font-medium focus:ring-2 focus:ring-slate-900 focus:border-slate-900"
                  >
                    <option value="Plant 1">Plant 1</option>
                    <option value="Plant 2">Plant 2</option>
                    <option value="Plant 3">Plant 3</option>
                    <option value="Plant 4">Plant 4</option>
                    <option value="Plant 5">Plant 5</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-bold text-slate-700 mb-1">
                    Planning Period
                  </label>
                  <div className="px-2.5 py-1.5 text-xs bg-slate-100 border border-slate-200 rounded-lg text-slate-700 font-semibold">
                    {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
                  </div>
                </div>
              </div>

              {/* File Dropzone */}
              <div>
                <label className="block text-[11px] font-bold text-slate-700 mb-1">
                  GRN File (.xlsx, .xls, .csv)
                </label>
                <div
                  onClick={() => grnFileInputRef.current?.click()}
                  className="border-2 border-dashed border-slate-300 hover:border-slate-400 bg-slate-50/50 hover:bg-slate-50 p-4 rounded-xl text-center cursor-pointer transition-colors"
                >
                  <input
                    ref={grnFileInputRef}
                    type="file"
                    accept=".xlsx,.xls,.csv"
                    className="hidden"
                    onChange={e => {
                      const file = e.target.files?.[0];
                      if (file) setGrnFile(file);
                    }}
                  />
                  {grnFile ? (
                    <div className="flex items-center justify-center gap-2 text-slate-800 font-medium">
                      <FileSpreadsheet className="w-5 h-5 text-emerald-600" />
                      <span className="font-semibold">{grnFile.name}</span>
                      <span className="text-slate-400 text-2xs">
                        ({(grnFile.size / 1024).toFixed(1)} KB)
                      </span>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <Upload className="w-6 h-6 text-slate-400 mx-auto" />
                      <div className="font-semibold text-slate-700">Click to choose store GRN file</div>
                      <div className="text-2xs text-slate-400">Supported columns: Item ID, Received Qty / GRN Qty, Rate, Date, Invoice No</div>
                    </div>
                  )}
                </div>
              </div>

              {grnError && (
                <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-lg text-xs flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                  <div>{grnError}</div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-5 py-3 border-t border-slate-200 bg-slate-50/60 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setIsGrnModalOpen(false);
                  setGrnFile(null);
                  setGrnError(null);
                }}
                disabled={isGrnUploading}
                className="px-3.5 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleUploadMRPGRN()}
                disabled={!grnFile || isGrnUploading}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-50 rounded-lg shadow-sm transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                {isGrnUploading ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Ingesting GRN…</span>
                  </>
                ) : (
                  <>
                    <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Upload & Reconcile GRN</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

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
                    Component & Consumable
                  </span>
                  <div className="text-sm font-bold text-gray-900 mt-0.5">
                    Part: {selectedAuditRow.part_name} ({selectedAuditRow.part_number})
                  </div>
                  <div className="text-base font-bold text-indigo-950 mt-1">
                    {selectedAuditRow.consumable_code} · {selectedAuditRow.consumable_name}
                  </div>
                </div>
                <div className="text-right space-y-1">
                  <div className="text-xs font-semibold text-gray-800">
                    Process: <span className="font-bold text-indigo-900">{selectedAuditRow.process_name}</span>
                  </div>
                  <div className="text-2xs text-gray-600">
                    Thickness: <span className="font-bold">{selectedAuditRow.part_thickness} mm</span> · Processes: <span className="font-bold">{selectedAuditRow.process_count}</span>
                  </div>
                  <div className="text-2xs text-gray-500">
                    Unit: <span className="font-bold">{selectedAuditRow.unit}</span>
                  </div>
                </div>
              </div>

              {/* Numerical Metrics Matrix */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div className="p-3 bg-gray-50 border border-gray-200 rounded">
                  <div className="text-2xs font-semibold text-gray-500 uppercase">1. Production Order Qty</div>
                  <div className="text-base font-bold text-gray-900 mt-1">
                    {selectedAuditRow.production_order_qty}
                  </div>
                  <div className="text-3xs text-gray-400 mt-0.5">Planned component quantity</div>
                </div>

                <div className="p-3 bg-indigo-50/70 border border-indigo-200 rounded">
                  <div className="text-2xs font-semibold text-indigo-800 uppercase">2. Scheduled Consumable Qty</div>
                  <div className="text-base font-bold text-indigo-950 mt-1">
                    {selectedAuditRow.scheduled_consumable_qty}{' '}
                    <span className="text-2xs font-normal text-gray-500">{selectedAuditRow.unit}</span>
                  </div>
                  <div className="text-3xs text-indigo-600 mt-0.5">Calculated requirement</div>
                </div>

                <div className="p-3 bg-gray-50 border border-gray-200 rounded">
                  <div className="text-2xs font-semibold text-gray-500 uppercase">3. Current Stock</div>
                  <div className="text-base font-bold text-gray-900 mt-1">
                    {selectedAuditRow.stock_qty}{' '}
                    <span className="text-2xs font-normal text-gray-500">{selectedAuditRow.unit}</span>
                  </div>
                  <div className="text-3xs text-gray-400 mt-0.5">Physical closing stock</div>
                </div>

                <div className="p-3 bg-blue-50/70 border border-blue-200 rounded">
                  <div className="text-2xs font-semibold text-blue-800 uppercase">4. Incoming PO Qty</div>
                  <div className="text-base font-bold text-blue-900 mt-1">
                    {selectedAuditRow.po_pending_qty}{' '}
                    <span className="text-2xs font-normal text-gray-500">{selectedAuditRow.unit}</span>
                  </div>
                  <div className="text-3xs text-blue-600 mt-0.5">Confirmed on order</div>
                </div>

                <div className={`p-3 border rounded ${
                  selectedAuditRow.status === 'Critical shortage'
                    ? 'bg-red-50/80 border-red-200'
                    : selectedAuditRow.status === 'Low'
                    ? 'bg-amber-50/80 border-amber-200'
                    : 'bg-emerald-50/80 border-emerald-200'
                }`}>
                  <div className="text-2xs font-semibold uppercase">5. Net Shortage</div>
                  <div className={`text-base font-bold mt-1 ${
                    selectedAuditRow.status === 'Critical shortage'
                      ? 'text-red-700'
                      : selectedAuditRow.status === 'Low'
                      ? 'text-amber-700'
                      : 'text-emerald-700'
                  }`}>
                    {selectedAuditRow.shortage_qty}{' '}
                    <span className="text-2xs font-normal text-gray-500">{selectedAuditRow.unit}</span>
                  </div>
                  <div className="text-3xs text-gray-500 mt-0.5">Status: {selectedAuditRow.status}</div>
                </div>
              </div>

              {/* Traceability Audit Trail */}
              <div className="border border-gray-200 rounded p-4 bg-gray-50 space-y-2 font-mono text-xs text-gray-700">
                <div className="font-bold text-gray-800 uppercase tracking-wide text-2xs font-sans">
                  Formula Traceability Evidence:
                </div>
                <div className="bg-white p-3 rounded border border-gray-200 space-y-1">
                  <div>• Production Quantity: {selectedAuditRow.production_order_qty}</div>
                  <div>• Thickness: {selectedAuditRow.part_thickness} mm · Process Count: {selectedAuditRow.process_count}</div>
                  <div>• Applied Rule / Result: {selectedAuditRow.remarks || 'Standard calculation'}</div>
                  <div>• Scheduled Quantity: {selectedAuditRow.scheduled_consumable_qty} {selectedAuditRow.unit}</div>
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
