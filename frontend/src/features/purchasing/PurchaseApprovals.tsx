import { useCallback, useEffect, useState } from 'react';
import { apiClient, ApiError } from '../../api/client';
import { useAuth } from '../auth/context';
import { TableSkeleton } from '../../components/ui/Skeleton';
import PurchasePlanWorkspace from './PurchasePlanWorkspace';
import type {
  ApprovalStatus,
  PurchaseApprovalResponse,
  ReviewPurchaseApprovalRequest,
} from './types';

const STATUS_BADGES: Record<ApprovalStatus, string> = {
  PENDING: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  APPROVED: 'bg-green-100 text-green-800 border-green-200',
  MODIFIED: 'bg-blue-100 text-blue-800 border-blue-200',
  REJECTED: 'bg-red-100 text-red-800 border-red-200',
};

function StatusBadge({ status }: { status: ApprovalStatus }) {
  return (
    <span className={`inline-block px-2.5 py-0.5 rounded border text-xs font-semibold ${STATUS_BADGES[status]}`}>
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

interface PurchaseApprovalsProps {
  currentUserId: string;
}

type TabKey = 'plan' | 'queue' | 'handoff';

export default function PurchaseApprovals({ currentUserId }: PurchaseApprovalsProps) {
  const { user } = useAuth();
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const hasModernFlags = user && (
    'purchase_read' in user ||
    'purchase_create' in user ||
    'purchase_update' in user ||
    'purchase_delete' in user
  );
  const canRead = Boolean(isSuperAdmin || (hasModernFlags ? user?.purchase_read : true));
  const canUpdate = Boolean(isSuperAdmin || (hasModernFlags ? user?.purchase_update : true));
  const hasActions = Boolean(isSuperAdmin || canUpdate);

  const [activeTab, setActiveTab] = useState<TabKey>('plan');
  const [items, setItems] = useState<PurchaseApprovalResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<ApprovalStatus | ''>('PENDING');

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (activeTab === 'queue') {
        const params = new URLSearchParams();
        if (statusFilter) params.set('status', statusFilter);
        const data = await apiClient.get<PurchaseApprovalResponse[]>(
          `/api/v1/purchasing/approvals?${params}`
        );
        setItems(data);
      } else {
        const data = await apiClient.get<PurchaseApprovalResponse[]>(
          '/api/v1/purchasing/approvals/approved-handoff'
        );
        setItems(data);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load purchase approvals.');
    } finally {
      setLoading(false);
    }
  }, [activeTab, statusFilter]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleReview = async (id: string, action: 'APPROVE' | 'MODIFY' | 'REJECT') => {
    setError(null);
    setSuccess(null);

    let approvedQty: string | null = null;
    let reason: string | null = null;

    if (action === 'MODIFY') {
      const inputQty = window.prompt('Enter overridden purchase quantity:');
      if (!inputQty || isNaN(Number(inputQty)) || Number(inputQty) <= 0) {
        setError('Valid positive override quantity is required.');
        return;
      }
      approvedQty = inputQty.trim();
      const inputReason = window.prompt('Mandatory reason for quantity modification:');
      if (!inputReason || !inputReason.trim()) {
        setError('Modification reason is required.');
        return;
      }
      reason = inputReason.trim();
    } else if (action === 'REJECT') {
      const inputReason = window.prompt('Mandatory reason for rejection:');
      if (!inputReason || !inputReason.trim()) {
        setError('Rejection reason is required.');
        return;
      }
      reason = inputReason.trim();
    }

    try {
      const payload: ReviewPurchaseApprovalRequest = {
        action,
        approved_qty: approvedQty,
        reason,
      };
      await apiClient.patch(`/api/v1/purchasing/approvals/${id}/review`, payload);
      setSuccess(`Recommendation ${action.toLowerCase()}d successfully.`);
      await fetchItems();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Review action failed.');
    }
  };

  if (!canRead) {
    return <p role="alert" className="text-red-700">You do not have permission to view purchase approvals.</p>;
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-gray-800 mb-1">Purchase Approvals Queue</h1>
        <p className="text-sm text-gray-500">
          Review, override, or approve purchase recommendations before Purchase Order creation.
        </p>
      </div>

      {error && <AlertBox message={error} type="error" />}
      {success && <AlertBox message={success} type="success" />}

      {/* Tabs & Filters */}
      <div className="flex flex-wrap items-center justify-between border-b pb-3 gap-4">
        <nav className="flex gap-2">
          <button
            onClick={() => setActiveTab('plan')}
            className={`px-4 py-2 text-sm font-medium rounded-t-md transition-colors ${
              activeTab === 'plan'
                ? 'bg-burnt-orange/10 text-burnt-orange border-b-2 border-burnt-orange font-semibold'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Purchase Planning (MD &amp; Normal View)
          </button>
          <button
            onClick={() => setActiveTab('queue')}
            className={`px-4 py-2 text-sm font-medium rounded-t-md transition-colors ${
              activeTab === 'queue'
                ? 'bg-blue-50 text-blue-700 border-b-2 border-blue-600 font-semibold'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Approval Queue
          </button>
          <button
            onClick={() => setActiveTab('handoff')}
            className={`px-4 py-2 text-sm font-medium rounded-t-md transition-colors ${
              activeTab === 'handoff'
                ? 'bg-blue-50 text-blue-700 border-b-2 border-blue-600 font-semibold'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Approved Handoff (PO Ready)
          </button>
        </nav>

        {activeTab === 'queue' && (
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-600 font-medium">Filter Status:</label>
            <select
              className="border rounded px-3 py-1.5 text-sm"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as ApprovalStatus | '')}
            >
              <option value="">All Statuses</option>
              <option value="PENDING">Pending</option>
              <option value="APPROVED">Approved</option>
              <option value="MODIFIED">Modified</option>
              <option value="REJECTED">Rejected</option>
            </select>
          </div>
        )}
      </div>

      {/* Tab Content */}
      {activeTab === 'plan' ? (
        <PurchasePlanWorkspace currentUserId={currentUserId} />
      ) : loading ? (
        <TableSkeleton columns={8 + (hasActions ? 1 : 0)} rows={5} />
      ) : items.length === 0 ? (
        <div className="bg-white border rounded-lg p-8 text-center text-gray-500 text-sm">
          No purchase recommendations found in this view.
        </div>
      ) : (
        <div className="bg-white border border-ink-text/10 rounded-lg overflow-hidden shadow-2xs">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm border-collapse">
              <thead>
                <tr className="bg-vanilla-surface border-b border-ink-text/10 text-ink-text">
                  <th className="px-4 py-3 text-left font-semibold">Consumable</th>
                  <th className="px-4 py-3 text-left font-semibold">Supplier</th>
                  <th className="px-4 py-3 text-right font-semibold">Raw Need</th>
                  <th className="px-4 py-3 text-right font-semibold">System Recommended Qty</th>
                  <th className="px-4 py-3 text-right font-semibold text-burnt-orange bg-burnt-orange/10">Approved Qty</th>
                  <th className="px-4 py-3 text-left font-semibold">UOM</th>
                  <th className="px-4 py-3 text-left font-semibold">Status</th>
                  <th className="px-4 py-3 text-left font-semibold">Reason / Comment</th>
                  {hasActions && <th className="px-4 py-3 text-left font-semibold">Action</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-text/10">
                {items.map((item) => {
                  const isSelfRequest = item.requested_by === currentUserId;
                  return (
                    <tr key={item.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs text-gray-500">{item.consumable_code}</span>
                        <span className="block font-medium text-gray-900">{item.consumable_name}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs text-gray-500">{item.supplier_code}</span>
                        <span className="block text-gray-800">{item.supplier_name}</span>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-gray-600">{item.raw_calculated_qty}</td>
                      <td className="px-4 py-3 text-right font-mono font-medium text-gray-800">{item.system_recommended_qty}</td>
                      <td className="px-4 py-3 text-right font-mono font-bold text-blue-900 bg-blue-50">
                        {item.approved_qty ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-gray-600">{item.uom}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={item.status} />
                      </td>
                      <td className="px-4 py-3 max-w-xs text-xs text-gray-700">
                        {item.reason ?? '—'}
                        {item.reviewed_by_username && (
                          <span className="block text-[11px] text-gray-400 mt-0.5">
                            Rev by {item.reviewed_by_username} at {new Date(item.reviewed_at || '').toLocaleTimeString()}
                          </span>
                        )}
                      </td>
                      {hasActions && (
                        <td className="px-4 py-3">
                          {item.status === 'PENDING' && !isSelfRequest && (
                            <div className="flex items-center gap-1.5">
                              <button
                                onClick={() => handleReview(item.id, 'APPROVE')}
                                className="text-xs bg-green-600 text-white px-2.5 py-1 rounded hover:bg-green-700 transition-colors shadow-sm"
                              >
                                Approve
                              </button>
                              <button
                                onClick={() => handleReview(item.id, 'MODIFY')}
                                className="text-xs bg-blue-600 text-white px-2.5 py-1 rounded hover:bg-blue-700 transition-colors shadow-sm"
                              >
                                Modify
                              </button>
                              <button
                                onClick={() => handleReview(item.id, 'REJECT')}
                                className="text-xs bg-red-600 text-white px-2.5 py-1 rounded hover:bg-red-700 transition-colors shadow-sm"
                              >
                                Reject
                              </button>
                            </div>
                          )}
                          {item.status === 'PENDING' && isSelfRequest && (
                            <span className="text-xs text-gray-400 italic">Self-request (Approval blocked)</span>
                          )}
                          {item.status !== 'PENDING' && (
                            <span className="text-xs text-gray-400 font-medium">✓ Reviewed</span>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
