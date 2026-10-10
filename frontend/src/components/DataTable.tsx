import React, { useEffect, useMemo, useRef, useState } from 'react';

export interface ColumnDef<T> {
  key: keyof T & string;
  label: string;
  width?: string;
  minWidth?: string;
  align?: 'left' | 'right' | 'center';
  isEditable?: boolean;
  isSticky?: boolean;
  render?: (value: any, row: T, isSelected: boolean) => React.ReactNode;
}

export interface HeaderGroupDef {
  label: string;
  colSpan: number;
  className?: string;
}

interface DataTableProps<T extends { id: string }> {
  columns: ColumnDef<T>[];
  data: T[];
  originalData?: Map<string, T>;
  selectedIds: Set<string>;
  onSelectionChange: (ids: Set<string>) => void;
  onCellChange?: (rowId: string, colKey: keyof T & string, value: string) => void;
  isLoading?: boolean;
  emptyMessage?: string;
  onAddRow?: () => void;
  canCreate?: boolean;
  // Selected cell for formula bar integration
  selectedCell?: { rowId: string; colKey: keyof T & string } | null;
  onSelectCell?: (cell: { rowId: string; colKey: keyof T & string } | null) => void;
  formulaValue?: string;
  onFormulaChange?: (val: string) => void;
  // Row highlighting (e.g. shortages red, low stock amber)
  getRowClassName?: (row: T) => string;
  // Section 7A: Grouped column headers
  headerGroups?: HeaderGroupDef[];
}

function parseWidthPixels(widthStr?: string): number {
  if (!widthStr) return 144;
  if (widthStr.startsWith('w-')) {
    const val = parseInt(widthStr.replace('w-', ''), 10);
    if (!isNaN(val)) return val * 4;
  }
  return 144;
}

export default function DataTable<T extends { id: string; row_index?: number | null }>({
  columns,
  data,
  originalData = new Map(),
  selectedIds,
  onSelectionChange,
  onCellChange,
  isLoading = false,
  emptyMessage = 'No records found matching your filters.',
  onAddRow,
  canCreate = true,
  selectedCell: externalSelectedCell,
  onSelectCell: externalOnSelectCell,
  formulaValue: externalFormulaValue,
  onFormulaChange: externalOnFormulaChange,
  getRowClassName,
  headerGroups,
}: DataTableProps<T>) {
  // Column visibility
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set());
  const [showColMenu, setShowColMenu] = useState(false);

  // Cell selection & editing
  const [internalSelectedCell, setInternalSelectedCell] = useState<{
    rowId: string;
    colKey: keyof T & string;
  } | null>(null);
  const selectedCell = externalSelectedCell !== undefined ? externalSelectedCell : internalSelectedCell;
  const setSelectedCell = externalOnSelectCell || setInternalSelectedCell;

  const [editingCell, setEditingCell] = useState<{
    rowId: string;
    colKey: keyof T & string;
  } | null>(null);
  const [editValue, setEditValue] = useState<string>('');
  const lastClickedIndexRef = useRef<number | null>(null);
  const cellInputRef = useRef<HTMLInputElement>(null);
  const tableContainerRef = useRef<HTMLDivElement>(null);

  const visibleColumns = useMemo(
    () => columns.filter(col => !hiddenColumns.has(col.key)),
    [columns, hiddenColumns]
  );

  // Cumulative horizontal offsets for sticky frozen identifying columns
  const stickyLeftOffsets = useMemo(() => {
    let offset = 84; // Checkbox (36px) + Row # (48px) = 84px
    const map = new Map<string, number>();
    visibleColumns.forEach(col => {
      if (col.isSticky) {
        map.set(col.key, offset);
        offset += parseWidthPixels(col.width);
      }
    });
    return map;
  }, [visibleColumns]);

  // Track modified cells
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
  const allSelected = data.length > 0 && data.every(r => selectedIds.has(r.id));
  const someSelected = data.some(r => selectedIds.has(r.id)) && !allSelected;

  const handleToggleSelectAll = () => {
    if (allSelected) {
      onSelectionChange(new Set());
    } else {
      const next = new Set<string>(selectedIds);
      data.forEach(r => next.add(r.id));
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
        next.add(data[i].id);
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

  // Keyboard shortcut Ctrl/Cmd+A inside grid
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
        const activeTag = document.activeElement?.tagName?.toLowerCase();
        if (activeTag === 'input' || activeTag === 'textarea') return;
        e.preventDefault();
        const next = new Set<string>();
        data.forEach(r => next.add(r.id));
        onSelectionChange(next);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [data, onSelectionChange]);

  // Start editing a cell
  const handleStartEdit = (rowId: string, colKey: keyof T & string) => {
    const colDef = columns.find(c => c.key === colKey);
    if (colDef && colDef.isEditable === false) return;

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
    onCellChange?.(editingCell.rowId, editingCell.colKey, val);
    setEditingCell(null);
  };

  // Selected cell value for formula bar
  const selectedCellValue = useMemo(() => {
    if (!selectedCell) return '';
    const row = data.find(r => r.id === selectedCell.rowId);
    if (!row) return '';
    return String((row as any)[selectedCell.colKey] ?? '');
  }, [selectedCell, data]);

  // Coordinate label
  const coordLabel = useMemo(() => {
    if (!selectedCell) return '—';
    const rowIdx = data.findIndex(r => r.id === selectedCell.rowId);
    const colIdx = visibleColumns.findIndex(c => c.key === selectedCell.colKey);
    if (rowIdx === -1 || colIdx === -1) return '—';
    const colLetter = String.fromCharCode(65 + colIdx);
    return `${colLetter}${rowIdx + 1}`;
  }, [selectedCell, data, visibleColumns]);

  return (
    <div className="flex flex-col flex-1 h-full min-h-0 bg-white">
      {/* Formula Bar & Column Options */}
      <div className="flex items-center gap-2 py-1 px-2 bg-vanilla-surface border-b border-ink-text/10 text-xs select-none">
        {/* Cell Reference Box */}
        <div className="w-16 px-2 py-0.5 font-mono text-center font-bold text-ink-text/80 bg-white border border-ink-text/15 rounded shadow-2xs">
          {coordLabel}
        </div>

        {/* fx symbol */}
        <div className="font-serif italic font-bold text-burnt-orange px-1 select-none">fx</div>

        {/* Formula Input */}
        <input
          type="text"
          aria-label="Formula bar"
          placeholder={selectedCell ? 'Edit cell value...' : 'Select a cell to view or edit its value'}
          value={externalFormulaValue !== undefined ? externalFormulaValue : selectedCellValue}
          disabled={!selectedCell || !onCellChange}
          onChange={e => {
            if (externalOnFormulaChange) {
              externalOnFormulaChange(e.target.value);
            } else if (selectedCell && onCellChange) {
              onCellChange(selectedCell.rowId, selectedCell.colKey, e.target.value);
            }
          }}
          className="flex-1 px-2.5 py-0.5 bg-white border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-brand-steel disabled:bg-gray-100 text-gray-800 font-mono text-xs"
        />

        {/* Column Show/Hide Toggle */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowColMenu(prev => !prev)}
            className="px-2 py-0.5 bg-white border border-gray-300 rounded text-gray-700 hover:bg-gray-50 text-[11px] font-medium flex items-center gap-1"
          >
            <span>Columns ({visibleColumns.length}/{columns.length}) ▾</span>
          </button>
          {showColMenu && (
            <div
              className="absolute right-0 mt-1 w-52 bg-white border border-gray-200 rounded shadow-lg p-2 z-40 max-h-60 overflow-y-auto space-y-1 text-xs"
              onMouseLeave={() => setShowColMenu(false)}
            >
              <div className="font-bold text-gray-700 border-b pb-1 mb-1">Show/Hide Columns</div>
              {columns.map(col => (
                <label key={col.key} className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                  <input
                    type="checkbox"
                    disabled={col.isSticky}
                    checked={!hiddenColumns.has(col.key)}
                    onChange={() => {
                      if (col.isSticky) return; // Keep frozen columns visible per Section 7A
                      const next = new Set(hiddenColumns);
                      if (next.has(col.key)) next.delete(col.key);
                      else next.add(col.key);
                      setHiddenColumns(next);
                    }}
                    className="text-brand-steel rounded"
                  />
                  <span className={col.isSticky ? 'font-semibold text-gray-900' : ''}>
                    {col.label} {col.isSticky ? '(Frozen)' : ''}
                  </span>
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Main Table Grid - Section 7A: Column headers ALWAYS visible in EVERY state */}
      <div ref={tableContainerRef} className="flex-1 overflow-auto border border-ink-text/15 bg-white relative">
        <table className="w-full border-collapse text-left text-xs table-fixed">
          <thead>
            {/* Optional Tier 1: Grouped Column Headers (FOR COMPONENT, FOR CONSUMABLES, etc.) */}
            {headerGroups && headerGroups.length > 0 && (
              <tr className="sticky top-0 z-20 bg-vanilla-surface border-b border-ink-text/15 shadow-2xs h-7">
                {/* Checkbox + Row # frozen span */}
                <th
                  colSpan={2}
                  className="p-1 border-r border-ink-text/10 bg-vanilla-surface sticky left-0 z-30 select-none"
                />
                {headerGroups.map((grp, gIdx) => (
                  <th
                    key={gIdx}
                    colSpan={grp.colSpan}
                    className={
                      grp.className ||
                      'p-1 text-center font-bold text-white uppercase tracking-wider text-[11px] border-r border-ink-text/20 bg-brand-navy select-none'
                    }
                  >
                    {grp.label}
                  </th>
                ))}
              </tr>
            )}

            {/* Tier 2: Column Headers Row */}
            <tr
              className={`sticky ${
                headerGroups && headerGroups.length > 0 ? 'top-[28px]' : 'top-0'
              } z-20 bg-vanilla-surface border-b border-ink-text/15 shadow-2xs h-8`}
            >
              {/* 1. Select All Checkbox Header */}
              <th className="w-9 p-1 text-center border-r border-ink-text/10 bg-vanilla-surface sticky left-0 z-30">
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

              {/* 2. Row Number Header */}
              <th className="w-12 p-1 text-center font-bold text-ink-text/70 border-r border-ink-text/10 bg-vanilla-surface select-none sticky left-9 z-30">
                #
              </th>

              {/* Data Column Headers */}
              {visibleColumns.map(col => {
                const stickyOffset = stickyLeftOffsets.get(col.key);
                const isFrozen = col.isSticky && stickyOffset !== undefined;

                return (
                  <th
                    key={col.key}
                    title={col.label}
                    style={isFrozen ? { left: `${stickyOffset}px` } : undefined}
                    className={`${col.width || 'w-36'} p-1.5 font-semibold text-ink-text border-r border-ink-text/10 select-none text-${
                      col.align || 'left'
                    } bg-vanilla-surface ${
                      isFrozen ? 'sticky z-30 shadow-2xs font-bold' : ''
                    }`}
                  >
                    <div className="line-clamp-2 leading-tight">{col.label}</div>
                  </th>
                );
              })}
            </tr>
          </thead>

          {/* Section 7A: State rendered inside tbody so thead is NEVER hidden */}
          <tbody>
            {isLoading ? (
              <tr className="h-48">
                <td
                  colSpan={visibleColumns.length + 2}
                  className="text-center p-8 bg-white border-b border-gray-200"
                >
                  <div className="flex flex-col items-center justify-center gap-2">
                    <div className="animate-spin h-6 w-6 border-2 border-brand-navy border-t-transparent rounded-full" />
                    <span className="text-xs text-gray-500 font-medium">Loading requirement records…</span>
                  </div>
                </td>
              </tr>
            ) : data.length === 0 ? (
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
                        + Add your first row
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ) : (
              data.map((row, rIdx) => {
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
                    className={`h-7 border-b border-ink-text/10 transition-colors ${
                      isRowSelected
                        ? 'bg-burnt-orange/15 font-medium'
                        : customRowClass ||
                          (isZebra ? 'bg-vanilla-bg/25 hover:bg-vanilla-surface/50' : 'bg-white hover:bg-vanilla-bg/40')
                    }`}
                  >
                    {/* Row Checkbox */}
                    <td
                      onClick={e => handleRowCheckbox(row.id, rIdx, e)}
                      className={`text-center border-r border-gray-300 select-none cursor-pointer sticky left-0 z-10 ${
                        isRowSelected ? 'bg-blue-200/70' : isZebra ? 'bg-gray-100/90' : 'bg-white'
                      }`}
                    >
                      <input
                        type="checkbox"
                        aria-label={`Select row ${rIdx + 1}`}
                        checked={isRowSelected}
                        onChange={() => {}} // handled by parent onClick
                        className="cursor-pointer text-brand-steel rounded"
                      />
                    </td>

                    {/* Row Index # */}
                    <td
                      onClick={e => handleRowCheckbox(row.id, rIdx, e)}
                      className={`text-center font-mono text-gray-500 border-r border-gray-300 select-none cursor-pointer sticky left-9 z-10 ${
                        isRowSelected ? 'bg-blue-200/70 font-bold text-blue-900' : isZebra ? 'bg-gray-100/90' : 'bg-white'
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
                      const stickyOffset = stickyLeftOffsets.get(col.key);
                      const isFrozen = col.isSticky && stickyOffset !== undefined;

                      return (
                        <td
                          key={col.key}
                          style={isFrozen ? { left: `${stickyOffset}px` } : undefined}
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
                          className={`relative border-r border-gray-200 px-2 py-0.5 truncate cursor-cell ${
                            col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'
                          } ${isFrozen ? `sticky z-10 ${isRowSelected ? 'bg-blue-100' : isZebra ? 'bg-gray-100' : 'bg-white'}` : ''} ${
                            isCellSelected ? 'ring-2 ring-blue-600 ring-inset bg-blue-50/50' : ''
                          } ${isModified && !isCellSelected ? 'bg-amber-50/80' : ''}`}
                        >
                          {/* Dirty Triangle Marker */}
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
                                  const curIdx = visibleColumns.findIndex(c => c.key === col.key);
                                  if (curIdx < visibleColumns.length - 1) {
                                    handleStartEdit(row.id, visibleColumns[curIdx + 1].key);
                                  }
                                }
                              }}
                              className="w-full h-full px-1 py-0 bg-white border-none outline-none font-sans text-xs text-gray-900"
                            />
                          ) : col.render ? (
                            col.render(cellValue, row, isRowSelected)
                          ) : (
                            <span className="font-mono text-xs text-gray-800">
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

      {/* Grid Footer status bar */}
      <div className="flex items-center justify-between px-3 py-1 bg-gray-100 border-t border-gray-300 text-[11px] text-gray-600 select-none">
        <div>
          <span>
            Total Records: <strong className="text-gray-800">{data.length}</strong>
          </span>
          {selectedIds.size > 0 && (
            <span className="ml-3 text-blue-700 font-semibold bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
              {selectedIds.size} row{selectedIds.size > 1 ? 's' : ''} selected
            </span>
          )}
        </div>
        <div className="text-gray-500">
          Tip: Double-click permitted cell to edit • Shift+click to select range • Ctrl+A to select all
        </div>
      </div>
    </div>
  );
}
