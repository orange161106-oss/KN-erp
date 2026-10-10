import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient, ApiError } from '../../api/client';
import { useAuth } from '../auth/context';
import DataTable, { type ColumnDef, type HeaderGroupDef } from '../../components/DataTable';
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

interface PurchaseApprovalsProps {
  currentUserId: string;
}

type TabKey = 'queue' | 'handoff';

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

  const [activeTab, setActiveTab] = useState<TabKey>('queue');
  const [items, setItems] = useState<PurchaseApprovalResponse[]>([]);
  const [originalMap, setOriginalMap] = useState<Map<string, PurchaseApprovalResponse>>(new Map());
  const [modifiedRecords, setModifiedRecords] = useState<Map<string, Partial<PurchaseApprovalResponse>>>(new Map());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<ApprovalStatus | ''>('PENDING');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectedCell, setSelectedCell] = useState<{ rowId: string; colKey: keyof PurchaseApprovalResponse & string } | null>(null);

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
        const orig = new Map<string, PurchaseApprovalResponse>();
        data.forEach(r => orig.set(r.id, { ...r }));
        setOriginalMap(orig);
        setModifiedRecords(new Map());
      } else {
        const data = await apiClient.get<PurchaseApprovalResponse[]>(
          '/api/v1/purchasing/approvals/approved-handoff'
        );
        setItems(data);
        const orig = new Map<string, PurchaseApprovalResponse>();
        data.forEach(r => orig.set(r.id, { ...r }));
        setOriginalMap(orig);
        setModifiedRecords(new Map());
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load purchase approvals.');
    } finally {
      setLoading(false);
    }
  }, [activeTab, statusFilter]);

  useEffect(() => {
    void fetchItems();
  }, [fetchItems]);

  // Handle cell edit
  const handleCellChange = (rowId: string, colKey: keyof PurchaseApprovalResponse & string, value: string) => {
    if (!hasActions) return;
    const permitted = ['approved_qty', 'reason'];
    if (!permitted.includes(colKey)) return;

    setItems(prev =>
      prev.map(row => {
        if (row.id !== rowId) return row;
        return { ...row, [colKey]: value };
      })
    );

    setModifiedRecords(prev => {
      const next = new Map(prev);
      const existing = next.get(rowId) || {};
      next.set(rowId, { ...existing, [colKey]: value });
      return next;
    });
  };

  // Review single action
  const handleReview = async (id: string, action: 'APPROVE' | 'MODIFY' | 'REJECT', explicitQty?: string, explicitReason?: string) => {
    setError(null);
    setSuccess(null);

    const targetRow = items.find(r => r.id === id);
    let approvedQty: string | null = explicitQty ?? targetRow?.approved_qty ?? null;
    let reason: string | null = explicitReason ?? targetRow?.reason ?? null;

    if (action === 'MODIFY') {
      if (!approvedQty || isNaN(Number(approvedQty)) || Number(approvedQty) <= 0) {
        const inputQty = window.prompt('Enter overridden purchase quantity:', targetRow?.system_recommended_qty || '');
        if (!inputQty || isNaN(Number(inputQty)) || Number(inputQty) <= 0) {
          setError('Valid positive override quantity is required.');
          return;
        }
        approvedQty = inputQty.trim();
      }
      if (!reason || !reason.trim()) {
        const inputReason = window.prompt('Mandatory reason for quantity modification:', 'Approved with adjusted quantity');
        if (!inputReason || !inputReason.trim()) {
          setError('Modification reason is required.');
          return;
        }
        reason = inputReason.trim();
      }
    } else if (action === 'REJECT') {
      if (!reason || !reason.trim()) {
        const inputReason = window.prompt('Mandatory reason for rejection:');
        if (!inputReason || !inputReason.trim()) {
          setError('Rejection reason is required.');
          return;
        }
        reason = inputReason.trim();
      }
    } else if (action === 'APPROVE') {
      if (!approvedQty || approvedQty === '0') {
        approvedQty = targetRow?.system_recommended_qty ?? null;
      }
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

  // Batch save modified rows
  const handleBatchSaveModified = async () => {
    if (modifiedRecords.size === 0) return;
    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      let savedCount = 0;
      for (const [rowId, changes] of modifiedRecords.entries()) {
        const row = items.find(r => r.id === rowId);
        if (!row) continue;

        const qty = changes.approved_qty ?? row.approved_qty ?? row.system_recommended_qty;
        const reason = changes.reason ?? row.reason ?? 'Reviewed with modified parameters';

        const payload: ReviewPurchaseApprovalRequest = {
          action: 'MODIFY',
          approved_qty: qty,
          reason,
        };
        await apiClient.patch(`/api/v1/purchasing/approvals/${rowId}/review`, payload);
        savedCount++;
      }

      setSuccess(`Successfully saved and applied ${savedCount} modified purchase recommendation(s).`);
      await fetchItems();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to save changes.');
    } finally {
      setSaving(false);
    }
  };

  // Filtered rows for display
  const filteredItems = useMemo(() => {
    if (!searchQuery) return items;
    const q = searchQuery.toLowerCase();
    return items.filter(item =>
      (item.consumable_code && item.consumable_code.toLowerCase().includes(q)) ||
      (item.consumable_name && item.consumable_name.toLowerCase().includes(q)) ||
      (item.supplier_name && item.supplier_name.toLowerCase().includes(q)) ||
      (item.supplier_code && item.supplier_code.toLowerCase().includes(q)) ||
      (item.reason && item.reason.toLowerCase().includes(q))
    );
  }, [items, searchQuery]);

  // CSV Export
  const handleExportCSV = () => {
    if (filteredItems.length === 0) return;
    const headers = [
      'Consumable Code',
      'Consumable Name',
      'Supplier Code',
      'Supplier Name',
      'Raw Need Qty',
      'System Recommended Qty',
      'Approved Qty',
      'UOM',
      'Status',
      'Reason',
      'Reviewed By',
    ];
    const rows = filteredItems.map(item => [
      `"${item.consumable_code || ''}"`,
      `"${item.consumable_name || ''}"`,
      `"${item.supplier_code || ''}"`,
      `"${item.supplier_name || ''}"`,
      `"${item.raw_calculated_qty || ''}"`,
      `"${item.system_recommended_qty || ''}"`,
      `"${item.approved_qty || ''}"`,
      `"${item.uom || ''}"`,
      `"${item.status || ''}"`,
      `"${(item.reason || '').replace(/"/g, '""')}"`,
      `"${item.reviewed_by_username || ''}"`,
    ]);

    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `Purchase_Approvals_${activeTab}_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Section 7A & Excel Header Groups
  const headerGroups: HeaderGroupDef[] = useMemo(
    () => [
      {
        label: 'CONSUMABLE & SUPPLIER DETAILS',
        columnKeys: ['consumable_code', 'consumable_name', 'supplier_name', 'supplier_code', 'uom'],
        isSticky: true,
        className: 'p-1 text-center font-bold text-white uppercase tracking-wider text-[11px] border-r border-b border-ink-text/20 bg-brand-navy select-none box-border',
      },
      {
        label: 'QUANTITIES (SYSTEM & APPROVED)',
        columnKeys: ['raw_calculated_qty', 'system_recommended_qty', 'approved_qty'],
        className: 'p-1 text-center font-bold text-white uppercase tracking-wider text-[11px] border-r border-b border-ink-text/20 bg-brand-steel select-none box-border',
      },
      {
        label: 'DECISION & ACTIONS',
        columnKeys: ['status', 'reason', 'reviewed_by_username', 'actions'],
        className: 'p-1 text-center font-bold text-white uppercase tracking-wider text-[11px] border-r border-b border-ink-text/20 bg-brand-navy select-none box-border',
      },
    ],
    []
  );

  // Column Definitions
  const columns: ColumnDef<PurchaseApprovalResponse>[] = useMemo(
    () => [
      {
        key: 'consumable_code',
        label: 'Consumable Code',
        width: 160,
        align: 'left',
        isSticky: true,
        render: val => <span className="font-mono font-bold text-blue-900">{val}</span>,
      },
      {
        key: 'consumable_name',
        label: 'Consumable Name',
        width: 220,
        align: 'left',
        render: val => <span className="font-medium text-gray-900 truncate block">{val}</span>,
      },
      {
        key: 'supplier_name',
        label: 'Supplier Name',
        width: 200,
        align: 'left',
        render: val => <span className="text-gray-800 truncate block">{val}</span>,
      },
      {
        key: 'supplier_code',
        label: 'Supplier Code',
        width: 130,
        align: 'left',
        render: val => <span className="font-mono text-gray-600">{val || '—'}</span>,
      },
      {
        key: 'uom',
        label: 'UOM',
        width: 80,
        align: 'center',
        render: val => <span className="text-gray-700 font-medium">{val}</span>,
      },
      {
        key: 'raw_calculated_qty',
        label: 'Raw Need Qty',
        width: 130,
        align: 'right',
        render: val => <span className="font-mono text-gray-600">{val}</span>,
      },
      {
        key: 'system_recommended_qty',
        label: 'Recommended Qty',
        width: 150,
        align: 'right',
        render: val => <span className="font-mono font-semibold text-gray-900">{val}</span>,
      },
      {
        key: 'approved_qty',
        label: 'Approved Qty',
        width: 140,
        align: 'right',
        isEditable: hasActions,
        render: val => (
          <span className="font-mono font-bold text-blue-950 bg-blue-50/70 px-1 py-0.5 rounded">
            {val ?? '—'}
          </span>
        ),
      },
      {
        key: 'status',
        label: 'Status',
        width: 130,
        align: 'center',
        render: val => <StatusBadge status={val} />,
      },
      {
        key: 'reason',
        label: 'Reason / Comment',
        width: 240,
        align: 'left',
        isEditable: hasActions,
        render: (val, row) => (
          <div>
            <span className="text-gray-800 text-xs block truncate">{val || '—'}</span>
            {row.reviewed_by_username && (
              <span className="text-[10px] text-gray-400 block truncate">
                by {row.reviewed_by_username} at {row.reviewed_at ? new Date(row.reviewed_at).toLocaleTimeString() : ''}
              </span>
            )}
          </div>
        ),
      },
      {
        key: 'reviewed_by_username',
        label: 'Reviewed By',
        width: 130,
        align: 'left',
        render: val => <span className="text-gray-600 text-xs">{val || '—'}</span>,
      },
      {
        key: 'id' as any,
        label: 'Actions',
        width: 220,
        align: 'center',
        render: (_val, row) => {
          const isSelfRequest = row.requested_by === currentUserId;
          if (!hasActions) return <span className="text-gray-400 text-xs">—</span>;

          if (row.status === 'PENDING') {
            if (isSelfRequest) {
              return <span className="text-xs text-gray-400 italic">Self-request</span>;
            }
            return (
              <div className="flex items-center justify-center gap-1.5" onClick={e => e.stopPropagation()}>
                <button
                  type="button"
                  onClick={() => void handleReview(row.id, 'APPROVE')}
                  className="px-2 py-0.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-[11px] font-medium shadow-xs"
                >
                  Approve
                </button>
                <button
                  type="button"
                  onClick={() => void handleReview(row.id, 'MODIFY')}
                  className="px-2 py-0.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-[11px] font-medium shadow-xs"
                >
                  Modify
                </button>
                <button
                  type="button"
                  onClick={() => void handleReview(row.id, 'REJECT')}
                  className="px-2 py-0.5 bg-rose-600 hover:bg-rose-700 text-white rounded text-[11px] font-medium shadow-xs"
                >
                  Reject
                </button>
              </div>
            );
          }

          return (
            <span className="text-xs text-emerald-700 font-semibold flex items-center justify-center gap-1">
              ✓ Reviewed
            </span>
          );
        },
      },
    ],
    [hasActions, currentUserId]
  );

  if (!canRead) {
    return <p role="alert" className="text-red-700 p-4">You do not have permission to view purchase approvals.</p>;
  }

  return (
    <div className="flex flex-col h-full space-y-3">
      {/* Top Banner & Info */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-white p-3 rounded border border-gray-200 shadow-2xs">
        <div>
          <h1 className="text-lg font-bold text-gray-900 tracking-tight flex items-center gap-2">
            <span>Purchase Approvals</span>
            <span className="text-xs font-normal text-gray-500 bg-gray-100 px-2 py-0.5 rounded border border-gray-300">
              Procurement Review Module
            </span>
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Spreadsheet-style review, inline quantity override, and approval queue for consumable purchase recommendations.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          {modifiedRecords.size > 0 && hasActions && (
            <button
              type="button"
              onClick={() => void handleBatchSaveModified()}
              disabled={saving}
              className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-bold shadow-xs flex items-center gap-1.5 transition-colors animate-pulse"
            >
              {saving ? 'Saving…' : `💾 Save Changes (${modifiedRecords.size})`}
            </button>
          )}

          <button
            type="button"
            onClick={handleExportCSV}
            className="px-3 py-1.5 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 rounded text-xs font-medium shadow-2xs flex items-center gap-1.5 transition-colors"
          >
            📊 Export CSV
          </button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="p-2.5 bg-red-50 text-red-800 border border-red-200 rounded text-xs flex items-center justify-between shadow-2xs">
          <span>⚠️ {error}</span>
          <button type="button" onClick={() => setError(null)} className="font-bold hover:text-red-950">✕</button>
        </div>
      )}
      {success && (
        <div className="p-2.5 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded text-xs flex items-center justify-between shadow-2xs">
          <span>✅ {success}</span>
          <button type="button" onClick={() => setSuccess(null)} className="font-bold hover:text-emerald-950">✕</button>
        </div>
      )}

      {/* Tabs & Search Filter Bar */}
      <div className="bg-white border border-gray-200 rounded p-2 flex flex-wrap items-center justify-between gap-3 shadow-2xs">
        <div className="flex items-center gap-2">
          {/* Tabs */}
          <div className="flex rounded border border-gray-300 overflow-hidden bg-gray-50 text-xs font-medium">
            <button
              type="button"
              onClick={() => setActiveTab('queue')}
              className={`px-3 py-1 transition-colors ${
                activeTab === 'queue' ? 'bg-brand-navy text-white font-bold' : 'text-gray-700 hover:bg-gray-200'
              }`}
            >
              Approval Queue ({items.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('handoff')}
              className={`px-3 py-1 transition-colors ${
                activeTab === 'handoff' ? 'bg-brand-navy text-white font-bold' : 'text-gray-700 hover:bg-gray-200'
              }`}
            >
              Approved Handoff (PO Ready)
            </button>
          </div>

          {/* Status Filter */}
          {activeTab === 'queue' && (
            <div className="flex items-center gap-1.5 ml-2">
              <label className="text-xs font-bold text-gray-700">Status:</label>
              <select
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value as ApprovalStatus | '')}
                className="px-2 py-1 text-xs border border-gray-300 rounded bg-white text-gray-800 font-medium"
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

        {/* Search */}
        <div className="relative">
          <input
            type="text"
            placeholder="Search code, name, supplier…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="pl-8 pr-3 py-1 text-xs border border-gray-300 rounded bg-white text-gray-800 placeholder-gray-400 focus:ring-1 focus:ring-brand-steel w-64"
          />
          <span className="absolute left-2.5 top-1.5 text-gray-400 text-xs">🔍</span>
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-1 text-gray-400 hover:text-gray-700 text-xs font-bold"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Spreadsheet Grid */}
      <div className="flex-1 flex flex-col min-h-0">
        <DataTable<PurchaseApprovalResponse>
          columns={columns}
          data={filteredItems}
          originalData={originalMap}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          onCellChange={handleCellChange}
          isLoading={loading}
          emptyMessage="No purchase recommendations found in this view."
          canCreate={false}
          selectedCell={selectedCell}
          onSelectCell={setSelectedCell}
          headerGroups={headerGroups}
        />
      </div>

      {/* Status Bar */}
      <div className="py-1 px-3 bg-vanilla-surface border border-ink-text/10 rounded flex items-center justify-between text-2xs text-gray-500 select-none">
        <div>
          Total Recommendations: <span className="font-bold text-gray-800">{filteredItems.length}</span>
          {modifiedRecords.size > 0 && (
            <span className="ml-3 font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
              ● {modifiedRecords.size} unsaved override(s)
            </span>
          )}
        </div>
        <div className="text-gray-400">
          Tip: Double-click Approved Qty or Reason to edit inline · Column visibility in Columns menu · Shift+click range selection
        </div>
      </div>
    </div>
  );
}
