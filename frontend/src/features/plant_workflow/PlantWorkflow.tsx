import React, { useCallback, useEffect, useState } from 'react';
import {
  Calendar,
  RefreshCw,
  Sparkles,
  Search,
  PackageCheck,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  X,
  Layers,
} from 'lucide-react';
import { apiClient, ApiError } from '../../api/client';
import { useAuth } from '../auth/context';
import {
  fetchAggregatedRequirements,
  runAggregation,
  fetchPlans,
  createPlan,
  approvePlan,
  bulkUploadItems,
  createSingleLineItem,
  updateLineItem,
  deleteLineItem,
  type AggregatedRequirementRecord,
  type MonthlyRequirementPlan,
  type UpdateLineItemPayload,
} from '../requirements/api';
import PlanGrid from '../requirements/PlanGrid';
import type {
  AdjustmentCategory,
  AdjustmentStatus,
  CalculatedRequirementItem,
  ConfirmRequirementRequest,
  PlantConfirmationResponse,
  RequirementAdjustmentResponse,
  ReviewAdjustmentRequest,
  SubmitAdjustmentRequest,
} from './types';

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

const ADJUSTMENT_CATEGORIES: AdjustmentCategory[] = [
  'SPECIAL',
  'MAINTENANCE',
  'TRIAL',
  'REWORK',
  'PLANT_REQUEST',
  'OTHER',
];

const STATUS_COLOURS: Record<AdjustmentStatus, string> = {
  PENDING: 'bg-yellow-100 text-yellow-800',
  APPROVED: 'bg-green-100 text-green-800',
  REJECTED: 'bg-red-100 text-red-800',
};

// ── Small shared components ────────────────────────────────────────────────────

function StatusBadge({ status }: { status: AdjustmentStatus }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${STATUS_COLOURS[status]}`}>
      {status}
    </span>
  );
}

function AlertBox({ message, type }: { message: string; type: 'error' | 'success' }) {
  const base = 'rounded p-3 text-sm mb-4';
  const colour = type === 'error'
    ? 'bg-red-50 border border-red-300 text-red-700'
    : 'bg-green-50 border border-green-300 text-green-700';
  return <div className={`${base} ${colour}`}>{message}</div>;
}

// ── Tab 1: Confirmations ───────────────────────────────────────────────────────

function ConfirmationsTab({
  planningVersionId,
  onVersionChange,
}: {
  planningVersionId: string;
  onVersionChange: (v: string) => void;
}) {
  const { user } = useAuth();
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const hasModernFlags = user && (
    'plant_workflow_read' in user ||
    'plant_workflow_create' in user ||
    'plant_workflow_update' in user ||
    'plant_workflow_delete' in user
  );
  const canUpdate = Boolean(isSuperAdmin || (hasModernFlags ? user?.plant_workflow_update : true));
  const hasActions = Boolean(isSuperAdmin || canUpdate);

  const [calcReqs, setCalcReqs] = useState<CalculatedRequirementItem[]>([]);
  const [confirmations, setConfirmations] = useState<PlantConfirmationResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const confirmedIds = new Set(confirmations.map((c) => c.calculated_requirement_id));

  const fetchData = useCallback(async () => {
    if (!planningVersionId) return;
    setLoading(true);
    setError(null);
    try {
      const [reqs, confs] = await Promise.all([
        apiClient.get<CalculatedRequirementItem[]>(
          `/api/v1/requirements/planning-versions/${planningVersionId}`
        ),
        apiClient.get<PlantConfirmationResponse[]>(
          `/api/v1/plant-workflow/confirmations?planning_version_id=${planningVersionId}`
        ),
      ]);
      setCalcReqs(reqs);
      setConfirmations(confs);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load requirements.');
    } finally {
      setLoading(false);
    }
  }, [planningVersionId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleConfirm = async (calcReqId: string) => {
    setError(null);
    setSuccess(null);
    try {
      const req: ConfirmRequirementRequest = {
        calculated_requirement_id: calcReqId,
        notes: notes[calcReqId] || null,
      };
      await apiClient.post('/api/v1/plant-workflow/confirmations', req);
      setSuccess('Requirement confirmed successfully.');
      await fetchData();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Confirmation failed.');
    }
  };

  const handleRetract = async (calcReqId: string) => {
    setError(null);
    setSuccess(null);
    const conf = confirmations.find((c) => c.calculated_requirement_id === calcReqId);
    if (!conf) return;
    try {
      await apiClient.delete(`/api/v1/plant-workflow/confirmations/${conf.id}`);
      setSuccess('Confirmation retracted.');
      await fetchData();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Retraction failed.');
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-white p-3 rounded-xl border border-gray-200 flex items-center gap-3">
        <label className="text-xs font-semibold text-gray-700 whitespace-nowrap">
          Planning Version UUID:
        </label>
        <input
          type="text"
          className="border border-gray-300 rounded px-2.5 py-1 text-xs w-80 font-mono focus:outline-none focus:ring-1 focus:ring-orange-500"
          placeholder="Paste planning version UUID to load confirmations…"
          value={planningVersionId}
          onChange={(e) => onVersionChange(e.target.value.trim())}
        />
      </div>

      {!planningVersionId ? (
        <p className="text-gray-500 text-sm py-8 text-center bg-white rounded-xl border border-gray-200">
          Enter a planning version UUID above to inspect individual version confirmations.
        </p>
      ) : loading ? (
        <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-orange-500" /></div>
      ) : (
        <div>
          {error && <AlertBox message={error} type="error" />}
          {success && <AlertBox message={success} type="success" />}

          {calcReqs.length === 0 ? (
            <p className="text-gray-500 text-sm">No calculated requirements found for this version.</p>
          ) : (
            <div className="overflow-x-auto border border-gray-200 rounded-xl shadow-2xs bg-white">
              <table className="min-w-full text-xs border-collapse">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200 text-gray-600 font-semibold uppercase tracking-wider text-[11px]">
                    <th className="px-3 py-2.5 text-left">Consumable</th>
                    <th className="px-3 py-2.5 text-left">Process</th>
                    <th className="px-3 py-2.5 text-right">Calc Qty</th>
                    <th className="px-3 py-2.5 text-left">UOM</th>
                    <th className="px-3 py-2.5 text-left">Rule</th>
                    <th className="px-3 py-2.5 text-left">Status</th>
                    {hasActions && (
                      <>
                        <th className="px-3 py-2.5 text-left">Notes</th>
                        <th className="px-3 py-2.5 text-left">Action</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {calcReqs.map((r) => {
                    const confirmed = confirmedIds.has(r.id);
                    return (
                      <tr key={r.id} className="hover:bg-gray-50">
                        <td className="px-3 py-2">
                          <span className="font-mono text-gray-500">{r.consumable_code}</span>
                          <span className="ml-1 font-medium text-gray-900">{r.consumable_name}</span>
                        </td>
                        <td className="px-3 py-2">{r.process_name ?? '—'}</td>
                        <td className="px-3 py-2 text-right font-mono font-bold">{r.calculated_qty}</td>
                        <td className="px-3 py-2">{r.uom}</td>
                        <td className="px-3 py-2">
                          <span className="bg-gray-100 px-1.5 py-0.5 rounded text-[10px] font-semibold">{r.rule_type}</span>
                        </td>
                        <td className="px-3 py-2">
                          {confirmed ? (
                            <span className="text-emerald-700 font-semibold">✓ Confirmed</span>
                          ) : (
                            <span className="text-gray-400">Pending</span>
                          )}
                        </td>
                        {hasActions && (
                          <>
                            <td className="px-3 py-2">
                              {!confirmed && (
                                <input
                                  type="text"
                                  placeholder="Optional note…"
                                  className="border rounded px-2 py-1 text-xs w-40"
                                  value={notes[r.id] ?? ''}
                                  onChange={(e) =>
                                    setNotes((prev) => ({ ...prev, [r.id]: e.target.value }))
                                  }
                                />
                              )}
                            </td>
                            <td className="px-3 py-2">
                              {confirmed ? (
                                <button
                                  onClick={() => handleRetract(r.id)}
                                  className="text-xs text-red-600 hover:text-red-800 underline cursor-pointer"
                                >
                                  Retract
                                </button>
                              ) : (
                                <button
                                  onClick={() => handleConfirm(r.id)}
                                  className="text-xs bg-orange-600 hover:bg-orange-700 text-white px-3 py-1 rounded shadow-xs transition-colors font-medium cursor-pointer"
                                >
                                  Confirm
                                </button>
                              )}
                            </td>
                          </>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Tab 2: Adjustments ─────────────────────────────────────────────────────────

function AdjustmentsTab({
  planningVersionId,
  onVersionChange,
  currentUserId,
}: {
  planningVersionId: string;
  onVersionChange: (v: string) => void;
  currentUserId: string;
}) {
  const { user } = useAuth();
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const hasModernFlags = user && (
    'plant_workflow_read' in user ||
    'plant_workflow_create' in user ||
    'plant_workflow_update' in user ||
    'plant_workflow_delete' in user
  );
  const canCreate = Boolean(isSuperAdmin || (hasModernFlags ? user?.plant_workflow_create : true));
  const canUpdate = Boolean(isSuperAdmin || (hasModernFlags ? user?.plant_workflow_update : true));
  const canDelete = Boolean(isSuperAdmin || (hasModernFlags ? user?.plant_workflow_delete : true));
  const hasActions = Boolean(isSuperAdmin || canCreate || canUpdate || canDelete);

  const [adjustments, setAdjustments] = useState<RequirementAdjustmentResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [consumableId, setConsumableId] = useState('');
  const [requestedQty, setRequestedQty] = useState('');
  const [category, setCategory] = useState<AdjustmentCategory>('PLANT_REQUEST');
  const [reason, setReason] = useState('');
  const [formOpen, setFormOpen] = useState(false);

  const fetchAdjustments = useCallback(async () => {
    if (!planningVersionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.get<RequirementAdjustmentResponse[]>(
        `/api/v1/plant-workflow/adjustments?planning_version_id=${planningVersionId}`
      );
      setAdjustments(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load adjustments.');
    } finally {
      setLoading(false);
    }
  }, [planningVersionId]);

  useEffect(() => {
    fetchAdjustments();
  }, [fetchAdjustments]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    try {
      const payload: SubmitAdjustmentRequest = {
        planning_version_id: planningVersionId,
        plant_id: user?.assigned_plant || 'PLANT_I',
        consumable_id: consumableId,
        requested_qty: requestedQty,
        category,
        reason,
      };
      await apiClient.post('/api/v1/plant-workflow/adjustments', payload);
      setSuccess('Adjustment submitted.');
      setConsumableId('');
      setRequestedQty('');
      setReason('');
      setFormOpen(false);
      await fetchAdjustments();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to submit adjustment.');
    }
  };

  const handleWithdraw = async (adjId: string) => {
    setError(null);
    setSuccess(null);
    try {
      await apiClient.delete(`/api/v1/plant-workflow/adjustments/${adjId}`);
      setSuccess('Adjustment withdrawn.');
      await fetchAdjustments();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Withdraw failed.');
    }
  };

  const handleReview = async (adjId: string, status: 'APPROVED' | 'REJECTED') => {
    setError(null);
    setSuccess(null);
    try {
      const payload: ReviewAdjustmentRequest = { status };
      await apiClient.patch(`/api/v1/plant-workflow/adjustments/${adjId}/review`, payload);
      setSuccess(`Adjustment ${status.toLowerCase()}.`);
      await fetchAdjustments();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Review failed.');
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-white p-3 rounded-xl border border-gray-200 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <label className="text-xs font-semibold text-gray-700 whitespace-nowrap">
            Planning Version UUID:
          </label>
          <input
            type="text"
            className="border border-gray-300 rounded px-2.5 py-1 text-xs w-80 font-mono focus:outline-none focus:ring-1 focus:ring-orange-500"
            placeholder="Paste planning version UUID for adjustments…"
            value={planningVersionId}
            onChange={(e) => onVersionChange(e.target.value.trim())}
          />
        </div>
        {canCreate && planningVersionId && (
          <button
            onClick={() => setFormOpen((v) => !v)}
            className="text-xs bg-orange-600 hover:bg-orange-700 text-white px-3 py-1.5 rounded-lg shadow-xs font-semibold cursor-pointer"
          >
            {formOpen ? 'Cancel' : '+ New Adjustment'}
          </button>
        )}
      </div>

      {formOpen && canCreate && (
        <form onSubmit={handleSubmit} className="bg-white p-4 rounded-xl border border-gray-200 shadow-2xs space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-gray-700">Submit Adjustment</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div>
              <label className="block text-gray-600 mb-1">Consumable UUID</label>
              <input
                type="text"
                required
                className="w-full border rounded px-2 py-1.5 font-mono"
                value={consumableId}
                onChange={(e) => setConsumableId(e.target.value.trim())}
              />
            </div>
            <div>
              <label className="block text-gray-600 mb-1">Requested Qty</label>
              <input
                type="number"
                step="any"
                required
                className="w-full border rounded px-2 py-1.5"
                value={requestedQty}
                onChange={(e) => setRequestedQty(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-gray-600 mb-1">Category</label>
              <select
                className="w-full border rounded px-2 py-1.5"
                value={category}
                onChange={(e) => setCategory(e.target.value as AdjustmentCategory)}
              >
                {ADJUSTMENT_CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-gray-600 mb-1">Reason</label>
              <input
                type="text"
                required
                className="w-full border rounded px-2 py-1.5"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </div>
          </div>
          <button type="submit" className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-1.5 rounded font-semibold cursor-pointer">
            Submit Adjustment
          </button>
        </form>
      )}

      {!planningVersionId ? (
        <p className="text-gray-500 text-sm py-8 text-center bg-white rounded-xl border border-gray-200">
          Enter a planning version UUID above to manage manual adjustments.
        </p>
      ) : loading ? (
        <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-orange-500" /></div>
      ) : (
        <div>
          {error && <AlertBox message={error} type="error" />}
          {success && <AlertBox message={success} type="success" />}

          {adjustments.length === 0 ? (
            <p className="text-gray-500 text-sm">No adjustments found for this version.</p>
          ) : (
            <div className="overflow-x-auto border border-gray-200 rounded-xl shadow-2xs bg-white">
              <table className="min-w-full text-xs border-collapse">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200 text-gray-600 font-semibold uppercase tracking-wider text-[11px]">
                    <th className="px-3 py-2.5 text-left">Consumable</th>
                    <th className="px-3 py-2.5 text-left">Category</th>
                    <th className="px-3 py-2.5 text-right">Requested Qty</th>
                    <th className="px-3 py-2.5 text-left">UOM</th>
                    <th className="px-3 py-2.5 text-left">Reason</th>
                    <th className="px-3 py-2.5 text-left">Requested By</th>
                    <th className="px-3 py-2.5 text-left">Status</th>
                    {hasActions && <th className="px-3 py-2.5 text-left">Action</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {adjustments.map((adj) => (
                    <tr key={adj.id} className="hover:bg-gray-50">
                      <td className="px-3 py-2">
                        <span className="font-mono text-gray-500">{adj.consumable_code}</span>
                        <span className="ml-1 font-medium text-gray-900">{adj.consumable_name}</span>
                      </td>
                      <td className="px-3 py-2">
                        <span className="bg-gray-100 px-1.5 py-0.5 rounded text-[10px] font-semibold">{adj.category}</span>
                      </td>
                      <td className="px-3 py-2 text-right font-mono font-bold">{adj.requested_qty}</td>
                      <td className="px-3 py-2">{adj.uom}</td>
                      <td className="px-3 py-2 max-w-xs">{adj.reason}</td>
                      <td className="px-3 py-2">{adj.requested_by_username ?? adj.requested_by}</td>
                      <td className="px-3 py-2"><StatusBadge status={adj.status} /></td>
                      {hasActions && (
                        <td className="px-3 py-2">
                          {canDelete && adj.status === 'PENDING' && adj.requested_by === currentUserId && (
                            <button
                              onClick={() => handleWithdraw(adj.id)}
                              className="text-xs text-red-600 hover:text-red-800 underline cursor-pointer"
                            >
                              Withdraw
                            </button>
                          )}
                          {canUpdate && adj.status === 'PENDING' && adj.requested_by !== currentUserId && (
                            <div className="flex gap-1">
                              <button
                                onClick={() => handleReview(adj.id, 'APPROVED')}
                                className="text-xs bg-emerald-600 text-white px-2 py-0.5 rounded hover:bg-emerald-700 cursor-pointer"
                              >
                                Approve
                              </button>
                              <button
                                onClick={() => handleReview(adj.id, 'REJECTED')}
                                className="text-xs bg-red-600 text-white px-2 py-0.5 rounded hover:bg-red-700 cursor-pointer"
                              >
                                Reject
                              </button>
                            </div>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Tab 3: Final Requirements (Handoff) ────────────────────────────────────────

interface FinalRequirementsTabProps {
  month: number;
  year: number;
  data: AggregatedRequirementRecord[];
  loading: boolean;
  aggregating: boolean;
  onRefresh: () => Promise<void>;
  onRunAggregation: () => Promise<void>;
}

function FinalRequirementsTab({
  month,
  year,
  data,
  loading,
  aggregating,
  onRunAggregation,
}: FinalRequirementsTabProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredItems = data.filter((item) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    const code = (item.item_code || item.item_id || item.consumable_id || '').toLowerCase();
    const desc = (item.item_description || item.consumable_name || '').toLowerCase();
    const partNo = (item.part_no || '').toLowerCase();
    return code.includes(q) || desc.includes(q) || partNo.includes(q);
  });

  const totalGrossQty = data.reduce((acc, it) => acc + (Number(it.total_gross_qty) || 0), 0);
  const totalNetQty = data.reduce((acc, it) => acc + (Number(it.net_purchase_qty) || 0), 0);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden flex flex-col font-['Plus_Jakarta_Sans',sans-serif]">
      {/* Grid Toolbar */}
      <div className="p-4 border-b border-gray-200 bg-white flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-orange-50 text-erp-orange rounded-lg border border-orange-100">
            <Layers className="w-5 h-5 text-orange-600" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-gray-900 tracking-tight">
                Final Requirements (Handoff)
              </h2>
              <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-gray-100 text-gray-700 border border-gray-200">
                {data.length} {data.length === 1 ? 'item' : 'items'}
              </span>
            </div>
            <p className="text-xs text-gray-500">
              Aggregated across approved plant plans for {MONTH_NAMES[month - 1]} {year}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto">
          {/* Search Input */}
          <div className="relative flex-1 sm:w-72">
            <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              placeholder="Search code, description, part no..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 transition-colors"
            />
          </div>
        </div>
      </div>

      {/* Grid Table */}
      <div className="overflow-x-auto min-h-[340px]">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-24 text-gray-400 space-y-3">
            <Loader2 className="w-8 h-8 animate-spin text-orange-500" />
            <p className="text-sm">Loading company-wide aggregated requirements...</p>
          </div>
        ) : data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 px-4 text-center">
            <div className="w-12 h-12 rounded-full bg-orange-50 flex items-center justify-center mb-3 border border-orange-100">
              <PackageCheck className="w-6 h-6 text-orange-600" />
            </div>
            <h3 className="text-sm font-semibold text-gray-800">
              No Aggregated Requirements Found
            </h3>
            <p className="text-xs text-gray-500 max-w-md mt-1">
              No aggregated requirements exist for {MONTH_NAMES[month - 1]} {year}. Click "Run/Refresh Aggregation Engine" to group approved monthly plans across all facilities.
            </p>
            <button
              type="button"
              onClick={onRunAggregation}
              disabled={aggregating}
              className="mt-4 inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-orange-600 hover:bg-orange-700 text-white shadow-xs cursor-pointer transition-colors"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>{aggregating ? 'Aggregating...' : 'Run Aggregation Engine Now'}</span>
            </button>
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 px-4 text-center">
            <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mb-3">
              <Search className="w-6 h-6 text-gray-400" />
            </div>
            <h3 className="text-sm font-semibold text-gray-800">No matching items found</h3>
            <p className="text-xs text-gray-500 max-w-sm mt-1">
              No records matched "{searchQuery}". Clear your search query to view all items.
            </p>
          </div>
        ) : (
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-gray-50/80 border-b border-gray-200 text-gray-600 font-semibold uppercase tracking-wider text-[11px]">
                <th className="py-3 px-4 w-14 text-center">S.No</th>
                <th className="py-3 px-4 w-40">Item Code</th>
                <th className="py-3 px-4">Item Description</th>
                <th className="py-3 px-4 w-36">Part No</th>
                <th className="py-3 px-4 w-24 text-center">Unit</th>
                <th className="py-3 px-4 w-44 text-right">Total Gross QTY (Sum across plants)</th>
                <th className="py-3 px-4 w-36 text-right">Net Purchase QTY</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 text-gray-700">
              {filteredItems.map((item, idx) => (
                <tr
                  key={item.id || item.consumable_id || idx}
                  className="hover:bg-orange-50/40 transition-colors group"
                >
                  <td className="py-3 px-4 text-center font-mono text-gray-400 group-hover:text-gray-600">
                    {idx + 1}
                  </td>
                  <td className="py-3 px-4 font-mono font-medium text-gray-900">
                    <span className="bg-gray-100 group-hover:bg-white px-2 py-0.5 rounded border border-gray-200">
                      {item.item_code || item.item_id || item.consumable_id}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-medium text-gray-900">
                    {item.item_description || item.consumable_name || 'Consumable Item'}
                  </td>
                  <td className="py-3 px-4 font-mono text-gray-600">
                    {item.part_no || item.item_id || '—'}
                  </td>
                  <td className="py-3 px-4 text-center">
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-100 text-gray-600 border border-gray-200">
                      {item.unit || 'Nos'}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right font-mono font-bold text-gray-900 text-sm">
                    {Number(item.total_gross_qty).toLocaleString(undefined, {
                      minimumFractionDigits: 0,
                      maximumFractionDigits: 2,
                    })}
                  </td>
                  <td className="py-3 px-4 text-right font-mono font-bold text-orange-600 text-sm">
                    {Number(item.net_purchase_qty).toLocaleString(undefined, {
                      minimumFractionDigits: 0,
                      maximumFractionDigits: 2,
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Grid Footer Summary */}
      {data.length > 0 && (
        <div className="p-3.5 bg-gray-50 border-t border-gray-200 flex flex-col sm:flex-row items-center justify-between text-xs text-gray-500 gap-3">
          <span>
            Showing <strong className="text-gray-700">{filteredItems.length}</strong> of{' '}
            <strong className="text-gray-700">{data.length}</strong> total consolidated consumables
          </span>
          <div className="flex items-center gap-6">
            <span>
              Total Gross QTY:{' '}
              <strong className="text-gray-900 font-mono text-sm ml-1">
                {totalGrossQty.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
              </strong>
            </span>
            <span>
              Total Net Purchase QTY:{' '}
              <strong className="text-orange-600 font-mono text-sm ml-1">
                {totalNetQty.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
              </strong>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main PlantWorkflow screen ──────────────────────────────────────────────────

type TabKey =
  | 'final-requirements'
  | 'PLANT_I'
  | 'PLANT_II'
  | 'PLANT_III'
  | 'PLANT_IV'
  | 'PLANT_V'
  | 'confirmations'
  | 'adjustments';

interface PlantWorkflowProps {
  currentUserId: string;
}

export default function PlantWorkflow({ currentUserId }: PlantWorkflowProps) {
  const { user } = useAuth();
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const hasModernFlags = user && (
    'plant_workflow_read' in user ||
    'plant_workflow_create' in user ||
    'plant_workflow_update' in user ||
    'plant_workflow_delete' in user
  );
  const canRead = Boolean(isSuperAdmin || (hasModernFlags ? user?.plant_workflow_read : true));

  const [activeTab, setActiveTab] = useState<TabKey>('final-requirements');
  const [selectedMonth, setSelectedMonth] = useState<number>(() => new Date().getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState<number>(() => new Date().getFullYear());
  const [planningVersionId, setPlanningVersionId] = useState('');

  const [aggregatedData, setAggregatedData] = useState<AggregatedRequirementRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [aggregating, setAggregating] = useState(false);
  const [toast, setToast] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);

  // Plant-specific plan states for 5 plant review tabs
  const [allPlans, setAllPlans] = useState<MonthlyRequirementPlan[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);

  // Modals for single intake & bulk upload within Plant Review
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [submittingAdd, setSubmittingAdd] = useState(false);
  const [newItemCode, setNewItemCode] = useState('');
  const [newItemDesc, setNewItemDesc] = useState('');
  const [newItemPartNo, setNewItemPartNo] = useState('');
  const [newItemUnit, setNewItemUnit] = useState('NOS');
  const [newItemQty, setNewItemQty] = useState<number | string>('');

  const [isBulkModalOpen, setIsBulkModalOpen] = useState(false);
  const [bulkUploadAllPlants, setBulkUploadAllPlants] = useState(true);
  const modalFileInputRef = React.useRef<HTMLInputElement>(null);

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ type, message });
    setTimeout(() => {
      setToast((prev) => (prev?.message === message ? null : prev));
    }, 4500);
  };

  const loadAllPlans = useCallback(async () => {
    setPlansLoading(true);
    try {
      const data = await fetchPlans();
      setAllPlans(data || []);
    } catch {
      // ignore
    } finally {
      setPlansLoading(false);
    }
  }, []);

  const handleLoadAggregation = useCallback(async () => {
    setLoading(true);
    try {
      const records = await fetchAggregatedRequirements(selectedMonth, selectedYear);
      setAggregatedData(records || []);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to load aggregated requirements.';
      showToast(msg, 'error');
    } finally {
      setLoading(false);
    }
  }, [selectedMonth, selectedYear]);

  useEffect(() => {
    handleLoadAggregation();
    loadAllPlans();
  }, [handleLoadAggregation, loadAllPlans]);

  const handleRunAggregation = async () => {
    setAggregating(true);
    try {
      const res = await runAggregation(selectedMonth, selectedYear);
      showToast(
        `Aggregation complete! Consolidated ${res.total_aggregated_consumables} items across ${res.total_approved_plans} approved plans.`,
        'success'
      );
      await handleLoadAggregation();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to calculate aggregation.';
      showToast(msg, 'error');
    } finally {
      setAggregating(false);
    }
  };

  const handleDirectApprovePlant = async (planId: string, plantName: string) => {
    try {
      await approvePlan(planId);
      showToast(`Successfully approved ${plantName} plan!`, 'success');
      await loadAllPlans();
      await handleLoadAggregation();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to approve plan.';
      showToast(msg, 'error');
    }
  };

  const handleBulkUploadFromReview = async (file: File) => {
    try {
      // Find or create plan for current plant or first plant
      const targetPlantId = activeTab.startsWith('PLANT_') ? activeTab : 'PLANT_I';
      let targetPlan = allPlans.find(
        (p) =>
          p.plant_id.toUpperCase() === targetPlantId.toUpperCase() &&
          p.month === selectedMonth &&
          p.year === selectedYear
      );
      if (!targetPlan) {
        targetPlan = await createPlan(targetPlantId, selectedMonth, selectedYear);
      }
      const res = await bulkUploadItems(targetPlan.id, file, bulkUploadAllPlants);
      showToast(
        `Bulk upload processed: ${res.upserted} items across ${res.plants_affected?.join(', ') || targetPlan.plant_id}.`,
        'success'
      );
      setIsBulkModalOpen(false);
      await loadAllPlans();
      await handleLoadAggregation();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Bulk upload failed.';
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
    { key: 'final-requirements', label: 'Final Requirements (Handoff)' },
    { key: 'PLANT_I', label: 'Plant I' },
    { key: 'PLANT_II', label: 'Plant II' },
    { key: 'PLANT_III', label: 'Plant III' },
    { key: 'PLANT_IV', label: 'Plant IV' },
    { key: 'PLANT_V', label: 'Plant V' },
    { key: 'confirmations', label: 'Confirmations' },
    { key: 'adjustments', label: 'Additional Requirements' },
  ];

  const currentPlantTabPlan = activeTab.startsWith('PLANT_')
    ? allPlans.find(
        (p) =>
          p.plant_id.toUpperCase() === activeTab.toUpperCase() &&
          p.month === selectedMonth &&
          p.year === selectedYear
      ) || null
    : null;

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
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-orange-50 text-orange-700 border border-orange-200">
                Phase 4 Workspace
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Review monthly plant demands across all 5 facilities, manage line items, and run cross-plant aggregation.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setIsAddModalOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-white border border-gray-300 hover:bg-gray-50 text-gray-800 shadow-2xs cursor-pointer"
            >
              <span>+ Add Item</span>
            </button>
            <button
              type="button"
              onClick={() => setIsBulkModalOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-white border border-gray-300 hover:bg-gray-50 text-gray-800 shadow-2xs cursor-pointer"
            >
              <span>Bulk Upload Workbook (All Plants)</span>
            </button>
          </div>
        </div>

        {/* Control Bar: Month, Year, Action Buttons */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* Month Dropdown (1-12) */}
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
                    {idx + 1} - {name}
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

          <div className="flex items-center gap-3">
            {/* Action Button: Load Aggregation */}
            <button
              type="button"
              onClick={handleLoadAggregation}
              disabled={loading || aggregating}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-white hover:bg-gray-50 text-gray-700 border border-gray-300 shadow-2xs transition-colors cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>{loading ? 'Loading...' : 'Load Aggregation'}</span>
            </button>

            {/* Action Button: Run/Refresh Aggregation Engine */}
            <button
              type="button"
              onClick={handleRunAggregation}
              disabled={aggregating || loading}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-orange-600 hover:bg-orange-700 text-white shadow-2xs transition-colors cursor-pointer"
            >
              <Sparkles className={`w-3.5 h-3.5 ${aggregating ? 'animate-spin' : ''}`} />
              <span>{aggregating ? 'Calculating Aggregation...' : 'Run/Refresh Aggregation Engine'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
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

      {/* Active Tab View */}
      {activeTab === 'final-requirements' && (
        <FinalRequirementsTab
          month={selectedMonth}
          year={selectedYear}
          data={aggregatedData}
          loading={loading}
          aggregating={aggregating}
          onRefresh={handleLoadAggregation}
          onRunAggregation={handleRunAggregation}
        />
      )}

      {activeTab.startsWith('PLANT_') && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-gray-900">
                {tabs.find((t) => t.key === activeTab)?.label} Review & Approval
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Status:{' '}
                <span className="font-semibold uppercase text-gray-800">
                  {currentPlantTabPlan ? currentPlantTabPlan.status : 'NO PLAN CREATED'}
                </span>{' '}
                • {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
              </p>
            </div>
            {currentPlantTabPlan && currentPlantTabPlan.status !== 'APPROVED' && (
              <button
                type="button"
                onClick={() =>
                  handleDirectApprovePlant(
                    currentPlantTabPlan.id,
                    tabs.find((t) => t.key === activeTab)?.label || activeTab
                  )
                }
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs cursor-pointer"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Approve {tabs.find((t) => t.key === activeTab)?.label}</span>
              </button>
            )}
            {currentPlantTabPlan && currentPlantTabPlan.status === 'APPROVED' && (
              <span className="inline-flex items-center gap-1 px-3 py-1 text-xs font-semibold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Approved & Locked
              </span>
            )}
          </div>

          <PlanGrid
            plan={currentPlantTabPlan}
            items={currentPlantTabPlan?.line_items || []}
            loading={plansLoading}
            uploading={false}
            onUpload={async (f: File) => {
              if (currentPlantTabPlan) {
                await bulkUploadItems(currentPlantTabPlan.id, f, false);
                await loadAllPlans();
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
            canUpload={currentPlantTabPlan?.status !== 'APPROVED'}
            canEdit={currentPlantTabPlan?.status !== 'APPROVED'}
          />
        </div>
      )}

      {activeTab === 'confirmations' && (
        <ConfirmationsTab
          planningVersionId={planningVersionId}
          onVersionChange={setPlanningVersionId}
        />
      )}

      {activeTab === 'adjustments' && (
        <AdjustmentsTab
          planningVersionId={planningVersionId}
          onVersionChange={setPlanningVersionId}
          currentUserId={currentUserId}
        />
      )}

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

      {/* Bulk Upload Modal */}
      {isBulkModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 max-w-md w-full overflow-hidden animate-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-gray-200 flex items-center justify-between">
              <h3 className="text-sm font-bold text-gray-900">Bulk Upload Workbook (All Plants)</h3>
              <button
                onClick={() => setIsBulkModalOpen(false)}
                className="p-1 text-gray-400 hover:text-gray-700 rounded-lg hover:bg-gray-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
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
                      Ingests sheets for Plant I, Plant II, Plant III, Plant IV, and Plant V.
                    </p>
                  </div>
                </label>
              </div>

              <input
                type="file"
                ref={modalFileInputRef}
                accept=".xlsx,.xls,.csv"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleBulkUploadFromReview(f);
                }}
                className="hidden"
              />

              <div
                onClick={() => modalFileInputRef.current?.click()}
                className="border-2 border-dashed border-gray-300 hover:border-orange-500 rounded-xl p-8 text-center cursor-pointer transition-colors bg-gray-50/50 hover:bg-orange-50/20"
              >
                <p className="text-xs font-semibold text-gray-800">
                  Click to select Excel/CSV file to upload
                </p>
                <p className="text-[11px] text-gray-400 mt-1">
                  Supports multi-sheet workbooks with plant sheets
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
    </div>
  );
}

