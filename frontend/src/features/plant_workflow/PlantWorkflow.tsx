import React, { useCallback, useEffect, useState } from 'react';
import { apiClient, ApiError } from '../../api/client';
import type {
  AdjustmentCategory,
  AdjustmentStatus,
  CalculatedRequirementItem,
  ConfirmRequirementRequest,
  FinalRequirementItemResponse,
  PlantConfirmationResponse,
  RequirementAdjustmentResponse,
  ReviewAdjustmentRequest,
  SubmitAdjustmentRequest,
} from './types';

// ── Constants ──────────────────────────────────────────────────────────────────

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

// ── Version selector ───────────────────────────────────────────────────────────

function PlanningVersionSelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="mb-4 flex items-center gap-3">
      <label className="text-sm font-medium text-gray-700 whitespace-nowrap">
        Planning Version ID
      </label>
      <input
        type="text"
        className="border rounded px-3 py-1.5 text-sm w-80 font-mono"
        placeholder="Paste planning version UUID…"
        value={value}
        onChange={(e) => onChange(e.target.value.trim())}
      />
    </div>
  );
}

// ── Tab 1: Confirmations ───────────────────────────────────────────────────────

function ConfirmationsTab({ planningVersionId }: { planningVersionId: string }) {
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

  if (!planningVersionId) {
    return <p className="text-gray-500 text-sm">Enter a planning version ID above to load requirements.</p>;
  }

  if (loading) return <p className="text-gray-500 text-sm">Loading…</p>;

  return (
    <div>
      {error && <AlertBox message={error} type="error" />}
      {success && <AlertBox message={success} type="success" />}

      {calcReqs.length === 0 ? (
        <p className="text-gray-500 text-sm">No calculated requirements found for this version.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm border-collapse">
            <thead>
              <tr className="bg-gray-50 border-b">
                <th className="px-3 py-2 text-left font-medium text-gray-600">Consumable</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Process</th>
                <th className="px-3 py-2 text-right font-medium text-gray-600">Calc Qty</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">UOM</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Rule</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Status</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Notes</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Action</th>
              </tr>
            </thead>
            <tbody>
              {calcReqs.map((r) => {
                const confirmed = confirmedIds.has(r.id);
                return (
                  <tr key={r.id} className="border-b hover:bg-gray-50">
                    <td className="px-3 py-2">
                      <span className="font-mono text-xs text-gray-500">{r.consumable_code}</span>
                      <span className="ml-1">{r.consumable_name}</span>
                    </td>
                    <td className="px-3 py-2">{r.process_name ?? '—'}</td>
                    {/* calculated_qty is READ-ONLY — shown as plain text, no input */}
                    <td className="px-3 py-2 text-right font-mono">{r.calculated_qty}</td>
                    <td className="px-3 py-2">{r.uom}</td>
                    <td className="px-3 py-2">
                      <span className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">{r.rule_type}</span>
                    </td>
                    <td className="px-3 py-2">
                      {confirmed ? (
                        <span className="text-green-700 font-semibold text-xs">✓ Confirmed</span>
                      ) : (
                        <span className="text-gray-400 text-xs">Pending</span>
                      )}
                    </td>
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
                          className="text-xs text-red-600 hover:text-red-800 underline"
                        >
                          Retract
                        </button>
                      ) : (
                        <button
                          onClick={() => handleConfirm(r.id)}
                          className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700"
                        >
                          Confirm
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Tab 2: Adjustments ─────────────────────────────────────────────────────────

const EMPTY_FORM: SubmitAdjustmentRequest = {
  planning_version_id: '',
  plant_id: '',
  consumable_id: '',
  category: 'MAINTENANCE',
  requested_qty: '',
  reason: '',
};

function AdjustmentsTab({
  planningVersionId,
  currentUserId,
}: {
  planningVersionId: string;
  currentUserId: string;
}) {
  const [adjustments, setAdjustments] = useState<RequirementAdjustmentResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<SubmitAdjustmentRequest>({
    ...EMPTY_FORM,
    planning_version_id: planningVersionId,
  });
  const [submitting, setSubmitting] = useState(false);
  const [statusFilter, setStatusFilter] = useState<AdjustmentStatus | ''>('');

  const fetchAdjustments = useCallback(async () => {
    if (!planningVersionId) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ planning_version_id: planningVersionId });
      if (statusFilter) params.set('status', statusFilter);
      const data = await apiClient.get<RequirementAdjustmentResponse[]>(
        `/api/v1/plant-workflow/adjustments?${params}`
      );
      setAdjustments(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load adjustments.');
    } finally {
      setLoading(false);
    }
  }, [planningVersionId, statusFilter]);

  useEffect(() => {
    fetchAdjustments();
  }, [fetchAdjustments]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setSubmitting(true);
    try {
      await apiClient.post('/api/v1/plant-workflow/adjustments', form);
      setSuccess('Additional requirement submitted.');
      setShowForm(false);
      setForm({ ...EMPTY_FORM, planning_version_id: planningVersionId });
      await fetchAdjustments();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Submission failed.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleWithdraw = async (id: string) => {
    setError(null);
    setSuccess(null);
    try {
      await apiClient.delete(`/api/v1/plant-workflow/adjustments/${id}`);
      setSuccess('Adjustment withdrawn.');
      await fetchAdjustments();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Withdrawal failed.');
    }
  };

  const handleReview = async (id: string, status: 'APPROVED' | 'REJECTED') => {
    setError(null);
    setSuccess(null);
    const comment = window.prompt(`Optional comment for ${status.toLowerCase()}:`);
    try {
      const payload: ReviewAdjustmentRequest = {
        status,
        reviewer_comment: comment || null,
      };
      await apiClient.patch(`/api/v1/plant-workflow/adjustments/${id}/review`, payload);
      setSuccess(`Adjustment ${status.toLowerCase()}.`);
      await fetchAdjustments();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Review action failed.');
    }
  };

  if (!planningVersionId) {
    return <p className="text-gray-500 text-sm">Enter a planning version ID above to load adjustments.</p>;
  }

  return (
    <div>
      {error && <AlertBox message={error} type="error" />}
      {success && <AlertBox message={success} type="success" />}

      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Filter by status:</label>
          <select
            className="border rounded px-2 py-1 text-sm"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as AdjustmentStatus | '')}
          >
            <option value="">All</option>
            <option value="PENDING">Pending</option>
            <option value="APPROVED">Approved</option>
            <option value="REJECTED">Rejected</option>
          </select>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="text-sm bg-blue-600 text-white px-4 py-1.5 rounded hover:bg-blue-700"
        >
          {showForm ? 'Cancel' : '+ Submit Additional Requirement'}
        </button>
      </div>

      {/* Submit Form */}
      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="bg-gray-50 border rounded p-4 mb-6 space-y-3"
        >
          <h3 className="font-semibold text-gray-700 mb-2">New Additional Requirement</h3>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Plant ID *</label>
              <input
                required
                type="text"
                className="border rounded px-2 py-1.5 text-sm w-full font-mono"
                placeholder="Plant UUID"
                value={form.plant_id}
                onChange={(e) => setForm((f) => ({ ...f, plant_id: e.target.value.trim() }))}
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Consumable ID *</label>
              <input
                required
                type="text"
                className="border rounded px-2 py-1.5 text-sm w-full font-mono"
                placeholder="Consumable UUID"
                value={form.consumable_id}
                onChange={(e) =>
                  setForm((f) => ({ ...f, consumable_id: e.target.value.trim() }))
                }
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Category *</label>
              <select
                required
                className="border rounded px-2 py-1.5 text-sm w-full"
                value={form.category}
                onChange={(e) =>
                  setForm((f) => ({ ...f, category: e.target.value as AdjustmentCategory }))
                }
              >
                {ADJUSTMENT_CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">Requested Qty *</label>
              <input
                required
                type="number"
                min="0.0001"
                step="0.0001"
                className="border rounded px-2 py-1.5 text-sm w-full"
                placeholder="e.g. 50.0000"
                value={form.requested_qty}
                onChange={(e) => setForm((f) => ({ ...f, requested_qty: e.target.value }))}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-600 mb-1">Reason * (required — must not be blank)</label>
            <textarea
              required
              rows={3}
              className="border rounded px-2 py-1.5 text-sm w-full"
              placeholder="Describe why this additional quantity is needed…"
              value={form.reason}
              onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="bg-green-600 text-white px-4 py-1.5 rounded text-sm hover:bg-green-700 disabled:opacity-50"
          >
            {submitting ? 'Submitting…' : 'Submit'}
          </button>
        </form>
      )}

      {/* Adjustments List */}
      {loading ? (
        <p className="text-gray-500 text-sm">Loading…</p>
      ) : adjustments.length === 0 ? (
        <p className="text-gray-500 text-sm">No adjustments found.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm border-collapse">
            <thead>
              <tr className="bg-gray-50 border-b">
                <th className="px-3 py-2 text-left font-medium text-gray-600">Consumable</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Category</th>
                <th className="px-3 py-2 text-right font-medium text-gray-600">Qty</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">UOM</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Reason</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Requested By</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Status</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Action</th>
              </tr>
            </thead>
            <tbody>
              {adjustments.map((adj) => (
                <tr key={adj.id} className="border-b hover:bg-gray-50">
                  <td className="px-3 py-2">
                    <span className="font-mono text-xs text-gray-500">{adj.consumable_code}</span>
                    <span className="ml-1">{adj.consumable_name}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className="bg-gray-100 px-1.5 py-0.5 rounded text-xs">{adj.category}</span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{adj.requested_qty}</td>
                  <td className="px-3 py-2">{adj.uom}</td>
                  <td className="px-3 py-2 max-w-xs">
                    <span className="text-xs text-gray-700 line-clamp-2" title={adj.reason}>
                      {adj.reason}
                    </span>
                    {adj.reviewer_comment && (
                      <span className="block text-[11px] text-gray-500 italic mt-0.5">
                        Comment: {adj.reviewer_comment}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs">{adj.requested_by_username ?? adj.requested_by}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={adj.status} />
                  </td>
                  <td className="px-3 py-2">
                    {adj.status === 'PENDING' && adj.requested_by === currentUserId && (
                      <button
                        onClick={() => handleWithdraw(adj.id)}
                        className="text-xs text-red-600 hover:text-red-800 underline"
                      >
                        Withdraw
                      </button>
                    )}
                    {adj.status === 'PENDING' && adj.requested_by !== currentUserId && (
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleReview(adj.id, 'APPROVED')}
                          className="text-xs bg-green-600 text-white px-2 py-0.5 rounded hover:bg-green-700"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => handleReview(adj.id, 'REJECTED')}
                          className="text-xs bg-red-600 text-white px-2 py-0.5 rounded hover:bg-red-700"
                        >
                          Reject
                        </button>
                      </div>
                    )}
                    {adj.status !== 'PENDING' && (
                      <span className="text-xs text-gray-400">Reviewed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Tab 3: Final Requirements Handoff ──────────────────────────────────────────

function FinalRequirementsTab({ planningVersionId }: { planningVersionId: string }) {
  const [items, setItems] = useState<FinalRequirementItemResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!planningVersionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.get<FinalRequirementItemResponse[]>(
        `/api/v1/plant-workflow/final-requirements?planning_version_id=${planningVersionId}`
      );
      setItems(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load final requirements.');
    } finally {
      setLoading(false);
    }
  }, [planningVersionId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (!planningVersionId) {
    return <p className="text-gray-500 text-sm">Enter a planning version ID above to view final requirements.</p>;
  }

  if (loading) return <p className="text-gray-500 text-sm">Calculating final requirements…</p>;

  return (
    <div>
      {error && <AlertBox message={error} type="error" />}

      {items.length === 0 ? (
        <p className="text-gray-500 text-sm">No requirement data available for this planning version.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm border-collapse">
            <thead>
              <tr className="bg-gray-50 border-b">
                <th className="px-3 py-2 text-left font-medium text-gray-600">Plant</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Consumable</th>
                <th className="px-3 py-2 text-right font-medium text-gray-600">Calculated Qty</th>
                <th className="px-3 py-2 text-right font-medium text-gray-600">Approved Adjustments</th>
                <th className="px-3 py-2 text-right font-semibold text-blue-900 bg-blue-50">Final Requirement Qty</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">UOM</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Confirmation Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => (
                <tr key={`${item.plant_id}-${item.consumable_id}-${idx}`} className="border-b hover:bg-gray-50">
                  <td className="px-3 py-2 font-medium">{item.plant_name ?? item.plant_id}</td>
                  <td className="px-3 py-2">
                    <span className="font-mono text-xs text-gray-500">{item.consumable_code}</span>
                    <span className="ml-1">{item.consumable_name}</span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{item.calculated_qty}</td>
                  <td className="px-3 py-2 text-right font-mono text-green-700">
                    +{item.approved_adjustment_qty}
                  </td>
                  <td className="px-3 py-2 text-right font-mono font-bold text-blue-900 bg-blue-50">
                    {item.final_required_qty}
                  </td>
                  <td className="px-3 py-2">{item.uom}</td>
                  <td className="px-3 py-2">
                    {item.is_fully_confirmed ? (
                      <span className="inline-block px-2 py-0.5 rounded text-xs font-semibold bg-green-100 text-green-800">
                        Fully Confirmed
                      </span>
                    ) : (
                      <span className="inline-block px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-600">
                        Unconfirmed / Partial
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Main PlantWorkflow screen ──────────────────────────────────────────────────

type TabKey = 'confirmations' | 'adjustments' | 'final-requirements';

interface PlantWorkflowProps {
  currentUserId: string;
}

export default function PlantWorkflow({ currentUserId }: PlantWorkflowProps) {
  const [activeTab, setActiveTab] = useState<TabKey>('confirmations');
  const [planningVersionId, setPlanningVersionId] = useState('');

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'confirmations', label: 'Confirmations' },
    { key: 'adjustments', label: 'Additional Requirements' },
    { key: 'final-requirements', label: 'Final Requirements (Handoff)' },
  ];

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-xl font-bold text-gray-800 mb-1">Plant Workflow</h1>
      <p className="text-sm text-gray-500 mb-5">
        Review calculated requirements, manage additional demand, and inspect Final Requirements handoff.
      </p>

      <PlanningVersionSelector value={planningVersionId} onChange={setPlanningVersionId} />

      {/* Tabs */}
      <div className="border-b mb-5">
        <nav className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-blue-600 text-blue-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {activeTab === 'confirmations' && (
        <ConfirmationsTab planningVersionId={planningVersionId} />
      )}
      {activeTab === 'adjustments' && (
        <AdjustmentsTab planningVersionId={planningVersionId} currentUserId={currentUserId} />
      )}
      {activeTab === 'final-requirements' && (
        <FinalRequirementsTab planningVersionId={planningVersionId} />
      )}
    </div>
  );
}
