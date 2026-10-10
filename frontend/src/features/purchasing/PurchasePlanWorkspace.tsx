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

  // Column Group Collapse toggles
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({
    plantWise: false,
    consumptionAnalysis: false,
    previousMonth: false,
    actualPurchase: false,
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
            const reason = window.prompt(`Please provide a reason for overriding Order Qty for ${it.item_id}:`);
            updated.override_reason = reason || 'Manual user adjustment';
          }
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

  // Filtered Items
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

  const prevMonthLabel = getPrevPeriodLabel(currentPeriod);
  const currentShortLabel = getPeriodShortLabel(currentPeriod);

  if (!canRead) {
    return <p role="alert" className="text-red-700 p-4">You do not have permission to view the purchase plan.</p>;
  }

  return (
    <div className="space-y-5">
      {/* View Switcher & Period Selector Bar */}
      <div className="bg-white rounded-xl border border-ink-text/10 p-4 shadow-2xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* View Switcher */}
          <div className="flex items-center gap-1.5 p-1 bg-ink-text/5 rounded-lg border border-ink-text/10">
            <button
              onClick={() => setViewMode('NORMAL_VIEW')}
              className={`px-3.5 py-1.5 text-xs font-semibold rounded-md transition-all ${
                viewMode === 'NORMAL_VIEW'
                  ? 'bg-burnt-orange text-white shadow-2xs'
                  : 'text-ink-text/70 hover:text-ink-text'
              }`}
            >
              Normal View (23 cols)
            </button>
            <button
              onClick={() => setViewMode('MD_VIEW')}
              className={`px-3.5 py-1.5 text-xs font-semibold rounded-md transition-all ${
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
              className="border border-ink-text/20 rounded-md px-2.5 py-1.5 text-sm bg-white font-medium focus:ring-1 focus:ring-burnt-orange"
            >
              {MONTH_NAMES.map((m, idx) => (
                <option key={m} value={idx + 1}>{m}</option>
              ))}
            </select>

            <label className="text-xs text-ink-text/70 uppercase font-semibold ml-2">Year:</label>
            <select
              value={selectedYear}
              onChange={e => setSelectedYear(parseInt(e.target.value, 10))}
              className="border border-ink-text/20 rounded-md px-2.5 py-1.5 text-sm bg-white font-medium focus:ring-1 focus:ring-burnt-orange"
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
            <>
              <p>Created: {formatLocalTime(plan.created_at)} by <span className="font-medium text-ink-text">{plan.created_by_name}</span></p>
              <p>Last Modified: {formatLocalTime(plan.modified_at)} by <span className="font-medium text-ink-text">{plan.modified_by_name || plan.created_by_name}</span></p>
            </>
          ) : (
            <p className="text-amber-700 italic">No monthly purchase plan has been created.</p>
          )}
        </div>
      </div>

      {/* Plan Parameters & Link Banner */}
      <div className="bg-vanilla-surface border border-burnt-orange/20 rounded-xl p-3.5 shadow-2xs flex flex-wrap items-center justify-between gap-3 text-xs">
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
          <span className="px-2 py-0.5 rounded bg-ink-text/5 text-ink-text/70 font-mono">
            Revision: {plan?.revision_label || 'R1'}
          </span>
          <span className={`px-2 py-0.5 rounded font-semibold ${
            plan?.status === 'SUBMITTED' ? 'bg-blue-100 text-blue-800' :
            plan?.status === 'CALCULATED' ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-700'
          }`}>
            {plan?.status || 'DRAFT'}
          </span>
        </div>
      </div>

      {/* Action Buttons Toolbar & Search */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => setIsUploadOpen(true)}
            className="px-3.5 py-1.5 bg-burnt-orange hover:bg-burnt-orange-dark text-white rounded-md text-xs font-semibold shadow-2xs transition-colors flex items-center gap-1.5"
          >
            <span>↑</span> Upload Excel Template
          </button>

          <button
            onClick={handleRecalculate}
            disabled={isRecalculating || (!plan && items.length === 0)}
            className="px-3.5 py-1.5 bg-blue-700 hover:bg-blue-800 text-white rounded-md text-xs font-semibold shadow-2xs transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            <span>↻</span> {isRecalculating ? 'Recalculating…' : 'Recalculate Gap & Orders'}
          </button>

          {canEdit && (
            <button
              onClick={handleSaveChanges}
              disabled={isSaving || dirtyItemIds.size === 0}
              className={`px-3.5 py-1.5 rounded-md text-xs font-semibold shadow-2xs transition-colors flex items-center gap-1.5 ${
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
            className="px-3.5 py-1.5 bg-ink-text hover:bg-black text-white rounded-md text-xs font-semibold shadow-2xs transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            <span>✓</span> {isSubmittingApproval ? 'Submitting…' : 'Send to Approval Queue'}
          </button>

          <button
            onClick={handleExport}
            disabled={!plan && items.length === 0}
            className="px-3.5 py-1.5 bg-white hover:bg-ink-text/5 text-ink-text rounded-md text-xs font-semibold border border-ink-text/20 shadow-2xs transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            <span>↓</span> Export {viewMode === 'MD_VIEW' ? 'MD View' : 'Normal View'}
          </button>
        </div>

        {/* Search & Filter Controls */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <input
            type="text"
            placeholder="Search code, description, supplier…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="border border-ink-text/20 rounded-md px-2.5 py-1.5 w-60 bg-white placeholder:text-ink-text/40 focus:ring-1 focus:ring-burnt-orange focus:outline-none"
          />

          <select
            value={categoryFilter}
            onChange={e => setCategoryFilter(e.target.value)}
            className="border border-ink-text/20 rounded-md px-2.5 py-1.5 bg-white"
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
            className="border border-ink-text/20 rounded-md px-2.5 py-1.5 bg-white"
          >
            <option value="">All Statuses</option>
            <option value="SHORTAGE">Requires Order (Qty &gt; 0)</option>
            <option value="BELOW_MSL">Below Min Stock Level</option>
          </select>
        </div>
      </div>

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

      {/* SPREADSHEET TABLE: ALWAYS VISIBLE STICKY HEADERS */}
      <div className="bg-white rounded-xl border border-ink-text/10 shadow-sm overflow-hidden flex flex-col h-[650px]">
        <div className="overflow-auto flex-1 relative">
          <table className="min-w-full text-xs text-left border-collapse">
            {/* GROUP BANDS HEADER ROW - STICKY TOP 0 */}
            <thead className="sticky top-0 z-30 bg-brand-navy text-white text-[11px] font-bold tracking-wider select-none border-b border-white/20">
              {viewMode === 'NORMAL_VIEW' ? (
                <tr>
                  {/* Sticky left columns in group band */}
                  <th colSpan={6} className="sticky left-0 z-40 bg-brand-navy px-3 py-2 text-center border-r border-white/20">
                    ITEM IDENTITY &amp; UOM
                  </th>
                  <th colSpan={4} className="px-3 py-2 text-center bg-blue-900 border-r border-white/20">
                    STOCK &amp; COMMERCIAL RULES
                  </th>
                  <th colSpan={5} className="px-3 py-2 text-center bg-slate-800 border-r border-white/20">
                    PREVIOUS MONTH STOCK ({prevMonthLabel})
                  </th>
                  <th colSpan={4} className="px-3 py-2 text-center bg-emerald-900 border-r border-white/20">
                    SELECTED MONTH PLAN ({currentShortLabel})
                  </th>
                  <th colSpan={4} className="px-3 py-2 text-center bg-indigo-900">
                    ACTUAL PURCHASE PROGRESS
                  </th>
                </tr>
              ) : (
                <tr>
                  <th colSpan={7} className="sticky left-0 z-40 bg-brand-navy px-3 py-2 text-center border-r border-white/20">
                    ITEM / SUPPLIER
                  </th>
                  <th colSpan={8} className="px-3 py-2 text-center bg-slate-900 border-r border-white/20">
                    PART / PROCESS (USAGE)
                  </th>
                  <th colSpan={7} className="px-3 py-2 text-center bg-slate-800 border-r border-white/20">
                    PREVIOUS MONTH STOCK ({prevMonthLabel})
                  </th>
                  <th colSpan={4} className="px-3 py-2 text-center bg-blue-900 border-r border-white/20">
                    STOCK PARAMETERS
                  </th>
                  <th colSpan={9} className="px-3 py-2 text-center bg-emerald-900 border-r border-white/20">
                    SCHEDULE R1
                  </th>
                  <th colSpan={10} className="px-3 py-2 text-center bg-teal-900 border-r border-white/20">
                    SCHEDULE R2 (REVISION)
                  </th>
                  <th colSpan={2} className="px-3 py-2 text-center bg-slate-800 border-r border-white/20">
                    TOTALS
                  </th>
                  {!collapsedGroups.plantWise && (
                    <th colSpan={15} className="px-3 py-2 text-center bg-purple-900 border-r border-white/20">
                      PLANT WISE PLAN &amp; ALLOCATIONS
                    </th>
                  )}
                  {!collapsedGroups.consumptionAnalysis && (
                    <th colSpan={14} className="px-3 py-2 text-center bg-indigo-900">
                      CONSUMPTION AND STOCK ANALYSIS
                    </th>
                  )}
                </tr>
              )}

              {/* INDIVIDUAL COLUMN HEADERS ROW - STICKY TOP 33px */}
              <tr className="bg-brand-steel text-white text-[11px] font-semibold border-b border-ink-text/15">
                {viewMode === 'NORMAL_VIEW' ? (
                  <>
                    <th className="sticky left-0 z-40 bg-brand-steel px-2.5 py-2 w-14 text-center border-r border-white/10">S. No.</th>
                    <th className="sticky left-14 z-40 bg-brand-steel px-3 py-2 w-32 border-r border-white/10">Req. Type</th>
                    <th className="sticky left-46 z-40 bg-brand-steel px-3 py-2 w-36 border-r border-white/10">Item Id</th>
                    <th className="px-3 py-2 min-w-56">Description</th>
                    <th className="px-2.5 py-2 w-16 text-center">Unit</th>
                    <th className="px-2.5 py-2 w-24 text-right">Output / Unit</th>
                    <th className="px-2.5 py-2 w-24 text-right">MOQ.</th>
                    <th className="px-2.5 py-2 w-28 text-right">Min. Stock. Level</th>
                    <th className="px-2.5 py-2 w-28 text-right">Max. Stock Level</th>
                    <th className="px-2.5 py-2 w-24 text-right">Rate</th>
                    <th className="px-2.5 py-2 w-24 text-right bg-slate-700/60">O/s. {prevMonthLabel}</th>
                    <th className="px-2.5 py-2 w-24 text-right bg-slate-700/60">Receipt</th>
                    <th className="px-2.5 py-2 w-24 text-right bg-slate-700/60">Issues</th>
                    <th className="px-2.5 py-2 w-24 text-right bg-slate-700/60">C/s. {prevMonthLabel}</th>
                    <th className="px-2.5 py-2 w-24 text-right bg-slate-700/60">Prd. Qty.</th>
                    <th className="px-2.5 py-2 w-24 text-right bg-emerald-800/60">Sch. {currentShortLabel}</th>
                    <th className="px-2.5 py-2 w-24 text-right bg-emerald-800/60">Req. Qty.</th>
                    <th className="px-2.5 py-2 w-28 text-right bg-emerald-800 text-white font-bold">Order Qty.</th>
                    <th className="px-2.5 py-2 w-28 text-right bg-emerald-800 text-white font-bold">Order Value</th>
                    <th className="px-2.5 py-2 w-24 text-right bg-indigo-800/60">Pur. Qty.</th>
                    <th className="px-2.5 py-2 w-28 text-right bg-indigo-800/60">Pur. Value</th>
                    <th className="px-2.5 py-2 w-24 text-right bg-indigo-800/60">Bal. Pur. Qty</th>
                    <th className="px-2.5 py-2 w-28 text-right bg-indigo-800/60">Bal. Pur. Value</th>
                  </>
                ) : (
                  <>
                    <th className="sticky left-0 z-40 bg-brand-steel px-2.5 py-2 w-28 border-r border-white/10">Supplier ID</th>
                    <th className="sticky left-28 z-40 bg-brand-steel px-3 py-2 w-48 border-r border-white/10">Supplier name</th>
                    <th className="sticky left-76 z-40 bg-brand-steel px-3 py-2 w-36 border-r border-white/10 font-bold">Item Id</th>
                    <th className="px-3 py-2 w-28">Category</th>
                    <th className="px-3 py-2 w-32">Type of material</th>
                    <th className="px-2 py-2 w-14 text-center">S. No.</th>
                    <th className="px-3 py-2 min-w-56 font-bold">Description</th>
                    <th className="px-2.5 py-2 w-36">Part No. saleable</th>
                    <th className="px-3 py-2 w-44">Used for part name</th>
                    <th className="px-2.5 py-2 w-32">Used Part no</th>
                    <th className="px-3 py-2 w-36">Process name</th>
                    <th className="px-2.5 py-2 w-28">Thickness/Gsm</th>
                    <th className="px-2.5 py-2 w-24 text-right">No of process</th>
                    <th className="px-2.5 py-2 w-24 text-right">Output/ Unit</th>
                    <th className="px-2.5 py-2 w-24 text-right">Rate</th>
                    <th className="px-2.5 py-2 w-24 text-right">Opening Qty</th>
                    <th className="px-2.5 py-2 w-28 text-right">Opening Value</th>
                    <th className="px-2.5 py-2 w-24 text-right">Receipt. Qty.</th>
                    <th className="px-2.5 py-2 w-24 text-right">Issue Qty.</th>
                    <th className="px-2.5 py-2 w-24 text-right">Closing Qty</th>
                    <th className="px-2.5 py-2 w-28 text-right">Closing Value</th>
                    <th className="px-2.5 py-2 w-24 text-right">Rate (Prev)</th>
                    <th className="px-2.5 py-2 w-28 text-right">Min stock level</th>
                    <th className="px-2.5 py-2 w-28 text-right">Max stock level</th>
                    <th className="px-2.5 py-2 w-28 text-right">Min order qty.</th>
                    <th className="px-2.5 py-2 w-24 text-right">Lead time days</th>
                    <th className="px-2.5 py-2 w-24 text-right">Sch. Qty. R1</th>
                    <th className="px-2.5 py-2 w-20 text-center">Purch. Unit</th>
                    <th className="px-2.5 py-2 w-24 text-right">Sch. Qty. Item R1</th>
                    <th className="px-2.5 py-2 w-24 text-right">Opening stock</th>
                    <th className="px-2.5 py-2 w-24 text-right">Req. Qty.</th>
                    <th className="px-2.5 py-2 w-28 text-right bg-emerald-800 text-white font-bold">Order Qty R1</th>
                    <th className="px-2.5 py-2 w-28 text-right bg-emerald-800 text-white font-bold">Order Value R1</th>
                    <th className="px-2.5 py-2 w-24 text-right">Receipt qty. R1</th>
                    <th className="px-2.5 py-2 w-28 text-right">Receipt value R1</th>
                    <th className="px-2.5 py-2 w-24 text-right">Sch. Qty. R2</th>
                    <th className="px-2.5 py-2 w-24 text-right">Sch. Cons. R2</th>
                    <th className="px-2.5 py-2 w-24 text-right">Req. R2</th>
                    <th className="px-2.5 py-2 w-24 text-right">Closing stock</th>
                    <th className="px-2.5 py-2 w-28 text-right">Req. lessed issue</th>
                    <th className="px-2.5 py-2 w-24 text-right">Issue Qty. till</th>
                    <th className="px-2.5 py-2 w-28 text-right font-bold">Order Qty. R2</th>
                    <th className="px-2.5 py-2 w-28 text-right font-bold">Order Value R2</th>
                    <th className="px-2.5 py-2 w-24 text-right">Receipt qty. R2</th>
                    <th className="px-2.5 py-2 w-28 text-right">Receipt value R2</th>
                    <th className="px-2.5 py-2 w-24 text-right font-bold">Total Receipt Qty.</th>
                    <th className="px-2.5 py-2 w-28 text-right font-bold">Total Receipt Val.</th>
                    {!collapsedGroups.plantWise && (
                      <>
                        <th className="px-2 py-2 w-16 text-right">P1</th>
                        <th className="px-2 py-2 w-16 text-right">P2</th>
                        <th className="px-2 py-2 w-16 text-right">P3</th>
                        <th className="px-2 py-2 w-16 text-right">P4</th>
                        <th className="px-2 py-2 w-16 text-right">P5</th>
                        <th className="px-2 py-2 w-20 text-right">tool room</th>
                        <th className="px-2 py-2 w-16 text-right">Quality</th>
                        <th className="px-2 py-2 w-16 text-right">PMD</th>
                        <th className="px-2 py-2 w-16 text-right">NPD</th>
                        <th className="px-2 py-2 w-16 text-right">HRD</th>
                        <th className="px-2 py-2 w-20 text-right">Accounts</th>
                        <th className="px-2 py-2 w-24 text-right">Purchase/Admin</th>
                        <th className="px-2 py-2 w-16 text-right">Sales</th>
                        <th className="px-2 py-2 w-24 text-right">Req. users</th>
                        <th className="px-2 py-2 w-24 text-right font-bold">Total Value.</th>
                      </>
                    )}
                    {!collapsedGroups.consumptionAnalysis && (
                      <>
                        <th className="px-2.5 py-2 w-28 text-right">Avg.Monthly Con</th>
                        <th className="px-2.5 py-2 w-28 text-right">Avg.Daily Con</th>
                        <th className="px-2.5 py-2 w-24 text-right">MOQ</th>
                        <th className="px-2.5 py-2 w-24 text-right">Lead days</th>
                        <th className="px-2.5 py-2 w-24 text-right">Hold days</th>
                        <th className="px-2.5 py-2 w-24 text-right">Min stock</th>
                        <th className="px-2.5 py-2 w-24 text-right">Max stock</th>
                        <th className="px-2.5 py-2 w-24 text-right">Lead qty</th>
                        <th className="px-2.5 py-2 w-24 text-right">Re-Order Level</th>
                        <th className="px-2.5 py-2 w-28 text-right">Cost of MSL</th>
                        <th className="px-3 py-2 w-48 text-right" title="REORDER LEVEL(MSL+(Avg.reqd.con per dayxLead timr to supply in days))">
                          Reorder Level (MSL Formula)
                        </th>
                        <th className="px-2.5 py-2 w-24 text-right">Avg. con/day</th>
                        <th className="px-2.5 py-2 w-28 text-right">Prev Plan val</th>
                        <th className="px-2.5 py-2 w-28 text-right">Prev Actual val</th>
                      </>
                    )}
                  </>
                )}
              </tr>
            </thead>

            {/* TABLE BODY */}
            <tbody className="divide-y divide-gray-200 font-mono text-[11px] text-ink-text">
              {isLoading ? (
                <tr>
                  <td colSpan={viewMode === 'NORMAL_VIEW' ? 23 : 76} className="p-8 text-center bg-gray-50/50">
                    <TableSkeleton rows={6} />
                  </td>
                </tr>
              ) : filteredItems.length === 0 ? (
                <tr>
                  <td
                    colSpan={viewMode === 'NORMAL_VIEW' ? 23 : 76}
                    className="p-12 text-center text-ink-text/60 bg-gray-50/50"
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
                filteredItems.map((it, idx) => {
                  const isDirty = dirtyItemIds.has(it.id);
                  const isShortage = parseFloat(String(it.order_qty || 0)) > 0;

                  return (
                    <tr
                      key={it.id}
                      className={`hover:bg-vanilla-surface/80 transition-colors ${
                        isDirty ? 'bg-amber-50/70' : idx % 2 === 0 ? 'bg-white' : 'bg-gray-50/30'
                      }`}
                    >
                      {viewMode === 'NORMAL_VIEW' ? (
                        <>
                          <td className="sticky left-0 z-20 bg-inherit px-2.5 py-2 text-center font-sans text-gray-500 border-r">
                            {it.s_no || idx + 1}
                          </td>
                          <td className="sticky left-14 z-20 bg-inherit px-3 py-2 font-sans truncate max-w-32 border-r">
                            {it.req_type || 'PRODUCTION'}
                          </td>
                          <td className="sticky left-46 z-20 bg-inherit px-3 py-2 font-bold text-blue-900 border-r">
                            {it.item_id}
                          </td>
                          <td className="px-3 py-2 font-sans max-w-56 truncate" title={it.description}>
                            {it.description}
                          </td>
                          <td className="px-2.5 py-2 text-center font-sans text-gray-600">{it.unit}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.output_per_unit)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.moq)}</td>
                          <td className="px-2.5 py-2 text-right text-gray-700">{formatQty(it.min_stock_level)}</td>
                          <td className="px-2.5 py-2 text-right text-gray-700">{formatQty(it.max_stock_level)}</td>
                          <td className="px-2.5 py-2 text-right">
                            {canEdit ? (
                              <input
                                type="number"
                                step="0.01"
                                value={it.rate || ''}
                                onChange={e => handleCellEdit(it.id, 'rate', e.target.value)}
                                className="w-20 text-right bg-transparent border-b border-gray-300 focus:border-burnt-orange focus:outline-none"
                              />
                            ) : (
                              formatCurrency(it.rate)
                            )}
                          </td>
                          <td className="px-2.5 py-2 text-right bg-slate-50/50">{formatQty(it.prev_opening_qty)}</td>
                          <td className="px-2.5 py-2 text-right bg-slate-50/50">{formatQty(it.prev_receipt_qty)}</td>
                          <td className="px-2.5 py-2 text-right bg-slate-50/50">{formatQty(it.prev_issue_qty)}</td>
                          <td className="px-2.5 py-2 text-right bg-slate-50/50 font-semibold">{formatQty(it.prev_closing_qty)}</td>
                          <td className="px-2.5 py-2 text-right bg-slate-50/50">{formatQty(it.prev_prd_qty)}</td>
                          <td className="px-2.5 py-2 text-right bg-emerald-50/30">{formatQty(it.sch_qty)}</td>
                          <td className="px-2.5 py-2 text-right bg-emerald-50/30">{formatQty(it.req_qty)}</td>
                          <td className={`px-2.5 py-2 text-right font-bold ${
                            isShortage ? 'text-red-700 bg-red-100/70 rounded' : 'text-gray-400'
                          }`}>
                            {canEdit ? (
                              <input
                                type="number"
                                step="0.01"
                                value={it.order_qty || ''}
                                onChange={e => handleCellEdit(it.id, 'order_qty', e.target.value)}
                                className="w-24 text-right font-bold bg-transparent border-b border-burnt-orange focus:outline-none"
                              />
                            ) : (
                              formatQty(it.order_qty)
                            )}
                          </td>
                          <td className="px-2.5 py-2 text-right font-bold text-emerald-900">
                            {formatCurrency(it.order_value)}
                          </td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.pur_qty)}</td>
                          <td className="px-2.5 py-2 text-right">{formatCurrency(it.pur_value)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.bal_pur_qty)}</td>
                          <td className="px-2.5 py-2 text-right">{formatCurrency(it.bal_pur_value)}</td>
                        </>
                      ) : (
                        <>
                          <td className="sticky left-0 z-20 bg-inherit px-2.5 py-2 truncate max-w-28 border-r font-sans text-gray-600">
                            {it.supplier_id || '—'}
                          </td>
                          <td className="sticky left-28 z-20 bg-inherit px-3 py-2 truncate max-w-48 border-r font-sans" title={it.supplier_name || ''}>
                            {it.supplier_name || '—'}
                          </td>
                          <td className="sticky left-76 z-20 bg-inherit px-3 py-2 font-bold text-blue-900 border-r">
                            {it.item_id}
                          </td>
                          <td className="px-3 py-2 font-sans truncate">{it.category || '—'}</td>
                          <td className="px-3 py-2 font-sans truncate">{it.type_of_material || '—'}</td>
                          <td className="px-2 py-2 text-center text-gray-500 font-sans">{it.s_no || idx + 1}</td>
                          <td className="px-3 py-2 font-sans max-w-56 truncate font-medium" title={it.description}>
                            {it.description}
                          </td>
                          <td className="px-2.5 py-2 font-sans">{it.part_no_saleable || '—'}</td>
                          <td className="px-3 py-2 font-sans truncate">{it.saleable_part_name || '—'}</td>
                          <td className="px-2.5 py-2 font-sans">{it.used_part_no || '—'}</td>
                          <td className="px-3 py-2 font-sans">{it.process_name || '—'}</td>
                          <td className="px-2.5 py-2 font-sans">{it.thickness_gsm || '—'}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.no_of_process_per_part)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.output_per_unit)}</td>
                          <td className="px-2.5 py-2 text-right">{formatCurrency(it.rate)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.prev_opening_qty)}</td>
                          <td className="px-2.5 py-2 text-right">{formatCurrency(it.prev_opening_val)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.prev_receipt_qty)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.prev_issue_qty)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.prev_closing_qty)}</td>
                          <td className="px-2.5 py-2 text-right">{formatCurrency(it.prev_closing_val)}</td>
                          <td className="px-2.5 py-2 text-right">{formatCurrency(it.rate)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.min_stock_level)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.max_stock_level)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.moq)}</td>
                          <td className="px-2.5 py-2 text-right font-sans">{it.lead_time_days || '—'}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.sch_qty)}</td>
                          <td className="px-2.5 py-2 text-center font-sans text-gray-500">{it.purchasing_unit || it.unit}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.sch_qty)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.prev_closing_qty)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.req_qty)}</td>
                          <td className={`px-2.5 py-2 text-right font-bold ${
                            isShortage ? 'text-red-700 bg-red-100/70 rounded' : 'text-gray-400'
                          }`}>
                            {canEdit ? (
                              <input
                                type="number"
                                step="0.01"
                                value={it.order_qty || ''}
                                onChange={e => handleCellEdit(it.id, 'order_qty', e.target.value)}
                                className="w-24 text-right font-bold bg-transparent border-b border-burnt-orange focus:outline-none"
                              />
                            ) : (
                              formatQty(it.order_qty)
                            )}
                          </td>
                          <td className="px-2.5 py-2 text-right font-bold text-emerald-900">
                            {formatCurrency(it.order_value)}
                          </td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.receipt_qty)}</td>
                          <td className="px-2.5 py-2 text-right">{formatCurrency(it.receipt_value)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.sch_qty_r2)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.sch_qty_r2)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.req_qty_r2)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.prev_closing_qty)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.req_qty_r2)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.prev_issue_qty)}</td>
                          <td className="px-2.5 py-2 text-right font-bold">{formatQty(it.order_qty_r2)}</td>
                          <td className="px-2.5 py-2 text-right font-bold">{formatCurrency(it.order_value_r2)}</td>
                          <td className="px-2.5 py-2 text-right">{formatQty(it.receipt_qty_r2)}</td>
                          <td className="px-2.5 py-2 text-right">{formatCurrency(it.receipt_val_r2)}</td>
                          <td className="px-2.5 py-2 text-right font-bold">{formatQty(it.receipt_qty)}</td>
                          <td className="px-2.5 py-2 text-right font-bold">{formatCurrency(it.receipt_value)}</td>
                          {!collapsedGroups.plantWise && (
                            <>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.p1)}</td>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.p2)}</td>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.p3)}</td>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.p4)}</td>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.p5)}</td>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.tool_room)}</td>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.quality)}</td>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.pmd)}</td>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.npd)}</td>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.hrd)}</td>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.accounts)}</td>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.admin)}</td>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.sales)}</td>
                              <td className="px-2 py-2 text-right">{formatQty(it.plant_allocations?.req_by_users)}</td>
                              <td className="px-2 py-2 text-right font-bold">{formatCurrency(it.plant_allocations?.total_value)}</td>
                            </>
                          )}
                          {!collapsedGroups.consumptionAnalysis && (
                            <>
                              <td className="px-2.5 py-2 text-right">{formatQty(it.consumption_analysis?.avg_monthly_con)}</td>
                              <td className="px-2.5 py-2 text-right">{formatQty(it.consumption_analysis?.avg_daily_con)}</td>
                              <td className="px-2.5 py-2 text-right">{formatQty(it.moq)}</td>
                              <td className="px-2.5 py-2 text-right font-sans">{it.lead_time_days || '—'}</td>
                              <td className="px-2.5 py-2 text-right font-sans">{it.consumption_analysis?.hold_days || '—'}</td>
                              <td className="px-2.5 py-2 text-right">{formatQty(it.min_stock_level)}</td>
                              <td className="px-2.5 py-2 text-right">{formatQty(it.max_stock_level)}</td>
                              <td className="px-2.5 py-2 text-right">{formatQty(it.consumption_analysis?.lead_time_qty)}</td>
                              <td className="px-2.5 py-2 text-right">{formatQty(it.consumption_analysis?.reorder_level)}</td>
                              <td className="px-2.5 py-2 text-right">{formatCurrency(it.consumption_analysis?.cost_of_msl)}</td>
                              <td className="px-3 py-2 text-right font-bold text-blue-900">{formatQty(it.consumption_analysis?.reorder_level)}</td>
                              <td className="px-2.5 py-2 text-right">{formatQty(it.consumption_analysis?.avg_daily_con)}</td>
                              <td className="px-2.5 py-2 text-right">{formatCurrency(it.consumption_analysis?.prev_plan_val)}</td>
                              <td className="px-2.5 py-2 text-right">{formatCurrency(it.consumption_analysis?.prev_actual_val)}</td>
                            </>
                          )}
                        </>
                      )}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Footer Summary Bar */}
        <div className="bg-gray-50 border-t border-ink-text/10 px-4 py-3 flex flex-wrap items-center justify-between text-xs font-semibold text-ink-text">
          <div className="flex items-center gap-6">
            <span>Total Items: <strong className="text-burnt-orange">{filteredItems.length}</strong></span>
            <span>Items Requiring Order: <strong className="text-red-700">{filteredItems.filter(i => parseFloat(String(i.order_qty || 0)) > 0).length}</strong></span>
            {dirtyItemIds.size > 0 && (
              <span className="text-amber-800 bg-amber-100 px-2 py-0.5 rounded font-bold">
                ⚠️ {dirtyItemIds.size} unsaved modifications
              </span>
            )}
          </div>
          <div>
            Total Estimated Purchase Value: <span className="text-emerald-900 text-sm font-bold ml-1">
              {formatCurrency(filteredItems.reduce((acc, curr) => acc + parseFloat(String(curr.order_value || 0)), 0))}
            </span>
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
