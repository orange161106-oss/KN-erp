import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../auth/context';
import { canPerform } from '../../core/rbac';
import DataTable, { type ColumnDef } from '../../components/DataTable';
import Toolbar from '../../components/Toolbar';

export interface RequirementRecord {
  id: string;
  plant: string;
  process: string;
  consumable_code: string;
  description: string;
  unit: string;
  required_qty: string;
  stock_qty: string;
  shortage_qty: string;
  po_pending_qty: string;
  status: 'Normal' | 'Low' | 'Critical shortage' | string;
  remarks: string | null;
  msl: string;
}

export default function Requirements() {
  const { user } = useAuth();

  // RBAC checks
  const isAdmin = Boolean(user?.is_super_admin || user?.roles.includes('ADMIN'));
  const canRead = isAdmin || Boolean(user?.can_access_requirements);
  const canExport = canRead;
  const canRecalculate = isAdmin || Boolean(user?.can_access_requirements);

  // Data state
  const [records, setRecords] = useState<RequirementRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Selection state
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set());
  const [selectedCell, setSelectedCell] = useState<{ rowId: string; colKey: keyof RequirementRecord & string } | null>(null);

  // Filters state
  const [searchQuery, setSearchQuery] = useState('');
  const [plantFilter, setPlantFilter] = useState('');
  const [consumableFilter, setConsumableFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // Load records
  const loadRecords = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append('search', searchQuery);
      if (plantFilter) params.append('plant', plantFilter);
      if (consumableFilter) params.append('consumable', consumableFilter);
      if (statusFilter) params.append('status', statusFilter);
      const q = params.toString();
      const data = await apiClient.get<RequirementRecord[]>(`/api/v1/requirements/workspace/records${q ? `?${q}` : ''}`);

      setRecords(data);
      setSelectedRowIds(new Set());
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to fetch requirements data.',
      });
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, plantFilter, consumableFilter, statusFilter]);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  // Recalculate
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
      }>('/api/v1/requirements/workspace/recalculate', {});

      setRecords(res.records);
      setSelectedRowIds(new Set());
      setStatusMessage({
        type: res.critical_shortages > 0 ? 'error' : 'success',
        text: `Recalculated: ${res.record_count} items (${res.critical_shortages} critical shortages, ${res.low_stock} low stock).`,
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

  // Export Excel
  const handleExport = (mode: 'ALL' | 'FILTERED' | 'SELECTED') => {
    let url = '/api/v1/requirements/workspace/export';
    const params = new URLSearchParams();

    if (mode === 'SELECTED') {
      Array.from(selectedRowIds).forEach(id => params.append('record_ids', id));
    } else if (mode === 'FILTERED') {
      if (searchQuery) params.append('search', searchQuery);
      if (plantFilter) params.append('plant', plantFilter);
      if (consumableFilter) params.append('consumable', consumableFilter);
      if (statusFilter) params.append('status', statusFilter);
    }

    const queryString = params.toString();
    if (queryString) url += `?${queryString}`;
    window.open(url, '_blank');
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
        r.consumable_code.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        r.process.toLowerCase().includes(q) ||
        r.plant.toLowerCase().includes(q) ||
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

  // Column definitions
  const columns: ColumnDef<RequirementRecord>[] = useMemo(
    () => [
      {
        key: 'plant',
        label: 'Plant',
        width: 'w-24',
        align: 'left',
        isSticky: true,
      },
      {
        key: 'process',
        label: 'Process',
        width: 'w-28',
        align: 'left',
        isSticky: true,
      },
      {
        key: 'consumable_code',
        label: 'Consumable / Item ID',
        width: 'w-44',
        align: 'left',
        render: val => <span className="font-mono font-bold text-blue-900">{val}</span>,
      },
      {
        key: 'description',
        label: 'Description',
        width: 'w-64',
        align: 'left',
      },
      {
        key: 'unit',
        label: 'Unit',
        width: 'w-16',
        align: 'center',
      },
      {
        key: 'required_qty',
        label: 'Required Qty',
        width: 'w-28',
        align: 'right',
        render: val => <span className="font-mono font-bold text-gray-900">{val}</span>,
      },
      {
        key: 'stock_qty',
        label: 'Stock Qty',
        width: 'w-28',
        align: 'right',
        render: val => <span className="font-mono text-gray-800">{val}</span>,
      },
      {
        key: 'shortage_qty',
        label: 'Shortage Qty',
        width: 'w-28',
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
        key: 'po_pending_qty',
        label: 'PO Pending Qty',
        width: 'w-28',
        align: 'right',
        render: val => <span className="font-mono text-gray-600">{val}</span>,
      },
      {
        key: 'status',
        label: 'Status',
        width: 'w-36',
        align: 'center',
        render: val => {
          if (val === 'Critical shortage') {
            return (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-800 border border-red-300 animate-pulse">
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
        width: 'w-52',
        align: 'left',
      },
    ],
    []
  );

  return (
    <div className="flex flex-col h-full space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 tracking-tight">Consumable Requirements Workspace</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Real-time material requirements computed from PRD Plan Qty × Consumption Norms vs Current Stock.
          </p>
        </div>

        {/* Quick status summary cards */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-3 py-1 bg-white border border-gray-200 rounded text-xs shadow-2xs">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
            <span className="font-semibold text-red-700">{summary.critical}</span>
            <span className="text-gray-500">Critical</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1 bg-white border border-gray-200 rounded text-xs shadow-2xs">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
            <span className="font-semibold text-amber-700">{summary.low}</span>
            <span className="text-gray-500">Low</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1 bg-white border border-gray-200 rounded text-xs shadow-2xs">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
            <span className="font-semibold text-emerald-700">{summary.normal}</span>
            <span className="text-gray-500">Normal</span>
          </div>
        </div>
      </div>

      {statusMessage && (
        <div
          className={`px-3 py-2 rounded text-xs font-medium border flex items-center justify-between ${
            statusMessage.type === 'error'
              ? 'bg-red-50 text-red-800 border-red-200'
              : statusMessage.type === 'success'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : 'bg-blue-50 text-blue-800 border-blue-200'
          }`}
        >
          <div className="flex items-center gap-2">
            <span>{statusMessage.type === 'error' ? '⚠️' : '✓'}</span>
            <span>{statusMessage.text}</span>
          </div>
          <button onClick={() => setStatusMessage(null)} className="text-gray-400 hover:text-gray-600 font-bold">
            ×
          </button>
        </div>
      )}

      {/* Workspace Table Panel */}
      <div className="flex-1 min-h-0 bg-white border border-gray-300 rounded shadow-xs flex flex-col overflow-hidden">
        {/* Toolbar */}
        <Toolbar
          canImport={false}
          canCreate={false}
          canUpdate={false}
          canDelete={false}
          canExport={canExport}
          onExport={handleExport}
          selectedCount={selectedRowIds.size}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          searchPlaceholder="🔍 Search item, description, process..."
          extraActions={
            canRecalculate ? (
              <button
                type="button"
                onClick={handleRecalculate}
                disabled={isRecalculating}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-white bg-brand-navy rounded shadow-xs hover:bg-opacity-90 active:bg-opacity-100 disabled:opacity-50 transition-colors"
              >
                {isRecalculating ? (
                  <>
                    <div className="animate-spin h-3 w-3 border-2 border-white border-t-transparent rounded-full" />
                    <span>Recalculating…</span>
                  </>
                ) : (
                  <>
                    <span>⚡</span>
                    <span>Recalculate</span>
                  </>
                )}
              </button>
            ) : null
          }
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
              ],
            },
          ]}
        />

        {/* Data Grid */}
        <div className="flex-1 min-h-0">
          <DataTable
            columns={columns}
            data={filteredRecords}
            selectedIds={selectedRowIds}
            onSelectionChange={setSelectedRowIds}
            isLoading={isLoading}
            emptyMessage="No consumable requirements found. Click 'Recalculate' to compute from the latest PRD plan."
            canCreate={false}
            selectedCell={selectedCell}
            onSelectCell={setSelectedCell}
            getRowClassName={row => {
              if (row.status === 'Critical shortage') return 'bg-red-50/70 hover:bg-red-100/70 font-medium';
              if (row.status === 'Low') return 'bg-amber-50/60 hover:bg-amber-100/60';
              return '';
            }}
          />
        </div>
      </div>
    </div>
  );
}
