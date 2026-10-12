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
  const [undoStack, setUndoStack] = useState<Array<{ rowId: string; colKey: keyof T & string; oldVal: string; newVal: string }>>([]);
  const [redoStack, setRedoStack] = useState<Array<{ rowId: string; colKey: keyof T & string; oldVal: string; newVal: string }>>([]);

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

  // --- Delete Confirmation Modal State ---
  const [confirmDeleteIds, setConfirmDeleteIds] = useState<string[] | null>(null);

  // --- DOM References ---
  const lastClickedIndexRef = useRef<number | null>(null);
  const cellInputRef = useRef<HTMLInputElement>(null);
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const groupHeaderRef = useRef<HTMLTableRowElement>(null);
  const [groupHeaderHeight, setGroupHeaderHeight] = useState<number>(32);
  const [isScrolledLeft, setIsScrolledLeft] = useState<boolean>(false);

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
    }
  }, []);

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

  // Keyboard shortcut Ctrl/Cmd+S and Ctrl/Cmd+A and Undo/Redo inside grid
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      // 1. Ctrl+S / Cmd+S: Save changes
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        // Commit any active editing cell first
        if (editingCell) {
          handleCommitEdit();
        }
        if (onSave) {
          void onSave();
        }
        return;
      }

      // 2. Ctrl+Z: Undo
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
        if (undoStack.length > 0 && onCellChange) {
          e.preventDefault();
          const lastAction = undoStack[undoStack.length - 1];
          setUndoStack(prev => prev.slice(0, -1));
          setRedoStack(prev => [...prev, lastAction]);
          onCellChange(lastAction.rowId, lastAction.colKey, lastAction.oldVal);
        }
        return;
      }

      // 3. Ctrl+Y or Ctrl+Shift+Z: Redo
      if (
        ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') ||
        ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'z')
      ) {
        if (redoStack.length > 0 && onCellChange) {
          e.preventDefault();
          const lastRedo = redoStack[redoStack.length - 1];
          setRedoStack(prev => prev.slice(0, -1));
          setUndoStack(prev => [...prev, lastRedo]);
          onCellChange(lastRedo.rowId, lastRedo.colKey, lastRedo.newVal);
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
  }, [editingCell, onSave, undoStack, redoStack, onCellChange, processedData, onSelectionChange]);

  // Start editing a cell
  const handleStartEdit = (rowId: string, colKey: keyof T & string) => {
    const colDef = columns.find(c => c.key === colKey);
    if (!canUpdate || (colDef && colDef.isEditable === false)) return;

    const row = data.find(r => r.id === rowId);
    if (!row) return;

    setSelectedCell({ rowId, colKey });
    setEditingCell({ rowId, colKey });
    setEditValue(String((row as any)[colKey] ?? ''));
    setTimeout(() => {
      cellInputRef.current?.focus();
      cellInputRef.current?.select();
    }, 10);
  };

  const handleCommitEdit = (newVal?: string) => {
    if (!editingCell) return;
    const val = newVal !== undefined ? newVal : editValue;
    const row = data.find(r => r.id === editingCell.rowId);
    const oldVal = row ? String((row as any)[editingCell.colKey] ?? '') : '';

    if (val !== oldVal && onCellChange) {
      setUndoStack(prev => [...prev, { rowId: editingCell.rowId, colKey: editingCell.colKey, oldVal, newVal: val }]);
      setRedoStack([]); // reset redo on new change
      onCellChange(editingCell.rowId, editingCell.colKey, val);
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
        onCellChange?.(processedData[rowIndex].id, colKey, '');
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
        setEditingCell({ rowId: processedData[rowIndex].id, colKey });
        setEditValue(e.key);
        setTimeout(() => {
          cellInputRef.current?.focus();
        }, 10);
        return;
      }
    }

    if (nextRow !== rowIndex || nextCol !== colIndex) {
      const targetRow = processedData[nextRow];
      const targetCol = visibleColumns[nextCol];
      if (targetRow && targetCol) {
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

  // Copy / Paste TSV
  const handleCopySelection = () => {
    if (!selectedCell) return;
    const row = data.find(r => r.id === selectedCell.rowId);
    if (!row) return;
    const val = String((row as any)[selectedCell.colKey] ?? '');
    void navigator.clipboard.writeText(val);
  };

  const handlePasteSelection = async () => {
    if (!selectedCell || !canUpdate) return;
    try {
      const text = await navigator.clipboard.readText();
      if (!text) return;
      const lines = text.split(/\r?\n/).filter(Boolean);
      if (lines.length === 1 && !lines[0].includes('\t')) {
        // Single cell paste
        onCellChange?.(selectedCell.rowId, selectedCell.colKey, lines[0]);
      }
    } catch {
      // clipboard access denied
    }
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
    <div className="flex flex-col flex-1 h-full min-h-0 bg-white border border-ink-text/15 rounded-lg shadow-2xs select-none">
      {/* 1. Formula Bar & Column Controls Toolbar */}
      <div className="flex items-center gap-2 py-1.5 px-3 bg-vanilla-surface border-b border-ink-text/10 text-xs">
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
          disabled={!selectedCell || !onCellChange || !canUpdate}
          onChange={e => {
            if (externalOnFormulaChange) {
              externalOnFormulaChange(e.target.value);
            } else if (selectedCell && onCellChange) {
              onCellChange(selectedCell.rowId, selectedCell.colKey, e.target.value);
            }
          }}
          className="flex-1 px-2.5 py-0.5 bg-white border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-brand-steel disabled:bg-gray-100 text-gray-800 font-mono text-xs"
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
              processedData.map((row, rIdx) => {
                const isRowSelected = selectedIds.has(row.id);
                const customRowClass = getRowClassName ? getRowClassName(row) : '';
                const isZebra = rIdx % 2 === 1;

                return (
                  <tr
                    key={row.id}
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
              })
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

      {/* 5. Custom Right-Click Context Menu (Rendered via Portal) */}
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
                        if (targetRow) setRowEditorItem(targetRow);
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
                        onClick={() => {
                          if (contextMenu.rowId && contextMenu.colKey) {
                            onCellChange?.(contextMenu.rowId, contextMenu.colKey as keyof T & string, '');
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
                        if (targetRow) setRowEditorItem(targetRow);
                        setContextMenu(null);
                      }}
                      className="w-full text-left px-3 py-1.5 hover:bg-gray-100"
                    >
                      Edit row…
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
              )}
            </div>
          </div>,
          document.body
        )}

      {/* 6. Row Editor Panel Modal */}
      {rowEditorItem && (
        <div className="fixed inset-0 bg-black/40 z-[10000] flex items-center justify-center p-4">
          <div className="bg-white rounded-lg shadow-2xl max-w-lg w-full p-5 space-y-4 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between border-b pb-2">
              <h3 className="text-base font-bold text-gray-900">
                Edit Row (ID: {String(rowEditorItem.id).slice(0, 8)}…)
              </h3>
              <button
                type="button"
                onClick={() => setRowEditorItem(null)}
                className="text-gray-400 hover:text-gray-700 text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 pr-1 text-xs">
              {columns.map(col => {
                const isEditable = canUpdate && col.isEditable !== false;
                const val = String((rowEditorItem as any)[col.key] ?? '');
                return (
                  <div key={col.key} className="space-y-1">
                    <label className="font-semibold text-gray-700 block">{col.label}</label>
                    {isEditable ? (
                      <input
                        type="text"
                        value={val}
                        onChange={e => {
                          const nextVal = e.target.value;
                          setRowEditorItem(prev => (prev ? { ...prev, [col.key]: nextVal } : null));
                          onCellChange?.(rowEditorItem.id, col.key, nextVal);
                        }}
                        className="w-full px-2.5 py-1.5 border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 font-mono text-xs"
                      />
                    ) : (
                      <div className="px-2.5 py-1.5 bg-gray-50 border border-gray-200 rounded text-gray-600 font-mono text-xs">
                        {val || '—'}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t">
              <button
                type="button"
                onClick={() => setRowEditorItem(null)}
                className="px-4 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-800 rounded font-semibold text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

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
