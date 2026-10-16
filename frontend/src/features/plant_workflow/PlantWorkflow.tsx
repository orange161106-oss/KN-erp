import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Calendar,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  X,
  Send,
  RotateCcw,
  Clock,
  FileCheck2,
  Unlock,
} from 'lucide-react';
import { useAuth } from '../auth/context';
import {
  fetchPlans,
  createPlan,
  approvePlan,
  submitPlan,
  rejectPlan,
  calculateFormulas,
  reopenPlan,
  bulkUploadItems,
  createSingleLineItem,
  updateLineItem,
  deleteLineItem,
  type MonthlyRequirementPlan,
  type UpdateLineItemPayload,
} from '../requirements/api';
import PlanGrid from '../requirements/PlanGrid';
import CentralRequirements from '../requirements/CentralRequirements';

// ── Constants ──────────────────────────────────────────────────────────────────

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

// ── Main PlantWorkflow screen ──────────────────────────────────────────────────

type TabKey =
  | 'PLANT_I'
  | 'PLANT_II'
  | 'PLANT_III'
  | 'PLANT_IV'
  | 'PLANT_V';

interface PlantWorkflowProps {
  currentUserId: string;
}

export default function PlantWorkflow(props: PlantWorkflowProps) {
  const {user}=useAuth();
  const [central,setCentral]=useState(Boolean(user?.is_super_admin));
  if(!user?.is_super_admin) return <LegacyPlantWorkflow {...props}/>;
  return <div className="space-y-3 min-w-0"><div className="flex gap-2"><button className="rounded border bg-white px-4 py-2" onClick={()=>setCentral(true)}>Central plan review</button><button className="rounded border bg-white px-4 py-2" onClick={()=>setCentral(false)}>Existing plant plans</button></div>{central?<CentralRequirements/>:<LegacyPlantWorkflow {...props}/>}</div>;
}

function LegacyPlantWorkflow({ currentUserId: _currentUserId }: PlantWorkflowProps) {
  const { user } = useAuth();
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const isAdminOrPlanner = Boolean(
    isSuperAdmin ||
    (user?.roles || []).some((r: string) => ['ADMIN', 'SUPER ADMIN', 'SUPER_ADMIN', 'PLANNER'].includes(String(r).toUpperCase().trim())) ||
    ['ADMIN', 'PLANNER'].includes(String(user?.role || '').toUpperCase().trim())
  );
  const hasModernFlags = user && (
    'plant_workflow_read' in user ||
    'plant_workflow_create' in user ||
    'plant_workflow_update' in user ||
    'plant_workflow_delete' in user
  );
  const canRead = Boolean(isSuperAdmin || (hasModernFlags ? user?.plant_workflow_read : true));

  const [activeTab, setActiveTab] = useState<TabKey>('PLANT_I');
  const [selectedMonth, setSelectedMonth] = useState<number>(() => new Date().getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState<number>(() => new Date().getFullYear());
  const [toast, setToast] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

  // Plant-specific plan states for 5 plant review tabs
  const [allPlans, setAllPlans] = useState<MonthlyRequirementPlan[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);

  // Formula generation state
  const [computingFormulas, setComputingFormulas] = useState(false);

  // Submission & Rejection states
  const [submittingPlan, setSubmittingPlan] = useState(false);
  const [isRejectModalOpen, setIsRejectModalOpen] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [submittingReject, setSubmittingReject] = useState(false);

  // Modals for single intake & bulk upload within Plant Review
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [submittingAdd, setSubmittingAdd] = useState(false);
  const [newItemCode, setNewItemCode] = useState('');
  const [newItemDesc, setNewItemDesc] = useState('');
  const [newItemPartNo, setNewItemPartNo] = useState('');
  const [newItemUnit, setNewItemUnit] = useState('NOS');
  const [newItemQty, setNewItemQty] = useState<number | string>('');

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ type, message });
    setTimeout(() => {
      setToast((prev) => (prev?.message === message ? null : prev));
    }, 4500);
  };

  const loadAllPlans = useCallback(async () => {
    setPlansLoading(true);
    try {
      const data = await fetchPlans(selectedMonth, selectedYear);
      setAllPlans(data || []);
    } catch {
      // ignore
    } finally {
      setPlansLoading(false);
    }
  }, [selectedMonth, selectedYear]);

  useEffect(() => {
    loadAllPlans();
  }, [loadAllPlans]);

  const handleComputeFormulas = async () => {
    setComputingFormulas(true);
    try {
      const res = await calculateFormulas(selectedMonth, selectedYear);
      showToast(
        res.message || `Formula demand computed for ${res.plans_updated.length} plants (${res.total_items_computed} items)!`,
        'success'
      );
      await loadAllPlans();
    } catch (e: unknown) {
      let msg = 'Failed to calculate formula requirements.';
      if (axios.isAxiosError(e)) {
        msg = e.response?.data?.detail || e.response?.data?.message || e.message || msg;
      } else if (e instanceof Error) {
        msg = e.message;
      }
      showToast(msg, 'error');
    } finally {
      setComputingFormulas(false);
    }
  };

  const handleSubmitPlant = async (planId: string, plantName: string) => {
    setSubmittingPlan(true);
    try {
      await submitPlan(planId);
      showToast(`Successfully submitted ${plantName} plan for approval!`, 'success');
      await loadAllPlans();
    } catch (e: unknown) {
      let msg = 'Failed to submit plan.';
      if (axios.isAxiosError(e)) {
        msg = e.response?.data?.detail || e.response?.data?.message || e.message || msg;
      } else if (e instanceof Error) {
        msg = e.message;
      }
      showToast(msg, 'error');
    } finally {
      setSubmittingPlan(false);
    }
  };

  const handleDirectApprovePlant = async (planId: string, plantName: string) => {
    try {
      await approvePlan(planId);
      showToast(`Successfully approved ${plantName} plan and released to Purchase!`, 'success');
      await loadAllPlans();
    } catch (e: unknown) {
      let msg = 'Failed to approve plan.';
      if (axios.isAxiosError(e)) {
        msg = e.response?.data?.detail || e.response?.data?.message || e.message || msg;
      } else if (e instanceof Error) {
        msg = e.message;
      }
      showToast(msg, 'error');
    }
  };

  const handleRejectPlant = async (planId: string, plantName: string) => {
    setSubmittingReject(true);
    try {
      await rejectPlan(planId, rejectionReason.trim() || undefined);
      showToast(`Revision requested for ${plantName} plan.`, 'info');
      setIsRejectModalOpen(false);
      setRejectionReason('');
      await loadAllPlans();
    } catch (e: unknown) {
      let msg = 'Failed to reject plan.';
      if (axios.isAxiosError(e)) {
        msg = e.response?.data?.detail || e.response?.data?.message || e.message || msg;
      } else if (e instanceof Error) {
        msg = e.message;
      }
      showToast(msg, 'error');
    } finally {
      setSubmittingReject(false);
    }
  };

  const handleReopenPlant = async (planId: string, plantName: string) => {
    try {
      await reopenPlan(planId);
      showToast(`Unlocked ${plantName} plan for editing!`, 'success');
      await loadAllPlans();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to reopen plan.';
      showToast(msg, 'error');
    }
  };

  const handleSingleIntakeFromReview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newItemCode.trim()) {
      showToast('Item ID / Code is required', 'error');
      return;
    }
    const qty = Number(newItemQty);
    if (isNaN(qty) || qty < 0) {
      showToast('Quantity must be non-negative', 'error');
      return;
    }

    const targetPlantId = activeTab.startsWith('PLANT_') ? activeTab : 'PLANT_I';
    setSubmittingAdd(true);
    try {
      let targetPlan = allPlans.find(
        (p) =>
          p.plant_id.toUpperCase() === targetPlantId.toUpperCase() &&
          p.month === selectedMonth &&
          p.year === selectedYear
      );
      if (!targetPlan) {
        targetPlan = await createPlan(targetPlantId, selectedMonth, selectedYear);
      }

      await createSingleLineItem(targetPlan.id, {
        item_code: newItemCode.trim(),
        item_description: newItemDesc.trim() || undefined,
        part_no: newItemPartNo.trim() || undefined,
        unit: newItemUnit.trim() || 'NOS',
        requested_qty: qty,
      });

      showToast(`Added ${newItemCode.trim()} to ${targetPlantId}!`, 'success');
      setIsAddModalOpen(false);
      setNewItemCode('');
      setNewItemDesc('');
      setNewItemPartNo('');
      setNewItemUnit('NOS');
      setNewItemQty('');
      await loadAllPlans();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to add item.';
      showToast(msg, 'error');
    } finally {
      setSubmittingAdd(false);
    }
  };

  if (!canRead) {
    return <p role="alert" className="text-red-700">You do not have permission to view plant workflow.</p>;
  }

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'PLANT_I', label: 'Plant I' },
    { key: 'PLANT_II', label: 'Plant II' },
    { key: 'PLANT_III', label: 'Plant III' },
    { key: 'PLANT_IV', label: 'Plant IV' },
    { key: 'PLANT_V', label: 'Plant V' },
  ];

  const normalizePlant = (id?: string) => {
    if (!id) return '';
    const clean = id.toUpperCase().replace(/\s+|-/g, '_');
    if (clean === 'PLANT_1') return 'PLANT_I';
    if (clean === 'PLANT_2') return 'PLANT_II';
    if (clean === 'PLANT_3') return 'PLANT_III';
    if (clean === 'PLANT_4') return 'PLANT_IV';
    if (clean === 'PLANT_5') return 'PLANT_V';
    return clean;
  };

  const currentPlantTabPlan = allPlans.find(
    (p) =>
      normalizePlant(p.plant_id) === normalizePlant(activeTab) &&
      p.month === selectedMonth &&
      p.year === selectedYear
  ) || null;

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

      {/* Floating White Card Control Bar */}
      <div className="bg-white rounded-xl shadow-xs border border-gray-200 p-5 flex flex-col gap-4">
        {/* Module Title */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-gray-100">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold text-gray-900 tracking-tight">Plant Review & Aggregation</h1>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Review monthly plant demands across all 5 facilities, manage line items, and approve requirements.
            </p>
          </div>
        </div>

        {/* Control Bar: Month, Year Selectors */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* Month Dropdown (Strictly Month Names) */}
            <div className="flex items-center gap-2 bg-gray-50 px-3 py-1.5 rounded-lg border border-gray-200">
              <Calendar className="w-4 h-4 text-gray-500" />
              <label htmlFor="workflow-month-select" className="text-xs font-medium text-gray-600">
                Month:
              </label>
              <select
                id="workflow-month-select"
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

            {/* Year Dropdown */}
            <div className="flex items-center gap-2 bg-gray-50 px-3 py-1.5 rounded-lg border border-gray-200">
              <label htmlFor="workflow-year-select" className="text-xs font-medium text-gray-600">
                Year:
              </label>
              <select
                id="workflow-year-select"
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

          {/* Action: Compute Formula Demands (Admin/Planner) */}
          {isAdminOrPlanner && (
            <button
              type="button"
              onClick={handleComputeFormulas}
              disabled={computingFormulas || plansLoading}
              title="Compute initial plant requirements across all 5 facilities using Production Orders and Consumption Norms"
              className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-orange-600 hover:bg-orange-700 text-white shadow-2xs transition-colors cursor-pointer disabled:opacity-50"
            >
              <Sparkles className={`w-3.5 h-3.5 ${computingFormulas ? 'animate-spin' : ''}`} />
              <span>{computingFormulas ? 'Computing Formulas...' : 'Compute Formula Demands'}</span>
            </button>
          )}
        </div>
      </div>

      {/* 5 Plant Tabs */}
      <div className="border-b border-gray-200 bg-white px-4 pt-2.5 rounded-t-xl shadow-2xs">
        <nav className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`pb-2.5 px-3 text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer border-b-2 ${
                activeTab === tab.key
                  ? 'border-orange-600 text-orange-600'
                  : 'border-transparent text-gray-500 hover:text-gray-800'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Active Plant Tab View */}
      {(() => {
        const currentPlanStatus = (currentPlantTabPlan?.status || 'DRAFT').toUpperCase();
        const isPlantPlanLocked =
          currentPlanStatus === 'APPROVED' || (!isAdminOrPlanner && currentPlanStatus === 'SUBMITTED');
        const activePlantLabel = tabs.find((t) => t.key === activeTab)?.label || activeTab;

        return (
          <div className="space-y-4">
            {/* Active Plant Header Card with Dynamic Status & Review Actions */}
            <div className="bg-white rounded-xl border border-gray-200 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-2xs">
              <div>
                <div className="flex flex-wrap items-center gap-2.5">
                  <h2 className="text-sm font-bold text-gray-900">
                    {activePlantLabel} Review & Approval
                  </h2>

                  {/* Status Badges */}
                  {currentPlanStatus === 'APPROVED' ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] font-bold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-300">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                      Approved & Locked • Released to Purchase
                    </span>
                  ) : currentPlanStatus === 'SUBMITTED' ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] font-bold rounded-full bg-blue-50 text-blue-700 border border-blue-300">
                      <Clock className="w-3.5 h-3.5 text-blue-600" />
                      Awaiting Admin Signoff
                    </span>
                  ) : currentPlanStatus === 'REJECTED' ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] font-bold rounded-full bg-rose-50 text-rose-700 border border-rose-300">
                      <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
                      Revision Requested
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] font-bold rounded-full bg-gray-100 text-gray-700 border border-gray-300">
                      Draft Review
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  {currentPlanStatus === 'APPROVED' &&
                    'Plan has received final admin approval. Quantities are locked and feeding the Purchase Module.'}
                  {currentPlanStatus === 'SUBMITTED' &&
                    'Plan has been submitted by shopfloor incharge. Awaiting final review, variance checks, and signoff.'}
                  {currentPlanStatus === 'REJECTED' &&
                    'Revisions were requested by admin. Please review modified shopfloor quantities and resubmit.'}
                  {currentPlanStatus === 'DRAFT' &&
                    'Review formula demands, adjust requested quantities for shopfloor conditions, and submit for approval.'}
                </p>
              </div>

              {/* Review Action Buttons */}
              <div className="flex flex-wrap items-center gap-2 self-end sm:self-center">
                {/* If DRAFT or REJECTED: Submit for Approval */}
                {currentPlantTabPlan &&
                  (currentPlanStatus === 'DRAFT' || currentPlanStatus === 'REJECTED') && (
                    <button
                      type="button"
                      onClick={() => handleSubmitPlant(currentPlantTabPlan.id, activePlantLabel)}
                      disabled={submittingPlan || (currentPlantTabPlan.line_items || []).length === 0}
                      className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-white shadow-xs cursor-pointer disabled:opacity-50 transition-colors"
                    >
                      <Send className="w-3.5 h-3.5" />
                      <span>{submittingPlan ? 'Submitting...' : 'Submit for Approval'}</span>
                    </button>
                  )}

                {/* If SUBMITTED: Admin can Reject */}
                {currentPlantTabPlan && currentPlanStatus === 'SUBMITTED' && isAdminOrPlanner && (
                  <button
                    type="button"
                    onClick={() => setIsRejectModalOpen(true)}
                    className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-lg bg-white hover:bg-rose-50 text-rose-700 border border-rose-300 shadow-2xs cursor-pointer transition-colors"
                  >
                    <RotateCcw className="w-3.5 h-3.5 text-rose-600" />
                    <span>Reject / Revisions</span>
                  </button>
                )}

                {/* Direct Approve Plant button for Admin/Planner (releases to purchase) */}
                {currentPlantTabPlan && currentPlanStatus !== 'APPROVED' && isAdminOrPlanner && (
                  <button
                    type="button"
                    disabled={(currentPlantTabPlan.line_items?.length ?? 0) === 0}
                    title={
                      (currentPlantTabPlan.line_items?.length ?? 0) === 0
                        ? 'Cannot approve an empty plan. Add items first.'
                        : undefined
                    }
                    onClick={() => handleDirectApprovePlant(currentPlantTabPlan.id, activePlantLabel)}
                    className={`inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg shadow-xs transition-colors ${
                      (currentPlantTabPlan.line_items?.length ?? 0) === 0
                        ? 'bg-gray-100 text-gray-400 border border-gray-200 cursor-not-allowed shadow-none'
                        : 'bg-emerald-600 hover:bg-emerald-700 text-white cursor-pointer'
                    }`}
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Approve {activePlantLabel}</span>
                  </button>
                )}

                {/* If SUBMITTED but user is not Admin/Planner: banner */}
                {currentPlantTabPlan && currentPlanStatus === 'SUBMITTED' && !isAdminOrPlanner && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-lg">
                    <Clock className="w-3.5 h-3.5" />
                    Under Admin Review
                  </span>
                )}

                {/* If APPROVED: Display locked confirmation pill + Reopen button */}
                {currentPlantTabPlan && currentPlanStatus === 'APPROVED' && (
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200">
                      <FileCheck2 className="w-3.5 h-3.5" />
                      Locked & Aggregated
                    </span>
                    {isAdminOrPlanner && (
                      <button
                        type="button"
                        onClick={() => handleReopenPlant(currentPlantTabPlan.id, activePlantLabel)}
                        className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-semibold rounded-lg border border-amber-300 text-amber-800 bg-amber-50 hover:bg-amber-100 shadow-2xs transition-colors cursor-pointer"
                        title="Reopen approved plan to add or edit line items"
                      >
                        <Unlock className="w-3.5 h-3.5 text-amber-600" />
                        <span>Reopen / Unlock</span>
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>

            <PlanGrid
              key={`${activeTab}-${currentPlantTabPlan?.id || 'none'}-${selectedMonth}-${selectedYear}`}
              plan={currentPlantTabPlan}
              items={currentPlantTabPlan?.line_items || []}
              loading={plansLoading}
              uploading={false}
              onUpload={async (f: File, uploadAll?: boolean) => {
                let targetPlan = currentPlantTabPlan;
                const targetPlantId = activeTab.startsWith('PLANT_') ? activeTab : 'PLANT_I';
                if (!targetPlan) {
                  try {
                    targetPlan = await createPlan(targetPlantId, selectedMonth, selectedYear);
                  } catch (err) {
                    console.error('[BULK UPLOAD] Failed to auto-create plan:', err);
                  }
                }
                if (!targetPlan) {
                  showToast('No active plan found or could be created for this plant', 'error');
                  return;
                }
                try {
                  console.log(
                    '[BULK UPLOAD] Triggered with planId:',
                    targetPlan.id,
                    'file:',
                    f.name,
                    'uploadAllPlants:',
                    Boolean(uploadAll)
                  );
                  const res = await bulkUploadItems(targetPlan.id, f, Boolean(uploadAll));
                  const plantLabel = uploadAll
                    ? res.plants_affected?.join(', ') || 'All Plants'
                    : targetPlan.plant_id;
                  showToast(
                    `Items uploaded successfully! Processed ${res.upserted} items into ${plantLabel}.`,
                    'success'
                  );
                  await loadAllPlans();
                } catch (e: unknown) {
                  let msg = 'Bulk upload failed.';
                  if (axios.isAxiosError(e)) {
                    msg = e.response?.data?.detail || e.response?.data?.message || e.message || msg;
                  } else if (e instanceof Error) {
                    msg = e.message;
                  }
                  showToast(msg, 'error');
                  throw e;
                }
              }}
              onAddItem={() => setIsAddModalOpen(true)}
              onUpdateItem={async (itemId: string, data: UpdateLineItemPayload) => {
                if (currentPlantTabPlan) {
                  await updateLineItem(currentPlantTabPlan.id, itemId, data);
                  await loadAllPlans();
                }
              }}
              onDeleteItem={async (itemId: string) => {
                if (currentPlantTabPlan) {
                  await deleteLineItem(currentPlantTabPlan.id, itemId);
                  await loadAllPlans();
                }
              }}
              canUpload={!isPlantPlanLocked}
              canEdit={!isPlantPlanLocked}
            />
          </div>
        );
      })()}

      {/* Single Intake Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 max-w-lg w-full overflow-hidden animate-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-gray-200 flex items-center justify-between">
              <h3 className="text-sm font-bold text-gray-900">Add Item (Single Intake)</h3>
              <button
                onClick={() => setIsAddModalOpen(false)}
                className="p-1 text-gray-400 hover:text-gray-700 rounded-lg hover:bg-gray-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleSingleIntakeFromReview} className="p-5 space-y-4">
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
                <label className="block text-xs font-semibold text-gray-700 mb-1">Item Description</label>
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
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Part No.</label>
                  <input
                    type="text"
                    placeholder="e.g. S-OIL-320"
                    value={newItemPartNo}
                    onChange={(e) => setNewItemPartNo(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Unit / UOM</label>
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
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-orange-600 hover:bg-orange-700 rounded-lg shadow-xs disabled:opacity-50"
                >
                  Save Line Item
                </button>
              </div>
            </form>
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
                This will unlock the plan for <strong>{tabs.find((t) => t.key === activeTab)?.label}</strong> and set its status back to <strong>REJECTED</strong> so the plant incharge can update requested quantities.
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
                  disabled={submittingReject}
                  onClick={() =>
                    currentPlantTabPlan &&
                    handleRejectPlant(
                      currentPlantTabPlan.id,
                      tabs.find((t) => t.key === activeTab)?.label || activeTab
                    )
                  }
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-xs disabled:opacity-50 cursor-pointer"
                >
                  {submittingReject ? 'Sending...' : 'Confirm Rejection'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

