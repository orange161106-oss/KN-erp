import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';

export interface ColumnDef<T> {
  id?: string;
  key: keyof T & string;
  label: string;
  width?: number | string;
  minWidth?: number;
  maxWidth?: number;
  align?: 'left' | 'right' | 'center';
  type?: 'text' | 'number' | 'select' | 'date';
  isEditable?: boolean;
  isSticky?: boolean;
  group?: string;
  render?: (value: any, row: T, isSelected: boolean) => React.ReactNode;
}

export interface HeaderGroupDef {
  label: string;
  colSpan?: number;
  className?: string;
}

export interface FilterState {
  type: 'text' | 'number' | 'select';
  textValue?: string;
  minNumber?: number;
  maxNumber?: number;
  selectedOptions?: string[];
}

export interface DataTableProps<T extends { id: string; row_index?: number | null }> {
  columns: ColumnDef<T>[];
  data: T[];
  originalData?: Map<string, T>;
  selectedIds: Set<string>;
  onSelectionChange: (ids: Set<string>) => void;
  onCellChange?: (rowId: string, colKey: keyof T & string, value: string) => void;
  onSave?: () => Promise<void> | void;
  onDeleteRows?: (rowIds: string[]) => Promise<void> | void;
  onDiscardChanges?: () => void;
  isLoading?: boolean;
  emptyMessage?: string;
  onAddRow?: () => void;
  canCreate?: boolean;
  canUpdate?: boolean;
  canDelete?: boolean;
  selectedCell?: { rowId: string; colKey: keyof T & string } | null;
  onSelectCell?: (cell: { rowId: string; colKey: keyof T & string } | null) => void;
  formulaValue?: string;
  onFormulaChange?: (val: string) => void;
  getRowClassName?: (row: T) => string;
  headerGroups?: HeaderGroupDef[];
  storageKey?: string;
  saveStatus?: 'idle' | 'saving' | 'saved' | 'error';
  lastModifiedText?: string;
  onExport?: (mode: 'ALL' | 'FILTERED' | 'SELECTED') => void;
  customRowActions?: (row: T) => Array<{ label: string; onClick: (row?: T) => void; icon?: React.ReactNode; disabled?: boolean; className?: string }>;
  onSaveRow?: (rowId: string, updates: Record<string, any>) => Promise<void>;
  virtualize?: boolean;
}

// Convert column width specifications (e.g. 'w-44', '180px', or 180) to pure pixel numbers
export function parseWidthPixels(width?: number | string, label?: string): number {
  if (typeof width === 'number' && !isNaN(width) && width > 0) return width;
  if (typeof width === 'string') {
    if (width.startsWith('w-')) {
      const val = parseInt(width.replace('w-', ''), 10);
      if (!isNaN(val)) return Math.max(val * 4, 60);
    }
    const parsed = parseInt(width.replace('px', ''), 10);
    if (!isNaN(parsed) && parsed > 0) return parsed;
  }
  // Sensible default based on label length
  const labelLen = (label || '').length;
  return Math.max(labelLen * 9 + 40, 140);
}

// Layering (z-index) constants documented in code:
// - Body cells: z-0
// - Frozen body cells: sticky z-10
// - Sticky header rows: sticky z-20
// - Frozen header corners (Checkbox, #, and frozen columns): sticky z-30
// - Column resize handles: z-35
// - Context menu: z-[9999] (rendered via portal)
// - Modals / Toasts: z-[10000]

export default function DataTable<T extends { id: string; row_index?: number | null }>({
  columns,
  data,
  originalData = new Map(),
  selectedIds,
  onSelectionChange,
  onCellChange,
  onSave,
  onDeleteRows,
  onDiscardChanges,
  isLoading = false,
  emptyMessage = 'No records found matching your filters.',
  onAddRow,
  canCreate = true,
  canUpdate = true,
  canDelete = true,
  selectedCell: externalSelectedCell,
  onSelectCell: externalOnSelectCell,
  formulaValue: externalFormulaValue,
  onFormulaChange: externalOnFormulaChange,
  getRowClassName,
  headerGroups,
  storageKey,
  saveStatus = 'idle',
  lastModifiedText,
  customRowActions,
  onSaveRow,
  virtualize = false,
}: DataTableProps<T>) {
  // --- Persistent Layout State ---
  const persistentKey = storageKey ? `knl_grid_layout_${storageKey}` : null;
  const loadStoredLayout = useCallback(() => {
    if (!persistentKey) return null;
    try {
      const raw = localStorage.getItem(persistentKey);
      if (raw) return JSON.parse(raw);
    } catch {
      // ignore
    }
    return null;
  }, [persistentKey]);

  const initialLayout = useMemo(() => loadStoredLayout(), [loadStoredLayout]);

  // Column visibility
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(() => {
    if (initialLayout?.hidden) {
      return new Set<string>(initialLayout.hidden);
    }
    return new Set<string>();
  });

  // Custom column widths
  const [customWidths, setCustomWidths] = useState<Record<string, number>>(() => {
    return initialLayout?.widths || {};
  });

  // Frozen column keys
  const [frozenColKeys, setFrozenColKeys] = useState<Set<string>>(() => {
    if (initialLayout?.frozen) {
      return new Set<string>(initialLayout.frozen);
    }
    const defaults = new Set<string>();
    columns.forEach(c => {
      if (c.isSticky) defaults.add(c.key);
    });
    return defaults;
  });

  // Save layout to localStorage on changes
  useEffect(() => {
    if (!persistentKey) return;
    try {
      localStorage.setItem(
        persistentKey,
        JSON.stringify({
          hidden: Array.from(hiddenColumns),
          widths: customWidths,
          frozen: Array.from(frozenColKeys),
        })
      );
    } catch {
      // localStorage full or restricted
    }
  }, [persistentKey, hiddenColumns, customWidths, frozenColKeys]);

  // --- Height Preferences & Resizing State (Section 9A) ---
  const heightStorageKey = storageKey ? `knl_grid_height_${storageKey}` : null;
  const loadStoredHeight = useCallback(() => {
    if (!heightStorageKey) return null;
    try {
      const raw = localStorage.getItem(heightStorageKey);
      if (raw) return JSON.parse(raw);
    } catch {
      // ignore
    }
    return null;
  }, [heightStorageKey]);

  const initialHeightPref = useMemo(() => loadStoredHeight(), [loadStoredHeight]);

  const [heightMode, setHeightMode] = useState<'fit' | 'compact' | 'standard' | 'large' | 'custom'>(
    initialHeightPref?.mode || 'fit'
  );
  const [customHeight, setCustomHeight] = useState<number>(
    initialHeightPref?.customHeight || 540
  );
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isResizingHeight, setIsResizingHeight] = useState(false);
  const rootContainerRef = useRef<HTMLDivElement>(null);

  // Fit follows the bounded flex parent, including sidebar transitions and
  // wrapping toolbars. A viewport measurement becomes stale as those change.
  // Persist height preference
  useEffect(() => {
    if (!heightStorageKey) return;
    try {
      localStorage.setItem(
        heightStorageKey,
        JSON.stringify({ mode: heightMode, customHeight })
      );
    } catch {
      // ignore
    }
  }, [heightStorageKey, heightMode, customHeight]);

  // Fullscreen escape listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen]);

  const currentHeightPx = useMemo(() => {
    if (isFullscreen) return window.innerHeight;
    if (heightMode === 'compact') return 380;
    if (heightMode === 'standard') return 540;
    if (heightMode === 'large') return 720;
    if (heightMode === 'custom') return customHeight;
    return 540;
  }, [isFullscreen, heightMode, customHeight]);

  const handleStartResizeHeight = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizingHeight(true);
    const startY = e.clientY;
    const startH = rootContainerRef.current?.getBoundingClientRect().height || currentHeightPx;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const diff = moveEvent.clientY - startY;
      const nextH = Math.max(320, Math.min(window.innerHeight - 50, startH + diff));
      setCustomHeight(nextH);
      setHeightMode('custom');
    };

    const onMouseUp = () => {
      setIsResizingHeight(false);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  const handleResizeHandleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setCustomHeight(prev => Math.max(320, prev - 20));
      setHeightMode('custom');
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setCustomHeight(prev => Math.min(window.innerHeight - 50, prev + 20));
      setHeightMode('custom');
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setHeightMode('fit');
    }
  };

  const handleResetLayout = () => {
    setHiddenColumns(new Set());
    setCustomWidths({});
    const defaults = new Set<string>();
    columns.forEach(c => {
      if (c.isSticky) defaults.add(c.key);
    });
    setFrozenColKeys(defaults);
    if (persistentKey) {
      try {
        localStorage.removeItem(persistentKey);
      } catch {
        // ignore
      }
    }
  };

  // --- Sort & Column Filter State ---
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' } | null>(null);
  const [columnFilters, setColumnFilters] = useState<Record<string, FilterState>>({});

  // --- UI Toolbars & Menus ---
  const [showColMenu, setShowColMenu] = useState(false);
  const [colMenuSearch, setColMenuSearch] = useState('');

  // --- Cell Selection & Range State ---
  const [internalSelectedCell, setInternalSelectedCell] = useState<{
    rowId: string;
    colKey: keyof T & string;
  } | null>(null);
  const selectedCell = externalSelectedCell !== undefined ? externalSelectedCell : internalSelectedCell;
  const setSelectedCell = externalOnSelectCell || setInternalSelectedCell;

  // --- Inline Editing State ---
  const [editingCell, setEditingCell] = useState<{
    rowId: string;
    colKey: keyof T & string;
  } | null>(null);
  const [editValue, setEditValue] = useState<string>('');

  // --- Undo / Redo History Stack ---
  type CellEdit = { rowId: string; colKey: keyof T & string; oldVal: string; newVal: string };
  const [undoStack, setUndoStack] = useState<CellEdit[][]>([]);
  const [redoStack, setRedoStack] = useState<CellEdit[][]>([]);
  const [editError, setEditError] = useState<string | null>(null);
  const saveHandlerRef = useRef(onSave);
  saveHandlerRef.current = onSave;

  // --- Context Menu State ---
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    type: 'cell' | 'header' | 'rowHeader';
    rowId?: string;
    rowIndex?: number;
    colKey?: string;
  } | null>(null);

  // --- Row Editor Modal State ---
  const [rowEditorItem, setRowEditorItem] = useState<T | null>(null);
  const [rowEditorDraft, setRowEditorDraft] = useState<Record<string, string>>({});
  const [rowEditorInitial, setRowEditorInitial] = useState<Record<string, string>>({});
  const [isSavingRowEditor, setIsSavingRowEditor] = useState(false);
  const [rowEditorError, setRowEditorError] = useState<string | null>(null);

  // --- Delete Confirmation Modal State ---
  const [confirmDeleteIds, setConfirmDeleteIds] = useState<string[] | null>(null);

  // --- DOM References ---
  const lastClickedIndexRef = useRef<number | null>(null);
  const cellInputRef = useRef<HTMLInputElement>(null);
  const selectEditorOnFocus = useRef(true);
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const groupHeaderRef = useRef<HTMLTableRowElement>(null);
  const [groupHeaderHeight, setGroupHeaderHeight] = useState<number>(32);
  const [isScrolledLeft, setIsScrolledLeft] = useState<boolean>(false);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(540);
  const [headerHeight, setHeaderHeight] = useState(56);
  const ROW_HEIGHT = 28;

  useLayoutEffect(() => {
    const container = tableContainerRef.current;
    if (!container || !virtualize) return;
    const measure = () => {
      setViewportHeight(container.clientHeight || 540);
      setHeaderHeight(container.querySelector('thead')?.getBoundingClientRect().height || 56);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    return () => observer.disconnect();
  }, [virtualize, heightMode, isFullscreen, columns, hiddenColumns, headerGroups]);

  useLayoutEffect(() => {
    if (!editingCell) return;
    cellInputRef.current?.focus();
    if (selectEditorOnFocus.current) cellInputRef.current?.select();
    else {
      const input = cellInputRef.current;
      if (input) input.setSelectionRange(input.value.length, input.value.length);
    }
  }, [editingCell?.rowId, editingCell?.colKey]);

  // Measure group header height dynamically to set column header `top` offset cleanly
  useLayoutEffect(() => {
    if (groupHeaderRef.current) {
      const h = groupHeaderRef.current.offsetHeight;
      if (h > 0) setGroupHeaderHeight(h);
    }
  }, [columns, hiddenColumns, headerGroups]);

  // Track container scrollLeft to show subtle shadow on frozen columns
  const handleScroll = useCallback(() => {
    if (tableContainerRef.current) {
      setIsScrolledLeft(tableContainerRef.current.scrollLeft > 2);
      if (virtualize) setScrollTop(tableContainerRef.current.scrollTop);
    }
  }, [virtualize]);

  // Filter visible columns
  const visibleColumns = useMemo(
    () => columns.filter(col => !hiddenColumns.has(col.key)),
    [columns, hiddenColumns]
  );

  // Measure individual column pixel width
  const getColWidth = useCallback(
    (colKey: string, label: string, defaultWidth?: number | string) => {
      if (customWidths[colKey]) return customWidths[colKey];
      return parseWidthPixels(defaultWidth, label);
    },
    [customWidths]
  );

  // Calculate frozen sticky left offsets
  // Checkbox (36px) at left: 0, Row # (48px) at left: 36px
  const stickyLeftOffsets = useMemo(() => {
    let offset = 84; // 36 + 48
    const map = new Map<string, number>();
    let lastFrozenKey = '';

    visibleColumns.forEach(col => {
      const isFrozen = frozenColKeys.has(col.key);
      if (isFrozen) {
        map.set(col.key, offset);
        const w = getColWidth(col.key, col.label, col.width);
        offset += w;
        lastFrozenKey = col.key;
      }
    });

    return { offsets: map, lastFrozenKey, totalFrozenWidth: offset };
  }, [visibleColumns, frozenColKeys, getColWidth]);

  // Calculate total table width in pixels
  const totalTableWidth = useMemo(() => {
    let w = 84; // 36 + 48
    visibleColumns.forEach(col => {
      w += getColWidth(col.key, col.label, col.width);
    });
    return w;
  }, [visibleColumns, getColWidth]);

  // --- Dynamic Group Header Calculation ---
  // Calculates real visible colSpans and visible group bands so Tier 1 and Tier 2 align 100%
  const computedHeaderGroups = useMemo(() => {
    if (!headerGroups || headerGroups.length === 0) return [];

    let currentVisibleColIndex = 0;
    const groups: Array<{ label: string; colSpan: number; pixelWidth: number; className?: string }> = [];

    headerGroups.forEach(grp => {
      const declaredSpan = grp.colSpan ?? 1;
      // Identify which columns fall within this group span
      const childCols = columns.slice(currentVisibleColIndex, currentVisibleColIndex + declaredSpan);
      currentVisibleColIndex += declaredSpan;

      // Count visible child columns
      const visibleChildren = childCols.filter(c => !hiddenColumns.has(c.key));
      if (visibleChildren.length > 0) {
        let spanWidth = 0;
        visibleChildren.forEach(c => {
          spanWidth += getColWidth(c.key, c.label, c.width);
        });

        groups.push({
          label: grp.label,
          colSpan: visibleChildren.length,
          pixelWidth: spanWidth,
          className: grp.className,
        });
      }
    });

    return groups;
  }, [headerGroups, columns, hiddenColumns, getColWidth]);

  // --- Data Sorting & Per-Column Filtering ---
  const processedData = useMemo(() => {
    let result = [...data];

    // 1. Column filters
    Object.entries(columnFilters).forEach(([colKey, filter]) => {
      if (!filter) return;
      result = result.filter(row => {
        const raw = (row as any)[colKey];
        if (filter.type === 'text' && filter.textValue) {
          const valStr = String(raw ?? '').toLowerCase();
          return valStr.includes(filter.textValue.toLowerCase());
        }
        if (filter.type === 'number') {
          const num = parseFloat(String(raw ?? ''));
          if (filter.minNumber !== undefined && (isNaN(num) || num < filter.minNumber)) return false;
          if (filter.maxNumber !== undefined && (isNaN(num) || num > filter.maxNumber)) return false;
          return true;
        }
        if (filter.type === 'select' && filter.selectedOptions && filter.selectedOptions.length > 0) {
          const valStr = String(raw ?? '');
          return filter.selectedOptions.includes(valStr);
        }
        return true;
      });
    });

    // 2. Sort
    if (sortConfig) {
      result.sort((a, b) => {
        const valA = (a as any)[sortConfig.key];
        const valB = (b as any)[sortConfig.key];
        if (valA === valB) return 0;
        if (valA === null || valA === undefined) return 1;
        if (valB === null || valB === undefined) return -1;

        const numA = parseFloat(valA);
        const numB = parseFloat(valB);
        if (!isNaN(numA) && !isNaN(numB)) {
          return sortConfig.direction === 'asc' ? numA - numB : numB - numA;
        }

        const comp = String(valA).localeCompare(String(valB));
        return sortConfig.direction === 'asc' ? comp : -comp;
      });
    }

    return result;
  }, [data, columnFilters, sortConfig]);

  const windowed = virtualize && processedData.length > 200;
  let windowStart = windowed
    ? Math.min(Math.max(0, processedData.length - 1), Math.max(0, Math.floor((scrollTop - headerHeight) / ROW_HEIGHT) - 8))
    : 0;
  let windowEnd = windowed
    ? Math.min(processedData.length, windowStart + Math.ceil(viewportHeight / ROW_HEIGHT) + 24)
    : processedData.length;
  // Keep an open input mounted while the user scrolls; all operations still
  // address processedData, never just the rendered window.
  if (windowed && editingCell) {
    const editingIndex = processedData.findIndex(row => row.id === editingCell.rowId);
    if (editingIndex >= 0) {
      windowStart = Math.min(windowStart, editingIndex);
      windowEnd = Math.max(windowEnd, editingIndex + 1);
    }
  }
  const renderedData = processedData.slice(windowStart, windowEnd);
  const pendingCellFocus = useRef<{ rowIndex: number; colKey: string } | null>(null);
  useLayoutEffect(() => {
    const target = pendingCellFocus.current;
    if (!target) return;
    const row = tableContainerRef.current?.querySelector(`[data-row-index="${target.rowIndex}"]`);
    const cell = Array.from(row?.querySelectorAll<HTMLElement>('td') || [])
      .find(item => item.dataset.columnKey === target.colKey);
    if (cell) {
      cell.focus({ preventScroll: true });
      pendingCellFocus.current = null;
    }
  }, [selectedCell, windowStart, windowEnd]);

  useEffect(() => {
    if (tableContainerRef.current) tableContainerRef.current.scrollTop = 0;
    setScrollTop(0);
  }, [sortConfig, columnFilters]);

  // Track modified dirty cells
  const modifiedCells = useMemo(() => {
    const diffs = new Set<string>();
    data.forEach(r => {
      const orig = originalData.get(r.id);
      if (!orig) {
        // new row
        visibleColumns.forEach(col => diffs.add(`${r.id}:${col.key}`));
      } else {
        visibleColumns.forEach(col => {
          const origVal = String((orig as any)[col.key] ?? '').trim();
          const currVal = String((r as any)[col.key] ?? '').trim();
          if (origVal !== currVal) {
            diffs.add(`${r.id}:${col.key}`);
          }
        });
      }
    });
    return diffs;
  }, [data, originalData, visibleColumns]);

  // Bulk Selection handlers
  const allSelected = processedData.length > 0 && processedData.every(r => selectedIds.has(r.id));
  const someSelected = processedData.some(r => selectedIds.has(r.id)) && !allSelected;

  const handleToggleSelectAll = () => {
    if (allSelected) {
      onSelectionChange(new Set());
    } else {
      const next = new Set<string>(selectedIds);
      processedData.forEach(r => next.add(r.id));
      onSelectionChange(next);
    }
  };

  const handleRowCheckbox = (id: string, index: number, event: React.MouseEvent) => {
    event.stopPropagation();
    const next = new Set(selectedIds);

    if (event.shiftKey && lastClickedIndexRef.current !== null) {
      const start = Math.min(lastClickedIndexRef.current, index);
      const end = Math.max(lastClickedIndexRef.current, index);
      for (let i = start; i <= end; i++) {
        if (processedData[i]) next.add(processedData[i].id);
      }
    } else {
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      lastClickedIndexRef.current = index;
    }

    onSelectionChange(next);
  };

  const applyEdits = (edits: Array<{ rowId: string; colKey: keyof T & string; value: string }>) => {
    if (!canUpdate || !onCellChange) return;
    const actions: CellEdit[] = [];
    for (const edit of edits) {
      if (columns.find(col => col.key === edit.colKey)?.isEditable === false) {
        setEditError('This column is read-only. Paste into an editable quantity or parameter column.');
        return;
      }
      const row = data.find(item => item.id === edit.rowId);
      if (!row) return;
      const oldVal = String(row[edit.colKey] ?? '');
      if (oldVal !== edit.value) actions.push({ ...edit, oldVal, newVal: edit.value });
    }
    if (!actions.length) return;
    setEditError(null);
    setUndoStack(prev => [...prev.slice(-99), actions]);
    setRedoStack([]);
    actions.forEach(action => onCellChange(action.rowId, action.colKey, action.newVal));
  };
  const applyCellEdit = (rowId: string, colKey: keyof T & string, value: string) =>
    applyEdits([{ rowId, colKey, value }]);

  const openRowEditor = useCallback((row: T) => {
    const initialMap: Record<string, string> = {};
    columns.forEach(col => {
      const rawVal = (row as any)[col.key];
      if (rawVal === null || rawVal === undefined) {
        initialMap[col.key] = '';
      } else if (typeof rawVal === 'number') {
        initialMap[col.key] = Number(rawVal).toFixed(2);
      } else {
        initialMap[col.key] = String(rawVal);
      }
    });
    setRowEditorInitial(initialMap);
    setRowEditorDraft(initialMap);
    setRowEditorError(null);
    setRowEditorItem(row);
  }, [columns]);

  useEffect(() => {
    if (!rowEditorItem || onSaveRow) return;
    const fresh = data.find(r => r.id === rowEditorItem.id);
    if (fresh) {
      setRowEditorDraft(prev => {
        const next = { ...prev };
        columns.forEach(col => {
          const raw = (fresh as any)[col.key];
          next[col.key] = raw === null || raw === undefined ? '' : String(raw);
        });
        return next;
      });
    }
  }, [data, rowEditorItem, onSaveRow, columns]);

  const isRowEditorDirty = useMemo(() => {
    if (!rowEditorItem) return false;
    return Object.keys(rowEditorDraft).some(k => (rowEditorDraft[k] ?? '') !== (rowEditorInitial[k] ?? ''));
  }, [rowEditorItem, rowEditorDraft, rowEditorInitial]);

  const handleCloseRowEditor = useCallback(() => {
    if (isSavingRowEditor) return;
    if (isRowEditorDirty) {
      if (window.confirm('Discard unsaved changes? Any edits made in this dialog will be lost.')) {
        setRowEditorItem(null);
        setRowEditorError(null);
      }
    } else {
      setRowEditorItem(null);
      setRowEditorError(null);
    }
  }, [isSavingRowEditor, isRowEditorDirty]);

  const handleSaveRowEditor = useCallback(async () => {
    if (!rowEditorItem || !isRowEditorDirty || isSavingRowEditor) return;
    setIsSavingRowEditor(true);
    setRowEditorError(null);
    try {
      const changedFields: Record<string, string> = {};
      for (const [k, v] of Object.entries(rowEditorDraft)) {
        if ((v ?? '') !== (rowEditorInitial[k] ?? '')) {
          changedFields[k] = v;
        }
      }
      if (onSaveRow) {
        await onSaveRow(rowEditorItem.id, changedFields);
      } else {
        const edits = Object.entries(changedFields).map(([k, v]) => ({
          rowId: rowEditorItem.id,
          colKey: k as any,
          value: v,
        }));
        applyEdits(edits);
        if (onSave) {
          await onSave();
        }
      }
      setRowEditorItem(null);
    } catch (err: any) {
      setRowEditorError(err?.message || 'Failed to save row changes.');
    } finally {
      setIsSavingRowEditor(false);
    }
  }, [rowEditorItem, isRowEditorDirty, isSavingRowEditor, rowEditorDraft, rowEditorInitial, onSaveRow, onSave, applyEdits]);

  useEffect(() => {
    if (!rowEditorItem) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        handleCloseRowEditor();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        e.stopPropagation();
        void handleSaveRowEditor();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [rowEditorItem, handleCloseRowEditor, handleSaveRowEditor]);

  // Keyboard shortcut Ctrl/Cmd+S and Ctrl/Cmd+A and Undo/Redo inside grid
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      const target = document.activeElement;
      if (!rootContainerRef.current?.contains(target) && !(target === document.body && selectedCell)) return;
      const typing = target instanceof HTMLElement &&
        (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable);

      // 1. Ctrl+S / Cmd+S: Save changes
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        // Commit any active editing cell first
        if (editingCell) {
          handleCommitEdit();
        }
        if (canUpdate && onSave) {
          // Let the just-committed editor update parent state before saving.
          if (editingCell) setTimeout(() => { void saveHandlerRef.current?.(); }, 0);
          else void onSave();
        }
        return;
      }

      // 2. Ctrl+Z: Undo
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
        if ((!typing || target?.getAttribute('aria-label') === 'Formula bar' || rowEditorItem) && !editingCell && canUpdate && undoStack.length > 0 && onCellChange) {
          e.preventDefault();
          const lastAction = undoStack[undoStack.length - 1];
          setUndoStack(prev => prev.slice(0, -1));
          setRedoStack(prev => [...prev, lastAction]);
          lastAction.forEach(action => onCellChange(action.rowId, action.colKey, action.oldVal));
        }
        return;
      }

      // 3. Ctrl+Y or Ctrl+Shift+Z: Redo
      if (
        ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') ||
        ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'z')
      ) {
        if ((!typing || target?.getAttribute('aria-label') === 'Formula bar' || rowEditorItem) && !editingCell && canUpdate && redoStack.length > 0 && onCellChange) {
          e.preventDefault();
          const lastRedo = redoStack[redoStack.length - 1];
          setRedoStack(prev => prev.slice(0, -1));
          setUndoStack(prev => [...prev, lastRedo]);
          lastRedo.forEach(action => onCellChange(action.rowId, action.colKey, action.newVal));
        }
        return;
      }

      // 4. Ctrl+A: Select All Rows
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
        const activeTag = document.activeElement?.tagName?.toLowerCase();
        if (activeTag === 'input' || activeTag === 'textarea') return;
        e.preventDefault();
        const next = new Set<string>();
        processedData.forEach(r => next.add(r.id));
        onSelectionChange(next);
      }
    };

    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [editingCell, onSave, undoStack, redoStack, onCellChange, processedData, onSelectionChange, canUpdate, selectedCell, editValue, rowEditorItem]);

  // Start editing a cell
  const handleStartEdit = (rowId: string, colKey: keyof T & string) => {
    const colDef = columns.find(c => c.key === colKey);
    if (!canUpdate || !onCellChange || (colDef && colDef.isEditable === false)) return;
    if (editingCell?.rowId === rowId && editingCell.colKey === colKey) return;

    const row = data.find(r => r.id === rowId);
    if (!row) return;

    selectEditorOnFocus.current = true;
    setSelectedCell({ rowId, colKey });
    setEditingCell({ rowId, colKey });
    setEditValue(String((row as any)[colKey] ?? ''));
  };

  const handleCommitEdit = (newVal?: string) => {
    if (!editingCell) return;
    const val = newVal !== undefined ? newVal : editValue;
    const row = data.find(r => r.id === editingCell.rowId);
    const oldVal = row ? String((row as any)[editingCell.colKey] ?? '') : '';

    if (val !== oldVal && onCellChange) {
      applyCellEdit(editingCell.rowId, editingCell.colKey, val);
    }
    setEditingCell(null);
  };

  // Cell Navigation via Keyboard
  const handleCellKeyDown = (
    e: React.KeyboardEvent,
    rowIndex: number,
    colKey: keyof T & string
  ) => {
    if (editingCell) return; // handled in input editor

    const colIndex = visibleColumns.findIndex(c => c.key === colKey);
    if (colIndex === -1) return;

    // F2 or Enter: Start editing
    if (e.key === 'F2' || e.key === 'Enter') {
      e.preventDefault();
      handleStartEdit(processedData[rowIndex].id, colKey);
      return;
    }

    // Delete / Backspace: Clear cell
    if (e.key === 'Delete' || e.key === 'Backspace') {
      const colDef = columns.find(c => c.key === colKey);
      if (canUpdate && colDef?.isEditable !== false) {
        e.preventDefault();
        applyCellEdit(processedData[rowIndex].id, colKey, '');
      }
      return;
    }

    // Arrow navigation
    let nextRow = rowIndex;
    let nextCol = colIndex;

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      nextRow = Math.max(0, rowIndex - 1);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      nextRow = Math.min(processedData.length - 1, rowIndex + 1);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      nextCol = Math.max(0, colIndex - 1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      nextCol = Math.min(visibleColumns.length - 1, colIndex + 1);
    } else if (e.key === 'Tab') {
      e.preventDefault();
      if (e.shiftKey) {
        nextCol = Math.max(0, colIndex - 1);
      } else {
        nextCol = Math.min(visibleColumns.length - 1, colIndex + 1);
      }
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      // Type printable character directly into cell
      const colDef = columns.find(c => c.key === colKey);
      if (canUpdate && colDef?.isEditable !== false) {
        e.preventDefault();
        setSelectedCell({ rowId: processedData[rowIndex].id, colKey });
        selectEditorOnFocus.current = false;
        setEditingCell({ rowId: processedData[rowIndex].id, colKey });
        setEditValue(e.key);
        return;
      }
    }

    if (nextRow !== rowIndex || nextCol !== colIndex) {
      const targetRow = processedData[nextRow];
      const targetCol = visibleColumns[nextCol];
      if (targetRow && targetCol) {
        if (windowed && tableContainerRef.current) {
          const container = tableContainerRef.current;
          const top = nextRow * ROW_HEIGHT;
          if (top < container.scrollTop || top + ROW_HEIGHT > container.scrollTop + viewportHeight - headerHeight) {
            container.scrollTop = top;
            setScrollTop(top);
          }
          pendingCellFocus.current = { rowIndex: nextRow, colKey: targetCol.key };
        }
        setSelectedCell({ rowId: targetRow.id, colKey: targetCol.key });
        onSelectionChange(new Set([targetRow.id]));
      }
    }
  };

  // Column Resizing Handlers
  const resizingColRef = useRef<{ key: string; startX: number; startWidth: number } | null>(null);

  const handleStartResize = (e: React.MouseEvent, colKey: string, currentWidth: number) => {
    e.preventDefault();
    e.stopPropagation();
    resizingColRef.current = { key: colKey, startX: e.clientX, startWidth: currentWidth };

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!resizingColRef.current) return;
      const diff = moveEvent.clientX - resizingColRef.current.startX;
      const newW = Math.max(resizingColRef.current.startWidth + diff, 60);
      setCustomWidths(prev => ({ ...prev, [resizingColRef.current!.key]: newW }));
    };

    const handleMouseUp = () => {
      resizingColRef.current = null;
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  // Double-click column border to auto-fit
  const handleAutoFitColumn = (colKey: string) => {
    const colDef = columns.find(c => c.key === colKey);
    if (!colDef) return;
    let maxLen = colDef.label.length;
    data.slice(0, 50).forEach(r => {
      const val = String((r as any)[colKey] ?? '');
      if (val.length > maxLen) maxLen = val.length;
    });
    const autoWidth = Math.min(Math.max(maxLen * 9 + 36, 90), 450);
    setCustomWidths(prev => ({ ...prev, [colKey]: autoWidth }));
  };

  // Native clipboard events support Ctrl+C/V without requiring clipboard-read permission.
  const selectedText = () => {
    const row = data.find(item => item.id === selectedCell?.rowId);
    return row && selectedCell ? String(row[selectedCell.colKey] ?? '') : '';
  };
  const handleCopySelection = async () => {
    if (!selectedCell) return;
    try { await navigator.clipboard.writeText(selectedText()); }
    catch { setEditError('Clipboard access was blocked. Select the cell and use Ctrl+C.'); }
  };
  const pasteText = (text: string) => {
    if (!selectedCell || !canUpdate) return;
    const rowIndex = processedData.findIndex(row => row.id === selectedCell.rowId);
    const colIndex = visibleColumns.findIndex(col => col.key === selectedCell.colKey);
    if (rowIndex < 0 || colIndex < 0) return;
    const rows = text.replace(/\r/g, '').replace(/\n$/, '').split('\n').map(row => row.split('\t'));
    const edits: Array<{ rowId: string; colKey: keyof T & string; value: string }> = [];
    for (let r = 0; r < rows.length; r++) {
      for (let c = 0; c < rows[r].length; c++) {
        const row = processedData[rowIndex + r];
        const col = visibleColumns[colIndex + c];
        if (!row || !col) { setEditError('The pasted range extends beyond the table.'); return; }
        edits.push({ rowId: row.id, colKey: col.key, value: rows[r][c] });
      }
    }
    applyEdits(edits);
  };
  const handlePasteSelection = async () => {
    if (!selectedCell || !canUpdate) return;
    try { pasteText(await navigator.clipboard.readText()); }
    catch { setEditError('Clipboard access was blocked. Select an editable cell and use Ctrl+V.'); }
  };

  // Context Menu Handlers
  const handleContextMenu = (e: React.MouseEvent, type: 'cell' | 'header' | 'rowHeader', rowId?: string, rowIndex?: number, colKey?: string) => {
    e.preventDefault();
    e.stopPropagation();

    // Select row or cell if not already
    if (rowId) {
      if (!selectedIds.has(rowId)) {
        onSelectionChange(new Set([rowId]));
      }
      if (colKey) {
        setSelectedCell({ rowId, colKey: colKey as keyof T & string });
      }
    }

    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      type,
      rowId,
      rowIndex,
      colKey,
    });
  };

  // Selected cell value for formula bar
  const selectedCellValue = useMemo(() => {
    if (!selectedCell) return '';
    const row = data.find(r => r.id === selectedCell.rowId);
    if (!row) return '';
    return String((row as any)[selectedCell.colKey] ?? '');
  }, [selectedCell, data]);

  // Coordinate label (e.g. A1, B4)
  const coordLabel = useMemo(() => {
    if (!selectedCell) return '—';
    const rowIdx = processedData.findIndex(r => r.id === selectedCell.rowId);
    const colIdx = visibleColumns.findIndex(c => c.key === selectedCell.colKey);
    if (rowIdx === -1 || colIdx === -1) return '—';
    const colLetter = String.fromCharCode(65 + (colIdx % 26));
    return `${colLetter}${rowIdx + 1}`;
  }, [selectedCell, processedData, visibleColumns]);

  // Selected Column Label for formula bar
  const selectedColLabel = useMemo(() => {
    if (!selectedCell) return '';
    const col = columns.find(c => c.key === selectedCell.colKey);
    return col ? col.label : '';
  }, [selectedCell, columns]);

  return (
    <div
      ref={rootContainerRef}
      onCopy={event => {
        if (!selectedCell || (event.target instanceof HTMLElement && ['INPUT', 'TEXTAREA'].includes(event.target.tagName))) return;
        event.preventDefault();
        event.clipboardData.setData('text/plain', selectedText());
      }}
      onPaste={event => {
        if (event.target instanceof HTMLElement && ['INPUT', 'TEXTAREA'].includes(event.target.tagName)) return;
        event.preventDefault();
        pasteText(event.clipboardData.getData('text/plain'));
      }}
      style={{
        height: isFullscreen ? '100dvh' : heightMode === 'fit' ? undefined : `${currentHeightPx}px`,
        maxHeight: isFullscreen ? '100dvh' : undefined,
      }}
      className={`min-w-0 w-full flex flex-col ${heightMode === 'fit' ? 'min-h-0' : 'min-h-[320px]'} bg-white border border-ink-text/15 rounded-lg shadow-2xs select-none transition-[height] duration-75 ${
        isFullscreen ? 'fixed inset-0 z-[9990] rounded-none p-3 shadow-2xl' : 'relative flex-1'
      }`}
    >
      {editError && <p role="alert" className="shrink-0 bg-red-50 text-red-700 p-2 text-xs">{editError}</p>}
      {/* 1. Formula Bar & Column Controls Toolbar */}
      <div className="shrink-0 flex flex-wrap items-center gap-2 py-1.5 px-3 bg-vanilla-surface border-b border-ink-text/10 text-xs">
        {/* Cell Reference Box */}
        <div
          title="Active cell reference"
          className="w-14 px-1.5 py-0.5 font-mono text-center font-bold text-ink-text/80 bg-white border border-ink-text/20 rounded shadow-2xs select-none text-[11px]"
        >
          {coordLabel}
        </div>

        {/* fx symbol */}
        <div className="font-serif italic font-bold text-burnt-orange px-1 select-none text-sm">fx</div>

        {/* Column Label Badge */}
        {selectedColLabel && (
          <span className="hidden sm:inline-block max-w-[160px] truncate px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-[11px] font-medium border border-gray-200">
            {selectedColLabel}
          </span>
        )}

        {/* Formula Input */}
        <input
          type="text"
          aria-label="Formula bar"
          placeholder={selectedCell ? `Value of ${selectedColLabel || 'selected cell'}` : 'Select a cell to view or edit value (Ctrl+S to save)'}
          value={externalFormulaValue !== undefined ? externalFormulaValue : selectedCellValue}
          disabled={!selectedCell || !onCellChange || !canUpdate || columns.find(col => col.key === selectedCell.colKey)?.isEditable === false}
          onChange={e => {
            if (externalOnFormulaChange) {
              externalOnFormulaChange(e.target.value);
            } else if (selectedCell && onCellChange) {
              applyCellEdit(selectedCell.rowId, selectedCell.colKey, e.target.value);
            }
          }}
          className="min-w-0 flex-1 px-2.5 py-0.5 bg-white border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-brand-steel disabled:bg-gray-100 text-gray-800 font-mono text-xs"
        />

        {/* Save Status Badge */}
        {modifiedCells.size > 0 && (
          <span className="flex items-center gap-1 px-2 py-0.5 bg-amber-100 text-amber-900 border border-amber-300 rounded text-[11px] font-semibold animate-pulse">
            <span>●</span> {modifiedCells.size} unsaved
          </span>
        )}

        {saveStatus === 'saving' && (
          <span className="text-[11px] text-blue-700 font-medium">Saving…</span>
        )}

        {/* Column Show/Hide Dropdown */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowColMenu(prev => !prev)}
            className="px-2.5 py-1 bg-white border border-gray-300 rounded text-gray-700 hover:bg-gray-50 text-[11px] font-medium flex items-center gap-1 shadow-2xs"
          >
            <span>Columns ({visibleColumns.length}/{columns.length}) ▾</span>
          </button>

          {showColMenu && (
            <div
              className="absolute right-0 mt-1 w-64 bg-white border border-gray-200 rounded-lg shadow-xl p-2.5 z-50 max-h-80 overflow-y-auto space-y-1 text-xs"
              onMouseLeave={() => setShowColMenu(false)}
            >
              <div className="flex items-center justify-between border-b pb-1.5 mb-1">
                <span className="font-bold text-gray-800 text-xs">Manage Columns</span>
                <button
                  type="button"
                  onClick={handleResetLayout}
                  className="text-[10px] text-blue-600 hover:underline"
                >
                  Reset layout
                </button>
              </div>

              <input
                type="text"
                placeholder="Search columns…"
                value={colMenuSearch}
                onChange={e => setColMenuSearch(e.target.value)}
                className="w-full px-2 py-1 text-xs border rounded mb-2"
              />

              <div className="flex gap-2 text-[10px] pb-1 border-b mb-1">
                <button
                  type="button"
                  onClick={() => setHiddenColumns(new Set())}
                  className="text-blue-700 font-semibold hover:underline"
                >
                  Show all
                </button>
                <span className="text-gray-300">|</span>
                <button
                  type="button"
                  onClick={() => {
                    const nonFrozen = new Set<string>();
                    columns.forEach(c => {
                      if (!frozenColKeys.has(c.key) && c.key !== columns[0]?.key) {
                        nonFrozen.add(c.key);
                      }
                    });
                    setHiddenColumns(nonFrozen);
                  }}
                  className="text-gray-600 hover:underline"
                >
                  Hide optional
                </button>
              </div>

              <div className="space-y-1">
                {columns
                  .filter(c => !colMenuSearch || c.label.toLowerCase().includes(colMenuSearch.toLowerCase()))
                  .map(col => {
                    const isFrozen = frozenColKeys.has(col.key);
                    return (
                      <label key={col.key} className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                        <input
                          type="checkbox"
                          disabled={isFrozen}
                          checked={!hiddenColumns.has(col.key)}
                          onChange={() => {
                            if (isFrozen) return;
                            const next = new Set(hiddenColumns);
                            if (next.has(col.key)) next.delete(col.key);
                            else next.add(col.key);
                            setHiddenColumns(next);
                          }}
                          className="text-brand-steel rounded"
                        />
                        <span className={`truncate ${isFrozen ? 'font-semibold text-gray-900' : 'text-gray-700'}`}>
                          {col.label} {isFrozen ? '(Frozen)' : ''}
                        </span>
                      </label>
                    );
                  })}
              </div>
            </div>
          )}
        </div>

        {/* Height Presets & Fullscreen Controls (Section 9A) */}
        <div className="flex items-center gap-1 border-l border-gray-300 pl-2">
          <div className="flex items-center bg-white border border-gray-300 rounded overflow-hidden text-[11px] shadow-2xs">
            <button
              type="button"
              title="Compact table height (380px)"
              onClick={() => setHeightMode('compact')}
              className={`px-2 py-0.5 font-medium transition-colors ${
                heightMode === 'compact'
                  ? 'bg-blue-50 text-blue-800 font-bold border-r border-blue-200'
                  : 'text-gray-600 hover:bg-gray-50 border-r border-gray-200'
              }`}
            >
              Compact
            </button>
            <button
              type="button"
              title="Standard table height (540px)"
              onClick={() => setHeightMode('standard')}
              className={`px-2 py-0.5 font-medium transition-colors ${
                heightMode === 'standard'
                  ? 'bg-blue-50 text-blue-800 font-bold border-r border-blue-200'
                  : 'text-gray-600 hover:bg-gray-50 border-r border-gray-200'
              }`}
            >
              Standard
            </button>
            <button
              type="button"
              title="Large table height (720px)"
              onClick={() => setHeightMode('large')}
              className={`px-2 py-0.5 font-medium transition-colors ${
                heightMode === 'large'
                  ? 'bg-blue-50 text-blue-800 font-bold border-r border-blue-200'
                  : 'text-gray-600 hover:bg-gray-50 border-r border-gray-200'
              }`}
            >
              Large
            </button>
            <button
              type="button"
              title="Fit to screen height (fills available viewport height)"
              onClick={() => {
                setHeightMode('fit');
              }}
              className={`px-2 py-0.5 font-medium transition-colors ${
                heightMode === 'fit'
                  ? 'bg-blue-50 text-blue-800 font-bold'
                  : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              Fit
            </button>
          </div>

          <button
            type="button"
            title={isFullscreen ? 'Exit fullscreen (Esc)' : 'Expand table to fullscreen'}
            onClick={() => setIsFullscreen(prev => !prev)}
            className="p-1 px-1.5 bg-white hover:bg-gray-50 border border-gray-300 rounded text-gray-700 font-bold text-xs shadow-2xs flex items-center gap-1"
          >
            <span>{isFullscreen ? '✕ Exit' : '⛶'}</span>
          </button>
        </div>
      </div>

      {/* 2. Active Column Filter Chips */}
      {Object.keys(columnFilters).length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 px-3 py-1 bg-blue-50/60 border-b border-blue-100 text-xs">
          <span className="text-blue-900 font-semibold text-[11px]">Active Filters:</span>
          {Object.entries(columnFilters).map(([k, f]) => {
            const col = columns.find(c => c.key === k);
            return (
              <span key={k} className="flex items-center gap-1 px-2 py-0.5 bg-white border border-blue-200 rounded-full text-[10px] text-blue-800">
                <span>{col?.label || k}: {f.textValue || `${f.minNumber ?? ''}-${f.maxNumber ?? ''}`}</span>
                <button
                  type="button"
                  onClick={() => {
                    const next = { ...columnFilters };
                    delete next[k];
                    setColumnFilters(next);
                  }}
                  className="text-blue-500 hover:text-red-700 font-bold ml-0.5"
                >
                  ×
                </button>
              </span>
            );
          })}
          <button
            type="button"
            onClick={() => setColumnFilters({})}
            className="text-[10px] text-blue-700 underline font-semibold ml-2 hover:text-blue-900"
          >
            Clear all filters
          </button>
        </div>
      )}

      {/* 3. Main Spreadsheet Table Grid */}
      <div
        ref={tableContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-auto bg-white relative min-h-0"
      >
        <table
          aria-rowcount={processedData.length + (headerGroups?.length ? 2 : 1)}
          style={{ width: `${totalTableWidth}px`, minWidth: `${totalTableWidth}px` }}
          className="border-collapse table-fixed text-left text-xs select-none"
        >
          {/* Explicit colgroup to guarantee exact column widths */}
          <colgroup>
            <col style={{ width: '36px' }} />
            <col style={{ width: '48px' }} />
            {visibleColumns.map(col => {
              const w = getColWidth(col.key, col.label, col.width);
              return <col key={col.key} style={{ width: `${w}px` }} />;
            })}
          </colgroup>

          <thead>
            {/* Tier 1: Grouped Column Headers (FOR COMPONENT, FOR CONSUMABLES, etc.) */}
            {computedHeaderGroups.length > 0 && (
              <tr
                ref={groupHeaderRef}
                className="sticky top-0 z-20 bg-vanilla-surface border-b border-ink-text/15 shadow-2xs"
              >
                {/* Frozen Checkbox + Row # header corner */}
                <th
                  colSpan={2}
                  className="p-1 border-r border-ink-text/10 bg-vanilla-surface sticky left-0 z-30 select-none"
                />
                {computedHeaderGroups.map((grp, gIdx) => (
                  <th
                    key={gIdx}
                    colSpan={grp.colSpan}
                    style={{ width: `${grp.pixelWidth}px` }}
                    className={
                      grp.className ||
                      'p-1.5 text-center font-bold text-white uppercase tracking-wider text-[11px] border-r border-ink-text/20 bg-brand-navy select-none truncate'
                    }
                  >
                    {grp.label}
                  </th>
                ))}
              </tr>
            )}

            {/* Tier 2: Column Headers Row */}
            <tr
              style={{ top: `${computedHeaderGroups.length > 0 ? groupHeaderHeight : 0}px` }}
              className="sticky z-20 bg-vanilla-surface border-b border-ink-text/15 shadow-2xs"
            >
              {/* 1. Select All Checkbox */}
              <th
                style={{ width: '36px', left: 0 }}
                className="p-1 text-center border-r border-ink-text/10 bg-vanilla-surface sticky z-30"
              >
                <input
                  type="checkbox"
                  aria-label="Select all rows"
                  checked={allSelected}
                  ref={input => {
                    if (input) input.indeterminate = someSelected;
                  }}
                  onChange={handleToggleSelectAll}
                  className="cursor-pointer text-burnt-orange rounded"
                />
              </th>

              {/* 2. Row # Header */}
              <th
                style={{ width: '48px', left: '36px' }}
                className={`p-1 text-center font-bold text-ink-text/70 border-r border-ink-text/10 bg-vanilla-surface select-none sticky z-30 ${
                  stickyLeftOffsets.offsets.size === 0 && isScrolledLeft
                    ? 'shadow-[4px_0_6px_-2px_rgba(0,0,0,0.12)]'
                    : ''
                }`}
              >
                #
              </th>

              {/* Data Column Headers */}
              {visibleColumns.map(col => {
                const isFrozen = frozenColKeys.has(col.key);
                const stickyOffset = stickyLeftOffsets.offsets.get(col.key);
                const isLastFrozen = col.key === stickyLeftOffsets.lastFrozenKey;
                const colW = getColWidth(col.key, col.label, col.width);

                return (
                  <th
                    key={col.key}
                    title={`${col.label} (Double-click border to auto-fit)`}
                    style={{
                      width: `${colW}px`,
                      minWidth: `${col.minWidth || 60}px`,
                      maxWidth: `${col.maxWidth || 600}px`,
                      left: isFrozen ? `${stickyOffset}px` : undefined,
                    }}
                    onContextMenu={e => handleContextMenu(e, 'header', undefined, undefined, col.key)}
                    onClick={() => {
                      setSortConfig(prev => {
                        if (!prev || prev.key !== col.key) return { key: col.key, direction: 'asc' };
                        if (prev.direction === 'asc') return { key: col.key, direction: 'desc' };
                        return null; // clear sort
                      });
                    }}
                    className={`relative p-2 font-semibold text-ink-text border-r border-ink-text/10 select-none bg-vanilla-surface cursor-pointer group hover:bg-vanilla-surface/80 ${
                      col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'
                    } ${
                      isFrozen ? 'sticky z-30 shadow-2xs font-bold' : ''
                    } ${isLastFrozen && isScrolledLeft ? 'shadow-[4px_0_6px_-2px_rgba(0,0,0,0.15)] border-r-2 border-r-gray-400' : ''}`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="whitespace-normal break-words leading-tight line-clamp-3">
                        {col.label}
                      </span>
                      {sortConfig?.key === col.key && (
                        <span className="text-burnt-orange font-bold text-xs ml-0.5">
                          {sortConfig.direction === 'asc' ? '▲' : '▼'}
                        </span>
                      )}
                    </div>

                    {/* Drag-to-resize Handle */}
                    <div
                      onMouseDown={e => handleStartResize(e, col.key, colW)}
                      onDoubleClick={e => {
                        e.stopPropagation();
                        handleAutoFitColumn(col.key);
                      }}
                      title="Drag to resize, double click to auto-fit"
                      className="absolute right-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-burnt-orange z-35"
                    />
                  </th>
                );
              })}
            </tr>
          </thead>

          {/* Table Body */}
          <tbody>
            {isLoading ? (
              <tr className="h-48">
                <td
                  colSpan={visibleColumns.length + 2}
                  className="text-center p-8 bg-white border-b border-gray-200"
                >
                  <div className="flex flex-col items-center justify-center gap-2">
                    <div className="animate-spin h-6 w-6 border-2 border-brand-navy border-t-transparent rounded-full" />
                    <span className="text-xs text-gray-500 font-medium">Loading records…</span>
                  </div>
                </td>
              </tr>
            ) : processedData.length === 0 ? (
              <tr className="h-48">
                <td
                  colSpan={visibleColumns.length + 2}
                  className="text-center p-8 bg-white border-b border-gray-200"
                >
                  <div className="flex flex-col items-center justify-center gap-2 text-gray-400">
                    <span className="text-3xl">📋</span>
                    <p className="font-medium text-gray-600 text-xs">{emptyMessage}</p>
                    {canCreate && onAddRow && (
                      <button
                        type="button"
                        onClick={onAddRow}
                        className="mt-2 px-3 py-1.5 bg-burnt-orange hover:bg-burnt-orange-dark text-white rounded font-medium shadow-xs transition-colors"
                      >
                        + Add row
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ) : (
              <>
              {windowStart > 0 && <tr aria-hidden="true"><td colSpan={visibleColumns.length + 2}
                style={{ height: windowStart * ROW_HEIGHT, padding: 0, border: 0 }} /></tr>}
              {renderedData.map((row, windowIndex) => {
                const rIdx = windowStart + windowIndex;
                const isRowSelected = selectedIds.has(row.id);
                const customRowClass = getRowClassName ? getRowClassName(row) : '';
                const isZebra = rIdx % 2 === 1;

                return (
                  <tr
                    key={row.id}
                    data-row-index={rIdx}
                    aria-rowindex={rIdx + (headerGroups?.length ? 3 : 2)}
                    onClick={() => {
                      const next = new Set(selectedIds);
                      if (next.has(row.id)) next.delete(row.id);
                      else next.add(row.id);
                      onSelectionChange(next);
                    }}
                    onContextMenu={e => handleContextMenu(e, 'cell', row.id, rIdx)}
                    className={`h-7 border-b border-ink-text/10 transition-colors ${
                      isRowSelected
                        ? 'bg-burnt-orange/15 font-medium'
                        : customRowClass ||
                          (isZebra ? 'bg-vanilla-bg/25 hover:bg-vanilla-surface/50' : 'bg-white hover:bg-vanilla-bg/40')
                    }`}
                  >
                    {/* Row Checkbox */}
                    <td
                      style={{ width: '36px', left: 0 }}
                      onClick={e => handleRowCheckbox(row.id, rIdx, e)}
                      className={`text-center border-r border-gray-300 select-none cursor-pointer sticky z-10 ${
                        isRowSelected ? 'bg-blue-200/70' : isZebra ? 'bg-gray-100/90' : 'bg-white'
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

                    {/* Row # */}
                    <td
                      style={{ width: '48px', left: '36px' }}
                      onContextMenu={e => handleContextMenu(e, 'rowHeader', row.id, rIdx)}
                      onClick={e => handleRowCheckbox(row.id, rIdx, e)}
                      className={`text-center font-mono text-gray-500 border-r border-gray-300 select-none cursor-pointer sticky z-10 ${
                        isRowSelected ? 'bg-blue-200/70 font-bold text-blue-900' : isZebra ? 'bg-gray-100/90' : 'bg-white'
                      } ${
                        stickyLeftOffsets.offsets.size === 0 && isScrolledLeft
                          ? 'shadow-[4px_0_6px_-2px_rgba(0,0,0,0.12)]'
                          : ''
                      }`}
                    >
                      {row.row_index ?? rIdx + 1}
                    </td>

                    {/* Data Cells */}
                    {visibleColumns.map(col => {
                      const isCellSelected = selectedCell?.rowId === row.id && selectedCell?.colKey === col.key;
                      const isCellEditing = editingCell?.rowId === row.id && editingCell?.colKey === col.key;
                      const isModified = modifiedCells.has(`${row.id}:${col.key}`);
                      const cellValue = (row as any)[col.key];
                      const isFrozen = frozenColKeys.has(col.key);
                      const stickyOffset = stickyLeftOffsets.offsets.get(col.key);
                      const isLastFrozen = col.key === stickyLeftOffsets.lastFrozenKey;
                      const colW = getColWidth(col.key, col.label, col.width);

                      return (
                        <td
                          key={col.key}
                          data-column-key={col.key}
                          tabIndex={0}
                          title={cellValue !== null && cellValue !== undefined ? String(cellValue) : ''}
                          style={{
                            width: `${colW}px`,
                            minWidth: `${col.minWidth || 60}px`,
                            maxWidth: `${col.maxWidth || 600}px`,
                            left: isFrozen ? `${stickyOffset}px` : undefined,
                          }}
                          onKeyDown={e => handleCellKeyDown(e, rIdx, col.key)}
                          onClick={e => {
                            e.stopPropagation();
                            setSelectedCell({ rowId: row.id, colKey: col.key });
                            setEditingCell(null);
                            onSelectionChange(new Set([row.id]));
                          }}
                          onDoubleClick={e => {
                            e.stopPropagation();
                            handleStartEdit(row.id, col.key);
                          }}
                          onContextMenu={e => handleContextMenu(e, 'cell', row.id, rIdx, col.key)}
                          className={`relative border-r border-gray-200 px-2 py-0.5 truncate cursor-cell select-none outline-none ${
                            col.align === 'right' ? 'text-right font-mono tabular-nums' : col.align === 'center' ? 'text-center' : 'text-left'
                          } ${
                            isFrozen
                              ? `sticky z-10 ${isRowSelected ? 'bg-blue-100' : isZebra ? 'bg-gray-100' : 'bg-white'}`
                              : ''
                          } ${
                            isLastFrozen && isScrolledLeft ? 'shadow-[4px_0_6px_-2px_rgba(0,0,0,0.15)] border-r-2 border-r-gray-400' : ''
                          } ${
                            isCellSelected ? 'ring-2 ring-blue-600 ring-inset bg-blue-50/60 z-15' : ''
                          } ${isModified && !isCellSelected ? 'bg-amber-50/80' : ''}`}
                        >
                          {/* Dirty Triangle Marker */}
                          {isModified && (
                            <span
                              title="Unsaved modification"
                              className="absolute top-0 right-0 w-0 h-0 border-t-[6px] border-t-amber-500 border-l-[6px] border-l-transparent z-10"
                            />
                          )}

                          {isCellEditing ? (
                            <input
                              ref={cellInputRef}
                              aria-label={`Edit ${col.label}`}
                              onClick={event => event.stopPropagation()}
                              onDoubleClick={event => event.stopPropagation()}
                              onContextMenu={event => event.stopPropagation()}
                              type="text"
                              value={editValue}
                              onChange={e => setEditValue(e.target.value)}
                              onBlur={() => handleCommitEdit()}
                              onKeyDown={e => {
                                // Let Ctrl+S/Z keep their existing global/native behavior.
                                if (e.key === 'Enter' || e.key === 'Escape' || e.key === 'Tab') e.stopPropagation();
                                if (e.key === 'Enter') { e.preventDefault(); handleCommitEdit(); }
                                if (e.key === 'Escape') setEditingCell(null);
                                if (e.key === 'Tab') {
                                  e.preventDefault();
                                  handleCommitEdit();
                                  const curIdx = visibleColumns.findIndex(c => c.key === col.key);
                                  if (curIdx < visibleColumns.length - 1) {
                                    handleStartEdit(row.id, visibleColumns[curIdx + 1].key);
                                  }
                                }
                              }}
                              className="w-full h-full px-1 py-0 bg-white border border-blue-500 outline-none font-sans text-xs text-gray-900 shadow-inner"
                            />
                          ) : col.render ? (
                            col.render(cellValue, row, isRowSelected)
                          ) : (
                            <span className="text-xs text-gray-800">
                              {cellValue !== null && cellValue !== undefined && String(cellValue).trim() !== ''
                                ? String(cellValue)
                                : '—'}
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
              {windowEnd < processedData.length && <tr aria-hidden="true"><td colSpan={visibleColumns.length + 2}
                style={{ height: (processedData.length - windowEnd) * ROW_HEIGHT, padding: 0, border: 0 }} /></tr>}
              </>
            )}
          </tbody>
        </table>
      </div>

      {/* 4. Grid Footer Status Bar */}
      <div className="flex flex-wrap items-center justify-between px-3 py-1.5 bg-gray-100 border-t border-gray-300 text-[11px] text-gray-600 select-none">
        <div className="flex items-center gap-3">
          <span>
            Showing <strong className="text-gray-900">{processedData.length}</strong> of{' '}
            <strong className="text-gray-900">{data.length}</strong> records
          </span>
          {selectedIds.size > 0 && (
            <span className="text-blue-800 font-semibold bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
              {selectedIds.size} row{selectedIds.size > 1 ? 's' : ''} selected
            </span>
          )}
          {lastModifiedText && (
            <span className="text-gray-500 hidden md:inline">| {lastModifiedText}</span>
          )}
        </div>

        <div className="flex items-center gap-4 text-gray-500">
          <span>Tip: Double-click cell to edit • Ctrl+S to save • Right-click for menu</span>
          {onSave && canUpdate && (
            <button
              type="button"
              disabled={saveStatus === 'saving' || modifiedCells.size === 0}
              onClick={() => void onSave()}
              className="px-2.5 py-0.5 bg-brand-steel hover:bg-brand-navy disabled:opacity-40 text-white rounded font-medium text-[11px] shadow-2xs"
            >
              {saveStatus === 'saving' ? 'Saving…' : `Save (Ctrl+S)${modifiedCells.size ? ` (${modifiedCells.size})` : ''}`}
            </button>
          )}
        </div>
      </div>

      {/* 5. Bottom Resize Drag Handle (Section 9A) */}
      {!isFullscreen && (
        <div
          role="separator"
          tabIndex={0}
          aria-orientation="horizontal"
          aria-label="Drag to resize table height"
          title="Drag up/down to resize height (min 320px) • Double-click for Fit to screen"
          onMouseDown={handleStartResizeHeight}
          onDoubleClick={() => {
            setHeightMode('fit');
          }}
          onKeyDown={handleResizeHandleKeyDown}
          className={`h-2.5 w-full bg-gray-100 hover:bg-burnt-orange/20 border-t border-gray-300 flex items-center justify-center cursor-row-resize select-none transition-colors group focus:outline-none focus:ring-1 focus:ring-burnt-orange ${
            isResizingHeight ? 'bg-burnt-orange/30' : ''
          }`}
        >
          <div className="w-12 h-1 bg-gray-400 group-hover:bg-burnt-orange rounded-full flex items-center justify-center space-x-1">
            <span className="w-1 h-1 bg-white rounded-full"></span>
            <span className="w-1 h-1 bg-white rounded-full"></span>
            <span className="w-1 h-1 bg-white rounded-full"></span>
          </div>
        </div>
      )}

      {/* 6. Custom Right-Click Context Menu (Rendered via Portal) */}
      {contextMenu &&
        createPortal(
          <div
            className="fixed inset-0 z-[9999]"
            onClick={() => setContextMenu(null)}
            onContextMenu={e => {
              e.preventDefault();
              setContextMenu(null);
            }}
          >
            <div
              style={{
                top: Math.min(contextMenu.y, window.innerHeight - 260),
                left: Math.min(contextMenu.x, window.innerWidth - 220),
              }}
              className="fixed bg-white border border-gray-200 rounded-lg shadow-2xl py-1 w-52 text-xs text-gray-800 z-[10000] divide-y divide-gray-100"
              onClick={e => e.stopPropagation()}
            >
              {/* Cell context options */}
              {contextMenu.type === 'cell' && (
                <>
                  <div className="py-1">
                    <button
                      type="button"
                      disabled={!canUpdate || Boolean(contextMenu.colKey && columns.find(c => c.key === contextMenu.colKey)?.isEditable === false)}
                      onClick={() => {
                        if (contextMenu.rowId && contextMenu.colKey) {
                          handleStartEdit(contextMenu.rowId, contextMenu.colKey as keyof T & string);
                        }
                        setContextMenu(null);
                      }}
                      className="w-full text-left px-3 py-1.5 hover:bg-gray-100 disabled:opacity-40 disabled:hover:bg-white flex items-center justify-between"
                    >
                      <span>Edit cell</span>
                      <kbd className="text-[10px] text-gray-400">F2</kbd>
                    </button>

                    <button
                      type="button"
                      disabled={!canUpdate}
                      onClick={() => {
                        const targetRow = data.find(r => r.id === contextMenu.rowId);
                        if (targetRow) openRowEditor(targetRow);
                        setContextMenu(null);
                      }}
                      className="w-full text-left px-3 py-1.5 hover:bg-gray-100 disabled:opacity-40 flex items-center justify-between"
                    >
                      <span>Edit row…</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        handleCopySelection();
                        setContextMenu(null);
                      }}
                      className="w-full text-left px-3 py-1.5 hover:bg-gray-100 flex items-center justify-between"
                    >
                      <span>Copy</span>
                      <kbd className="text-[10px] text-gray-400">Ctrl+C</kbd>
                    </button>

                    {canUpdate && (
                      <button
                        type="button"
                        disabled={columns.find(col => col.key === contextMenu.colKey)?.isEditable === false}
                        onClick={() => {
                          void handlePasteSelection();
                          setContextMenu(null);
                        }}
                        className="w-full text-left px-3 py-1.5 hover:bg-gray-100 flex items-center justify-between"
                      >
                        <span>Paste</span>
                        <kbd className="text-[10px] text-gray-400">Ctrl+V</kbd>
                      </button>
                    )}

                    {canUpdate && (
                      <button
                        type="button"
                        disabled={columns.find(col => col.key === contextMenu.colKey)?.isEditable === false}
                        onClick={() => {
                          if (contextMenu.rowId && contextMenu.colKey) {
                            applyCellEdit(contextMenu.rowId, contextMenu.colKey as keyof T & string, '');
                          }
                          setContextMenu(null);
                        }}
                        className="w-full text-left px-3 py-1.5 hover:bg-gray-100 text-gray-600 flex items-center justify-between"
                      >
                        <span>Clear cell</span>
                        <kbd className="text-[10px] text-gray-400">Del</kbd>
                      </button>
                    )}
                  </div>

                  <div className="py-1">
                    {canUpdate && onSave && (
                      <button
                        type="button"
                        onClick={() => {
                          void onSave();
                          setContextMenu(null);
                        }}
                        className="w-full text-left px-3 py-1.5 hover:bg-gray-100 text-blue-700 font-semibold flex items-center justify-between"
                      >
                        <span>Save changes</span>
                        <kbd className="text-[10px] text-gray-400">Ctrl+S</kbd>
                      </button>
                    )}

                    {onDiscardChanges && modifiedCells.size > 0 && (
                      <button
                        type="button"
                        onClick={() => {
                          onDiscardChanges();
                          setContextMenu(null);
                        }}
                        className="w-full text-left px-3 py-1.5 hover:bg-gray-100 text-amber-800"
                      >
                        Discard changes
                      </button>
                    )}

                    {canDelete && onDeleteRows && (
                      <button
                        type="button"
                        onClick={() => {
                          const idsToDelete = selectedIds.size > 0 ? Array.from(selectedIds) : contextMenu.rowId ? [contextMenu.rowId] : [];
                          setConfirmDeleteIds(idsToDelete);
                          setContextMenu(null);
                        }}
                        className="w-full text-left px-3 py-1.5 hover:bg-red-50 text-red-600 font-semibold"
                      >
                        Delete row(s)…
                      </button>
                    )}
                  </div>

                  <div className="py-1">
                    {contextMenu.colKey && (
                      <button
                        type="button"
                        onClick={() => {
                          const k = contextMenu.colKey!;
                          setFrozenColKeys(prev => {
                            const next = new Set(prev);
                            if (next.has(k)) next.delete(k);
                            else next.add(k);
                            return next;
                          });
                          setContextMenu(null);
                        }}
                        className="w-full text-left px-3 py-1.5 hover:bg-gray-100"
                      >
                        {frozenColKeys.has(contextMenu.colKey) ? 'Unfreeze column' : 'Freeze up to this column'}
                      </button>
                    )}
                  </div>
                </>
              )}

              {/* Column Header context options */}
              {contextMenu.type === 'header' && (
                <>
                  <div className="py-1">
                    <button
                      type="button"
                      onClick={() => {
                        if (contextMenu.colKey) setSortConfig({ key: contextMenu.colKey, direction: 'asc' });
                        setContextMenu(null);
                      }}
                      className="w-full text-left px-3 py-1.5 hover:bg-gray-100 flex items-center justify-between"
                    >
                      <span>Sort A to Z</span>
                      <span>▲</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (contextMenu.colKey) setSortConfig({ key: contextMenu.colKey, direction: 'desc' });
                        setContextMenu(null);
                      }}
                      className="w-full text-left px-3 py-1.5 hover:bg-gray-100 flex items-center justify-between"
                    >
                      <span>Sort Z to A</span>
                      <span>▼</span>
                    </button>
                    {sortConfig?.key === contextMenu.colKey && (
                      <button
                        type="button"
                        onClick={() => {
                          setSortConfig(null);
                          setContextMenu(null);
                        }}
                        className="w-full text-left px-3 py-1.5 hover:bg-gray-100 text-gray-500"
                      >
                        Clear sort
                      </button>
                    )}
                  </div>

                  <div className="py-1">
                    {contextMenu.colKey && (
                      <button
                        type="button"
                        onClick={() => {
                          handleAutoFitColumn(contextMenu.colKey!);
                          setContextMenu(null);
                        }}
                        className="w-full text-left px-3 py-1.5 hover:bg-gray-100"
                      >
                        Auto-fit column width
                      </button>
                    )}

                    {contextMenu.colKey && (
                      <button
                        type="button"
                        onClick={() => {
                          const k = contextMenu.colKey!;
                          setFrozenColKeys(prev => {
                            const next = new Set(prev);
                            if (next.has(k)) next.delete(k);
                            else next.add(k);
                            return next;
                          });
                          setContextMenu(null);
                        }}
                        className="w-full text-left px-3 py-1.5 hover:bg-gray-100"
                      >
                        {frozenColKeys.has(contextMenu.colKey) ? 'Unfreeze column' : 'Freeze column'}
                      </button>
                    )}

                    {contextMenu.colKey && (
                      <button
                        type="button"
                        disabled={frozenColKeys.has(contextMenu.colKey)}
                        onClick={() => {
                          const next = new Set(hiddenColumns);
                          next.add(contextMenu.colKey!);
                          setHiddenColumns(next);
                          setContextMenu(null);
                        }}
                        className="w-full text-left px-3 py-1.5 hover:bg-gray-100 text-gray-700 disabled:opacity-40"
                      >
                        Hide this column
                      </button>
                    )}
                  </div>
                </>
              )}

              {/* Row Header context options */}
              {contextMenu.type === 'rowHeader' && (
                <div className="py-1">
                  <button
                    type="button"
                    onClick={() => {
                      if (contextMenu.rowId) onSelectionChange(new Set([contextMenu.rowId]));
                      setContextMenu(null);
                    }}
                    className="w-full text-left px-3 py-1.5 hover:bg-gray-100"
                  >
                    Select row
                  </button>

                  {canUpdate && (
                    <button
                      type="button"
                      onClick={() => {
                        const targetRow = data.find(r => r.id === contextMenu.rowId);
                        if (targetRow) openRowEditor(targetRow);
                        setContextMenu(null);
                      }}
                      className="w-full text-left px-3 py-1.5 hover:bg-gray-100"
                    >
                      Edit row…
                    </button>
                  )}

                  {customRowActions && contextMenu.rowId && (() => {
                    const targetRow = data.find(r => r.id === contextMenu.rowId);
                    if (!targetRow) return null;
                    const actions = customRowActions(targetRow);
                    if (!actions || actions.length === 0) return null;
                    return (
                      <div className="py-1 border-t border-gray-100">
                        {actions.map((act, idx) => (
                          <button
                            key={idx}
                            type="button"
                            disabled={act.disabled}
                            onClick={() => {
                              setContextMenu(null);
                              act.onClick(targetRow);
                            }}
                            className={`w-full text-left px-3 py-1.5 hover:bg-gray-100 flex items-center gap-2 ${
                              act.className || 'text-gray-800'
                            }`}
                          >
                            {act.icon}
                            <span>{act.label}</span>
                          </button>
                        ))}
                      </div>
                    );
                  })()}

                  {canDelete && onDeleteRows && (
                    <button
                      type="button"
                      onClick={() => {
                        const idsToDelete = selectedIds.size > 0 ? Array.from(selectedIds) : contextMenu.rowId ? [contextMenu.rowId] : [];
                        setConfirmDeleteIds(idsToDelete);
                        setContextMenu(null);
                      }}
                      className="w-full text-left px-3 py-1.5 hover:bg-red-50 text-red-600 font-semibold border-t border-gray-100"
                    >
                      Delete row(s)…
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>,
          document.body
        )}

      {/* 6. Row Editor Panel Modal */}
      {rowEditorItem && (() => {
        const rowItemId = String((rowEditorItem as any).item_id || rowEditorItem.id || '');
        const rowItemDesc = String(
          (rowEditorItem as any).item_description ||
          (rowEditorItem as any).name ||
          (rowEditorItem as any).description ||
          ''
        );
        const modalTitle = rowItemId && rowItemDesc
          ? `Edit row: ${rowItemId} - ${rowItemDesc}`
          : `Edit row: ${rowItemId}`;

        // Arithmetic check for stock statements
        const hasQtyCols = ['opening_qty', 'receipt_qty', 'issue_qty', 'closing_qty'].every(k =>
          columns.some(c => c.key === k)
        );
        let arithmeticMismatchMsg: string | null = null;
        if (hasQtyCols) {
          const op = parseFloat(rowEditorDraft['opening_qty'] || '0') || 0;
          const rc = parseFloat(rowEditorDraft['receipt_qty'] || '0') || 0;
          const is = parseFloat(rowEditorDraft['issue_qty'] || '0') || 0;
          const cl = parseFloat(rowEditorDraft['closing_qty'] || '0') || 0;
          const expected = op + rc - is;
          if (Math.abs(expected - cl) > 0.01) {
            arithmeticMismatchMsg = `Opening (${op.toFixed(2)}) + Receipt (${rc.toFixed(2)}) - Issue (${is.toFixed(2)}) = ${expected.toFixed(2)}, which differs from entered Closing (${cl.toFixed(2)}) by ${(cl - expected).toFixed(2)}.`;
          }
        }

        return (
          <div className="fixed inset-0 bg-black/50 z-[10000] flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-xl w-full flex flex-col max-h-[85vh] overflow-hidden border border-gray-200">
              {/* Header */}
              <div className="flex items-center justify-between border-b px-5 py-3.5 bg-gray-50">
                <h3 className="text-sm font-bold text-gray-900 truncate pr-2" title={modalTitle}>
                  {modalTitle}
                </h3>
                <button
                  type="button"
                  onClick={handleCloseRowEditor}
                  className="text-gray-400 hover:text-gray-700 text-base font-bold p-1 rounded hover:bg-gray-200 transition-colors"
                  title="Close (Esc)"
                >
                  ✕
                </button>
              </div>

              {/* Error banner if save fails */}
              {rowEditorError && (
                <div className="mx-5 mt-3 p-2.5 bg-red-50 border border-red-200 text-red-700 rounded text-xs flex items-center gap-2">
                  <span>⚠️</span>
                  <span>{rowEditorError}</span>
                </div>
              )}

              {/* Arithmetic mismatch warning banner */}
              {arithmeticMismatchMsg && (
                <div className="mx-5 mt-3 p-2.5 bg-amber-50 border border-amber-200 text-amber-800 rounded text-xs flex items-start gap-2">
                  <span className="shrink-0 mt-0.5">⚠️</span>
                  <div>
                    <span className="font-semibold">Arithmetic check warning: </span>
                    <span>{arithmeticMismatchMsg}</span>
                  </div>
                </div>
              )}

              {/* Form scrollable body */}
              <div className="flex-1 overflow-y-auto p-5 space-y-3.5 text-xs">
                {columns.map(col => {
                  const readOnlyKeys = ['item_id', 'unit', 'item_class', 'store_group'];
                  const isEditable = canUpdate && col.isEditable !== false && !readOnlyKeys.includes(col.key);
                  const currentVal = rowEditorDraft[col.key] ?? '';
                  const isNumericCol = col.key.includes('qty') || col.key.includes('value') || col.key.includes('rate') || col.key.includes('amount');
                  const isValueCol = col.key.includes('value') || col.key.includes('rate') || col.key.includes('amount');

                  return (
                    <div key={col.key} className="space-y-1">
                      <div className="flex items-center justify-between">
                        <label htmlFor={`edit-row-${rowEditorItem.id}-${col.key}`} className="font-semibold text-gray-700">
                          {col.label}
                          {!isEditable && <span className="ml-1.5 text-[10px] text-gray-400 font-normal">(Read-only)</span>}
                        </label>
                        {isValueCol && currentVal && !isNaN(parseFloat(currentVal)) && (
                          <span className="text-[11px] font-mono text-emerald-700 font-semibold">
                            Preview: ₹ {parseFloat(currentVal).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </span>
                        )}
                      </div>
                      {isEditable ? (
                        <div>
                          <input
                            type="text"
                            id={`edit-row-${rowEditorItem.id}-${col.key}`}
                            value={currentVal}
                            onChange={e => {
                              const nextVal = e.target.value;
                              setRowEditorDraft(prev => ({ ...prev, [col.key]: nextVal }));
                              if (!onSaveRow) {
                                applyCellEdit(rowEditorItem.id, col.key, nextVal);
                              }
                            }}
                            placeholder={isNumericCol ? 'Empty (null)' : 'Enter value'}
                            className="w-full px-2.5 py-1.5 border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 font-mono text-xs bg-white text-gray-900"
                          />
                          {isNumericCol && (
                            <p className="text-[10px] text-gray-400 mt-0.5">
                              {col.key.includes('qty') ? 'Quantity (2 decimals, empty = null)' : 'Value (currency ₹, empty = null)'}
                            </p>
                          )}
                        </div>
                      ) : (
                        <div className="px-2.5 py-1.5 bg-gray-100 border border-gray-200 rounded text-gray-600 font-mono text-xs select-none">
                          {currentVal || '—'}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Sticky Footer */}
              <div className="flex items-center justify-between px-5 py-3 border-t bg-gray-50 shrink-0">
                <div className="text-[11px] text-gray-500">
                  {isRowEditorDirty ? (
                    <span className="text-amber-700 font-medium">Unsaved changes (Ctrl+S to save)</span>
                  ) : (
                    <span>No changes made</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleCloseRowEditor}
                    disabled={isSavingRowEditor}
                    className="px-3.5 py-1.5 bg-white border border-gray-300 hover:bg-gray-100 text-gray-700 rounded font-semibold text-xs transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleSaveRowEditor}
                    disabled={!isRowEditorDirty || isSavingRowEditor}
                    className="flex items-center gap-1.5 px-4 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded font-semibold text-xs shadow-xs transition-colors"
                  >
                    {isSavingRowEditor ? (
                      <>
                        <span className="inline-block w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        <span>Saving…</span>
                      </>
                    ) : (
                      <span>Save</span>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* 7. Row Delete Confirmation Dialog */}
      {confirmDeleteIds && (
        <div className="fixed inset-0 bg-black/50 z-[10000] flex items-center justify-center p-4">
          <div className="bg-white rounded-lg shadow-2xl max-w-md w-full p-5 space-y-4">
            <h3 className="text-base font-bold text-red-700 flex items-center gap-2">
              <span>⚠️</span> Confirm Deletion
            </h3>
            <p className="text-xs text-gray-600">
              Are you sure you want to delete{' '}
              <strong>
                {confirmDeleteIds.length} row{confirmDeleteIds.length > 1 ? 's' : ''}
              </strong>
              ? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2 pt-2 border-t">
              <button
                type="button"
                onClick={() => setConfirmDeleteIds(null)}
                className="px-3.5 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={async () => {
                  if (onDeleteRows) {
                    await onDeleteRows(confirmDeleteIds);
                  }
                  setConfirmDeleteIds(null);
                }}
                className="px-4 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded text-xs font-semibold shadow-xs"
              >
                Delete {confirmDeleteIds.length} Row{confirmDeleteIds.length > 1 ? 's' : ''}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
