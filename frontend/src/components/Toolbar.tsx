import React, { useState } from 'react';

interface FilterOption {
  value: string;
  label: string;
}

interface FilterConfig {
  key: string;
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (value: string) => void;
}

interface ToolbarProps {
  // Action handlers
  onUpload?: () => void;
  onAddRow?: () => void;
  onSave?: () => void;
  onDeleteSelected?: () => void;
  onExport?: (mode: 'ALL' | 'FILTERED' | 'SELECTED') => void;

  // Permissions & States
  canImport?: boolean;
  canCreate?: boolean;
  canUpdate?: boolean;
  canDelete?: boolean;
  canExport?: boolean;

  isSaving?: boolean;
  unsavedCount?: number;
  selectedCount?: number;

  // Search & Filters
  searchQuery?: string;
  onSearchChange?: (query: string) => void;
  searchPlaceholder?: string;
  filters?: FilterConfig[];

  // Custom action buttons (e.g. Recalculate)
  extraActions?: React.ReactNode;
}

export default function Toolbar({
  onUpload,
  onAddRow,
  onSave,
  onDeleteSelected,
  onExport,
  canImport = true,
  canCreate = true,
  canUpdate = true,
  canDelete = true,
  canExport = true,
  isSaving = false,
  unsavedCount = 0,
  selectedCount = 0,
  searchQuery = '',
  onSearchChange,
  searchPlaceholder = '🔍 Search...',
  filters = [],
  extraActions,
}: ToolbarProps) {
  const [showExportMenu, setShowExportMenu] = useState(false);

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 py-2 border-b border-ink-text/10 bg-vanilla-surface px-2 rounded-t select-none">
      {/* Left: Action Buttons */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {canImport && onUpload && (
          <button
            type="button"
            onClick={onUpload}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded shadow-xs hover:bg-gray-100 active:bg-gray-200 transition-colors"
          >
            <span>📊</span>
            <span>Upload Excel</span>
          </button>
        )}

        {canCreate && onAddRow && (
          <button
            type="button"
            onClick={onAddRow}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded shadow-xs hover:bg-gray-100 active:bg-gray-200 transition-colors"
          >
            <span>➕</span>
            <span>Add Row</span>
          </button>
        )}

        {canUpdate && onSave && (
          <button
            type="button"
            onClick={onSave}
            disabled={isSaving || unsavedCount === 0}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-white bg-burnt-orange hover:bg-burnt-orange-dark active:bg-burnt-orange-dark rounded shadow-xs disabled:opacity-40 transition-colors"
          >
            {isSaving ? (
              <>
                <div className="animate-spin h-3 w-3 border-2 border-white border-t-transparent rounded-full" />
                <span>Saving…</span>
              </>
            ) : (
              <>
                <span>💾</span>
                <span>Save Changes</span>
              </>
            )}
          </button>
        )}

        {canDelete && onDeleteSelected && (
          <button
            type="button"
            onClick={onDeleteSelected}
            disabled={selectedCount === 0 || isSaving}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-red-700 bg-white border border-red-200 rounded shadow-xs hover:bg-red-50 active:bg-red-100 disabled:opacity-40 transition-colors"
          >
            <span>🗑️</span>
            <span>
              {selectedCount > 0 ? `Delete Selected (${selectedCount})` : 'Delete Selected'}
            </span>
          </button>
        )}

        {extraActions}

        {canExport && onExport && (
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowExportMenu(prev => !prev)}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded shadow-xs hover:bg-gray-100 active:bg-gray-200 transition-colors"
            >
              <span>📥</span>
              <span>Export Excel ▾</span>
            </button>
            {showExportMenu && (
              <div
                className="absolute left-0 mt-1 w-44 bg-white border border-gray-200 rounded shadow-lg py-1 z-30 animate-in fade-in zoom-in-95 duration-100"
                onMouseLeave={() => setShowExportMenu(false)}
              >
                <button
                  type="button"
                  onClick={() => {
                    setShowExportMenu(false);
                    onExport('ALL');
                  }}
                  className="block w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-100"
                >
                  Export All Records
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowExportMenu(false);
                    onExport('FILTERED');
                  }}
                  className="block w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-100"
                >
                  Export Current View
                </button>
                {selectedCount > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      setShowExportMenu(false);
                      onExport('SELECTED');
                    }}
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

      {/* Right: Unsaved Badge, Search, and Filters */}
      <div className="flex items-center gap-2.5 flex-wrap">
        {/* Unsaved State Pill */}
        <div className="text-xs">
          {unsavedCount > 0 ? (
            <span className="font-semibold text-amber-700 bg-amber-50 border border-amber-300 px-2.5 py-0.5 rounded-full inline-flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              <span>
                Unsaved changes • {unsavedCount} cell{unsavedCount > 1 ? 's' : ''} modified
              </span>
            </span>
          ) : (
            <span className="font-semibold text-emerald-700 bg-emerald-50 border border-emerald-300 px-2.5 py-0.5 rounded-full">
              Saved ✓
            </span>
          )}
        </div>

        {/* Dynamic Filters */}
        {filters.map(filter => (
          <select
            key={filter.key}
            aria-label={filter.label}
            value={filter.value}
            onChange={e => filter.onChange(e.target.value)}
            className="px-2 py-1 text-xs bg-white border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-brand-steel"
          >
            {filter.options.map(opt => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        ))}

        {/* Search Input */}
        {onSearchChange && (
          <div className="relative">
            <input
              type="text"
              aria-label="Search records"
              placeholder={searchPlaceholder}
              value={searchQuery}
              onChange={e => onSearchChange(e.target.value)}
              className="w-40 px-2.5 py-1 text-xs bg-white border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-brand-steel transition-all focus:w-52"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => onSearchChange('')}
                className="absolute right-2 top-1 text-gray-400 hover:text-gray-600 text-xs"
              >
                ✕
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
