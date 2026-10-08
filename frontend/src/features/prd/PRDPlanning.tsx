import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../auth/context';
import { canPerform } from '../../core/rbac';
import DataTable, { type ColumnDef } from '../../components/DataTable';
import Toolbar from '../../components/Toolbar';
import ExcelUploadModal, { type InspectResult } from '../../components/ExcelUploadModal';
import ConfirmDialog from '../../components/ConfirmDialog';

export interface PRDRecord {
  id: string;
  row_index: number | null;
  plant: string;
  customer: string | null;
  product_code: string;
  description: string;
  planned_quantity: string;
  uom: string;
  target_period: string;
  planning_version: string;
  status: string;
  remarks: string | null;
  is_new?: boolean;
}

export default function PRDPlanning() {
  const { user } = useAuth();

  // RBAC checks
  const canRead = canPerform(user, 'prd', 'read');
  const canCreate = canPerform(user, 'prd', 'create') || !!user?.permissions.includes('prd.plan.create');
  const canUpdate = canPerform(user, 'prd', 'update') || !!user?.permissions.includes('prd.plan.update');
  const canDelete = canPerform(user, 'prd', 'delete') || !!user?.permissions.includes('prd.plan.delete');
  const canImport = canPerform(user, 'prd', 'import') || !!user?.permissions.includes('prd.plan.import');
  const canExport = canPerform(user, 'prd', 'export') || canRead;

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
  const [periodFilter, setPeriodFilter] = useState('');
  const [versionFilter, setVersionFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [importPeriod, setImportPeriod] = useState('');
  const [importRevision, setImportRevision] = useState('');

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
  }, [searchQuery, plantFilter, periodFilter, versionFilter, statusFilter]);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  // Unique options for filters
  const uniquePlants = useMemo(() => {
    const set = new Set<string>();
    records.forEach(r => { if (r.plant) set.add(r.plant); });
    return Array.from(set).sort();
  }, [records]);

  const uniquePeriods = useMemo(() => {
    const set = new Set<string>();
    records.forEach(r => { if (r.target_period) set.add(r.target_period); });
    return Array.from(set).sort();
  }, [records]);

  const uniqueVersions = useMemo(() => {
    const set = new Set<string>();
    records.forEach(r => { if (r.planning_version) set.add(r.planning_version); });
    return Array.from(set).sort();
  }, [records]);

  // Filtered records
  const filteredRecords = useMemo(() => {
    return records.filter(r => {
      if (plantFilter && r.plant !== plantFilter) return false;
      if (periodFilter && r.target_period !== periodFilter) return false;
      if (versionFilter && r.planning_version !== versionFilter) return false;
      if (statusFilter && r.status !== statusFilter) return false;
      if (!searchQuery) return true;
      const q = searchQuery.toLowerCase();
      return (
        r.product_code.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        (r.customer && r.customer.toLowerCase().includes(q)) ||
        r.plant.toLowerCase().includes(q) ||
        (r.remarks && r.remarks.toLowerCase().includes(q))
      );
    });
  }, [records, plantFilter, periodFilter, versionFilter, statusFilter, searchQuery]);

  // Unsaved changes count
  const unsavedCount = useMemo(() => {
    let count = deletedIds.length;
    records.forEach(r => {
      const orig = originalMap.get(r.id);
      if (!orig) {
        count++;
      } else {
        const keys: (keyof PRDRecord)[] = [
          'plant', 'customer', 'product_code', 'description', 'planned_quantity',
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
      customer: 'Default Customer',
      product_code: 'NEW-PART-01',
      description: 'New Planned Product',
      planned_quantity: '100.0000',
      uom: 'Nos',
      target_period: periodFilter || new Date().toISOString().slice(0, 7),
      planning_version: versionFilter || 'V1',
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
        product_code: r.product_code,
        description: r.description,
        planned_quantity: r.planned_quantity,
        uom: r.uom,
        target_period: r.target_period,
        planning_version: r.planning_version,
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
        text: `Saved ${res.saved_count} records successfully${res.deleted_count > 0 ? ` (${res.deleted_count} deleted)` : ''}.`,
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

  // Bulk Delete
  const handleDeleteSelected = async () => {
    const toDelete = Array.from(selectedRowIds);
    if (toDelete.length === 0) return;

    setIsSaving(true);
    try {
      const persistedIds = toDelete.filter(id => !id.startsWith('new-'));
      if (persistedIds.length > 0) {
        await apiClient.post<{ deleted_count: number }>('/api/v1/prd/workspace/bulk-delete', {
          ids: persistedIds,
          reason: 'Deleted from PRD workspace',
        });
      }

      setRecords(prev => prev.filter(r => !selectedRowIds.has(r.id)));
      setSelectedRowIds(new Set());
      setSelectedCell(null);
      setShowDeleteConfirm(false);
      setStatusMessage({
        type: 'success',
        text: `Successfully deleted ${toDelete.length} record(s).`,
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

  // Excel Inspect
  const handleInspect = async (file: File): Promise<InspectResult> => {
    const form = new FormData();
    form.append('file', file);
    return await apiClient.post<InspectResult>('/api/v1/prd/workspace/inspect', form);
  };

  // Excel Import
  const handleImport = async (file: File, sheetName: string) => {
    const form = new FormData();
    form.append('file', file);
    form.append('sheet_name', sheetName);
    if (importPeriod) form.append('target_period', importPeriod);
    if (importRevision.trim()) form.append('revision_label', importRevision.trim());

    const res = await apiClient.post<{
      sheet_name: string;
      imported_count: number;
      records: PRDRecord[];
    }>('/api/v1/prd/workspace/import-sheet', form);

    setRecords(res.records);
    const nextMap = new Map<string, PRDRecord>();
    res.records.forEach(r => nextMap.set(r.id, { ...r }));
    setOriginalMap(nextMap);
    setDeletedIds([]);
    setSelectedRowIds(new Set());
    setShowUploadModal(false);

    setStatusMessage({
      type: 'success',
      text: `Successfully imported ${res.imported_count} rows from "${sheetName}".`,
    });
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
      if (periodFilter) params.append('target_period', periodFilter);
      if (versionFilter) params.append('planning_version', versionFilter);
      if (statusFilter) params.append('status', statusFilter);
    }

    const queryString = params.toString();
    if (queryString) url += `?${queryString}`;
    window.open(url, '_blank');
  };

  // Columns definition
  const columns: ColumnDef<PRDRecord>[] = useMemo(
    () => [
      {
        key: 'row_index',
        label: '#',
        width: 'w-14',
        align: 'center',
        isSticky: true,
        render: (_val, _row, _sel) => (
          <span className="text-[11px] font-mono text-gray-500 font-medium">
            {records.findIndex(r => r.id === _row.id) + 1}
          </span>
        ),
      },
      {
        key: 'plant',
        label: 'Plant',
        width: 'w-28',
        align: 'left',
        isSticky: true,
      },
      {
        key: 'customer',
        label: 'Customer',
        width: 'w-36',
        align: 'left',
      },
      {
        key: 'product_code',
        label: 'Product / Part No.',
        width: 'w-36',
        align: 'left',
        render: val => <span className="font-mono font-semibold text-blue-900">{val}</span>,
      },
      {
        key: 'description',
        label: 'Description',
        width: 'w-60',
        align: 'left',
      },
      {
        key: 'planned_quantity',
        label: 'Plan Qty',
        width: 'w-28',
        align: 'right',
        render: val => <span className="font-mono font-bold text-gray-900">{val}</span>,
      },
      {
        key: 'uom',
        label: 'Unit',
        width: 'w-20',
        align: 'center',
      },
      {
        key: 'target_period',
        label: 'Month / Date',
        width: 'w-28',
        align: 'center',
        render: val => <span className="font-mono text-gray-700">{val}</span>,
      },
      {
        key: 'planning_version',
        label: 'Version',
        width: 'w-24',
        align: 'center',
        render: val => (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
            {val}
          </span>
        ),
      },
      {
        key: 'status',
        label: 'Status',
        width: 'w-28',
        align: 'center',
        render: val => {
          let badge = 'bg-gray-100 text-gray-700 border-gray-300';
          if (val === 'CONFIRMED' || val === 'ACTIVE') badge = 'bg-emerald-50 text-emerald-800 border-emerald-300';
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
        width: 'w-56',
        align: 'left',
      },
    ],
    [records]
  );

  return (
    <div className="flex flex-col h-full space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 tracking-tight">PRD / Planning Workspace</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Excel-style production plan editor with multi-row selection, bulk operations, and real-time syncing.
          </p>
        </div>
        {statusMessage && (
          <div
            className={`px-3 py-1.5 rounded text-xs font-medium border flex items-center gap-1.5 ${
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
          searchPlaceholder="🔍 Search plan, part, customer..."
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
              label: 'Version',
              value: versionFilter,
              onChange: setVersionFilter,
              options: [
                { value: '', label: 'All Versions' },
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
                { value: 'CONFIRMED', label: 'CONFIRMED' },
              ],
            },
          ]}
        />

        {/* Excel Data Grid */}
        <div className="flex-1 min-h-0">
          <DataTable
            columns={columns}
            data={filteredRecords}
            originalData={originalMap}
            selectedIds={selectedRowIds}
            onSelectionChange={setSelectedRowIds}
            onCellChange={handleCellChange}
            isLoading={isLoading}
            emptyMessage="No PRD records found. Click 'Add Row' or 'Upload Excel' to start planning."
            onAddRow={handleAddRow}
            canCreate={canCreate}
            selectedCell={selectedCell}
            onSelectCell={setSelectedCell}
          />
        </div>
      </div>

      {/* Modals */}
      <ExcelUploadModal
        isOpen={showUploadModal}
        title="Import PRD Planning Excel"
        subtitle="Select or drag a PRD Excel file (.xlsx) with production plan rows."
        onClose={() => setShowUploadModal(false)}
        onInspect={handleInspect}
        onImport={handleImport}
        isLoading={isSaving}
      >
        <div className="flex gap-3 border p-3">
          <label>Planning month <input type="month" value={importPeriod} onChange={e => setImportPeriod(e.target.value)} /></label>
          <label>Revision (blank selects latest for this month) <input value={importRevision} placeholder="R3" onChange={e => setImportRevision(e.target.value)} /></label>
        </div>
        <p>Review products and plant mappings first. Imports preserve revision history and do not approve requirements.</p>
      </ExcelUploadModal>

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
