import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import { useAuth } from '../auth/context';
import { TableSkeleton } from '../../components/ui/Skeleton';
import type {
  PlanInspectResult,
  PurchasePlanItem,
  PurchasePlanResponse,
} from './types';

export type ViewMode = 'NORMAL_VIEW' | 'MD_VIEW';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

function getPrevPeriodLabel(periodStr: string): string {
  try {
    const [yStr, mStr] = periodStr.split('-');
    let y = parseInt(yStr, 10);
    let m = parseInt(mStr, 10);
    m -= 1;
    if (m === 0) {
      m = 12;
      y -= 1;
    }
    const shortMonth = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m - 1];
    return `${shortMonth}'${String(y).slice(-2)}`;
  } catch {
    return 'Prev Month';
  }
}

function getPeriodShortLabel(periodStr: string): string {
  try {
    const [yStr, mStr] = periodStr.split('-');
    const y = parseInt(yStr, 10);
    const m = parseInt(mStr, 10);
    const shortMonth = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m - 1];
    return `${shortMonth}'${String(y).slice(-2)}`;
  } catch {
    return periodStr;
  }
}

function formatCurrency(val: any): string {
  const num = parseFloat(val);
  if (isNaN(num)) return '₹ 0.00';
  return '₹ ' + num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatQty(val: any): string {
  const num = parseFloat(val);
  if (isNaN(num)) return '0.00';
  return num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function formatLocalTime(isoStr?: string | null): string {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      dateStyle: 'medium',
      timeStyle: 'short',
    }) + ' IST';
  } catch {
    return isoStr;
  }
}

interface ColumnConfig {
  key: string;
  label: string;
  group: string;
  width: string; // Tailwind width or pixel width
  align?: 'left' | 'center' | 'right';
  editable?: boolean;
  field?: keyof PurchasePlanItem;
  formulaDesc?: string;
  getValue?: (item: PurchasePlanItem, idx: number) => any;
  format?: (val: any) => string;
}

interface PurchasePlanWorkspaceProps {
  currentUserId?: string;
}

export default function PurchasePlanWorkspace({ currentUserId: _currentUserId }: PurchasePlanWorkspaceProps) {
  const { user } = useAuth();
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const canRead = Boolean(isSuperAdmin || user?.purchase_read !== false);
  const canEdit = Boolean(isSuperAdmin || user?.purchase_update !== false);

  // Month & Year selection
  const [selectedMonth, setSelectedMonth] = useState<number>(10); // October
  const [selectedYear, setSelectedYear] = useState<number>(2026); // 2026
  const currentPeriod = `${selectedYear}-${String(selectedMonth).padStart(2, '0')}`;

  // View Switcher: MD View vs Normal View
  const [viewMode, setViewMode] = useState<ViewMode>('NORMAL_VIEW');

  // Plan Data State
  const [plan, setPlan] = useState<PurchasePlanResponse | null>(null);
  const [items, setItems] = useState<PurchasePlanItem[]>([]);
  const [dirtyItemIds, setDirtyItemIds] = useState<Set<string>>(new Set());

  // Loading & Feedback
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isRecalculating, setIsRecalculating] = useState<boolean>(false);
  const [isSubmittingApproval, setIsSubmittingApproval] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');

  // Column Visibility & Hide/Show Manager
  const [hiddenCols, setHiddenCols] = useState<Set<string>>(new Set());
  const [showColMenu, setShowColMenu] = useState<boolean>(false);
  const [colSearchQuery, setColSearchQuery] = useState<string>('');
  const colMenuRef = useRef<HTMLDivElement>(null);

  // Freeze Panes toggle
  const [freezePanes, setFreezePanes] = useState<boolean>(true);

  // Excel Edit Mode: 'EXCEL_CLICK' (double click to edit cell) vs 'DIRECT_INPUT' (inputs always visible)
  const [editMode, setEditMode] = useState<'EXCEL_CLICK' | 'DIRECT_INPUT'>('EXCEL_CLICK');

  // Excel Selected Cell & Formula Bar state
  const [selectedCell, setSelectedCell] = useState<{ rowId: string; colKey: string } | null>(null);
  const [editingCell, setEditingCell] = useState<{ rowId: string; colKey: string } | null>(null);
  const [formulaValue, setFormulaValue] = useState<string>('');
  const editInputRef = useRef<HTMLInputElement>(null);

  // Column context menu (for right-click or dropdown header hide)
  const [activeHeaderMenu, setActiveHeaderMenu] = useState<string | null>(null);

  // Column Group Collapse toggles for MD View
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({
    plantWise: false,
    consumptionAnalysis: false,
  });

  const toggleGroup = (groupKey: string) => {
    setCollapsedGroups(prev => ({ ...prev, [groupKey]: !prev[groupKey] }));
  };

  // Excel Upload Modal State
  const [isUploadOpen, setIsUploadOpen] = useState<boolean>(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [inspectResult, setInspectResult] = useState<PlanInspectResult | null>(null);
  const [isInspecting, setIsInspecting] = useState<boolean>(false);
  const [isImporting, setIsImporting] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Close menus when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (colMenuRef.current && !colMenuRef.current.contains(event.target as Node)) {
        setShowColMenu(false);
      }
      if (activeHeaderMenu && !(event.target as HTMLElement).closest('.header-menu-container')) {
        setActiveHeaderMenu(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [activeHeaderMenu]);

  // Load Purchase Plan
  const loadPlan = useCallback(async (period: string) => {
    setIsLoading(true);
    setFeedback(null);
    try {
      const data = await apiClient.get<PurchasePlanResponse | null>(`/api/v1/purchasing/plan?planning_period=${period}`);
      if (data) {
        setPlan(data);
        setItems(data.items || []);
        setDirtyItemIds(new Set());
      } else {
        setPlan(null);
        setItems([]);
        setDirtyItemIds(new Set());
      }
    } catch (err: unknown) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to load purchase plan.',
      });
      setPlan(null);
      setItems([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPlan(currentPeriod);
  }, [loadPlan, currentPeriod]);

  // Recalculate Plan
  const handleRecalculate = async () => {
    if (!plan && items.length === 0) {
      setFeedback({ type: 'error', message: 'No purchase plan loaded to recalculate.' });
      return;
    }
    setIsRecalculating(true);
    setFeedback(null);
    try {
      const updated = await apiClient.post<PurchasePlanResponse>('/api/v1/purchasing/plan/recalculate', {
        planning_period: currentPeriod,
        msl_days_gas: plan?.msl_days_gas,
        msl_days_general: plan?.msl_days_general,
      });
      setPlan(updated);
      setItems(updated.items || []);
      setDirtyItemIds(new Set());
      setFeedback({
        type: 'success',
        message: 'Purchase quantities successfully recalculated using approved deterministic MSL gap formulas.',
      });
    } catch (err: unknown) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Recalculation failed.',
      });
    } finally {
      setIsRecalculating(false);
    }
  };

  // Inline Cell Editing
  const handleCellEdit = (itemId: string, field: keyof PurchasePlanItem, value: any) => {
    if (!canEdit) return;

    setItems(prevItems =>
      prevItems.map(it => {
        if (it.id !== itemId) return it;

        const updated = { ...it, [field]: value };
        if (field === 'order_qty') {
          const numRate = parseFloat(String(it.rate || 0));
          const numQty = parseFloat(String(value || 0));
          updated.order_value = (numRate * numQty).toFixed(2);
          if (!it.override_reason) {
            updated.override_reason = 'Manual user adjustment';
          }
        }
        if (field === 'rate') {
          const numRate = parseFloat(String(value || 0));
          const numQty = parseFloat(String(it.order_qty || 0));
          updated.order_value = (numRate * numQty).toFixed(2);
        }
        return updated;
      })
    );

    setDirtyItemIds(prev => new Set(prev).add(itemId));
  };

  // Save Changes
  const handleSaveChanges = async () => {
    if (dirtyItemIds.size === 0) return;
    setIsSaving(true);
    setFeedback(null);

    const dirtyList = items
      .filter(it => dirtyItemIds.has(it.id))
      .map(it => ({
        id: it.id,
        item_id: it.item_id,
        description: it.description,
        rate: it.rate,
        moq: it.moq,
        min_stock_level: it.min_stock_level,
        max_stock_level: it.max_stock_level,
        lead_time_days: it.lead_time_days,
        order_qty: it.order_qty,
        override_reason: it.override_reason,
        plant_allocations: it.plant_allocations,
      }));

    try {
      const updated = await apiClient.post<PurchasePlanResponse>('/api/v1/purchasing/plan/save', {
        planning_period: currentPeriod,
        items: dirtyList,
      });
      setPlan(updated);
      setItems(updated.items || []);
      setDirtyItemIds(new Set());
      setFeedback({ type: 'success', message: 'All changes saved successfully.' });
    } catch (err: unknown) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to save changes.',
      });
    } finally {
      setIsSaving(false);
    }
  };

  // Send to Approval Queue
  const handleSendToApproval = async () => {
    const eligibleCount = items.filter(it => parseFloat(String(it.order_qty || 0)) > 0).length;
    if (eligibleCount === 0) {
      setFeedback({ type: 'error', message: 'No items with positive Order Qty to submit for approval.' });
      return;
    }

    if (!window.confirm(`Submit ${eligibleCount} purchase recommendations for ${currentPeriod} to the Approval Queue?`)) {
      return;
    }

    setIsSubmittingApproval(true);
    setFeedback(null);
    try {
      const res = await apiClient.post<{ submitted_count: number; message: string }>('/api/v1/purchasing/plan/send-to-approval', {
        planning_period: currentPeriod,
      });
      setFeedback({
        type: 'success',
        message: res.message || `Submitted ${res.submitted_count} items to the Approval Queue!`,
      });
      void loadPlan(currentPeriod);
    } catch (err: unknown) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Submission to approval queue failed.',
      });
    } finally {
      setIsSubmittingApproval(false);
    }
  };

  // Export Excel
  const handleExport = () => {
    const url = `/api/v1/purchasing/plan/export?planning_period=${currentPeriod}&view_type=${viewMode}${searchQuery ? `&search=${encodeURIComponent(searchQuery)}` : ''}`;
    window.open(url, '_blank');
  };

  // Excel File Inspection
  const handleFileChosen = async (file: File) => {
    setUploadFile(file);
    setIsInspecting(true);
    setInspectResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await apiClient.postFormData<PlanInspectResult>('/api/v1/purchasing/plan/inspect', formData);
      setInspectResult(res);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to inspect Excel file.');
    } finally {
      setIsInspecting(false);
    }
  };

  // Confirm Import
  const handleConfirmImport = async () => {
    if (!uploadFile || !inspectResult) return;
    setIsImporting(true);
    try {
      const res = await apiClient.post<PurchasePlanResponse>('/api/v1/purchasing/plan/import-sheet', {
        planning_period: currentPeriod,
        detected_view: inspectResult.detected_view,
        filename: uploadFile.name,
        rows: inspectResult.sample_rows,
      });
      setPlan(res);
      setItems(res.items || []);
      setDirtyItemIds(new Set());
      setIsUploadOpen(false);
      setUploadFile(null);
      setInspectResult(null);
      setFeedback({
        type: 'success',
        message: `Successfully imported ${res.total_items} items from ${uploadFile.name} (${inspectResult.detected_view === 'MD_VIEW' ? 'MD View' : 'Normal View'}).`,
      });
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Import failed.');
    } finally {
      setIsImporting(false);
    }
  };

  const prevMonthLabel = getPrevPeriodLabel(currentPeriod);
  const currentShortLabel = getPeriodShortLabel(currentPeriod);

  // Definition of ALL columns for Normal View
  const NORMAL_COLUMNS: ColumnConfig[] = useMemo(() => [
    { key: 's_no', label: 'S. No.', group: 'ITEM IDENTITY & UOM', width: 'w-14 min-w-[56px]', align: 'center', getValue: (it, idx) => it.s_no || idx + 1 },
    { key: 'req_type', label: 'Req. Type', group: 'ITEM IDENTITY & UOM', width: 'w-32 min-w-[128px]', align: 'left', getValue: it => it.req_type || 'PRODUCTION' },
    { key: 'item_id', label: 'Item Id', group: 'ITEM IDENTITY & UOM', width: 'w-36 min-w-[144px]', align: 'left', getValue: it => it.item_id },
    { key: 'description', label: 'Description', group: 'ITEM IDENTITY & UOM', width: 'w-64 min-w-[256px]', align: 'left', getValue: it => it.description },
    { key: 'unit', label: 'Unit', group: 'ITEM IDENTITY & UOM', width: 'w-16 min-w-[64px]', align: 'center', getValue: it => it.unit },
    { key: 'output_per_unit', label: 'Output / Unit', group: 'ITEM IDENTITY & UOM', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.output_per_unit, format: formatQty },
    { key: 'moq', label: 'MOQ.', group: 'STOCK & COMMERCIAL RULES', width: 'w-24 min-w-[96px]', align: 'right', editable: true, field: 'moq', getValue: it => it.moq, format: formatQty },
    { key: 'min_stock_level', label: 'Min. Stock. Level', group: 'STOCK & COMMERCIAL RULES', width: 'w-28 min-w-[112px]', align: 'right', editable: true, field: 'min_stock_level', getValue: it => it.min_stock_level, format: formatQty, formulaDesc: '= MSL_Days * Daily_Req' },
    { key: 'max_stock_level', label: 'Max. Stock Level', group: 'STOCK & COMMERCIAL RULES', width: 'w-28 min-w-[112px]', align: 'right', editable: true, field: 'max_stock_level', getValue: it => it.max_stock_level, format: formatQty },
    { key: 'rate', label: 'Rate', group: 'STOCK & COMMERCIAL RULES', width: 'w-24 min-w-[96px]', align: 'right', editable: true, field: 'rate', getValue: it => it.rate, format: formatCurrency },
    { key: 'prev_opening_qty', label: `O/s. ${prevMonthLabel}`, group: `PREVIOUS MONTH STOCK (${prevMonthLabel})`, width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.prev_opening_qty, format: formatQty },
    { key: 'prev_receipt_qty', label: 'Receipt', group: `PREVIOUS MONTH STOCK (${prevMonthLabel})`, width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.prev_receipt_qty, format: formatQty },
    { key: 'prev_issue_qty', label: 'Issues', group: `PREVIOUS MONTH STOCK (${prevMonthLabel})`, width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.prev_issue_qty, format: formatQty },
    { key: 'prev_closing_qty', label: `C/s. ${prevMonthLabel}`, group: `PREVIOUS MONTH STOCK (${prevMonthLabel})`, width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.prev_closing_qty, format: formatQty, formulaDesc: '= Opening + Receipts - Issues' },
    { key: 'prev_prd_qty', label: 'Prd. Qty.', group: `PREVIOUS MONTH STOCK (${prevMonthLabel})`, width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.prev_prd_qty, format: formatQty },
    { key: 'sch_qty', label: `Sch. ${currentShortLabel}`, group: `SELECTED MONTH PLAN (${currentShortLabel})`, width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.sch_qty, format: formatQty },
    { key: 'req_qty', label: 'Req. Qty.', group: `SELECTED MONTH PLAN (${currentShortLabel})`, width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.req_qty, format: formatQty },
    { key: 'order_qty', label: 'Order Qty.', group: `SELECTED MONTH PLAN (${currentShortLabel})`, width: 'w-28 min-w-[112px]', align: 'right', editable: true, field: 'order_qty', getValue: it => it.order_qty, format: formatQty, formulaDesc: '= MAX(0, Min_Stock_Level - Prev_Closing_Qty)' },
    { key: 'order_value', label: 'Order Value', group: `SELECTED MONTH PLAN (${currentShortLabel})`, width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.order_value, format: formatCurrency, formulaDesc: '= Order_Qty * Rate' },
    { key: 'pur_qty', label: 'Pur. Qty.', group: 'ACTUAL PURCHASE PROGRESS', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.pur_qty, format: formatQty },
    { key: 'pur_value', label: 'Pur. Value', group: 'ACTUAL PURCHASE PROGRESS', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.pur_value, format: formatCurrency },
    { key: 'bal_pur_qty', label: 'Bal. Pur. Qty', group: 'ACTUAL PURCHASE PROGRESS', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.bal_pur_qty, format: formatQty },
    { key: 'bal_pur_value', label: 'Bal. Pur. Value', group: 'ACTUAL PURCHASE PROGRESS', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.bal_pur_value, format: formatCurrency },
  ], [prevMonthLabel, currentShortLabel]);

  // Definition of ALL columns for MD View
  const MD_COLUMNS: ColumnConfig[] = useMemo(() => [
    { key: 'supplier_id', label: 'Supplier ID', group: 'ITEM / SUPPLIER', width: 'w-28 min-w-[112px]', align: 'left', getValue: it => it.supplier_id || '—' },
    { key: 'supplier_name', label: 'Supplier name', group: 'ITEM / SUPPLIER', width: 'w-48 min-w-[192px]', align: 'left', getValue: it => it.supplier_name || '—' },
    { key: 'item_id', label: 'Item Id', group: 'ITEM / SUPPLIER', width: 'w-36 min-w-[144px]', align: 'left', getValue: it => it.item_id },
    { key: 'category', label: 'Category', group: 'ITEM / SUPPLIER', width: 'w-28 min-w-[112px]', align: 'left', getValue: it => it.category || '—' },
    { key: 'type_of_material', label: 'Type of material', group: 'ITEM / SUPPLIER', width: 'w-32 min-w-[128px]', align: 'left', getValue: it => it.type_of_material || '—' },
    { key: 's_no', label: 'S. No.', group: 'ITEM / SUPPLIER', width: 'w-14 min-w-[56px]', align: 'center', getValue: (it, idx) => it.s_no || idx + 1 },
    { key: 'description', label: 'Description', group: 'ITEM / SUPPLIER', width: 'w-64 min-w-[256px]', align: 'left', getValue: it => it.description },
    { key: 'part_no_saleable', label: 'Part No. saleable', group: 'PART / PROCESS (USAGE)', width: 'w-36 min-w-[144px]', align: 'left', getValue: it => it.part_no_saleable || '—' },
    { key: 'saleable_part_name', label: 'Used for part name', group: 'PART / PROCESS (USAGE)', width: 'w-48 min-w-[192px]', align: 'left', getValue: it => it.saleable_part_name || '—' },
    { key: 'used_part_no', label: 'Used Part no', group: 'PART / PROCESS (USAGE)', width: 'w-32 min-w-[128px]', align: 'left', getValue: it => it.used_part_no || '—' },
    { key: 'process_name', label: 'Process name', group: 'PART / PROCESS (USAGE)', width: 'w-36 min-w-[144px]', align: 'left', getValue: it => it.process_name || '—' },
    { key: 'thickness_gsm', label: 'Thickness/Gsm', group: 'PART / PROCESS (USAGE)', width: 'w-28 min-w-[112px]', align: 'left', getValue: it => it.thickness_gsm || '—' },
    { key: 'no_of_process_per_part', label: 'No of process', group: 'PART / PROCESS (USAGE)', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.no_of_process_per_part, format: formatQty },
    { key: 'output_per_unit', label: 'Output/ Unit', group: 'PART / PROCESS (USAGE)', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.output_per_unit, format: formatQty },
    { key: 'rate', label: 'Rate', group: 'PART / PROCESS (USAGE)', width: 'w-24 min-w-[96px]', align: 'right', editable: true, field: 'rate', getValue: it => it.rate, format: formatCurrency },
    { key: 'prev_opening_qty', label: 'Opening Qty', group: `PREVIOUS MONTH STOCK (${prevMonthLabel})`, width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.prev_opening_qty, format: formatQty },
    { key: 'prev_opening_val', label: 'Opening Value', group: `PREVIOUS MONTH STOCK (${prevMonthLabel})`, width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.prev_opening_val, format: formatCurrency },
    { key: 'prev_receipt_qty', label: 'Receipt. Qty.', group: `PREVIOUS MONTH STOCK (${prevMonthLabel})`, width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.prev_receipt_qty, format: formatQty },
    { key: 'prev_issue_qty', label: 'Issue Qty.', group: `PREVIOUS MONTH STOCK (${prevMonthLabel})`, width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.prev_issue_qty, format: formatQty },
    { key: 'prev_closing_qty', label: 'Closing Qty', group: `PREVIOUS MONTH STOCK (${prevMonthLabel})`, width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.prev_closing_qty, format: formatQty },
    { key: 'prev_closing_val', label: 'Closing Value', group: `PREVIOUS MONTH STOCK (${prevMonthLabel})`, width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.prev_closing_val, format: formatCurrency },
    { key: 'rate_prev', label: 'Rate (Prev)', group: `PREVIOUS MONTH STOCK (${prevMonthLabel})`, width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.rate, format: formatCurrency },
    { key: 'min_stock_level', label: 'Min stock level', group: 'STOCK PARAMETERS', width: 'w-28 min-w-[112px]', align: 'right', editable: true, field: 'min_stock_level', getValue: it => it.min_stock_level, format: formatQty },
    { key: 'max_stock_level', label: 'Max stock level', group: 'STOCK PARAMETERS', width: 'w-28 min-w-[112px]', align: 'right', editable: true, field: 'max_stock_level', getValue: it => it.max_stock_level, format: formatQty },
    { key: 'moq', label: 'Min order qty.', group: 'STOCK PARAMETERS', width: 'w-28 min-w-[112px]', align: 'right', editable: true, field: 'moq', getValue: it => it.moq, format: formatQty },
    { key: 'lead_time_days', label: 'Lead time days', group: 'STOCK PARAMETERS', width: 'w-24 min-w-[96px]', align: 'right', editable: true, field: 'lead_time_days', getValue: it => it.lead_time_days },
    { key: 'sch_qty', label: 'Sch. Qty. R1', group: 'SCHEDULE R1', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.sch_qty, format: formatQty },
    { key: 'purch_unit', label: 'Purch. Unit', group: 'SCHEDULE R1', width: 'w-20 min-w-[80px]', align: 'center', getValue: it => it.purchasing_unit || it.unit },
    { key: 'sch_qty_item_r1', label: 'Sch. Qty. Item R1', group: 'SCHEDULE R1', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.sch_qty, format: formatQty },
    { key: 'opening_stock_r1', label: 'Opening stock', group: 'SCHEDULE R1', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.prev_closing_qty, format: formatQty },
    { key: 'req_qty', label: 'Req. Qty.', group: 'SCHEDULE R1', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.req_qty, format: formatQty },
    { key: 'order_qty', label: 'Order Qty R1', group: 'SCHEDULE R1', width: 'w-28 min-w-[112px]', align: 'right', editable: true, field: 'order_qty', getValue: it => it.order_qty, format: formatQty },
    { key: 'order_value', label: 'Order Value R1', group: 'SCHEDULE R1', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.order_value, format: formatCurrency },
    { key: 'receipt_qty_r1', label: 'Receipt qty. R1', group: 'SCHEDULE R1', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.receipt_qty, format: formatQty },
    { key: 'receipt_val_r1', label: 'Receipt value R1', group: 'SCHEDULE R1', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.receipt_value, format: formatCurrency },
    { key: 'sch_qty_r2', label: 'Sch. Qty. R2', group: 'SCHEDULE R2 (REVISION)', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.sch_qty_r2, format: formatQty },
    { key: 'sch_cons_r2', label: 'Sch. Cons. R2', group: 'SCHEDULE R2 (REVISION)', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.sch_qty_r2, format: formatQty },
    { key: 'req_r2', label: 'Req. R2', group: 'SCHEDULE R2 (REVISION)', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.req_qty_r2, format: formatQty },
    { key: 'closing_stock_r2', label: 'Closing stock', group: 'SCHEDULE R2 (REVISION)', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.prev_closing_qty, format: formatQty },
    { key: 'req_less_issue_r2', label: 'Req. lessed issue', group: 'SCHEDULE R2 (REVISION)', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.req_qty_r2, format: formatQty },
    { key: 'issue_till_r2', label: 'Issue Qty. till', group: 'SCHEDULE R2 (REVISION)', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.prev_issue_qty, format: formatQty },
    { key: 'order_qty_r2', label: 'Order Qty. R2', group: 'SCHEDULE R2 (REVISION)', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.order_qty_r2, format: formatQty },
    { key: 'order_value_r2', label: 'Order Value R2', group: 'SCHEDULE R2 (REVISION)', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.order_value_r2, format: formatCurrency },
    { key: 'receipt_qty_r2', label: 'Receipt qty. R2', group: 'SCHEDULE R2 (REVISION)', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.receipt_qty_r2, format: formatQty },
    { key: 'receipt_val_r2', label: 'Receipt value R2', group: 'SCHEDULE R2 (REVISION)', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.receipt_val_r2, format: formatCurrency },
    { key: 'total_receipt_qty', label: 'Total Receipt Qty.', group: 'TOTALS', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.receipt_qty, format: formatQty },
    { key: 'total_receipt_val', label: 'Total Receipt Val.', group: 'TOTALS', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.receipt_value, format: formatCurrency },
    // Plant Wise Plan allocations
    { key: 'alloc_p1', label: 'P1', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-16 min-w-[64px]', align: 'right', getValue: it => it.plant_allocations?.p1, format: formatQty },
    { key: 'alloc_p2', label: 'P2', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-16 min-w-[64px]', align: 'right', getValue: it => it.plant_allocations?.p2, format: formatQty },
    { key: 'alloc_p3', label: 'P3', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-16 min-w-[64px]', align: 'right', getValue: it => it.plant_allocations?.p3, format: formatQty },
    { key: 'alloc_p4', label: 'P4', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-16 min-w-[64px]', align: 'right', getValue: it => it.plant_allocations?.p4, format: formatQty },
    { key: 'alloc_p5', label: 'P5', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-16 min-w-[64px]', align: 'right', getValue: it => it.plant_allocations?.p5, format: formatQty },
    { key: 'alloc_tr', label: 'tool room', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-20 min-w-[80px]', align: 'right', getValue: it => it.plant_allocations?.tool_room, format: formatQty },
    { key: 'alloc_qa', label: 'Quality', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-16 min-w-[64px]', align: 'right', getValue: it => it.plant_allocations?.quality, format: formatQty },
    { key: 'alloc_pmd', label: 'PMD', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-16 min-w-[64px]', align: 'right', getValue: it => it.plant_allocations?.pmd, format: formatQty },
    { key: 'alloc_npd', label: 'NPD', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-16 min-w-[64px]', align: 'right', getValue: it => it.plant_allocations?.npd, format: formatQty },
    { key: 'alloc_hrd', label: 'HRD', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-16 min-w-[64px]', align: 'right', getValue: it => it.plant_allocations?.hrd, format: formatQty },
    { key: 'alloc_acc', label: 'Accounts', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-16 min-w-[64px]', align: 'right', getValue: it => it.plant_allocations?.accounts, format: formatQty },
    { key: 'alloc_adm', label: 'Admin', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-16 min-w-[64px]', align: 'right', getValue: it => it.plant_allocations?.admin, format: formatQty },
    { key: 'alloc_sales', label: 'Sales', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-16 min-w-[64px]', align: 'right', getValue: it => it.plant_allocations?.sales, format: formatQty },
    { key: 'alloc_users', label: 'Req by Users', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.plant_allocations?.req_by_users, format: formatQty },
    { key: 'alloc_tot', label: 'Total Value', group: 'PLANT WISE PLAN & ALLOCATIONS', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.plant_allocations?.total_value, format: formatCurrency },
    // Consumption Analysis
    { key: 'ca_avg_m', label: 'Avg.Monthly Con', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.consumption_analysis?.avg_monthly_con, format: formatQty },
    { key: 'ca_avg_d', label: 'Avg.Daily Con', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.consumption_analysis?.avg_daily_con, format: formatQty },
    { key: 'ca_moq', label: 'MOQ', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.moq, format: formatQty },
    { key: 'ca_lead', label: 'Lead days', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.lead_time_days },
    { key: 'ca_hold', label: 'Hold days', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.consumption_analysis?.hold_days },
    { key: 'ca_min', label: 'Min stock', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.min_stock_level, format: formatQty },
    { key: 'ca_max', label: 'Max stock', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.max_stock_level, format: formatQty },
    { key: 'ca_lead_qty', label: 'Lead qty', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.consumption_analysis?.lead_time_qty, format: formatQty },
    { key: 'ca_reorder', label: 'Re-Order Level', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.consumption_analysis?.reorder_level, format: formatQty },
    { key: 'ca_cost_msl', label: 'Cost of MSL', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.consumption_analysis?.cost_of_msl, format: formatCurrency },
    { key: 'ca_formula', label: 'Reorder Level (MSL Formula)', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-48 min-w-[192px]', align: 'right', getValue: it => it.consumption_analysis?.reorder_level, format: formatQty },
    { key: 'ca_avg_con_d', label: 'Avg. con/day', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-24 min-w-[96px]', align: 'right', getValue: it => it.consumption_analysis?.avg_daily_con, format: formatQty },
    { key: 'ca_prev_plan', label: 'Prev Plan val', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.consumption_analysis?.prev_plan_val, format: formatCurrency },
    { key: 'ca_prev_act', label: 'Prev Actual val', group: 'CONSUMPTION AND STOCK ANALYSIS', width: 'w-28 min-w-[112px]', align: 'right', getValue: it => it.consumption_analysis?.prev_actual_val, format: formatCurrency },
  ], [prevMonthLabel]);

  // Active column set based on view mode
  const currentAllColumns = viewMode === 'NORMAL_VIEW' ? NORMAL_COLUMNS : MD_COLUMNS;

  // Visible columns considering hiddenCols and group collapses
  const visibleColumns = useMemo(() => {
    return currentAllColumns.filter(c => {
      if (hiddenCols.has(c.key)) return false;
      if (viewMode === 'MD_VIEW') {
        if (collapsedGroups.plantWise && c.group === 'PLANT WISE PLAN & ALLOCATIONS') return false;
        if (collapsedGroups.consumptionAnalysis && c.group === 'CONSUMPTION AND STOCK ANALYSIS') return false;
      }
      return true;
    });
  }, [currentAllColumns, hiddenCols, viewMode, collapsedGroups]);

  // Group bands for visible columns
  const visibleGroups = useMemo(() => {
    const groups: { name: string; colSpan: number }[] = [];
    visibleColumns.forEach(c => {
      const last = groups[groups.length - 1];
      if (last && last.name === c.group) {
        last.colSpan += 1;
      } else {
        groups.push({ name: c.group, colSpan: 1 });
      }
    });
    return groups;
  }, [visibleColumns]);

  // Filtered items
  const filteredItems = useMemo(() => {
    return items.filter(it => {
      if (categoryFilter && (it.category || it.req_type) !== categoryFilter) return false;
      if (statusFilter === 'SHORTAGE' && parseFloat(String(it.order_qty || 0)) <= 0) return false;
      if (statusFilter === 'BELOW_MSL') {
        const avail = parseFloat(String(it.prev_closing_qty || 0));
        const msl = parseFloat(String(it.min_stock_level || 0));
        if (avail >= msl) return false;
      }
      if (!searchQuery) return true;
      const q = searchQuery.toLowerCase();
      return (
        it.item_id.toLowerCase().includes(q) ||
        it.description.toLowerCase().includes(q) ||
        (it.supplier_name && it.supplier_name.toLowerCase().includes(q)) ||
        (it.part_no_saleable && it.part_no_saleable.toLowerCase().includes(q)) ||
        (it.saleable_part_name && it.saleable_part_name.toLowerCase().includes(q))
      );
    });
  }, [items, categoryFilter, statusFilter, searchQuery]);

  // Selected cell helper
  const selectedItem = useMemo(() => {
    if (!selectedCell) return null;
    return filteredItems.find(it => it.id === selectedCell.rowId) || null;
  }, [selectedCell, filteredItems]);

  const selectedColConfig = useMemo(() => {
    if (!selectedCell) return null;
    return currentAllColumns.find(c => c.key === selectedCell.colKey) || null;
  }, [selectedCell, currentAllColumns]);

  // Update formula bar value when selected cell changes
  useEffect(() => {
    if (selectedItem && selectedColConfig) {
      const val = selectedColConfig.getValue ? selectedColConfig.getValue(selectedItem, 0) : (selectedItem as any)[selectedColConfig.key];
      setFormulaValue(String(val ?? ''));
    } else {
      setFormulaValue('');
    }
  }, [selectedCell, selectedItem, selectedColConfig]);

  // Focus inline edit input
  useEffect(() => {
    if (editingCell && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingCell]);

  // Formula bar commit
  const handleFormulaCommit = () => {
    if (!selectedCell || !selectedColConfig || !selectedColConfig.field) return;
    handleCellEdit(selectedCell.rowId, selectedColConfig.field, formulaValue);
  };

  // Cell Click & Double Click
  const handleCellClick = (rowId: string, colKey: string) => {
    setSelectedCell({ rowId, colKey });
  };

  const handleCellDoubleClick = (rowId: string, col: ColumnConfig) => {
    if (!canEdit || !col.editable) return;
    setSelectedCell({ rowId, colKey: col.key });
    setEditingCell({ rowId, colKey: col.key });
  };

  // Keyboard navigation for Excel grid
  const handleCellKeyDown = (e: React.KeyboardEvent, rowIdx: number, colIdx: number, col: ColumnConfig, rowId: string) => {
    if (editingCell) {
      if (e.key === 'Enter') {
        setEditingCell(null);
        if (rowIdx < filteredItems.length - 1) {
          setSelectedCell({ rowId: filteredItems[rowIdx + 1].id, colKey: col.key });
        }
      } else if (e.key === 'Escape') {
        setEditingCell(null);
      } else if (e.key === 'Tab') {
        e.preventDefault();
        setEditingCell(null);
        if (colIdx < visibleColumns.length - 1) {
          setSelectedCell({ rowId, colKey: visibleColumns[colIdx + 1].key });
        }
      }
      return;
    }

    if (e.key === 'Enter') {
      if (col.editable && canEdit) {
        setEditingCell({ rowId, colKey: col.key });
      }
    } else if (e.key === 'ArrowDown' && rowIdx < filteredItems.length - 1) {
      setSelectedCell({ rowId: filteredItems[rowIdx + 1].id, colKey: col.key });
    } else if (e.key === 'ArrowUp' && rowIdx > 0) {
      setSelectedCell({ rowId: filteredItems[rowIdx - 1].id, colKey: col.key });
    } else if (e.key === 'ArrowRight' && colIdx < visibleColumns.length - 1) {
      setSelectedCell({ rowId, colKey: visibleColumns[colIdx + 1].key });
    } else if (e.key === 'ArrowLeft' && colIdx > 0) {
      setSelectedCell({ rowId, colKey: visibleColumns[colIdx - 1].key });
    }
  };

  // Column visibility controls
  const toggleColumnVisibility = (colKey: string) => {
    setHiddenCols(prev => {
      const next = new Set(prev);
      if (next.has(colKey)) {
        next.delete(colKey);
      } else {
        next.add(colKey);
      }
      return next;
    });
  };

  const showAllColumns = () => {
    setHiddenCols(new Set());
    setCollapsedGroups({ plantWise: false, consumptionAnalysis: false });
  };

  const resetDefaultColumns = () => {
    setHiddenCols(new Set());
    setCollapsedGroups({ plantWise: false, consumptionAnalysis: false });
  };

  if (!canRead) {
    return <p role="alert" className="text-red-700 p-4">You do not have permission to view the purchase plan.</p>;
  }

  // Calculate stats for Excel status bar
  const totalOrderQty = filteredItems.reduce((acc, it) => acc + parseFloat(String(it.order_qty || 0)), 0);
  const totalOrderVal = filteredItems.reduce((acc, it) => acc + parseFloat(String(it.order_value || 0)), 0);

  return (
    <div className="space-y-4">
      {/* 1. TOP HEADER & PERIOD BAR */}
      <div className="bg-white rounded-xl border border-ink-text/10 p-3.5 shadow-2xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          {/* View Switcher */}
          <div className="flex items-center gap-1 p-1 bg-ink-text/5 rounded-lg border border-ink-text/10">
            <button
              onClick={() => { setViewMode('NORMAL_VIEW'); setHiddenCols(new Set()); }}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
                viewMode === 'NORMAL_VIEW'
                  ? 'bg-burnt-orange text-white shadow-2xs'
                  : 'text-ink-text/70 hover:text-ink-text'
              }`}
            >
              Normal View (23 cols)
            </button>
            <button
              onClick={() => { setViewMode('MD_VIEW'); setHiddenCols(new Set()); }}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
                viewMode === 'MD_VIEW'
                  ? 'bg-burnt-orange text-white shadow-2xs'
                  : 'text-ink-text/70 hover:text-ink-text'
              }`}
            >
              MD View (76 cols)
            </button>
          </div>

          <div className="h-5 w-px bg-ink-text/15" />

          {/* Month & Year Selectors */}
          <div className="flex items-center gap-2 text-sm font-medium">
            <label className="text-xs text-ink-text/70 uppercase font-semibold">Month:</label>
            <select
              value={selectedMonth}
              onChange={e => setSelectedMonth(parseInt(e.target.value, 10))}
              className="border border-ink-text/20 rounded-md px-2.5 py-1.5 text-xs bg-white font-medium focus:ring-1 focus:ring-burnt-orange"
            >
              {MONTH_NAMES.map((m, idx) => (
                <option key={m} value={idx + 1}>{m}</option>
              ))}
            </select>

            <label className="text-xs text-ink-text/70 uppercase font-semibold ml-2">Year:</label>
            <select
              value={selectedYear}
              onChange={e => setSelectedYear(parseInt(e.target.value, 10))}
              className="border border-ink-text/20 rounded-md px-2.5 py-1.5 text-xs bg-white font-medium focus:ring-1 focus:ring-burnt-orange"
            >
              {[2024, 2025, 2026, 2027, 2028].map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>

            <button
              aria-label="Load Plan"
              onClick={() => void loadPlan(currentPeriod)}
              disabled={isLoading}
              className="ml-2 px-3 py-1.5 bg-ink-text/5 hover:bg-ink-text/10 text-ink-text rounded-md text-xs font-semibold border border-ink-text/15 transition-colors disabled:opacity-50"
            >
              {isLoading ? 'Loading…' : 'Load Plan'}
            </button>
          </div>
        </div>

        {/* Plan Persisted Metadata */}
        <div className="text-right text-xs text-ink-text/70 leading-relaxed">
          <p className="font-semibold text-ink-text">
            Planning Period: {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
          </p>
          {plan ? (
            <p className="text-[11px] text-gray-500">
              Rev: <span className="font-mono font-semibold text-gray-700">{plan.revision_label}</span> • Last Modified: {formatLocalTime(plan.modified_at)}
            </p>
          ) : (
            <p className="text-amber-700 italic text-[11px]">No monthly purchase plan has been created.</p>
          )}
        </div>
      </div>

      {/* 2. PLAN PARAMETERS BANNER */}
      <div className="bg-vanilla-surface border border-burnt-orange/20 rounded-xl p-3 shadow-2xs flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-4">
          <span className="font-bold text-burnt-orange uppercase tracking-wider">Plan Parameters:</span>
          <span>No. of MSL Days for Gas: <strong className="text-ink-text">{plan?.msl_days_gas || '2.0'}</strong></span>
          <span>No. of MSL Days: <strong className="text-ink-text">{plan?.msl_days_general || '10.0'}</strong></span>
          <span>Month Days: <strong className="text-ink-text">{plan?.month_days || '31'}</strong></span>
          <span>Working Days: <strong className="text-ink-text">{plan?.working_days || '27'}</strong></span>
        </div>

        <div className="flex items-center gap-3">
          <Link
            to="/requirements"
            className="text-burnt-orange hover:text-burnt-orange-dark underline font-medium"
          >
            → View {MONTH_NAMES[selectedMonth - 1]} Requirements Plan
          </Link>
          <span className={`px-2 py-0.5 rounded font-semibold text-[11px] ${
            plan?.status === 'SUBMITTED' ? 'bg-blue-100 text-blue-800' :
            plan?.status === 'CALCULATED' ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-700'
          }`}>
            {plan?.status || 'DRAFT'}
          </span>
        </div>
      </div>

      {/* 3. EXCEL TOOLBAR (Action buttons + Column Visibility + Edit Mode) */}
      <div className="bg-white rounded-xl border border-gray-300 p-2.5 shadow-xs flex flex-wrap items-center justify-between gap-2.5 text-xs">
        {/* Left Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setIsUploadOpen(true)}
            className="px-3 py-1.5 bg-burnt-orange hover:bg-burnt-orange-dark text-white rounded-md font-semibold shadow-2xs transition-colors flex items-center gap-1.5"
          >
            <span>↑</span> Upload Excel Template
          </button>

          <button
            onClick={handleRecalculate}
            disabled={isRecalculating || (!plan && items.length === 0)}
            className="px-3 py-1.5 bg-blue-700 hover:bg-blue-800 text-white rounded-md font-semibold shadow-2xs transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            <span>↻</span> {isRecalculating ? 'Recalculating…' : 'Recalculate Gap & Orders'}
          </button>

          {canEdit && (
            <button
              onClick={handleSaveChanges}
              disabled={isSaving || dirtyItemIds.size === 0}
              className={`px-3 py-1.5 rounded-md font-semibold shadow-2xs transition-colors flex items-center gap-1.5 ${
                dirtyItemIds.size > 0
                  ? 'bg-emerald-700 hover:bg-emerald-800 text-white animate-pulse'
                  : 'bg-ink-text/5 text-ink-text/40 border border-ink-text/10'
              }`}
            >
              <span>💾</span> {isSaving ? 'Saving…' : `Save Changes (${dirtyItemIds.size})`}
            </button>
          )}

          <button
            onClick={handleSendToApproval}
            disabled={isSubmittingApproval || (!plan && items.length === 0)}
            className="px-3 py-1.5 bg-ink-text hover:bg-black text-white rounded-md font-semibold shadow-2xs transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            <span>✓</span> {isSubmittingApproval ? 'Submitting…' : 'Send to Approval Queue'}
          </button>

          <button
            onClick={handleExport}
            disabled={!plan && items.length === 0}
            className="px-3 py-1.5 bg-white hover:bg-gray-100 text-ink-text rounded-md font-semibold border border-gray-300 shadow-2xs transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            <span>↓</span> Export {viewMode === 'MD_VIEW' ? 'MD View' : 'Normal View'}
          </button>

          <div className="h-5 w-px bg-gray-300 mx-1" />

          {/* COLUMN VISIBILITY DROPDOWN */}
          <div className="relative" ref={colMenuRef}>
            <button
              onClick={() => setShowColMenu(p => !p)}
              className={`px-3 py-1.5 rounded-md font-semibold border shadow-2xs transition-colors flex items-center gap-1.5 ${
                hiddenCols.size > 0
                  ? 'bg-amber-50 text-amber-900 border-amber-300'
                  : 'bg-white hover:bg-gray-100 text-gray-700 border-gray-300'
              }`}
            >
              <span>👁️</span> Columns (Hide/Show)
              {hiddenCols.size > 0 && (
                <span className="bg-amber-600 text-white rounded-full px-1.5 py-0.2 text-[10px] font-bold">
                  {hiddenCols.size} hidden
                </span>
              )}
              <span className="text-[10px]">▾</span>
            </button>

            {showColMenu && (
              <div className="absolute left-0 mt-1 w-80 bg-white border border-gray-300 rounded-lg shadow-xl p-3 z-50 text-xs max-h-96 flex flex-col">
                <div className="flex items-center justify-between border-b pb-2 mb-2 font-bold text-gray-800">
                  <span>Manage Column Visibility</span>
                  <div className="flex gap-1.5 text-[11px] font-normal">
                    <button
                      onClick={showAllColumns}
                      className="text-blue-600 hover:underline"
                    >
                      Show All
                    </button>
                    <span>•</span>
                    <button
                      onClick={resetDefaultColumns}
                      className="text-gray-500 hover:underline"
                    >
                      Reset
                    </button>
                  </div>
                </div>

                <input
                  type="text"
                  placeholder="Filter columns…"
                  value={colSearchQuery}
                  onChange={e => setColSearchQuery(e.target.value)}
                  className="w-full px-2 py-1 mb-2 border border-gray-300 rounded text-xs bg-gray-50 focus:bg-white"
                />

                <div className="overflow-y-auto flex-1 space-y-1 divide-y divide-gray-100">
                  {currentAllColumns
                    .filter(c => !colSearchQuery || c.label.toLowerCase().includes(colSearchQuery.toLowerCase()) || c.group.toLowerCase().includes(colSearchQuery.toLowerCase()))
                    .map(col => {
                      const isHidden = hiddenCols.has(col.key);
                      return (
                        <label
                          key={col.key}
                          className="flex items-center justify-between p-1 hover:bg-gray-50 rounded cursor-pointer"
                        >
                          <div className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={!isHidden}
                              onChange={() => toggleColumnVisibility(col.key)}
                              className="text-emerald-700 rounded cursor-pointer"
                            />
                            <span className={isHidden ? 'text-gray-400 line-through' : 'text-gray-800 font-medium'}>
                              {col.label}
                            </span>
                          </div>
                          <span className="text-[10px] text-gray-400 truncate max-w-28 text-right">
                            {col.group}
                          </span>
                        </label>
                      );
                    })}
                </div>
              </div>
            )}
          </div>

          {/* Freeze Panes toggle */}
          <button
            onClick={() => setFreezePanes(p => !p)}
            className={`px-2.5 py-1.5 rounded-md font-semibold border text-xs shadow-2xs transition-colors flex items-center gap-1 ${
              freezePanes ? 'bg-slate-100 text-slate-800 border-slate-300' : 'bg-white text-gray-500 border-gray-200'
            }`}
            title="Freeze key ID columns while scrolling"
          >
            <span>📌</span> Freeze ID: {freezePanes ? 'ON' : 'OFF'}
          </button>

          {/* Edit Mode Toggle */}
          <button
            onClick={() => setEditMode(m => m === 'EXCEL_CLICK' ? 'DIRECT_INPUT' : 'EXCEL_CLICK')}
            className="px-2.5 py-1.5 rounded-md font-semibold border border-gray-300 bg-white hover:bg-gray-50 text-gray-700 text-xs shadow-2xs"
            title="Switch between Excel double-click edit mode and always-open input fields"
          >
            Mode: {editMode === 'EXCEL_CLICK' ? 'Excel Cell Mode' : 'Direct Inputs'}
          </button>
        </div>

        {/* Right Search & Filter Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            placeholder="Search code, description, supplier…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="border border-gray-300 rounded-md px-2.5 py-1.5 w-52 bg-white placeholder:text-gray-400 focus:ring-1 focus:ring-burnt-orange focus:outline-none"
          />

          <select
            value={categoryFilter}
            onChange={e => setCategoryFilter(e.target.value)}
            className="border border-gray-300 rounded-md px-2 py-1.5 bg-white text-gray-700"
          >
            <option value="">All Categories</option>
            <option value="Sheet Metal & Coil">Sheet Metal &amp; Coil</option>
            <option value="Fasteners & Hardware">Fasteners &amp; Hardware</option>
            <option value="Lubricants & Coolants">Lubricants &amp; Coolants</option>
            <option value="Packaging Materials">Packaging Materials</option>
            <option value="Welding Wire & Electrodes">Welding Wire &amp; Electrodes</option>
          </select>

          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="border border-gray-300 rounded-md px-2 py-1.5 bg-white text-gray-700"
          >
            <option value="">All Statuses</option>
            <option value="SHORTAGE">Requires Order (Qty &gt; 0)</option>
            <option value="BELOW_MSL">Below Min Stock Level</option>
          </select>
        </div>
      </div>

      {/* 4. EXCEL FORMULA / VALUE BAR (fx) */}
      <div className="flex items-center gap-2 py-1.5 px-3 bg-gray-100 rounded-lg border border-gray-300 text-xs shadow-2xs">
        {/* Cell Coordinate Box */}
        <div className="w-24 px-2 py-1 font-mono text-center font-bold text-gray-800 bg-white border border-gray-300 rounded shadow-2xs truncate">
          {selectedCell ? `${selectedItem?.item_id || 'Cell'}:${selectedColConfig?.label || ''}` : 'Ready'}
        </div>

        {/* fx symbol */}
        <div className="font-serif italic font-bold text-gray-600 px-1 select-none text-sm">
          fx
        </div>

        {/* Formula Input */}
        <input
          type="text"
          aria-label="Formula bar"
          placeholder={selectedCell ? (selectedColConfig?.formulaDesc || 'Enter cell value or formula…') : 'Select any cell to view formula or edit its value'}
          value={formulaValue}
          disabled={!selectedCell || !selectedColConfig?.editable || !canEdit}
          onChange={e => setFormulaValue(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') handleFormulaCommit();
          }}
          className="flex-1 px-3 py-1 bg-white border border-gray-300 rounded font-mono text-xs text-gray-900 focus:outline-none focus:ring-1 focus:ring-emerald-600 disabled:bg-gray-100 disabled:text-gray-600"
        />

        {selectedCell && selectedColConfig?.editable && canEdit && (
          <button
            onClick={handleFormulaCommit}
            className="px-2.5 py-1 bg-emerald-700 text-white rounded text-xs font-semibold hover:bg-emerald-800"
          >
            Enter ✓
          </button>
        )}
      </div>

      {/* Hidden columns banner if any are hidden */}
      {hiddenCols.size > 0 && (
        <div className="bg-amber-50 border border-amber-200 text-amber-900 px-3 py-1.5 rounded-lg text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span>👁️ {hiddenCols.size} columns are currently hidden.</span>
          </div>
          <button
            onClick={showAllColumns}
            className="font-bold underline hover:text-amber-950 cursor-pointer text-xs"
          >
            Unhide All Columns
          </button>
        </div>
      )}

      {/* Feedback banner */}
      {feedback && (
        <div
          role="alert"
          className={`p-3 rounded-lg text-xs font-medium border flex items-center justify-between ${
            feedback.type === 'success' ? 'bg-emerald-50 text-emerald-800 border-emerald-200' :
            feedback.type === 'error' ? 'bg-red-50 text-red-800 border-red-200' :
            'bg-blue-50 text-blue-800 border-blue-200'
          }`}
        >
          <span>{feedback.message}</span>
          <button onClick={() => setFeedback(null)} className="font-bold ml-2">×</button>
        </div>
      )}

      {/* Group Collapse Toggles for MD View */}
      {viewMode === 'MD_VIEW' && (
        <div className="flex items-center gap-2 text-[11px] bg-white p-2 rounded-lg border border-ink-text/10">
          <span className="font-semibold text-ink-text/60 uppercase">Group View Toggles:</span>
          <button
            onClick={() => toggleGroup('plantWise')}
            className={`px-2 py-0.5 rounded border ${
              collapsedGroups.plantWise ? 'bg-amber-100 text-amber-900 border-amber-200' : 'bg-gray-100 text-gray-700'
            }`}
          >
            {collapsedGroups.plantWise ? '+ Expand Plant Wise Plan' : '− Collapse Plant Wise Plan (15 cols)'}
          </button>
          <button
            onClick={() => toggleGroup('consumptionAnalysis')}
            className={`px-2 py-0.5 rounded border ${
              collapsedGroups.consumptionAnalysis ? 'bg-amber-100 text-amber-900 border-amber-200' : 'bg-gray-100 text-gray-700'
            }`}
          >
            {collapsedGroups.consumptionAnalysis ? '+ Expand Consumption Analysis' : '− Collapse Consumption Analysis (14 cols)'}
          </button>
        </div>
      )}

      {/* 5. EXCEL SPREADSHEET TABLE GRID (NO OVERLAPPING, CLEAN BORDERS & CELL CLIP) */}
      <div className="bg-white rounded-xl border border-gray-300 shadow-sm overflow-hidden flex flex-col h-[650px]">
        <div className="overflow-auto flex-1 relative bg-white">
          <table className="min-w-full text-xs text-left border-collapse table-fixed">
            {/* GROUP BANDS HEADER ROW - STICKY TOP 0 (NO HORIZONTAL STICKY COLLISION) */}
            <thead className="sticky top-0 z-30 select-none">
              <tr className="bg-brand-navy text-white text-[11px] font-bold tracking-wider border-b border-white/20">
                {/* Excel Row # Corner Gutter */}
                <th
                  style={{ width: 44, minWidth: 44 }}
                  className={`p-1.5 text-center bg-slate-900 text-slate-400 border-r border-white/20 ${
                    freezePanes ? 'sticky left-0 z-40' : ''
                  }`}
                >
                  #
                </th>

                {visibleGroups.map((grp, gIdx) => (
                  <th
                    key={`${grp.name}-${gIdx}`}
                    colSpan={grp.colSpan}
                    className="px-3 py-2 text-center border-r border-white/20 truncate uppercase text-[10px] tracking-wider"
                    style={{
                      backgroundColor:
                        grp.name.includes('ITEM') ? '#1e293b' :
                        grp.name.includes('STOCK &') ? '#1e3a8a' :
                        grp.name.includes('PREVIOUS') ? '#334155' :
                        grp.name.includes('SELECTED') || grp.name.includes('R1') ? '#064e3b' :
                        grp.name.includes('R2') ? '#134e4a' :
                        grp.name.includes('PLANT') ? '#581c87' :
                        grp.name.includes('CONSUMPTION') ? '#312e81' : '#1e293b'
                    }}
                  >
                    {grp.name}
                  </th>
                ))}
              </tr>

              {/* INDIVIDUAL COLUMN HEADERS ROW - STICKY TOP 32px */}
              <tr className="bg-brand-steel text-white text-[11px] font-semibold border-b border-gray-400 shadow-2xs">
                {/* Excel Row Index header */}
                <th
                  style={{ width: 44, minWidth: 44 }}
                  className={`p-1.5 text-center bg-slate-800 text-slate-400 font-mono border-r border-gray-400 ${
                    freezePanes ? 'sticky left-0 z-40' : ''
                  }`}
                >
                  №
                </th>

                {visibleColumns.map(col => {
                  const isKeyFreeze = freezePanes && (col.key === 'item_id' || (viewMode === 'MD_VIEW' && col.key === 'supplier_id'));
                  return (
                    <th
                      key={col.key}
                      className={`${col.width} px-2.5 py-1.5 select-none border-r border-white/20 relative group text-${col.align ?? 'left'} ${
                        isKeyFreeze ? 'sticky left-[44px] z-30 bg-slate-800 shadow-[2px_0_4px_rgba(0,0,0,0.15)]' : 'bg-brand-steel'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-1 overflow-hidden">
                        <span className="truncate font-semibold" title={col.label}>
                          {col.label}
                        </span>

                        {/* Column Header Menu Button (Hide Column) */}
                        <div className="relative header-menu-container">
                          <button
                            onClick={e => {
                              e.stopPropagation();
                              setActiveHeaderMenu(activeHeaderMenu === col.key ? null : col.key);
                            }}
                            className="opacity-0 group-hover:opacity-100 hover:bg-white/20 px-1 rounded text-[10px] text-white/80 transition-opacity"
                            title="Column options"
                          >
                            ▾
                          </button>

                          {activeHeaderMenu === col.key && (
                            <div className="absolute right-0 mt-1 w-36 bg-white border border-gray-200 rounded shadow-lg p-1.5 z-50 text-gray-800 font-normal text-left">
                              <button
                                onClick={() => {
                                  toggleColumnVisibility(col.key);
                                  setActiveHeaderMenu(null);
                                }}
                                className="w-full text-left px-2 py-1 hover:bg-gray-100 rounded text-xs flex items-center gap-1.5"
                              >
                                <span>👁️‍🗨️</span> Hide Column
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>

            {/* SPREADSHEET TABLE BODY (GRID CELLS WITH BORDER AND SELECTION) */}
            <tbody className="divide-y divide-gray-200 font-mono text-[11px] text-ink-text bg-white">
              {isLoading ? (
                <tr>
                  <td colSpan={visibleColumns.length + 1} className="p-8 text-center bg-gray-50/50">
                    <TableSkeleton rows={6} />
                  </td>
                </tr>
              ) : filteredItems.length === 0 ? (
                <tr>
                  <td
                    colSpan={visibleColumns.length + 1}
                    className="p-12 text-center text-ink-text/60 bg-gray-50/50 font-sans"
                  >
                    <p className="text-sm font-semibold text-ink-text/70 mb-1">
                      No purchase plan records found for {MONTH_NAMES[selectedMonth - 1]} {selectedYear}.
                    </p>
                    <p className="text-xs">
                      Click <strong>Upload Excel Template</strong> to import the monthly sheet, or <strong>Load Plan</strong> to refresh.
                    </p>
                  </td>
                </tr>
              ) : (
                filteredItems.map((it, rIdx) => {
                  const isDirty = dirtyItemIds.has(it.id);
                  const isShortage = parseFloat(String(it.order_qty || 0)) > 0;

                  return (
                    <tr
                      key={it.id}
                      className={`h-8 transition-colors ${
                        isDirty ? 'bg-amber-50/60' : rIdx % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'
                      } hover:bg-emerald-50/40`}
                    >
                      {/* Excel Row Number Cell */}
                      <td
                        style={{ width: 44, minWidth: 44 }}
                        className={`text-center font-mono text-gray-400 border-r border-b border-gray-300 select-none ${
                          freezePanes ? 'sticky left-0 z-20 bg-slate-100' : 'bg-slate-100'
                        }`}
                      >
                        {rIdx + 1}
                      </td>

                      {/* Data Cells */}
                      {visibleColumns.map((col, cIdx) => {
                        const rawVal = col.getValue ? col.getValue(it, rIdx) : (it as any)[col.key];
                        const displayVal = col.format ? col.format(rawVal) : String(rawVal ?? '—');
                        const isSelected = selectedCell?.rowId === it.id && selectedCell?.colKey === col.key;
                        const isEditingThis = editingCell?.rowId === it.id && editingCell?.colKey === col.key;
                        const isKeyFreeze = freezePanes && (col.key === 'item_id' || (viewMode === 'MD_VIEW' && col.key === 'supplier_id'));

                        return (
                          <td
                            key={col.key}
                            tabIndex={0}
                            onClick={() => handleCellClick(it.id, col.key)}
                            onDoubleClick={() => handleCellDoubleClick(it.id, col)}
                            onKeyDown={e => handleCellKeyDown(e, rIdx, cIdx, col, it.id)}
                            style={{
                              backgroundColor: isSelected ? '#ecfdf5' : undefined,
                            }}
                            className={`${col.width} px-2.5 py-1 border-r border-b border-gray-300 overflow-hidden text-ellipsis whitespace-nowrap text-${col.align ?? 'left'} relative cursor-cell select-none outline-none ${
                              isKeyFreeze ? 'sticky left-[44px] z-10 bg-white shadow-[2px_0_4px_rgba(0,0,0,0.08)]' : ''
                            } ${
                              isSelected ? 'ring-2 ring-emerald-600 ring-inset bg-emerald-50 font-semibold' : ''
                            } ${
                              col.key === 'order_qty' && isShortage ? 'text-red-700 font-bold bg-red-50/50' : ''
                            } ${
                              col.key === 'item_id' ? 'font-bold text-blue-900 font-sans' : ''
                            }`}
                            title={`${col.label}: ${rawVal ?? ''}`}
                          >
                            {/* Inline Cell Editor when double-clicked or in DIRECT_INPUT mode */}
                            {isEditingThis ? (
                              <input
                                ref={editInputRef}
                                type="text"
                                defaultValue={String(rawVal ?? '')}
                                onBlur={e => {
                                  if (col.field) handleCellEdit(it.id, col.field, e.target.value);
                                  setEditingCell(null);
                                }}
                                onKeyDown={e => {
                                  if (e.key === 'Enter') {
                                    if (col.field) handleCellEdit(it.id, col.field, (e.target as HTMLInputElement).value);
                                    setEditingCell(null);
                                  } else if (e.key === 'Escape') {
                                    setEditingCell(null);
                                  }
                                }}
                                className="w-full h-full p-0 bg-white border border-emerald-600 font-mono text-[11px] focus:outline-none"
                              />
                            ) : editMode === 'DIRECT_INPUT' && col.editable && canEdit ? (
                              <input
                                type="number"
                                step="0.01"
                                value={rawVal ?? ''}
                                onChange={e => {
                                  if (col.field) handleCellEdit(it.id, col.field, e.target.value);
                                }}
                                className={`w-full bg-transparent border-b border-gray-300 focus:border-burnt-orange focus:outline-none text-${col.align ?? 'left'}`}
                              />
                            ) : (
                              <span>{displayVal}</span>
                            )}

                            {/* Small indicator if cell was modified */}
                            {isDirty && col.field && (
                              <span className="absolute top-0 right-0 w-1.5 h-1.5 bg-amber-500 rounded-bl-sm" />
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* 6. EXCEL BOTTOM STATUS BAR */}
        <div className="bg-gray-100 border-t border-gray-300 px-3 py-1.5 flex flex-wrap items-center justify-between text-[11px] font-sans text-gray-700 select-none">
          <div className="flex items-center gap-4">
            <span className="bg-white border border-gray-300 px-2 py-0.5 rounded text-xs font-semibold text-emerald-800 flex items-center gap-1.5">
              <span>📄</span> Sheet 1: {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
            </span>

            <span className="text-gray-500">
              Total Rows: <strong className="text-gray-900">{filteredItems.length}</strong>
            </span>

            <span>
              Orders Needed: <strong className="text-red-700">{filteredItems.filter(i => parseFloat(String(i.order_qty || 0)) > 0).length}</strong>
            </span>

            {dirtyItemIds.size > 0 && (
              <span className="text-amber-800 bg-amber-100 px-2 py-0.5 rounded font-bold">
                ⚠️ {dirtyItemIds.size} unsaved modifications
              </span>
            )}
          </div>

          <div className="flex items-center gap-5 font-mono text-[11px]">
            <span>Sum Order Qty: <strong className="text-gray-900 font-semibold">{formatQty(totalOrderQty)}</strong></span>
            <span>Total Value: <strong className="text-emerald-800 font-bold">{formatCurrency(totalOrderVal)}</strong></span>
            <span className="text-gray-400 font-sans">100% 🔍</span>
          </div>
        </div>
      </div>

      {/* EXCEL UPLOAD MODAL */}
      {isUploadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
          <div className="bg-white rounded-xl max-w-2xl w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="text-lg font-bold text-brand-navy">Import Purchase Plan Template</h3>
              <button onClick={() => { setIsUploadOpen(false); setUploadFile(null); setInspectResult(null); }} className="text-gray-400 hover:text-gray-600 text-xl font-bold">×</button>
            </div>

            <p className="text-xs text-gray-600">
              Upload either the <strong>Normal View template (23 columns)</strong> or the <strong>MD View template (76 columns)</strong> for {MONTH_NAMES[selectedMonth - 1]} {selectedYear}. The system will auto-detect the view format, validate headers and decimal entries, and merge into the month&apos;s plan.
            </p>

            <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-burnt-orange transition-colors">
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls"
                onChange={e => {
                  if (e.target.files?.[0]) void handleFileChosen(e.target.files[0]);
                }}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="px-4 py-2 bg-burnt-orange text-white text-xs font-semibold rounded shadow-xs hover:bg-burnt-orange-dark transition-colors"
              >
                Choose Excel Workbook (.xlsx)
              </button>
              {uploadFile && (
                <p className="mt-2 text-xs font-mono text-gray-800">
                  Selected: <strong>{uploadFile.name}</strong> ({Math.round(uploadFile.size / 1024)} KB)
                </p>
              )}
            </div>

            {isInspecting && (
              <p className="text-xs text-blue-700 animate-pulse text-center">Analyzing workbook structure and checking column headers…</p>
            )}

            {inspectResult && (
              <div className="space-y-3 bg-gray-50 p-3.5 rounded-lg border text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-brand-navy">
                    Detected Format: <span className="text-burnt-orange uppercase">{inspectResult.detected_view === 'MD_VIEW' ? 'MD View (76 Columns)' : 'Normal View (23 Columns)'}</span>
                  </span>
                  <span className="text-gray-600 font-mono">
                    Found {inspectResult.total_rows} data rows, {inspectResult.total_columns} columns
                  </span>
                </div>

                {inspectResult.validation_errors.length > 0 ? (
                  <div className="bg-red-50 text-red-800 p-2.5 rounded border border-red-200">
                    <p className="font-bold mb-1">Validation Warnings ({inspectResult.validation_errors.length}):</p>
                    <ul className="list-disc pl-4 space-y-0.5 text-[11px]">
                      {inspectResult.validation_errors.slice(0, 5).map((e, i) => (
                        <li key={i}>Row {e.row}, Col &quot;{e.column}&quot;: {e.error}</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p className="text-emerald-700 font-semibold">✓ All headers and formula evaluations passed validation checks.</p>
                )}
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2 border-t">
              <button
                type="button"
                onClick={() => { setIsUploadOpen(false); setUploadFile(null); setInspectResult(null); }}
                className="px-4 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-100 rounded"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!inspectResult || isImporting}
                onClick={handleConfirmImport}
                className="px-4 py-2 bg-brand-navy hover:bg-blue-900 text-white text-xs font-semibold rounded disabled:opacity-50"
              >
                {isImporting ? 'Importing…' : 'Confirm & Import Into Plan'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
