import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../auth/context';
import { canPerform } from '../../core/rbac';
import DataTable, { type ColumnDef } from '../../components/DataTable';
import Toolbar from '../../components/Toolbar';
import ConfirmDialog from '../../components/ConfirmDialog';
import SalesScheduleImportModal from './SalesScheduleImportModal';

export interface PRDRecord {
  id: string;
  row_index: number | null;
  plant: string;
  customer: string | null;
  customer_id?: string | null;
  customer_code?: string | null;
  customer_group?: string | null;
  product_code: string;
  description: string;
  planned_quantity: string;
  uom: string;
  target_period: string;
  planning_version: string;
  revision?: string | null;
  section_type?: string | null;
  status: string;
  remarks: string | null;
  is_new?: boolean;
}

export default function PRDPlanning() {
  const { user } = useAuth();

  // RBAC checks
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const canRead = Boolean(isSuperAdmin || user?.prd_planning_read || canPerform(user, 'prd', 'read'));
  const canCreate = Boolean(isSuperAdmin || user?.prd_planning_create || canPerform(user, 'prd', 'create') || user?.permissions?.includes('prd.plan.create'));
  const canUpdate = Boolean(isSuperAdmin || user?.prd_planning_update || canPerform(user, 'prd', 'update') || user?.permissions?.includes('prd.plan.update'));
  const canDelete = Boolean(isSuperAdmin || user?.prd_planning_delete || canPerform(user, 'prd', 'delete') || user?.permissions?.includes('prd.plan.delete'));
  const canImport = Boolean(canCreate || canPerform(user, 'prd', 'import') || user?.permissions?.includes('prd.plan.import'));
  const canExport = Boolean(canRead || canPerform(user, 'prd', 'export'));

  // Data state
  const [records, setRecords] = useState<PRDRecord[]>([]);
  const [originalMap, setOriginalMap] = useState<Map<string, PRDRecord>>(new Map());
  const [deletedIds, setDeletedIds] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Selection state
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set());
  const [selectedCell, setSelectedCell] = useState<{ rowId: string; colKey: keyof PRDRecord & string } | null>(null);

  // Search & Filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [plantFilter, setPlantFilter] = useState('');
  const [customerFilter, setCustomerFilter] = useState('');
  const [periodFilter, setPeriodFilter] = useState('');
  const [versionFilter, setVersionFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // Modals state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Load records
  const loadRecords = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append('search', searchQuery);
      if (plantFilter) params.append('plant', plantFilter);
      if (customerFilter) params.append('customer', customerFilter);
      if (periodFilter) params.append('target_period', periodFilter);
      if (versionFilter) params.append('planning_version', versionFilter);
      if (statusFilter) params.append('status', statusFilter);
      params.append('limit', '1000');
      const q = params.toString();
      const data = await apiClient.get<PRDRecord[]>(`/api/v1/prd/workspace/records${q ? `?${q}` : ''}`);

      setRecords(data);
      const orig = new Map<string, PRDRecord>();
      data.forEach(r => orig.set(r.id, { ...r }));
      setOriginalMap(orig);
      setDeletedIds([]);
      setSelectedRowIds(new Set());
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to fetch PRD workspace records.',
      });
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, plantFilter, customerFilter, periodFilter, versionFilter, statusFilter]);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  // Unique options for filters
  const uniquePlants = useMemo(() => {
    const set = new Set<string>();
    records.forEach(r => { if (r.plant) set.add(r.plant); });
    return Array.from(set).sort();
  }, [records]);

  const uniqueCustomers = useMemo(() => {
    const set = new Set<string>();
    records.forEach(r => { if (r.customer) set.add(r.customer); });
    return Array.from(set).sort();
  }, [records]);

  const uniquePeriods = useMemo(() => {
    const set = new Set<string>();
    records.forEach(r => { if (r.target_period) set.add(r.target_period); });
    return Array.from(set).sort();
  }, [records]);

  const uniqueVersions = useMemo(() => {
    const set = new Set<string>();
    records.forEach(r => {
      const rev = r.revision || r.planning_version;
      if (rev) set.add(rev);
    });
    return Array.from(set).sort();
  }, [records]);

  // Filtered records
  const filteredRecords = useMemo(() => {
    return records.filter(r => {
      if (plantFilter && r.plant !== plantFilter) return false;
      if (customerFilter && r.customer !== customerFilter && r.customer_code !== customerFilter) return false;
      if (periodFilter && r.target_period !== periodFilter) return false;
      if (versionFilter && r.planning_version !== versionFilter && r.revision !== versionFilter) return false;
      if (statusFilter && r.status !== statusFilter) return false;
      if (!searchQuery) return true;
      const q = searchQuery.toLowerCase();
      return (
        r.product_code.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        (r.customer && r.customer.toLowerCase().includes(q)) ||
        (r.customer_code && r.customer_code.toLowerCase().includes(q)) ||
        (r.customer_group && r.customer_group.toLowerCase().includes(q)) ||
        r.plant.toLowerCase().includes(q) ||
        (r.remarks && r.remarks.toLowerCase().includes(q))
      );
    });
  }, [records, plantFilter, customerFilter, periodFilter, versionFilter, statusFilter, searchQuery]);

  // Per-Customer Summaries
  const customerSummaries = useMemo(() => {
    const map = new Map<string, { count: number; totalQty: number; code?: string }>();
    filteredRecords.forEach(r => {
      const custName = r.customer || 'Unassigned';
      const existing = map.get(custName) || { count: 0, totalQty: 0, code: r.customer_code || '' };
      existing.count += 1;
      existing.totalQty += parseFloat(r.planned_quantity || '0') || 0;
      map.set(custName, existing);
    });
    return Array.from(map.entries()).sort((a, b) => b[1].totalQty - a[1].totalQty);
  }, [filteredRecords]);

  // Unsaved changes count
  const unsavedCount = useMemo(() => {
    let count = deletedIds.length;
    records.forEach(r => {
      const orig = originalMap.get(r.id);
      if (!orig) {
        count++;
      } else {
        const keys: (keyof PRDRecord)[] = [
          'plant', 'customer', 'customer_code', 'customer_group', 'product_code', 'description', 'planned_quantity',
          'uom', 'target_period', 'planning_version', 'status', 'remarks'
        ];
        const changed = keys.some(k => String(orig[k] ?? '').trim() !== String(r[k] ?? '').trim());
        if (changed) count++;
      }
    });
    return count;
  }, [records, originalMap, deletedIds]);

  // Cell editing
  const handleCellChange = (rowId: string, colKey: keyof PRDRecord & string, value: string) => {
    setRecords(prev =>
      prev.map(r => {
        if (r.id !== rowId) return r;
        return { ...r, [colKey]: value };
      })
    );
  };

  // Add row
  const handleAddRow = () => {
    const newId = `new-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    const nextIndex = records.length + 1;
    const newRecord: PRDRecord = {
      id: newId,
      row_index: nextIndex,
      plant: plantFilter || (records[0]?.plant ?? 'Plant 1'),
      customer: 'Ashok Leyland',
      customer_code: 'CUST-AL',
      customer_group: 'Component',
      product_code: 'NEW-PART-01',
      description: 'New Planned Product',
      planned_quantity: '100.0000',
      uom: 'Nos',
      target_period: periodFilter || new Date().toISOString().slice(0, 7),
      planning_version: versionFilter || 'R0',
      revision: versionFilter || 'R0',
      section_type: 'STANDARD',
      status: 'DRAFT',
      remarks: '',
      is_new: true,
    };
    setRecords(prev => [newRecord, ...prev]);
    setSelectedCell({ rowId: newId, colKey: 'product_code' });
    setSelectedRowIds(new Set([newId]));
  };

  // Save changes
  const handleSave = async () => {
    setIsSaving(true);
    setStatusMessage(null);
    try {
      const payloadRecords = records.map((r, idx) => ({
        id: r.id.startsWith('new-') ? null : r.id,
        row_index: idx + 1,
        plant: r.plant,
        customer: r.customer,
        customer_id: r.customer_id,
        customer_code: r.customer_code,
        customer_group: r.customer_group,
        product_code: r.product_code,
        description: r.description,
        planned_quantity: r.planned_quantity,
        uom: r.uom,
        target_period: r.target_period,
        planning_version: r.planning_version || r.revision || 'R0',
        revision: r.revision || r.planning_version || 'R0',
        section_type: r.section_type || 'STANDARD',
        status: r.status,
        remarks: r.remarks,
      }));

      const res = await apiClient.post<{
        saved_count: number;
        deleted_count: number;
        records: PRDRecord[];
      }>('/api/v1/prd/workspace/save', {
        records: payloadRecords,
        deleted_ids: deletedIds,
        reason: 'PRD Workspace sync',
      });

      setRecords(res.records);
      const nextMap = new Map<string, PRDRecord>();
      res.records.forEach(r => nextMap.set(r.id, { ...r }));
      setOriginalMap(nextMap);
      setDeletedIds([]);
      setStatusMessage({
        type: 'success',
        text: `Saved successfully (${res.saved_count} saved, ${res.deleted_count} deleted).`,
      });
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to save PRD changes.',
      });
    } finally {
      setIsSaving(false);
    }
  };

  // Delete selected rows
  const handleDeleteSelected = async () => {
    if (selectedRowIds.size === 0) return;
    setIsSaving(true);
    setStatusMessage(null);

    try {
      const realIds: string[] = [];
      const newIds: string[] = [];

      selectedRowIds.forEach(id => {
        if (id.startsWith('new-')) newIds.push(id);
        else realIds.push(id);
      });

      if (realIds.length > 0) {
        await apiClient.post('/api/v1/prd/workspace/bulk-delete', {
          ids: realIds,
          reason: 'Deleted selected rows via PRD toolbar',
        });
      }

      setRecords(prev => prev.filter(r => !selectedRowIds.has(r.id)));
      setSelectedRowIds(new Set());
      setShowDeleteConfirm(false);

      setStatusMessage({
        type: 'success',
        text: `Deleted ${realIds.length + newIds.length} row(s) successfully.`,
      });
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to delete selected rows.',
      });
    } finally {
      setIsSaving(false);
    }
  };

  // Export Excel
  const handleExport = (mode: 'ALL' | 'FILTERED' | 'SELECTED') => {
    let url = '/api/v1/prd/workspace/export';
    const params = new URLSearchParams();

    if (mode === 'SELECTED') {
      const ids = Array.from(selectedRowIds).filter(id => !id.startsWith('new-'));
      ids.forEach(id => params.append('record_ids', id));
    } else if (mode === 'FILTERED') {
      if (searchQuery) params.append('search', searchQuery);
      if (plantFilter) params.append('plant', plantFilter);
      if (customerFilter) params.append('customer', customerFilter);
      if (periodFilter) params.append('target_period', periodFilter);
      if (versionFilter) params.append('planning_version', versionFilter);
      if (statusFilter) params.append('status', statusFilter);
    }

    const queryString = params.toString();
    if (queryString) url += `?${queryString}`;
    window.open(url, '_blank');
  };

  // Columns definition (Customer, Customer ID, Group first-class visible columns)
  const columns: ColumnDef<PRDRecord>[] = useMemo(
    () => [
      {
        key: 'row_index',
        label: '#',
        width: 48,
        align: 'center',
        isSticky: true,
        render: (_val, _row, _sel) => (
          <span className="text-[11px] font-mono text-gray-500 font-medium">
            {records.findIndex(r => r.id === _row.id) + 1}
          </span>
        ),
      },
      {
        key: 'customer',
        label: 'Customer',
        width: 140,
        align: 'left',
        render: val => <span className="font-semibold text-gray-900">{val || '—'}</span>,
      },
      {
        key: 'customer_code',
        label: 'Customer ID',
        width: 110,
        align: 'left',
        render: val => <span className="font-mono text-xs font-semibold text-gray-700">{val || '—'}</span>,
      },
      {
        key: 'customer_group',
        label: 'Group',
        width: 110,
        align: 'left',
        render: val => val ? (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-gray-100 text-gray-700 border border-gray-200">
            {val}
          </span>
        ) : <span className="text-gray-400">—</span>,
      },
      {
        key: 'plant',
        label: 'Plant',
        width: 100,
        align: 'left',
      },
      {
        key: 'product_code',
        label: 'Product / Part No.',
        width: 150,
        align: 'left',
        render: val => <span className="font-mono font-semibold text-blue-900">{val}</span>,
      },
      {
        key: 'description',
        label: 'Description',
        width: 220,
        align: 'left',
      },
      {
        key: 'planned_quantity',
        label: 'Plan Qty',
        width: 110,
        align: 'right',
        render: val => <span className="font-mono font-bold text-gray-900">{val}</span>,
      },
      {
        key: 'uom',
        label: 'Unit',
        width: 80,
        align: 'center',
      },
      {
        key: 'target_period',
        label: 'Month / Date',
        width: 110,
        align: 'center',
        render: val => <span className="font-mono text-gray-700">{val}</span>,
      },
      {
        key: 'planning_version',
        label: 'Revision',
        width: 90,
        align: 'center',
        render: val => (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
            {val}
          </span>
        ),
      },
      {
        key: 'section_type',
        label: 'Section',
        width: 100,
        align: 'center',
        render: val => val === 'JOB_WORK' ? (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-100 text-purple-800 border border-purple-200">
            Job Work
          </span>
        ) : (
          <span className="text-[10px] text-gray-500 font-medium">Standard</span>
        ),
      },
      {
        key: 'status',
        label: 'Status',
        width: 100,
        align: 'center',
        render: val => {
          let badge = 'bg-gray-100 text-gray-700 border-gray-300';
          if (val === 'VALIDATED' || val === 'CONFIRMED' || val === 'ACTIVE') badge = 'bg-emerald-50 text-emerald-800 border-emerald-300';
          if (val === 'DRAFT') badge = 'bg-amber-50 text-amber-800 border-amber-300';
          return (
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wide border ${badge}`}>
              {val}
            </span>
          );
        },
      },
      {
        key: 'remarks',
        label: 'Remarks',
        width: 160,
        align: 'left',
      },
    ],
    [records]
  );

  return (
    <div className="flex flex-col h-full space-y-2.5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 bg-white px-3.5 py-2.5 rounded-lg border border-gray-200 shadow-2xs flex-shrink-0">
        <div>
          <h1 className="text-base font-bold text-gray-900 tracking-tight flex items-center gap-2">
            <span>Production for sale</span>
            <span className="text-[11px] font-normal text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded border border-gray-300">
              Sales Schedule
            </span>
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Production Order sales schedules by customer, part, revision, and planning month.
          </p>
        </div>

        {statusMessage && (
          <div
            className={`px-3 py-1 rounded text-xs font-medium border flex items-center gap-1.5 ${
              statusMessage.type === 'success'
                ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                : statusMessage.type === 'error'
                ? 'bg-red-50 text-red-800 border-red-200'
                : 'bg-blue-50 text-blue-800 border-blue-200'
            }`}
          >
            <span>{statusMessage.type === 'success' ? '✓' : '⚠️'}</span>
            <span>{statusMessage.text}</span>
            <button
              onClick={() => setStatusMessage(null)}
              className="ml-2 text-gray-400 hover:text-gray-600 font-bold"
            >
              ×
            </button>
          </div>
        )}
      </div>

      {/* Per-Customer Summary Strip */}
      {customerSummaries.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 px-3 py-1.5 bg-white rounded-lg border border-gray-200 shadow-2xs text-xs flex-shrink-0">
          <span className="font-bold text-gray-700 text-[11px] uppercase tracking-wider flex items-center gap-1 mr-1">
            <span>🏢</span> Customers ({customerSummaries.length}):
          </span>
          {customerSummaries.map(([custName, stats]) => (
            <span
              key={custName}
              onClick={() => setCustomerFilter(customerFilter === custName ? '' : custName)}
              title={`Click to filter by ${custName}`}
              className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium border cursor-pointer transition-colors ${
                customerFilter === custName
                  ? 'bg-blue-100 text-blue-900 border-blue-400 font-bold shadow-xs'
                  : 'bg-gray-50 hover:bg-gray-100 text-gray-700 border-gray-200'
              }`}
            >
              <span>{custName}</span>
              <span className="font-mono font-bold text-gray-900">
                {stats.count} parts ({stats.totalQty.toLocaleString(undefined, { maximumFractionDigits: 1 })} Nos)
              </span>
            </span>
          ))}
          {customerFilter && (
            <button
              type="button"
              onClick={() => setCustomerFilter('')}
              className="text-[11px] text-blue-600 hover:underline font-semibold ml-1"
            >
              Clear filter
            </button>
          )}
        </div>
      )}

      {/* Workspace Panel */}
      <div className="flex-1 min-h-0 bg-white border border-gray-300 rounded shadow-xs flex flex-col overflow-hidden">
        {/* Toolbar */}
        <Toolbar
          onUpload={() => setShowUploadModal(true)}
          onAddRow={handleAddRow}
          onSave={handleSave}
          onDeleteSelected={() => setShowDeleteConfirm(true)}
          onExport={handleExport}
          canImport={canImport}
          canCreate={canCreate}
          canUpdate={canUpdate}
          canDelete={canDelete}
          canExport={canExport}
          isSaving={isSaving}
          unsavedCount={unsavedCount}
          selectedCount={selectedRowIds.size}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          searchPlaceholder="🔍 Search part, customer, group..."
          filters={[
            {
              key: 'customer',
              label: 'Customer',
              value: customerFilter,
              onChange: setCustomerFilter,
              options: [
                { value: '', label: 'All Customers' },
                ...uniqueCustomers.map(c => ({ value: c, label: c })),
              ],
            },
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
              key: 'period',
              label: 'Month',
              value: periodFilter,
              onChange: setPeriodFilter,
              options: [
                { value: '', label: 'All Months' },
                ...uniquePeriods.map(p => ({ value: p, label: p })),
              ],
            },
            {
              key: 'version',
              label: 'Revision',
              value: versionFilter,
              onChange: setVersionFilter,
              options: [
                { value: '', label: 'All Revisions' },
                ...uniqueVersions.map(v => ({ value: v, label: v })),
              ],
            },
            {
              key: 'status',
              label: 'Status',
              value: statusFilter,
              onChange: setStatusFilter,
              options: [
                { value: '', label: 'All Statuses' },
                { value: 'DRAFT', label: 'DRAFT' },
                { value: 'SAVED', label: 'SAVED' },
                { value: 'VALIDATED', label: 'VALIDATED' },
              ],
            },
          ]}
        />

        {/* Excel Data Grid with Resizable Height and Section 9A presets */}
        <div className="flex-1 min-h-0">
          <DataTable
            columns={columns}
            data={filteredRecords}
            originalData={originalMap}
            selectedIds={selectedRowIds}
            onSelectionChange={setSelectedRowIds}
            onCellChange={handleCellChange}
            isLoading={isLoading}
            emptyMessage="No production records found. Click 'Upload Excel' to import a Sales Schedule or 'Add Row' to start."
            onAddRow={handleAddRow}
            canCreate={canCreate}
            selectedCell={selectedCell}
            onSelectCell={setSelectedCell}
            storageKey="knl_prd_planning_grid"
            onSave={handleSave}
            onDeleteRows={handleDeleteSelected}
          />
        </div>
      </div>

      {/* Multi-Step Sales Schedule Import Modal */}
      <SalesScheduleImportModal
        isOpen={showUploadModal}
        onClose={() => setShowUploadModal(false)}
        onImportSuccess={(count, sheetName) => {
          setStatusMessage({
            type: 'success',
            text: `Successfully imported ${count} sales schedule parts from "${sheetName}".`,
          });
          void loadRecords();
        }}
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        title="Confirm Row Deletion"
        message={`Are you sure you want to delete ${
          selectedRowIds.size === 1 ? 'this row' : `${selectedRowIds.size} selected rows`
        }? This operation cannot be undone.`}
        confirmLabel="Delete"
        isDestructive={true}
        isLoading={isSaving}
        onConfirm={handleDeleteSelected}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </div>
  );
}
