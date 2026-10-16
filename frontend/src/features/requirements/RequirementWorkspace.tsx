import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import axios from 'axios';
import {
  Calendar,
  Building2,
  Plus,
  Send,
  CheckCircle2,
  RefreshCw,
  Clock,
  Lock,
  Sparkles,
  AlertTriangle,
  X,
  FileCheck2,
  Upload,
  FileSpreadsheet,
  RotateCcw,
} from 'lucide-react';
import { useAuth } from '../auth/context';
import {
  fetchPlans,
  createPlan,
  bulkUploadItems,
  createSingleLineItem,
  updateLineItem,
  deleteLineItem,
  submitPlan,
  approvePlan,
  rejectPlan,
  calculateFormulas,
  runAggregation,
  type MonthlyRequirementPlan,
  type AggregationRunResponse,
  type SingleLineItemPayload,
  type UpdateLineItemPayload,
} from './api';
import PlanGrid from './PlanGrid';

const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

const DEFAULT_PLANTS = [
  { id: 'PLANT_I', name: 'Plant 1 (Main Facility)' },
  { id: 'PLANT_II', name: 'Plant 2 (Fabrication)' },
  { id: 'PLANT_III', name: 'Plant 3 (Assembly)' },
  { id: 'PLANT_IV', name: 'Plant 4 (Machining)' },
  { id: 'PLANT_V', name: 'Plant 5 (Storage/Dispatch)' },
];

export const RequirementWorkspace: React.FC = () => {
  const { user } = useAuth();

  const isAdminOrPlanner = useMemo(() => {
    if (!user) return false;
    if (user.is_super_admin || user.is_superuser) return true;
    const roles = (user.roles || []).map((r) => String(r).toUpperCase().trim());
    if (roles.some((r) => ['ADMIN', 'SUPER ADMIN', 'SUPER_ADMIN', 'PLANNER'].includes(r))) return true;
    const singleRole = (user.role || '').toUpperCase().trim();
    return singleRole === 'ADMIN' || singleRole === 'PLANNER';
  }, [user]);

  // Available plants
  const availablePlants = useMemo(() => {
    const list = [...DEFAULT_PLANTS];
    if (user?.assigned_plant && !list.some((p) => p.id.toUpperCase() === user.assigned_plant?.toUpperCase())) {
      list.push({ id: user.assigned_plant, name: user.assigned_plant });
    }
    return list;
  }, [user]);

  // Selections
  const [selectedPlant, setSelectedPlant] = useState<string>(() => {
    if (!isAdminOrPlanner && user?.assigned_plant) {
      return user.assigned_plant;
    }
    return 'PLANT_I';
  });

  const [selectedMonth, setSelectedMonth] = useState<number>(() => {
    return new Date().getMonth() + 1;
  });

  const [selectedYear, setSelectedYear] = useState<number>(() => {
    return new Date().getFullYear();
  });

  // Keep plant synced for standard users
  useEffect(() => {
    if (!isAdminOrPlanner && user?.assigned_plant) {
      setSelectedPlant(user.assigned_plant);
    }
  }, [isAdminOrPlanner, user?.assigned_plant]);

  // Data states
  const [plans, setPlans] = useState<MonthlyRequirementPlan[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [uploading, setUploading] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

  // Single Intake Modal State
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [submittingAdd, setSubmittingAdd] = useState(false);
  const [newItemCode, setNewItemCode] = useState('');
  const [newItemDesc, setNewItemDesc] = useState('');
  const [newItemPartNo, setNewItemPartNo] = useState('');
  const [newItemUnit, setNewItemUnit] = useState('NOS');
  const [newItemQty, setNewItemQty] = useState<number | string>('');

  // Bulk Upload Modal State
  const [isBulkModalOpen, setIsBulkModalOpen] = useState(false);
  const [bulkUploadAllPlants, setBulkUploadAllPlants] = useState(false);
  const modalFileInputRef = useRef<HTMLInputElement>(null);

  // Aggregation Modal State
  const [aggregationResult, setAggregationResult] = useState<AggregationRunResponse | null>(null);
  const [aggregationLoading, setAggregationLoading] = useState<boolean>(false);

  // Formula Generation State
  const [computingFormulas, setComputingFormulas] = useState<boolean>(false);

  // Reject Modal State
  const [isRejectModalOpen, setIsRejectModalOpen] = useState<boolean>(false);
  const [rejectionReason, setRejectionReason] = useState<string>('');
  const [rejecting, setRejecting] = useState<boolean>(false);

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ type, message });
    setTimeout(() => {
      setToast((prev) => (prev?.message === message ? null : prev));
    }, 4500);
  };

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchPlans(selectedMonth, selectedYear);
      setPlans(data || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch requirement plans';
      showToast(msg, 'error');
    } finally {
      setLoading(false);
    }
  }, [selectedMonth, selectedYear]);

  useEffect(() => {
    loadPlans();
  }, [loadPlans]);

  // Find active plan for selected plant + month + year
  const activePlan = useMemo(() => {
    return (
      plans.find(
        (p) =>
          p.plant_id.toUpperCase() === selectedPlant.toUpperCase() &&
          Number(p.month) === Number(selectedMonth) &&
          Number(p.year) === Number(selectedYear)
      ) || null
    );
  }, [plans, selectedPlant, selectedMonth, selectedYear]);

  // Helper to ensure plan exists before line item action
  const ensurePlanExists = async (): Promise<MonthlyRequirementPlan> => {
    if (activePlan) return activePlan;
    const created = await createPlan(selectedPlant, selectedMonth, selectedYear);
    await loadPlans();
    return created;
  };

  // Handlers
  const handleCreatePlan = async () => {
    setActionLoading('create');
    try {
      await createPlan(selectedPlant, selectedMonth, selectedYear);
      showToast(`Plan created for ${selectedPlant} (${MONTH_NAMES[selectedMonth - 1]} ${selectedYear})`, 'success');
      await loadPlans();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create plan';
      showToast(msg, 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleUpload = async (file: File, uploadAll = false) => {
    setUploading(true);
    try {
      const targetPlan = await ensurePlanExists();
      const res = uploadAll
        ? await bulkUploadItems(targetPlan.id, file, true)
        : await bulkUploadItems(targetPlan.id, file);
      if (res.errors && res.errors.length > 0) {
        showToast(
          `Upserted ${res.upserted} of ${res.total_rows} items with ${res.errors.length} warnings.`,
          'info'
        );
      } else {
        const msg = uploadAll
          ? `Successfully processed ${res.upserted} items across ${res.plants_affected?.join(', ') || targetPlan.plant_id}.`
          : `Successfully uploaded and parsed ${res.upserted} items into the plan.`;
        showToast(msg, 'success');
      }
      setIsBulkModalOpen(false);
      await loadPlans();
    } catch (err: unknown) {
      let msg = 'Bulk upload failed';
      if (axios.isAxiosError(err)) {
        msg = err.response?.data?.detail || err.response?.data?.message || err.message || msg;
      } else if (err instanceof Error) {
        msg = err.message;
      }
      showToast(msg, 'error');
    } finally {
      setUploading(false);
      if (modalFileInputRef.current) {
        modalFileInputRef.current.value = '';
      }
    }
  };

  const handleSingleIntakeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newItemCode.trim()) {
      showToast('Item ID / Code is required', 'error');
      return;
    }
    const qty = Number(newItemQty);
    if (isNaN(qty) || qty < 0) {
      showToast('Quantity must be a non-negative number', 'error');
      return;
    }

    setSubmittingAdd(true);
    try {
      const plan = await ensurePlanExists();
      const payload: SingleLineItemPayload = {
        item_code: newItemCode.trim(),
        item_description: newItemDesc.trim() || undefined,
        part_no: newItemPartNo.trim() || undefined,
        unit: newItemUnit.trim() || 'NOS',
        requested_qty: qty,
      };
      await createSingleLineItem(plan.id, payload);
      showToast(`Added ${payload.item_code} successfully to ${selectedPlant}!`, 'success');
      setIsAddModalOpen(false);
      setNewItemCode('');
      setNewItemDesc('');
      setNewItemPartNo('');
      setNewItemUnit('NOS');
      setNewItemQty('');
      await loadPlans();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to add item';
      showToast(msg, 'error');
    } finally {
      setSubmittingAdd(false);
    }
  };

  const handleUpdateItem = async (itemId: string, data: UpdateLineItemPayload) => {
    if (!activePlan) return;
    try {
      await updateLineItem(activePlan.id, itemId, data);
      showToast('Line item updated successfully', 'success');
      await loadPlans();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update item';
      showToast(msg, 'error');
    }
  };

  const handleDeleteItem = async (itemId: string) => {
    if (!activePlan) return;
    try {
      await deleteLineItem(activePlan.id, itemId);
      showToast('Line item deleted from plan', 'success');
      await loadPlans();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete item';
      showToast(msg, 'error');
    }
  };

  const handleSubmitPlan = async () => {
    if (!activePlan) return;
    setActionLoading('submit');
    try {
      await submitPlan(activePlan.id);
      showToast('Monthly requirement plan successfully submitted for review and approval!', 'success');
      await loadPlans();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to submit plan';
      showToast(msg, 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleApprovePlan = async () => {
    if (!activePlan) return;
    setActionLoading('approve');
    try {
      await approvePlan(activePlan.id);
      showToast('Plan approved successfully! Locked for monthly aggregation.', 'success');
      await loadPlans();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to approve plan';
      showToast(msg, 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRejectPlan = async () => {
    if (!activePlan) return;
    setRejecting(true);
    try {
      await rejectPlan(activePlan.id, rejectionReason.trim() || undefined);
      showToast(`Plan for ${selectedPlant} rejected for revisions.`, 'info');
      setIsRejectModalOpen(false);
      setRejectionReason('');
      await loadPlans();
    } catch (err: unknown) {
      let msg = 'Failed to reject plan';
      if (axios.isAxiosError(err)) {
        msg = err.response?.data?.detail || err.response?.data?.message || err.message || msg;
      } else if (err instanceof Error) {
        msg = err.message;
      }
      showToast(msg, 'error');
    } finally {
      setRejecting(false);
    }
  };

  const handleComputeFormulas = async () => {
    setComputingFormulas(true);
    try {
      const res = await calculateFormulas(selectedMonth, selectedYear);
      showToast(
        res.message || `Formula demand computed for ${res.plans_updated.length} plants (${res.total_items_computed} items)!`,
        'success'
      );
      await loadPlans();
    } catch (err: unknown) {
      let msg = 'Failed to calculate formula requirements';
      if (axios.isAxiosError(err)) {
        msg = err.response?.data?.detail || err.response?.data?.message || err.message || msg;
      } else if (err instanceof Error) {
        msg = err.message;
      }
      showToast(msg, 'error');
    } finally {
      setComputingFormulas(false);
    }
  };

  const handleRunAggregation = async () => {
    setAggregationLoading(true);
    try {
      const res = await runAggregation(selectedMonth, selectedYear);
      setAggregationResult(res);
      showToast(
        `Aggregation complete! Consolidated ${res.total_aggregated_consumables} items across ${res.total_approved_plans} approved plans.`,
        'success'
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Aggregation run failed';
      showToast(msg, 'error');
    } finally {
      setAggregationLoading(false);
    }
  };

  // State machine button logic
  const isDraft = !activePlan || activePlan?.status?.toUpperCase() === 'DRAFT';
  const isSubmitted = activePlan?.status?.toUpperCase() === 'SUBMITTED';
  const isApproved = activePlan?.status?.toUpperCase() === 'APPROVED';
  const isRejected = activePlan?.status?.toUpperCase() === 'REJECTED';

  // Plant incharge can submit if it's their assigned plant (or admin/planner) and status is DRAFT or REJECTED
  const canSubmit = Boolean(
    (isDraft || isRejected) &&
      activePlan &&
      (isAdminOrPlanner ||
        !user?.assigned_plant ||
        user.assigned_plant.toUpperCase() === selectedPlant.toUpperCase())
  );

  // Admin or Planner can approve or reject
  const canApprove = Boolean(isSubmitted && isAdminOrPlanner);
  const canReject = Boolean(isSubmitted && isAdminOrPlanner);
  const isPlanLocked = isApproved || (!isAdminOrPlanner && isSubmitted);

  return (
    <div className="font-['Plus_Jakarta_Sans',sans-serif] bg-gray-50 min-h-screen p-4 sm:p-6 flex flex-col space-y-5">
      {/* Toast Notification */}
      {toast && (
        <div
          className={`fixed top-4 right-4 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg border text-xs font-medium transition-all animate-in fade-in slide-in-from-top-2 ${
            toast.type === 'success'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : toast.type === 'error'
              ? 'bg-red-50 text-red-800 border-red-200'
              : 'bg-blue-50 text-blue-800 border-blue-200'
          }`}
        >
          {toast.type === 'success' && <CheckCircle2 className="w-4 h-4 text-emerald-600" />}
          {toast.type === 'error' && <AlertTriangle className="w-4 h-4 text-red-600" />}
          {toast.type === 'info' && <Sparkles className="w-4 h-4 text-blue-600" />}
          <span>{toast.message}</span>
          <button
            onClick={() => setToast(null)}
            className="p-1 hover:bg-black/5 rounded cursor-pointer"
          >
            <X className="w-3.5 h-3.5 text-gray-500" />
          </button>
        </div>
      )}

      {/* Floating Header Card & Control Bar */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-5 flex flex-col gap-4">
        {/* Module Title & Global Aggregation Action */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-gray-100">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold text-gray-900 tracking-tight">Monthly Requirement Planner</h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-orange-50 text-orange-700 border border-orange-200">
                Phase 4 Consumable-Style CRUD
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Manual Single Intake CRUD, Smart Multi-Sheet Bulk Upload, and Dynamic Factory Requirement Planning.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={loadPlans}
              disabled={loading}
              title="Refresh plans"
              className="p-2 text-gray-600 hover:text-gray-900 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-lg cursor-pointer transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>

            {/* Bulk Upload Modal Trigger */}
            <button
              type="button"
              onClick={() => setIsBulkModalOpen(true)}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-white hover:bg-gray-50 text-gray-700 border border-gray-300 shadow-2xs transition-colors cursor-pointer"
            >
              <Upload className="w-3.5 h-3.5 text-orange-600" />
              <span>Smart Bulk Upload</span>
            </button>

            {/* Global Action: Compute Formula Demands (Admin/Planner only) */}
            {isAdminOrPlanner && (
              <button
                type="button"
                onClick={handleComputeFormulas}
                disabled={computingFormulas}
                title="Compute initial plant requirements across all 5 facilities using Production Orders and Consumption Norms"
                className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-orange-600 hover:bg-orange-700 text-white shadow-2xs transition-colors cursor-pointer disabled:opacity-50"
              >
                <Sparkles className={`w-3.5 h-3.5 ${computingFormulas ? 'animate-spin' : ''}`} />
                <span>{computingFormulas ? 'Computing Formulas...' : 'Compute Formula Demands'}</span>
              </button>
            )}

            {/* Global Action: Run Monthly Aggregation (Admin/Planner only) */}
            {isAdminOrPlanner && (
              <button
                type="button"
                onClick={handleRunAggregation}
                disabled={aggregationLoading}
                className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-white hover:bg-gray-50 text-gray-800 border border-gray-300 shadow-2xs transition-colors cursor-pointer"
              >
                <Sparkles className={`w-3.5 h-3.5 ${aggregationLoading ? 'animate-spin text-orange-600' : 'text-orange-600'}`} />
                <span>{aggregationLoading ? 'Aggregating Requirements...' : 'Run Monthly Aggregation'}</span>
              </button>
            )}
          </div>
        </div>

        {/* Task 2: Floating Selectors Bar */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* Plant Selector */}
            <div className="flex items-center gap-2 bg-gray-50 px-3 py-1.5 rounded-lg border border-gray-200">
              <Building2 className="w-4 h-4 text-gray-500" />
              <label htmlFor="plant-select" className="text-xs font-medium text-gray-600">
                Plant:
              </label>
              {!isAdminOrPlanner && user?.assigned_plant ? (
                <div title="Locked to your assigned plant" className="flex items-center gap-1.5 text-xs font-semibold text-gray-900">
                  <Lock className="w-3.5 h-3.5 text-gray-400" />
                  <span>
                    {availablePlants.find((p) => p.id === user.assigned_plant)?.name || user.assigned_plant}
                  </span>
                </div>
              ) : (
                <select
                  id="plant-select"
                  value={selectedPlant}
                  onChange={(e) => setSelectedPlant(e.target.value)}
                  className="bg-transparent text-xs font-semibold text-gray-900 focus:outline-none cursor-pointer"
                >
                  {availablePlants.map((plant) => (
                    <option key={plant.id} value={plant.id}>
                      {plant.name}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Month Selector (1-12) */}
            <div className="flex items-center gap-2 bg-gray-50 px-3 py-1.5 rounded-lg border border-gray-200">
              <Calendar className="w-4 h-4 text-gray-500" />
              <label htmlFor="month-select" className="text-xs font-medium text-gray-600">
                Month:
              </label>
              <select
                id="month-select"
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(Number(e.target.value))}
                className="bg-transparent text-xs font-semibold text-gray-900 focus:outline-none cursor-pointer"
              >
                {MONTH_NAMES.map((name, idx) => (
                  <option key={idx + 1} value={idx + 1}>
                    {name}
                  </option>
                ))}
              </select>
            </div>

            {/* Year Selector */}
            <div className="flex items-center gap-2 bg-gray-50 px-3 py-1.5 rounded-lg border border-gray-200">
              <label htmlFor="year-select" className="text-xs font-medium text-gray-600">
                Year:
              </label>
              <select
                id="year-select"
                value={selectedYear}
                onChange={(e) => setSelectedYear(Number(e.target.value))}
                className="bg-transparent text-xs font-semibold text-gray-900 focus:outline-none cursor-pointer"
              >
                {[2024, 2025, 2026, 2027, 2028, 2029, 2030].map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Right Action: Plan Status & Create Plan Button */}
          <div className="flex items-center gap-3">
            {activePlan ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">Plan Status:</span>
                <span
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider border ${
                    activePlan.status === 'APPROVED'
                      ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                      : activePlan.status === 'SUBMITTED'
                      ? 'bg-blue-50 text-blue-800 border-blue-300'
                      : activePlan.status === 'REJECTED'
                      ? 'bg-rose-50 text-rose-800 border-rose-300'
                      : 'bg-amber-50 text-amber-800 border-amber-300'
                  }`}
                >
                  {activePlan.status}
                </span>
              </div>
            ) : (
              <button
                type="button"
                onClick={handleCreatePlan}
                disabled={actionLoading === 'create'}
                className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-orange-600 hover:bg-orange-700 text-white shadow-xs cursor-pointer transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>{actionLoading === 'create' ? 'Initializing...' : 'Create Plan'}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Main Excel-like Grid */}
      <PlanGrid
        plan={activePlan}
        items={activePlan?.line_items || []}
        loading={loading}
        uploading={uploading}
        onUpload={(file) => handleUpload(file, false)}
        onAddItem={() => setIsAddModalOpen(true)}
        onUpdateItem={handleUpdateItem}
        onDeleteItem={handleDeleteItem}
        canUpload={!isPlanLocked}
        canEdit={!isPlanLocked}
      />

      {/* State Machine Action Panel (Floating Bottom Card) */}
      {activePlan && (
        <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div
              className={`p-2 rounded-lg border ${
                isApproved
                  ? 'bg-emerald-50 text-emerald-600 border-emerald-200'
                  : isSubmitted
                  ? 'bg-blue-50 text-blue-600 border-blue-200'
                  : isRejected
                  ? 'bg-rose-50 text-rose-600 border-rose-200'
                  : 'bg-amber-50 text-amber-600 border-amber-200'
              }`}
            >
              {isApproved ? (
                <FileCheck2 className="w-5 h-5" />
              ) : isSubmitted ? (
                <Clock className="w-5 h-5" />
              ) : isRejected ? (
                <AlertTriangle className="w-5 h-5" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500">
                  Workflow State Machine
                </h3>
                <span className="text-xs font-semibold text-gray-900">
                  {selectedPlant} • {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-0.5">
                {isDraft && 'Plan is in DRAFT. Review formula demands, edit shopfloor quantities, or upload spreadsheet before submitting for approval.'}
                {isSubmitted && 'Plan is SUBMITTED for approval. Awaiting review and sign-off from Admin or Planner.'}
                {isApproved && 'Plan is APPROVED. Line items are locked and eligible for cross-plant MRP aggregation.'}
                {isRejected && 'Plan is in REJECTED status. Revisions were requested by admin. Review quantities and resubmit.'}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto justify-end">
            {/* If DRAFT or REJECTED & Plant Incharge: Submit for Approval */}
            {(isDraft || isRejected) && canSubmit && (
              <button
                type="button"
                onClick={handleSubmitPlan}
                disabled={actionLoading === 'submit' || (activePlan.line_items || []).length === 0}
                title={
                  (activePlan.line_items || []).length === 0
                    ? 'Add at least one line item before submitting'
                    : 'Submit monthly requirement plan for approval'
                }
                className={`inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer ${
                  (activePlan.line_items || []).length === 0 || actionLoading === 'submit'
                    ? 'bg-gray-100 text-gray-400 border border-gray-200 cursor-not-allowed shadow-none'
                    : 'bg-blue-600 hover:bg-blue-700 text-white'
                }`}
              >
                <Send className="w-3.5 h-3.5" />
                <span>
                  {actionLoading === 'submit'
                    ? 'Submitting...'
                    : isRejected
                    ? 'Re-submit for Approval'
                    : 'Submit for Approval'}
                </span>
              </button>
            )}

            {/* If SUBMITTED & Admin/Planner: Reject or Approve Plan */}
            {isSubmitted && (canApprove || canReject) && (
              <>
                <button
                  type="button"
                  onClick={() => setIsRejectModalOpen(true)}
                  className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg bg-white hover:bg-rose-50 text-rose-700 border border-rose-300 shadow-2xs cursor-pointer transition-colors"
                >
                  <RotateCcw className="w-3.5 h-3.5 text-rose-600" />
                  <span>Reject / Request Revisions</span>
                </button>
                <button
                  type="button"
                  onClick={handleApprovePlan}
                  disabled={actionLoading === 'approve'}
                  className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs cursor-pointer transition-colors"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{actionLoading === 'approve' ? 'Approving...' : 'Approve Plan'}</span>
                </button>
              </>
            )}

            {/* If APPROVED: Display locked confirmation pill */}
            {isApproved && (
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span>Plan Approved & Ready for Aggregation</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Single Intake Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 max-w-lg w-full overflow-hidden animate-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-gray-200 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-orange-50 text-orange-600 rounded-lg border border-orange-100">
                  <Plus className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-gray-900">Add Item (Single Intake)</h3>
                  <p className="text-xs text-gray-500">
                    Add consumable directly to {selectedPlant} for {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsAddModalOpen(false)}
                className="p-1 text-gray-400 hover:text-gray-700 rounded-lg hover:bg-gray-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSingleIntakeSubmit} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Item Id / Code <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. CON-1001 or 50000004"
                  value={newItemCode}
                  onChange={(e) => setNewItemCode(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Item Description
                </label>
                <input
                  type="text"
                  placeholder="e.g. Synthetic Gear Oil 320"
                  value={newItemDesc}
                  onChange={(e) => setNewItemDesc(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    Part No.
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. S-OIL-320"
                    value={newItemPartNo}
                    onChange={(e) => setNewItemPartNo(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    Unit / UOM
                  </label>
                  <input
                    type="text"
                    placeholder="NOS, LTR, KG"
                    value={newItemUnit}
                    onChange={(e) => setNewItemUnit(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Requested Quantity <span className="text-red-500">*</span>
                </label>
                <input
                  type="number"
                  step="any"
                  min="0"
                  required
                  placeholder="e.g. 50"
                  value={newItemQty}
                  onChange={(e) => setNewItemQty(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 font-mono"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-3.5 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingAdd}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-orange-600 hover:bg-orange-700 rounded-lg shadow-xs disabled:opacity-50"
                >
                  {submittingAdd && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>Save Line Item</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Bulk Upload Modal */}
      {isBulkModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 max-w-md w-full overflow-hidden animate-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-gray-200 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-orange-50 text-orange-600 rounded-lg border border-orange-100">
                  <FileSpreadsheet className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-gray-900">Bulk Upload Spreadsheet</h3>
                  <p className="text-xs text-gray-500">
                    Upload Excel (.xlsx, .xls) or CSV workbook
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsBulkModalOpen(false)}
                className="p-1 text-gray-400 hover:text-gray-700 rounded-lg hover:bg-gray-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {isAdminOrPlanner && (
                <div className="p-3 bg-gray-50 rounded-xl border border-gray-200">
                  <label className="flex items-start gap-2.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={bulkUploadAllPlants}
                      onChange={(e) => setBulkUploadAllPlants(e.target.checked)}
                      className="mt-0.5 rounded border-gray-300 text-orange-600 focus:ring-orange-500"
                    />
                    <div className="text-xs">
                      <span className="font-semibold text-gray-800">
                        Import All 5 Plants (Multi-Sheet Workbook)
                      </span>
                      <p className="text-gray-500 mt-0.5">
                        Detects sheets for Plant I, Plant II, Plant III, Plant IV, and Plant V automatically and imports into all plans at once.
                      </p>
                    </div>
                  </label>
                </div>
              )}

              <input
                type="file"
                ref={modalFileInputRef}
                accept=".xlsx,.xls,.csv"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleUpload(f, bulkUploadAllPlants);
                }}
                className="hidden"
              />

              <div
                onClick={() => modalFileInputRef.current?.click()}
                className="border-2 border-dashed border-gray-300 hover:border-orange-500 rounded-xl p-8 text-center cursor-pointer transition-colors bg-gray-50/50 hover:bg-orange-50/20"
              >
                <Upload className="w-8 h-8 mx-auto text-gray-400 mb-2" />
                <p className="text-xs font-semibold text-gray-800">
                  Click to select file or drag & drop here
                </p>
                <p className="text-[11px] text-gray-400 mt-1">
                  Supports .xlsx, .xls, and .csv with columns: Item Id., Item Description, Part No., Unit, QTY
                </p>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsBulkModalOpen(false)}
                  className="px-3.5 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Aggregation Result Modal */}
      {aggregationResult && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 max-w-3xl w-full max-h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="p-5 border-b border-gray-200 bg-white flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-orange-50 border border-orange-200 text-orange-600">
                  <Sparkles className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-gray-900">
                    Monthly Aggregation Report ({MONTH_NAMES[aggregationResult.month - 1]} {aggregationResult.year})
                  </h2>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Consolidated gross and net consumable requirements across all approved plant plans.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setAggregationResult(null)}
                className="p-1.5 text-gray-400 hover:text-gray-700 rounded-lg hover:bg-gray-100 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Stats Bar */}
            <div className="grid grid-cols-2 gap-4 p-5 bg-gray-50/60 border-b border-gray-200">
              <div className="bg-white p-3 rounded-xl border border-gray-200">
                <span className="text-[11px] font-semibold uppercase text-gray-500 tracking-wider">
                  Total Approved Plans
                </span>
                <p className="text-xl font-extrabold text-gray-900 mt-1 font-mono">
                  {aggregationResult.total_approved_plans}
                </p>
              </div>
              <div className="bg-white p-3 rounded-xl border border-gray-200">
                <span className="text-[11px] font-semibold uppercase text-gray-500 tracking-wider">
                  Aggregated Consumables
                </span>
                <p className="text-xl font-extrabold text-orange-600 mt-1 font-mono">
                  {aggregationResult.total_aggregated_consumables}
                </p>
              </div>
            </div>

            {/* Aggregated Items Table */}
            <div className="flex-1 overflow-y-auto p-5">
              {aggregationResult.records.length === 0 ? (
                <div className="text-center py-12 text-gray-400 text-xs">
                  No consumables aggregated. Ensure plant plans are submitted and approved first.
                </div>
              ) : (
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200 text-gray-600 font-semibold uppercase tracking-wider text-[11px]">
                      <th className="py-2.5 px-3">Item Code</th>
                      <th className="py-2.5 px-3">Consumable Name</th>
                      <th className="py-2.5 px-3 text-right">Gross QTY</th>
                      <th className="py-2.5 px-3 text-right">Net Purchase QTY</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 text-gray-700">
                    {aggregationResult.records.map((rec) => (
                      <tr key={rec.id} className="hover:bg-gray-50">
                        <td className="py-2.5 px-3 font-mono font-medium text-gray-900">
                          {rec.item_id || rec.consumable_id}
                        </td>
                        <td className="py-2.5 px-3 font-medium">
                          {rec.consumable_name || 'Consumable Item'}
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono font-bold text-gray-900">
                          {rec.total_gross_qty.toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono font-bold text-orange-600">
                          {rec.net_purchase_qty.toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 bg-gray-50 border-t border-gray-200 flex justify-end">
              <button
                type="button"
                onClick={() => setAggregationResult(null)}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-gray-800 hover:bg-gray-900 text-white cursor-pointer"
              >
                Close Report
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reject / Revision Request Modal */}
      {isRejectModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 max-w-md w-full overflow-hidden animate-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-gray-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-rose-50 text-rose-600 border border-rose-200">
                  <AlertTriangle className="w-4 h-4" />
                </div>
                <h3 className="text-sm font-bold text-gray-900">Request Revisions</h3>
              </div>
              <button
                onClick={() => {
                  setIsRejectModalOpen(false);
                  setRejectionReason('');
                }}
                className="p-1 text-gray-400 hover:text-gray-700 rounded-lg hover:bg-gray-100 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-3">
              <p className="text-xs text-gray-600">
                This will unlock the plan for <strong>{selectedPlant}</strong> and set its status back to <strong>REJECTED</strong> so shopfloor incharge can revise requested quantities.
              </p>
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Revision Feedback / Reason (Optional)
                </label>
                <textarea
                  rows={3}
                  placeholder="e.g. Please verify line 2 cutting oil demand based on adjusted production target..."
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500/20 focus:border-rose-500"
                />
              </div>
              <div className="pt-2 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => {
                    setIsRejectModalOpen(false);
                    setRejectionReason('');
                  }}
                  className="px-3.5 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={rejecting}
                  onClick={handleRejectPlan}
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-xs disabled:opacity-50 cursor-pointer"
                >
                  {rejecting ? 'Sending...' : 'Confirm Rejection'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RequirementWorkspace;
