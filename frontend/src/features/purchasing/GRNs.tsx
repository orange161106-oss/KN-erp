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

const COLUMNS: { key: keyof WorkspaceRecord; label: string; width: string; align?: 'left' | 'right' | 'center' }[] = [
  { key: 'part_number', label: 'Part Number', width: 'w-40', align: 'left' },
  { key: 'item_id', label: 'Item ID', width: 'w-28', align: 'left' },
  { key: 'description', label: 'Description', width: 'w-64', align: 'left' },
  { key: 'quantity', label: 'Qty', width: 'w-24', align: 'right' },
  { key: 'unit', label: 'Unit', width: 'w-20', align: 'center' },
  { key: 'po_number', label: 'PO Number', width: 'w-32', align: 'left' },
  { key: 'supplier_name', label: 'Supplier', width: 'w-48', align: 'left' },
  { key: 'status', label: 'Status', width: 'w-24', align: 'center' },
];

export default function GRNs() {
  const { user } = useAuth();
  const canRead = !!user?.permissions.includes('purchase.grns.read');
  const canImport = !!user?.permissions.includes('purchase.grns.import') || !!user?.permissions.includes('inventory.stock.import');
  const canCreate = !!user?.permissions.includes('purchase.grns.create') || !!user?.roles.includes('ADMIN');
  const canUpdate = !!user?.permissions.includes('purchase.grns.update') || !!user?.roles.includes('ADMIN');
  const canDelete = !!user?.permissions.includes('purchase.grns.delete') || !!user?.roles.includes('ADMIN');
  const canExport = !!user?.permissions.includes('purchase.grns.export') || canRead;

  const [records, setRecords] = useState<WorkspaceRecord[]>([]);
  const [originalMap, setOriginalMap] = useState<Map<string, WorkspaceRecord>>(new Map());
  const [deletedIds, setDeletedIds] = useState<string[]>([]);

  const [selectedCell, setSelectedCell] = useState<CellCoord | null>(null);
  const [editingCell, setEditingCell] = useState<CellCoord | null>(null);
  const [editValue, setEditValue] = useState<string>('');
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'SAVED' | 'DRAFT'>('ALL');

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

  const cellInputRef = useRef<HTMLInputElement>(null);

  // Load records from backend
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

  // Track modified cells
  const modifiedCells = useMemo(() => {
    const diffs = new Set<string>();
    records.forEach(r => {
      const orig = originalMap.get(r.id);
      if (!orig) {
        // Entire row is new
        COLUMNS.forEach(col => diffs.add(`${r.id}:${col.key}`));
      } else {
        COLUMNS.forEach(col => {
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

  // Filter & Search records
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
        r.unit.toLowerCase().includes(q)
      );
    });
  }, [records, statusFilter, searchQuery]);

  // Selected cell value for formula bar
  const currentSelectedValue = useMemo(() => {
    if (!selectedCell) return '';
    const row = records.find(r => r.id === selectedCell.rowId);
    if (!row) return '';
    return String(row[selectedCell.colKey] ?? '');
  }, [selectedCell, records]);

  // Coordinate display (e.g., "A3" or "Part Number • Row 1")
  const currentCoordLabel = useMemo(() => {
    if (!selectedCell) return '';
    const rowIdx = records.findIndex(r => r.id === selectedCell.rowId);
    const colIdx = COLUMNS.findIndex(c => c.key === selectedCell.colKey);
    if (rowIdx === -1 || colIdx === -1) return '';
    const colLetter = String.fromCharCode(65 + colIdx);
    return `${colLetter}${rowIdx + 1}`;
  }, [selectedCell, records]);

  // Cell Click / Selection
  const handleSelectCell = (rowId: string, colKey: keyof WorkspaceRecord) => {
    setSelectedCell({ rowId, colKey });
    setSelectedRowId(rowId);
    setEditingCell(null);
  };

  // Start Editing Cell
  const handleStartEdit = (rowId: string, colKey: keyof WorkspaceRecord) => {
    const row = records.find(r => r.id === rowId);
    if (!row) return;
    setSelectedCell({ rowId, colKey });
    setSelectedRowId(rowId);
    setEditingCell({ rowId, colKey });
    setEditValue(String(row[colKey] ?? ''));
    setTimeout(() => {
      cellInputRef.current?.focus();
      cellInputRef.current?.select();
    }, 10);
  };

  // Commit Cell Edit
  const handleCommitEdit = (newValue?: string) => {
    if (!editingCell) return;
    const val = newValue !== undefined ? newValue : editValue;
    setRecords(prev =>
      prev.map(r => {
        if (r.id !== editingCell.rowId) return r;
        return {
          ...r,
          [editingCell.colKey]: val,
        };
      })
    );
    setEditingCell(null);
  };

  // Handle Formula Bar Edit
  const handleFormulaBarChange = (val: string) => {
    if (!selectedCell) return;
    setRecords(prev =>
      prev.map(r => {
        if (r.id !== selectedCell.rowId) return r;
        return {
          ...r,
          [selectedCell.colKey]: val,
        };
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
      status: 'DRAFT',
      is_new: true,
    };
    setRecords(prev => [...prev, newRow]);
    setSelectedRowId(newId);
    setSelectedCell({ rowId: newId, colKey: 'part_number' });
    setSuccess('New draft row added.');
  };

  // Delete Row
  const handleDeleteSelectedRow = async () => {
    if (!selectedRowId) return;
    setShowDeleteConfirm(false);
    const row = records.find(r => r.id === selectedRowId);
    if (!row) return;

    if (row.is_new || row.id.startsWith('draft-')) {
      // Local draft row, remove immediately
      setRecords(prev => prev.filter(r => r.id !== selectedRowId));
      setSelectedRowId(null);
      setSelectedCell(null);
      setSuccess('Draft row removed.');
      return;
    }

    // Saved row: track for backend deletion
    try {
      setSaving(true);
      setError('');
      await apiClient.delete(`/api/v1/grns/workspace/records/${selectedRowId}?reason=Deleted+from+workspace`);
      setRecords(prev => prev.filter(r => r.id !== selectedRowId));
      const map = new Map(originalMap);
      map.delete(selectedRowId);
      setOriginalMap(map);
      setSelectedRowId(null);
      setSelectedCell(null);
      setSuccess(`Row ${row.part_number} deleted successfully.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete row.');
    } finally {
      setSaving(false);
    }
  };

  // Save Changes
  const handleSaveChanges = async () => {
    try {
      setSaving(true);
      setError('');
      setSuccess('');

      // Validation
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

  // Export Excel
  const handleExport = (type: 'ALL' | 'FILTERED') => {
    setShowExportMenu(false);
    try {
      let url = '/api/v1/grns/workspace/export';
      const params = new URLSearchParams();
      if (type === 'FILTERED') {
        if (searchQuery) params.append('search', searchQuery);
        if (statusFilter !== 'ALL') params.append('status', statusFilter);
      }
      if (params.toString()) url += `?${params.toString()}`;

      window.open(url, '_blank');
      setSuccess(`Export started for ${type === 'ALL' ? 'all' : 'filtered'} records.`);
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
      setError(err instanceof Error ? err.message : 'Failed to inspect Excel workbook.');
    } finally {
      setInspectLoading(false);
    }
  };

  // Import Selected Sheet
  const handleImportSheet = async () => {
    if (!uploadFile || !selectedSheet) return;
    try {
      setImportingSheet(true);
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
      setSuccess(`Successfully imported ${res.imported_count} rows from sheet "${selectedSheet}".`);
      await loadRecords();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import selected sheet.');
    } finally {
      setImportingSheet(false);
    }
  };

  if (!canRead) {
    return <p role="alert" className="p-4 text-red-700 bg-red-50 rounded">You do not have permission to view goods receipts.</p>;
  }

  const selectedRow = records.find(r => r.id === selectedRowId);

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)] -m-6 p-4 bg-white select-none">
      {/* 1. Header & Title */}
      <div className="flex items-center justify-between pb-2 border-b border-gray-200">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Goods Receipts</h2>
          <p className="text-xs text-gray-500">Manage receipt data in an Excel-style workspace.</p>
        </div>

        {/* Global Alerts */}
        <div className="flex items-center gap-2 text-xs">
          {error && <span role="alert" className="px-2.5 py-1 text-red-800 bg-red-100 rounded border border-red-300 font-medium">{error}</span>}
          {success && <span role="status" className="px-2.5 py-1 text-emerald-800 bg-emerald-100 rounded border border-emerald-300 font-medium">{success}</span>}
        </div>
      </div>

      {/* 2. Excel Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 py-2 border-b border-gray-200 bg-gray-50 px-2 rounded-t">
        <div className="flex items-center gap-1.5">
          {canImport && (
            <button
              onClick={() => { setShowUploadModal(true); setError(''); setSuccess(''); }}
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
              disabled={!selectedRowId || saving}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-red-700 bg-white border border-red-200 rounded shadow-xs hover:bg-red-50 active:bg-red-100 disabled:opacity-40"
            >
              <span>🗑️</span> Delete Row
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
                <div className="absolute left-0 mt-1 w-44 bg-white border border-gray-200 rounded shadow-lg py-1 z-30">
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
                </div>
              )}
            </div>
          )}
        </div>

        {/* Status & Search / Filter Controls */}
        <div className="flex items-center gap-3">
          {/* Unsaved State Pill */}
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

          {/* Search */}
          <div className="relative">
            <input
              type="text"
              aria-label="Search records"
              placeholder="🔍 Search..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-44 px-2.5 py-1 text-xs bg-white border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-brand-steel"
            />
          </div>

          {/* Filter */}
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
        </div>
      </div>

      {/* 3. Excel Formula / Value Bar */}
      <div className="flex items-center gap-2 py-1.5 px-2 bg-gray-100 border-b border-gray-300 text-xs">
        {/* Cell Reference Box */}
        <div className="w-16 px-2 py-0.5 font-mono text-center font-bold text-gray-700 bg-white border border-gray-300 rounded shadow-2xs">
          {currentCoordLabel || '—'}
        </div>

        {/* fx symbol */}
        <div className="font-serif italic font-bold text-gray-500 px-1 select-none">
          fx
        </div>

        {/* Formula / Value Input */}
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
              <button onClick={handleAddRow} className="px-3 py-1 bg-gray-100 border border-gray-300 rounded hover:bg-gray-200 text-gray-700">
                + Add your first row
              </button>
            )}
          </div>
        ) : (
          <table className="w-full border-collapse text-left text-xs table-fixed">
            <thead>
              <tr className="sticky top-0 z-10 bg-gray-100 shadow-xs border-b border-gray-300">
                {/* Row Number Header */}
                <th className="w-12 p-1.5 text-center font-bold text-gray-600 border-r border-gray-300 bg-gray-200/80">
                  #
                </th>
                {COLUMNS.map(col => (
                  <th
                    key={col.key}
                    className={`${col.width} p-1.5 font-semibold text-gray-700 border-r border-gray-300 select-none text-${col.align ?? 'left'}`}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredRecords.map((row, rIdx) => {
                const isRowSelected = selectedRowId === row.id;
                return (
                  <tr
                    key={row.id}
                    onClick={() => setSelectedRowId(row.id)}
                    className={`h-7 border-b border-gray-200 transition-colors ${
                      isRowSelected ? 'bg-blue-50/50' : 'hover:bg-gray-50/70'
                    }`}
                  >
                    {/* Excel Row Index Header */}
                    <td
                      onClick={() => setSelectedRowId(row.id)}
                      className={`text-center font-mono text-gray-500 border-r border-gray-300 select-none cursor-pointer ${
                        isRowSelected ? 'bg-blue-200/60 font-bold text-blue-900' : 'bg-gray-100'
                      }`}
                    >
                      {row.row_index ?? rIdx + 1}
                    </td>

                    {/* Data Cells */}
                    {COLUMNS.map(col => {
                      const isCellSelected = selectedCell?.rowId === row.id && selectedCell?.colKey === col.key;
                      const isCellEditing = editingCell?.rowId === row.id && editingCell?.colKey === col.key;
                      const isModified = modifiedCells.has(`${row.id}:${col.key}`);
                      const cellValue = String(row[col.key] ?? '');

                      return (
                        <td
                          key={col.key}
                          onClick={() => handleSelectCell(row.id, col.key)}
                          onDoubleClick={() => handleStartEdit(row.id, col.key)}
                          className={`relative border-r border-gray-200 px-2 py-0.5 truncate cursor-cell ${
                            col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'
                          } ${
                            isCellSelected ? 'ring-2 ring-blue-600 ring-inset bg-blue-50/30' : ''
                          } ${isModified && !isCellSelected ? 'bg-amber-50/70' : ''}`}
                        >
                          {/* Dirty / Modified cell triangle marker */}
                          {isModified && (
                            <span
                              title="Unsaved modification"
                              className="absolute top-0 right-0 w-0 h-0 border-t-[5px] border-t-amber-500 border-l-[5px] border-l-transparent"
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
                                  const curColIdx = COLUMNS.findIndex(c => c.key === col.key);
                                  if (curColIdx < COLUMNS.length - 1) {
                                    handleStartEdit(row.id, COLUMNS[curColIdx + 1].key);
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

      {/* 5. Upload Excel Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-2xl w-full max-w-xl border border-gray-300 overflow-hidden">
            {/* Modal Header */}
            <div className="px-5 py-3.5 bg-brand-navy text-white flex items-center justify-between">
              <div>
                <h3 className="font-bold text-sm">Import Excel File</h3>
                <p className="text-xs text-gray-300">Upload your Excel file to populate the table</p>
              </div>
              <button
                onClick={() => { setShowUploadModal(false); setUploadFile(null); setInspectResult(null); }}
                className="text-gray-300 hover:text-white text-lg font-bold"
              >
                ✕
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 space-y-4 text-xs">
              {!inspectResult ? (
                <div>
                  <div
                    onDragOver={e => e.preventDefault()}
                    onDrop={e => {
                      e.preventDefault();
                      void handleFileChosen(e.dataTransfer.files?.[0]);
                    }}
                    className="border-2 border-dashed border-gray-300 rounded-lg p-6 flex flex-col items-center justify-center text-center hover:border-brand-steel transition-colors cursor-pointer bg-gray-50"
                  >
                    <span className="text-3xl mb-2">📁</span>
                    <p className="font-semibold text-gray-700">Drag & Drop Excel File Here</p>
                    <p className="text-gray-400 mt-1">or</p>
                    <label className="mt-2 px-4 py-1.5 bg-brand-navy text-white font-medium rounded shadow-xs cursor-pointer hover:bg-opacity-90">
                      Browse File
                      <input
                        type="file"
                        accept=".xlsx,.csv"
                        className="hidden"
                        onChange={e => { void handleFileChosen(e.target.files?.[0]); }}
                      />
                    </label>
                    <p className="text-[11px] text-gray-400 mt-3">Supported: .xlsx, .csv</p>
                  </div>

                  {inspectLoading && (
                    <div className="mt-4 p-3 bg-blue-50 text-blue-800 rounded border border-blue-200 text-center">
                      Inspecting workbook sheets…
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-4">
                  {/* File Info */}
                  <div className="bg-gray-50 p-3 rounded border border-gray-200 space-y-1">
                    <p className="font-semibold text-gray-700">File: <span className="font-normal font-mono">{inspectResult.filename}</span></p>
                    <p className="font-semibold text-gray-700">Sheets found: <span className="font-normal">{inspectResult.sheets.length}</span></p>
                  </div>

                  {/* Sheet Selector */}
                  <div>
                    <label className="block font-bold text-gray-700 mb-1">Select Sheet to Import:</label>
                    <div className="space-y-1.5 max-h-40 overflow-y-auto border border-gray-200 rounded p-2">
                      {inspectResult.sheets.map(sheet => (
                        <label
                          key={sheet.name}
                          className={`flex items-center justify-between p-2 rounded cursor-pointer border ${
                            selectedSheet === sheet.name
                              ? 'bg-blue-50 border-brand-steel text-brand-navy font-bold'
                              : 'hover:bg-gray-50 border-gray-200'
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
                          <span className="text-gray-400 text-[11px]">
                            {sheet.row_count} rows • {sheet.column_count} cols
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Preview Selected Sheet */}
                  {selectedSheet && (() => {
                    const activeInfo = inspectResult.sheets.find(s => s.name === selectedSheet);
                    if (!activeInfo) return null;
                    return (
                      <div className="bg-gray-50 p-2.5 rounded border border-gray-200 space-y-1.5">
                        <div className="flex justify-between text-gray-600 font-semibold">
                          <span>Rows: {activeInfo.row_count}</span>
                          <span>Columns: {activeInfo.column_count}</span>
                        </div>
                        {activeInfo.headers.length > 0 && (
                          <div className="text-[11px] text-gray-500 truncate">
                            Headers: {activeInfo.headers.slice(0, 6).join(', ')}{activeInfo.headers.length > 6 ? '…' : ''}
                          </div>
                        )}
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-5 py-3 bg-gray-50 border-t border-gray-200 flex justify-end gap-2 text-xs">
              <button
                onClick={() => { setShowUploadModal(false); setUploadFile(null); setInspectResult(null); }}
                className="px-4 py-1.5 bg-white border border-gray-300 rounded font-semibold text-gray-700 hover:bg-gray-100"
              >
                Cancel
              </button>

              {inspectResult && (
                <button
                  onClick={() => { void handleImportSheet(); }}
                  disabled={!selectedSheet || importingSheet}
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
              Are you sure you want to delete this row?
            </p>
            {selectedRow && (
              <div className="p-2 bg-gray-50 rounded border border-gray-200 font-mono space-y-0.5">
                <p>Part: {selectedRow.part_number}</p>
                <p>Item: {selectedRow.item_id}</p>
                <p>Desc: {selectedRow.description}</p>
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
                onClick={() => { void handleDeleteSelectedRow(); }}
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
