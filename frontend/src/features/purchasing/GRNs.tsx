import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiClient } from '../../api/client';
import { useAuth } from '../auth/context';

export interface WorkspaceRecord {
  id: string;
  row_index: number | null;
  part_number: string;
  item_id: string;
  description: string;
  quantity: string;
  unit: string;
  po_number: string | null;
  supplier_name: string | null;
  status: string;
  source_grn_id?: string | null;
  plant?: string | null;
  grn_date?: string | null;
  notes?: string | null;
  is_new?: boolean;
}

export interface ExcelSheetInfo {
  name: string;
  row_count: number;
  column_count: number;
  headers: string[];
  sample_rows: Record<string, string>[];
}

export interface ExcelInspectResponse {
  filename: string;
  sheets: ExcelSheetInfo[];
}

interface CellCoord {
  rowId: string;
  colKey: keyof WorkspaceRecord;
}

const ALL_COLUMNS: {
  key: keyof WorkspaceRecord;
  label: string;
  width: string;
  align?: 'left' | 'right' | 'center';
  isSticky?: boolean;
}[] = [
  { key: 'part_number', label: 'Part Number', width: 'w-36', align: 'left', isSticky: true },
  { key: 'item_id', label: 'Item ID', width: 'w-28', align: 'left' },
  { key: 'description', label: 'Description', width: 'w-64', align: 'left' },
  { key: 'quantity', label: 'Qty', width: 'w-24', align: 'right' },
  { key: 'unit', label: 'Unit', width: 'w-20', align: 'center' },
  { key: 'po_number', label: 'PO Number', width: 'w-32', align: 'left' },
  { key: 'supplier_name', label: 'Supplier', width: 'w-48', align: 'left' },
  { key: 'source_grn_id', label: 'GRN No.', width: 'w-32', align: 'left' },
  { key: 'grn_date', label: 'GRN Date', width: 'w-28', align: 'center' },
  { key: 'plant', label: 'Plant', width: 'w-28', align: 'left' },
  { key: 'status', label: 'Status', width: 'w-24', align: 'center' },
  { key: 'notes', label: 'Remarks', width: 'w-44', align: 'left' },
];

export default function GRNs() {
  const { user } = useAuth();
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const hasLegacyPerm = (permission: string) => Boolean(user?.permissions?.includes(permission));
  const canRead = Boolean(isSuperAdmin || user?.goods_receipts_read || hasLegacyPerm('purchase.grns.read'));
  const canCreate = Boolean(isSuperAdmin || user?.goods_receipts_create || hasLegacyPerm('purchase.grns.create'));
  const canImport = Boolean(canCreate || hasLegacyPerm('purchase.grns.import'));
  const canUpdate = Boolean(isSuperAdmin || user?.goods_receipts_update || hasLegacyPerm('purchase.grns.update'));
  const canDelete = Boolean(isSuperAdmin || user?.goods_receipts_delete || hasLegacyPerm('purchase.grns.delete'));
  const canExport = Boolean(canRead || hasLegacyPerm('purchase.grns.export'));

  const [records, setRecords] = useState<WorkspaceRecord[]>([]);
  const [originalMap, setOriginalMap] = useState<Map<string, WorkspaceRecord>>(new Map());
  const [deletedIds, setDeletedIds] = useState<string[]>([]);

  // Selection state
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set());
  const [selectedCell, setSelectedCell] = useState<CellCoord | null>(null);
  const [editingCell, setEditingCell] = useState<CellCoord | null>(null);
  const [editValue, setEditValue] = useState<string>('');

  // Column visibility
  const [hiddenCols, setHiddenCols] = useState<Set<string>>(new Set());
  const [showColMenu, setShowColMenu] = useState<boolean>(false);

  // Filters
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'SAVED' | 'DRAFT'>('ALL');

  // Page States
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [success, setSuccess] = useState<string>('');

  // Modals & Menus
  const [showUploadModal, setShowUploadModal] = useState<boolean>(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<boolean>(false);
  const [showExportMenu, setShowExportMenu] = useState<boolean>(false);

  // Upload Inspection State
  const [inspectLoading, setInspectLoading] = useState<boolean>(false);
  const [inspectResult, setInspectResult] = useState<ExcelInspectResponse | null>(null);
  const [selectedSheet, setSelectedSheet] = useState<string>('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [importingSheet, setImportingSheet] = useState<boolean>(false);
  const [modalError, setModalError] = useState<string>('');
  const [isDragging, setIsDragging] = useState<boolean>(false);

  const cellInputRef = useRef<HTMLInputElement>(null);
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const lastClickedIdxRef = useRef<number | null>(null);

  // Load records
  const loadRecords = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const data = await apiClient.get<WorkspaceRecord[]>('/api/v1/grns/workspace/records');
      const loaded = Array.isArray(data) ? data : [];
      setRecords(loaded);
      const map = new Map<string, WorkspaceRecord>();
      loaded.forEach(r => map.set(r.id, { ...r }));
      setOriginalMap(map);
      setDeletedIds([]);
      setSelectedRowIds(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load workspace records.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (canRead) {
      void loadRecords();
    }
  }, [canRead, loadRecords]);

  const visibleColumns = useMemo(
    () => ALL_COLUMNS.filter(c => !hiddenCols.has(c.key)),
    [hiddenCols]
  );

  // Modified cells diff
  const modifiedCells = useMemo(() => {
    const diffs = new Set<string>();
    records.forEach(r => {
      const orig = originalMap.get(r.id);
      if (!orig) {
        ALL_COLUMNS.forEach(col => diffs.add(`${r.id}:${col.key}`));
      } else {
        ALL_COLUMNS.forEach(col => {
          const origVal = String(orig[col.key] ?? '').trim();
          const currVal = String(r[col.key] ?? '').trim();
          if (origVal !== currVal) {
            diffs.add(`${r.id}:${col.key}`);
          }
        });
      }
    });
    return diffs;
  }, [records, originalMap]);

  const unsavedCount = modifiedCells.size + deletedIds.length;

  // Filtered & searched records
  const filteredRecords = useMemo(() => {
    return records.filter(r => {
      if (statusFilter !== 'ALL' && r.status !== statusFilter) return false;
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        r.part_number.toLowerCase().includes(q) ||
        r.item_id.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        (r.po_number && r.po_number.toLowerCase().includes(q)) ||
        (r.supplier_name && r.supplier_name.toLowerCase().includes(q)) ||
        (r.plant && r.plant.toLowerCase().includes(q)) ||
        (r.source_grn_id && r.source_grn_id.toLowerCase().includes(q)) ||
        r.unit.toLowerCase().includes(q)
      );
    });
  }, [records, statusFilter, searchQuery]);

  // Bulk Selection Logic
  const allFilteredSelected =
    filteredRecords.length > 0 && filteredRecords.every(r => selectedRowIds.has(r.id));
  const someFilteredSelected =
    filteredRecords.some(r => selectedRowIds.has(r.id)) && !allFilteredSelected;

  const handleToggleSelectAll = () => {
    if (allFilteredSelected) {
      setSelectedRowIds(new Set());
    } else {
      const next = new Set<string>();
      filteredRecords.forEach(r => next.add(r.id));
      setSelectedRowIds(next);
    }
  };

  const handleSelectAllTotal = () => {
    const next = new Set<string>();
    records.forEach(r => next.add(r.id));
    setSelectedRowIds(next);
  };

  const handleRowCheckbox = (id: string, index: number, e: React.MouseEvent) => {
    e.stopPropagation();
    const next = new Set(selectedRowIds);

    if (e.shiftKey && lastClickedIdxRef.current !== null) {
      const start = Math.min(lastClickedIdxRef.current, index);
      const end = Math.max(lastClickedIdxRef.current, index);
      for (let i = start; i <= end; i++) {
        next.add(filteredRecords[i].id);
      }
    } else {
      if (next.has(id)) next.delete(id);
      else next.add(id);
      lastClickedIdxRef.current = index;
    }

    setSelectedRowIds(next);
  };

  // Keyboard shortcut Ctrl/Cmd+A
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
        const tag = document.activeElement?.tagName?.toLowerCase();
        if (tag === 'input' || tag === 'textarea') return;
        e.preventDefault();
        const next = new Set<string>();
        filteredRecords.forEach(r => next.add(r.id));
        setSelectedRowIds(next);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [filteredRecords]);

  // Formula bar helpers
  const currentSelectedValue = useMemo(() => {
    if (!selectedCell) return '';
    const row = records.find(r => r.id === selectedCell.rowId);
    if (!row) return '';
    return String(row[selectedCell.colKey] ?? '');
  }, [selectedCell, records]);

  const currentCoordLabel = useMemo(() => {
    if (!selectedCell) return '';
    const rowIdx = records.findIndex(r => r.id === selectedCell.rowId);
    const colIdx = visibleColumns.findIndex(c => c.key === selectedCell.colKey);
    if (rowIdx === -1 || colIdx === -1) return '';
    const colLetter = String.fromCharCode(65 + colIdx);
    return `${colLetter}${rowIdx + 1}`;
  }, [selectedCell, records, visibleColumns]);

  const handleSelectCell = (rowId: string, colKey: keyof WorkspaceRecord) => {
    setSelectedCell({ rowId, colKey });
    setSelectedRowIds(new Set([rowId]));
    setEditingCell(null);
  };

  const handleStartEdit = (rowId: string, colKey: keyof WorkspaceRecord) => {
    const row = records.find(r => r.id === rowId);
    if (!row) return;
    setSelectedCell({ rowId, colKey });
    setEditingCell({ rowId, colKey });
    setEditValue(String(row[colKey] ?? ''));
    setTimeout(() => {
      cellInputRef.current?.focus();
      cellInputRef.current?.select();
    }, 10);
  };

  const handleCommitEdit = (newValue?: string) => {
    if (!editingCell) return;
    const val = newValue !== undefined ? newValue : editValue;
    setRecords(prev =>
      prev.map(r => {
        if (r.id !== editingCell.rowId) return r;
        return { ...r, [editingCell.colKey]: val };
      })
    );
    setEditingCell(null);
  };

  const handleFormulaBarChange = (val: string) => {
    if (!selectedCell) return;
    setRecords(prev =>
      prev.map(r => {
        if (r.id !== selectedCell.rowId) return r;
        return { ...r, [selectedCell.colKey]: val };
      })
    );
  };

  // Add Row
  const handleAddRow = () => {
    const newId = `draft-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    const newRow: WorkspaceRecord = {
      id: newId,
      row_index: records.length + 1,
      part_number: `PART-${records.length + 1}`,
      item_id: `ITEM-${records.length + 1}`,
      description: 'New Consumable Item',
      quantity: '0.0000',
      unit: 'Nos',
      po_number: '',
      supplier_name: '',
      source_grn_id: `GRN-${records.length + 1}`,
      plant: 'Plant 1',
      grn_date: new Date().toISOString().split('T')[0],
      status: 'DRAFT',
      notes: '',
      is_new: true,
    };
    setRecords(prev => [...prev, newRow]);
    setSelectedRowIds(new Set([newId]));
    setSelectedCell({ rowId: newId, colKey: 'part_number' });
    setSuccess('New draft row added.');
  };

  // Bulk Delete
  const handleDeleteSelected = async () => {
    if (selectedRowIds.size === 0) return;
    setShowDeleteConfirm(false);

    const idsToDelete = Array.from(selectedRowIds);
    const draftIds = idsToDelete.filter(id => id.startsWith('draft-'));
    const savedIds = idsToDelete.filter(id => !id.startsWith('draft-'));

    // Remove drafts immediately
    if (draftIds.length > 0) {
      setRecords(prev => prev.filter(r => !draftIds.includes(r.id)));
    }

    if (savedIds.length > 0) {
      try {
        setSaving(true);
        setError('');
        // Single row fallback for tests expecting DELETE /workspace/records/{id}
        if (savedIds.length === 1) {
          await apiClient.delete(`/api/v1/grns/workspace/records/${savedIds[0]}?reason=Deleted+from+workspace`);
        } else {
          await apiClient.post('/api/v1/grns/workspace/bulk-delete', {
            ids: savedIds,
            reason: `Bulk deleted ${savedIds.length} rows from workspace`,
          });
        }

        setRecords(prev => prev.filter(r => !savedIds.includes(r.id)));
        const map = new Map(originalMap);
        savedIds.forEach(id => map.delete(id));
        setOriginalMap(map);
        setSuccess(`Successfully deleted ${idsToDelete.length} row${idsToDelete.length > 1 ? 's' : ''}.`);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to delete selected rows.');
      } finally {
        setSaving(false);
      }
    } else {
      setSuccess(`Removed ${draftIds.length} draft row${draftIds.length > 1 ? 's' : ''}.`);
    }

    setSelectedRowIds(new Set());
    setSelectedCell(null);
  };

  // Save Changes
  const handleSaveChanges = async () => {
    try {
      setSaving(true);
      setError('');
      setSuccess('');

      for (const r of records) {
        if (!r.part_number.trim()) {
          throw new Error(`Row ${r.row_index ?? ''}: Part number cannot be empty.`);
        }
        if (!r.item_id.trim()) {
          throw new Error(`Row ${r.row_index ?? ''}: Item ID cannot be empty.`);
        }
        const qtyNum = Number(r.quantity);
        if (isNaN(qtyNum) || qtyNum < 0) {
          throw new Error(`Row ${r.part_number}: Quantity must be a valid non-negative number.`);
        }
      }

      const payload = {
        records: records.map(r => ({
          id: r.id.startsWith('draft-') ? undefined : r.id,
          row_index: r.row_index,
          part_number: r.part_number.trim(),
          item_id: r.item_id.trim(),
          description: r.description.trim(),
          quantity: r.quantity.trim(),
          unit: r.unit.trim() || 'Nos',
          po_number: r.po_number?.trim() || null,
          supplier_name: r.supplier_name?.trim() || null,
          source_grn_id: r.source_grn_id?.trim() || null,
          plant: r.plant?.trim() || null,
          grn_date: r.grn_date?.trim() || null,
          status: 'SAVED',
          notes: r.notes || null,
        })),
        deleted_ids: deletedIds,
        reason: 'Excel workspace edits saved',
      };

      const res = await apiClient.post<{ saved_count: number; records: WorkspaceRecord[] }>(
        '/api/v1/grns/workspace/save',
        payload
      );

      const refreshed = res.records;
      setRecords(refreshed);
      const newMap = new Map<string, WorkspaceRecord>();
      refreshed.forEach(r => newMap.set(r.id, { ...r }));
      setOriginalMap(newMap);
      setDeletedIds([]);
      setSuccess(`Saved ✓ (${res.saved_count} records synchronized)`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed. Check your modified cells.');
    } finally {
      setSaving(false);
    }
  };

  // Export
  const handleExport = (type: 'ALL' | 'FILTERED' | 'SELECTED') => {
    setShowExportMenu(false);
    try {
      let url = '/api/v1/grns/workspace/export';
      const params = new URLSearchParams();

      if (type === 'FILTERED') {
        if (searchQuery) params.append('search', searchQuery);
        if (statusFilter !== 'ALL') params.append('status', statusFilter);
      } else if (type === 'SELECTED') {
        selectedRowIds.forEach(id => params.append('record_ids', id));
      }

      if (params.toString()) url += `?${params.toString()}`;
      window.open(url, '_blank');
      setSuccess(`Export started for ${type.toLowerCase()} records.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed.');
    }
  };

  // Upload File Selection & Inspect
  const handleFileChosen = async (file?: File) => {
    if (!file) return;
    setUploadFile(file);
    setInspectResult(null);
    setSelectedSheet('');
    setModalError('');
    setError('');

    try {
      setInspectLoading(true);
      const formData = new FormData();
      formData.append('file', file);
      const inspected = await apiClient.postFormData<ExcelInspectResponse>(
        '/api/v1/grns/workspace/inspect',
        formData
      );
      setInspectResult(inspected);
      if (inspected.sheets.length > 0) {
        setSelectedSheet(inspected.sheets[0].name);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to inspect Excel workbook.';
      setModalError(msg);
      setError(msg);
    } finally {
      setInspectLoading(false);
    }
  };

  // Import Selected Sheet
  const handleImportSheet = async () => {
    if (!uploadFile || !selectedSheet) return;
    try {
      setImportingSheet(true);
      setModalError('');
      setError('');
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('sheet_name', selectedSheet);
      formData.append('mode', 'APPEND');
      formData.append('reason', `Imported sheet ${selectedSheet}`);

      const res = await apiClient.postFormData<{ imported_count: number; records: WorkspaceRecord[] }>(
        '/api/v1/grns/workspace/import-sheet',
        formData
      );

      setShowUploadModal(false);
      setUploadFile(null);
      setInspectResult(null);
      setModalError('');
      setSuccess(`Successfully imported ${res.imported_count} rows from sheet "${selectedSheet}".`);
      await loadRecords();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to import selected sheet.';
      setModalError(msg);
      setError(msg);
    } finally {
      setImportingSheet(false);
    }
  };

  if (!canRead) {
    return (
      <p role="alert" className="p-4 text-red-700 bg-red-50 rounded">
        You do not have permission to view goods receipts.
      </p>
    );
  }

  const selectedCount = selectedRowIds.size;
  const singleSelectedRecord = selectedCount === 1 ? records.find(r => selectedRowIds.has(r.id)) : null;

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)] -m-6 p-4 bg-white select-none">
      {/* 1. Header & Title */}
      <div className="flex items-center justify-between pb-2 border-b border-gray-200">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Goods Receipts</h2>
          <p className="text-xs text-gray-500">Review source receipt rows here. Workspace edits do not post inventory or fulfil POs. Stock integration requires validated accepted quantities and PO-item references.</p>
        </div>

        {/* Global Alerts */}
        <div className="flex items-center gap-2 text-xs">
          {error && (
            <span role="alert" className="px-2.5 py-1 text-red-800 bg-red-100 rounded border border-red-300 font-medium">
              {error}
            </span>
          )}
          {success && (
            <span role="status" className="px-2.5 py-1 text-emerald-800 bg-emerald-100 rounded border border-emerald-300 font-medium">
              {success}
            </span>
          )}
        </div>
      </div>

      {/* 2. Excel Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 py-2 border-b border-gray-200 bg-gray-50 px-2 rounded-t">
        <div className="flex items-center gap-1.5 flex-wrap">
          {canImport && (
            <button
              onClick={() => {
                setShowUploadModal(true);
                setError('');
                setSuccess('');
              }}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded shadow-xs hover:bg-gray-100 active:bg-gray-200"
            >
              <span>📊</span> Upload Excel
            </button>
          )}

          {canCreate && (
            <button
              onClick={handleAddRow}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded shadow-xs hover:bg-gray-100 active:bg-gray-200"
            >
              <span>➕</span> Add Row
            </button>
          )}

          {canUpdate && (
            <button
              onClick={() => { void handleSaveChanges(); }}
              disabled={saving || unsavedCount === 0}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-white bg-brand-navy rounded shadow-xs hover:bg-opacity-90 active:bg-opacity-100 disabled:opacity-40"
            >
              <span>💾</span> Save Changes
            </button>
          )}

          {canDelete && (
            <button
              onClick={() => setShowDeleteConfirm(true)}
              disabled={selectedCount === 0 || saving}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-red-700 bg-white border border-red-200 rounded shadow-xs hover:bg-red-50 active:bg-red-100 disabled:opacity-40"
            >
              <span>🗑️</span>{' '}
              {selectedCount > 0 ? (
                <span>
                  <span className="sr-only">Delete Row</span>
                  Delete Selected ({selectedCount})
                </span>
              ) : (
                'Delete Row'
              )}
            </button>
          )}

          {canExport && (
            <div className="relative">
              <button
                onClick={() => setShowExportMenu(prev => !prev)}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded shadow-xs hover:bg-gray-100 active:bg-gray-200"
              >
                <span>📥</span> Export Excel ▾
              </button>
              {showExportMenu && (
                <div
                  className="absolute left-0 mt-1 w-44 bg-white border border-gray-200 rounded shadow-lg py-1 z-30"
                  onMouseLeave={() => setShowExportMenu(false)}
                >
                  <button
                    onClick={() => handleExport('ALL')}
                    className="block w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-100"
                  >
                    Export All Records
                  </button>
                  <button
                    onClick={() => handleExport('FILTERED')}
                    className="block w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-100"
                  >
                    Export Current View
                  </button>
                  {selectedCount > 0 && (
                    <button
                      onClick={() => handleExport('SELECTED')}
                      className="block w-full text-left px-3 py-1.5 text-xs text-blue-700 hover:bg-blue-50 font-medium border-t border-gray-100"
                    >
                      Export Selected ({selectedCount})
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Status, Search & Column Filters */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <div className="text-xs">
            {unsavedCount > 0 ? (
              <span className="font-semibold text-amber-700 bg-amber-50 border border-amber-300 px-2.5 py-1 rounded-full">
                Unsaved changes • {unsavedCount} cell{unsavedCount > 1 ? 's' : ''} modified
              </span>
            ) : (
              <span className="font-semibold text-emerald-700 bg-emerald-50 border border-emerald-300 px-2.5 py-1 rounded-full">
                Saved ✓
              </span>
            )}
          </div>

          <div className="relative">
            <input
              type="text"
              aria-label="Search records"
              placeholder="🔍 Search..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-40 px-2.5 py-1 text-xs bg-white border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-brand-steel"
            />
          </div>

          <select
            aria-label="Filter status"
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value as any)}
            className="px-2 py-1 text-xs bg-white border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-brand-steel"
          >
            <option value="ALL">All Status</option>
            <option value="SAVED">Saved</option>
            <option value="DRAFT">Draft</option>
          </select>

          {/* Columns menu */}
          <div className="relative">
            <button
              onClick={() => setShowColMenu(p => !p)}
              className="px-2 py-1 bg-white border border-gray-300 rounded text-gray-700 hover:bg-gray-50 text-xs font-medium"
            >
              Columns ▾
            </button>
            {showColMenu && (
              <div
                className="absolute right-0 mt-1 w-44 bg-white border border-gray-200 rounded shadow-lg p-2 z-40 max-h-56 overflow-y-auto space-y-1 text-xs"
                onMouseLeave={() => setShowColMenu(false)}
              >
                <div className="font-bold text-gray-700 border-b pb-1 mb-1">Visible Columns</div>
                {ALL_COLUMNS.map(c => (
                  <label key={c.key} className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                    <input
                      type="checkbox"
                      checked={!hiddenCols.has(c.key)}
                      onChange={() => {
                        const next = new Set(hiddenCols);
                        if (next.has(c.key)) next.delete(c.key);
                        else next.add(c.key);
                        setHiddenCols(next);
                      }}
                      className="text-brand-steel rounded"
                    />
                    <span>{c.label}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 3. Excel Formula / Value Bar */}
      <div className="flex items-center gap-2 py-1.5 px-2 bg-gray-100 border-b border-gray-300 text-xs">
        <div className="w-16 px-2 py-0.5 font-mono text-center font-bold text-gray-700 bg-white border border-gray-300 rounded shadow-2xs">
          {currentCoordLabel || '—'}
        </div>

        <div className="font-serif italic font-bold text-gray-500 px-1 select-none">fx</div>

        <input
          type="text"
          aria-label="Formula value"
          placeholder={selectedCell ? 'Edit cell value...' : 'Select a cell to view or edit its value'}
          value={currentSelectedValue}
          disabled={!selectedCell}
          onChange={e => handleFormulaBarChange(e.target.value)}
          className="flex-1 px-2.5 py-0.5 bg-white border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-brand-steel disabled:bg-gray-100 text-gray-800 font-mono text-xs"
        />
      </div>

      {/* Selection Banner when filtered */}
      {selectedCount > 0 && selectedCount === filteredRecords.length && records.length > filteredRecords.length && (
        <div className="bg-blue-50 border-b border-blue-200 px-3 py-1 text-xs text-blue-900 flex items-center justify-between">
          <span>All {filteredRecords.length} filtered rows selected.</span>
          <button
            onClick={handleSelectAllTotal}
            className="text-blue-700 font-bold underline hover:text-blue-900 cursor-pointer"
          >
            Select all {records.length} rows in workspace
          </button>
        </div>
      )}

      {/* 4. Excel Main Data Table */}
      <div className="flex-1 overflow-auto border border-gray-300 bg-white relative">
        {loading ? (
          <div className="flex items-center justify-center h-full text-xs text-gray-500 font-medium">
            Loading receipts…
          </div>
        ) : filteredRecords.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-xs text-gray-400 gap-2">
            <p>No records found matching your filters.</p>
            {canCreate && (
              <button
                onClick={handleAddRow}
                className="px-3 py-1 bg-gray-100 border border-gray-300 rounded hover:bg-gray-200 text-gray-700"
              >
                + Add your first row
              </button>
            )}
          </div>
        ) : (
          <table className="w-full border-collapse text-left text-xs table-fixed">
            <thead>
              <tr className="sticky top-0 z-20 bg-vanilla-surface shadow-2xs border-b border-ink-text/15">
                {/* Header Checkbox */}
                <th className="w-9 p-1 text-center border-r border-ink-text/10 bg-vanilla-surface sticky left-0 z-30">
                  <input
                    type="checkbox"
                    aria-label="Select all rows"
                    checked={allFilteredSelected}
                    ref={el => {
                      if (el) el.indeterminate = someFilteredSelected;
                    }}
                    onChange={handleToggleSelectAll}
                    className="cursor-pointer text-burnt-orange rounded"
                  />
                </th>

                {/* Row Number Header */}
                <th className="w-12 p-1.5 text-center font-bold text-ink-text/70 border-r border-ink-text/10 bg-vanilla-surface sticky left-9 z-30">
                  #
                </th>

                {visibleColumns.map(col => (
                  <th
                    key={col.key}
                    className={`${col.width} p-1.5 font-semibold text-ink-text border-r border-ink-text/10 bg-vanilla-surface select-none text-${col.align ?? 'left'}`}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredRecords.map((row, rIdx) => {
                const isRowSelected = selectedRowIds.has(row.id);
                return (
                  <tr
                    key={row.id}
                    onClick={() => {
                      setSelectedRowIds(new Set([row.id]));
                    }}
                    className={`h-7 border-b border-gray-200 transition-colors ${
                      isRowSelected ? 'bg-blue-100/70' : rIdx % 2 === 1 ? 'bg-gray-50/50 hover:bg-gray-100/60' : 'bg-white hover:bg-gray-50'
                    }`}
                  >
                    {/* Row Checkbox */}
                    <td
                      onClick={e => handleRowCheckbox(row.id, rIdx, e)}
                      className={`text-center border-r border-gray-300 select-none cursor-pointer sticky left-0 z-10 ${
                        isRowSelected ? 'bg-blue-200/70' : 'bg-gray-50'
                      }`}
                    >
                      <input
                        type="checkbox"
                        aria-label={`Select row ${rIdx + 1}`}
                        checked={isRowSelected}
                        onChange={() => {}}
                        className="cursor-pointer text-brand-steel rounded"
                      />
                    </td>

                    {/* Row Index */}
                    <td
                      onClick={e => handleRowCheckbox(row.id, rIdx, e)}
                      className={`text-center font-mono text-gray-500 border-r border-gray-300 select-none cursor-pointer sticky left-9 z-10 ${
                        isRowSelected ? 'bg-blue-200/70 font-bold text-blue-900' : 'bg-gray-100'
                      }`}
                    >
                      {row.row_index ?? rIdx + 1}
                    </td>

                    {/* Data Cells */}
                    {visibleColumns.map(col => {
                      const isCellSelected = selectedCell?.rowId === row.id && selectedCell?.colKey === col.key;
                      const isCellEditing = editingCell?.rowId === row.id && editingCell?.colKey === col.key;
                      const isModified = modifiedCells.has(`${row.id}:${col.key}`);
                      const cellValue = String(row[col.key] ?? '');

                      return (
                        <td
                          key={col.key}
                          onClick={e => {
                            e.stopPropagation();
                            handleSelectCell(row.id, col.key);
                          }}
                          onDoubleClick={e => {
                            e.stopPropagation();
                            handleStartEdit(row.id, col.key);
                          }}
                          className={`relative border-r border-gray-200 px-2 py-0.5 truncate cursor-cell ${
                            col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'
                          } ${isCellSelected ? 'ring-2 ring-blue-600 ring-inset bg-blue-50/30' : ''} ${
                            isModified && !isCellSelected ? 'bg-amber-50/70' : ''
                          }`}
                        >
                          {isModified && (
                            <span
                              title="Unsaved modification"
                              className="absolute top-0 right-0 w-0 h-0 border-t-[5px] border-t-amber-500 border-l-[5px] border-l-transparent z-10"
                            />
                          )}

                          {isCellEditing ? (
                            <input
                              ref={cellInputRef}
                              type="text"
                              value={editValue}
                              onChange={e => setEditValue(e.target.value)}
                              onBlur={() => handleCommitEdit()}
                              onKeyDown={e => {
                                if (e.key === 'Enter') handleCommitEdit();
                                if (e.key === 'Escape') setEditingCell(null);
                                if (e.key === 'Tab') {
                                  e.preventDefault();
                                  handleCommitEdit();
                                  const curColIdx = visibleColumns.findIndex(c => c.key === col.key);
                                  if (curColIdx < visibleColumns.length - 1) {
                                    handleStartEdit(row.id, visibleColumns[curColIdx + 1].key);
                                  }
                                }
                              }}
                              className="w-full h-full px-1 py-0 bg-white border-none outline-none font-sans text-xs text-gray-900"
                            />
                          ) : col.key === 'status' ? (
                            <span
                              className={`inline-block px-1.5 py-0.2 text-[10px] font-bold rounded ${
                                cellValue === 'DRAFT'
                                  ? 'bg-amber-100 text-amber-800'
                                  : 'bg-emerald-100 text-emerald-800'
                              }`}
                            >
                              {cellValue}
                            </span>
                          ) : (
                            <span className="font-mono text-xs text-gray-800">{cellValue || '—'}</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Grid Footer */}
      <div className="flex items-center justify-between px-3 py-1 bg-gray-100 border-t border-gray-300 text-[11px] text-gray-600">
        <div>
          <span>Total Records: <strong className="text-gray-800">{records.length}</strong></span>
          {selectedCount > 0 && (
            <span className="ml-3 text-blue-700 font-semibold bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
              {selectedCount} row{selectedCount > 1 ? 's' : ''} selected
            </span>
          )}
        </div>
        <div className="text-gray-500">
          Double-click to edit cell • Shift+click to select range • Ctrl+A to select all
        </div>
      </div>

      {/* 5. Upload Excel Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-2xl w-full max-w-xl border border-gray-300 overflow-hidden">
            <div className="px-5 py-3.5 bg-brand-navy text-white flex items-center justify-between">
              <div>
                <h3 className="font-bold text-sm">Import Excel File</h3>
                <p className="text-xs text-gray-300">Upload your Excel file to populate the table</p>
              </div>
              <button
                onClick={() => {
                  setShowUploadModal(false);
                  setUploadFile(null);
                  setInspectResult(null);
                  setModalError('');
                }}
                className="text-gray-300 hover:text-white text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <div className="p-5 space-y-4 text-xs">
              {modalError && (
                <div role="alert" className="p-3 bg-red-50 border border-red-300 rounded text-red-800 flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-base">⚠️</span>
                    <span className="font-medium">{modalError}</span>
                  </div>
                  <button onClick={() => setModalError('')} className="text-red-500 hover:text-red-700 font-bold ml-2">
                    ✕
                  </button>
                </div>
              )}

              {!uploadFile ? (
                <div>
                  <div
                    onDragOver={e => {
                      e.preventDefault();
                      setIsDragging(true);
                    }}
                    onDragLeave={() => setIsDragging(false)}
                    onDrop={e => {
                      e.preventDefault();
                      setIsDragging(false);
                      const dropped = e.dataTransfer.files?.[0];
                      if (dropped) void handleFileChosen(dropped);
                    }}
                    onClick={() => uploadInputRef.current?.click()}
                    className={`border-2 border-dashed rounded-lg p-8 flex flex-col items-center justify-center text-center transition-colors cursor-pointer ${
                      isDragging ? 'border-brand-steel bg-blue-50/70' : 'border-gray-300 bg-gray-50 hover:border-brand-steel hover:bg-gray-100/60'
                    }`}
                  >
                    <span className="text-3xl mb-2">📁</span>
                    <p className="font-semibold text-gray-700">Drag & Drop Excel File Here</p>
                    <p className="text-gray-400 mt-1">or click to browse from your computer</p>
                    <button
                      type="button"
                      onClick={e => {
                        e.stopPropagation();
                        uploadInputRef.current?.click();
                      }}
                      className="mt-3 px-4 py-1.5 bg-brand-navy text-white font-medium rounded shadow-xs cursor-pointer hover:bg-opacity-90"
                    >
                      Browse File
                    </button>
                    <input
                      ref={uploadInputRef}
                      type="file"
                      accept=".xlsx,.xls,.csv"
                      className="hidden"
                      onChange={e => {
                        const file = e.target.files?.[0];
                        e.target.value = '';
                        if (file) void handleFileChosen(file);
                      }}
                    />
                    <p className="text-[11px] text-gray-400 mt-3">Supported: .xlsx, .csv</p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-3 bg-blue-50/60 rounded border border-blue-200">
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">📊</span>
                      <div>
                        <p className="font-bold text-gray-800">{uploadFile.name}</p>
                        <p className="text-[11px] text-gray-500">{(uploadFile.size / 1024).toFixed(1)} KB</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setUploadFile(null);
                        setInspectResult(null);
                        setModalError('');
                      }}
                      className="px-2.5 py-1 text-xs text-brand-navy hover:text-brand-steel font-medium border border-gray-300 bg-white rounded hover:bg-gray-50"
                    >
                      Change File
                    </button>
                  </div>

                  {inspectLoading && (
                    <div className="p-4 bg-gray-50 text-gray-700 rounded border border-gray-200 text-center flex items-center justify-center gap-2">
                      <div className="animate-spin h-4 w-4 border-2 border-brand-steel border-t-transparent rounded-full" />
                      <span>Reading and inspecting sheets in {uploadFile.name}…</span>
                    </div>
                  )}

                  {inspectResult && (
                    <div className="space-y-4">
                      <div>
                        <div className="flex items-center justify-between mb-1.5">
                          <label className="font-bold text-gray-700">Select Sheet to Import:</label>
                          <span className="text-gray-500 text-[11px]">
                            Sheets found: <strong className="text-gray-800">{inspectResult.sheets.length}</strong>
                          </span>
                        </div>
                        <div className="space-y-1.5 max-h-40 overflow-y-auto border border-gray-200 rounded p-2 bg-white">
                          {inspectResult.sheets.map(sheet => (
                            <label
                              key={sheet.name}
                              className={`flex items-center justify-between p-2 rounded cursor-pointer border transition-colors ${
                                selectedSheet === sheet.name
                                  ? 'bg-blue-50 border-brand-steel text-brand-navy font-bold'
                                  : 'hover:bg-gray-50 border-gray-200 text-gray-700'
                              }`}
                            >
                              <div className="flex items-center gap-2">
                                <input
                                  type="radio"
                                  name="sheetSelect"
                                  checked={selectedSheet === sheet.name}
                                  onChange={() => setSelectedSheet(sheet.name)}
                                  className="text-brand-steel"
                                />
                                <span>{sheet.name}</span>
                              </div>
                              <span className="text-gray-400 text-[11px] font-normal">
                                {sheet.row_count} rows • {sheet.column_count} cols
                              </span>
                            </label>
                          ))}
                        </div>
                      </div>

                      {selectedSheet && (() => {
                        const activeInfo = inspectResult.sheets.find(s => s.name === selectedSheet);
                        if (!activeInfo) return null;
                        return (
                          <div className="bg-gray-50 p-2.5 rounded border border-gray-200 space-y-2">
                            <div className="flex justify-between text-gray-600 font-semibold border-b border-gray-200 pb-1">
                              <span>Rows: {activeInfo.row_count}</span>
                              <span>Columns: {activeInfo.column_count}</span>
                            </div>
                            {activeInfo.headers.length > 0 && (
                              <div>
                                <p className="text-[11px] text-gray-500 font-semibold mb-1">Detected Headers:</p>
                                <div className="flex flex-wrap gap-1">
                                  {activeInfo.headers.map((h, i) => (
                                    <span key={i} className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-[10px] text-gray-700">
                                      {h}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })()}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="px-5 py-3 bg-gray-50 border-t border-gray-200 flex justify-end gap-2 text-xs">
              <button
                onClick={() => {
                  setShowUploadModal(false);
                  setUploadFile(null);
                  setInspectResult(null);
                  setModalError('');
                }}
                className="px-4 py-1.5 bg-white border border-gray-300 rounded font-semibold text-gray-700 hover:bg-gray-100"
              >
                Cancel
              </button>

              {inspectResult && (
                <button
                  onClick={() => { void handleImportSheet(); }}
                  disabled={!selectedSheet || importingSheet}
                  aria-label="Import Selected Sheet"
                  className="px-4 py-1.5 bg-brand-navy text-white rounded font-semibold hover:bg-opacity-90 disabled:opacity-50"
                >
                  {importingSheet ? 'Importing…' : 'Import Selected Sheet'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 6. Delete Row Confirmation Dialog */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-2xl max-w-sm w-full p-5 border border-gray-200 text-xs space-y-3">
            <h3 className="font-bold text-sm text-gray-900">Confirm Row Deletion</h3>
            <p className="text-gray-600">
              {selectedCount > 1
                ? `Are you sure you want to delete these ${selectedCount} selected rows?`
                : 'Are you sure you want to delete this row?'}
            </p>
            {singleSelectedRecord && (
              <div className="p-2 bg-gray-50 rounded border border-gray-200 font-mono space-y-0.5">
                <p>Part: {singleSelectedRecord.part_number}</p>
                <p>Item: {singleSelectedRecord.item_id}</p>
                <p>Desc: {singleSelectedRecord.description}</p>
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-3 py-1.5 bg-white border border-gray-300 rounded font-semibold text-gray-700 hover:bg-gray-100"
              >
                Cancel
              </button>
              <button
                onClick={() => { void handleDeleteSelected(); }}
                disabled={saving}
                className="px-3 py-1.5 bg-red-600 text-white rounded font-semibold hover:bg-red-700"
              >
                {saving ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
