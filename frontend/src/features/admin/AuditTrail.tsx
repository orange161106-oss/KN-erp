import React, { useState, useEffect } from 'react';
import { RefreshCw, Download, FileSpreadsheet, Search, History, Layers, CheckCircle, AlertTriangle, Trash2, UploadCloud, LogIn, LogOut } from 'lucide-react';
import { adminAuditApi, type AuditLogItem } from '../../api/adminAudit';
import { downloadCSV, downloadExcel } from '../reports/exportUtils';
import { TableSkeleton } from '../../components/ui/Skeleton';
import { formatAuditDateTime } from './ActiveSessions';

const MODULE_OPTIONS = [
  { value: '', label: 'All Modules' },
  { value: 'Product Master - Consumables', label: 'Product Master - Consumables' },
  { value: 'Product Master - Sales Parts', label: 'Product Master - Sales Parts' },
  { value: 'Product Master - Assembly BOM', label: 'Product Master - Assembly BOM' },
  { value: 'User Permissions', label: 'User Permissions' },
  { value: 'Authentication', label: 'Authentication' },
  { value: 'Inventory', label: 'Inventory' },
];

const ACTION_OPTIONS = [
  { value: '', label: 'All Actions' },
  { value: 'CREATE', label: 'CREATE' },
  { value: 'UPDATE', label: 'UPDATE' },
  { value: 'DELETE', label: 'DELETE' },
  { value: 'BULK_UPLOAD', label: 'BULK_UPLOAD' },
  { value: 'LOGIN', label: 'LOGIN' },
  { value: 'LOGOUT', label: 'LOGOUT' },
];

function renderActionBadge(action: string) {
  const act = action.toUpperCase();
  switch (act) {
    case 'CREATE':
    case 'UPSERT':
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <CheckCircle className="w-3 h-3" />
          {action}
        </span>
      );
    case 'UPDATE':
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-erp-topaz border border-amber-200">
          <AlertTriangle className="w-3 h-3" />
          {action}
        </span>
      );
    case 'DELETE':
    case 'DEACTIVATE':
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
          <Trash2 className="w-3 h-3" />
          {action}
        </span>
      );
    case 'BULK_UPLOAD':
    case 'BULK_IMPORT':
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
          <UploadCloud className="w-3 h-3" />
          {action}
        </span>
      );
    case 'LOGIN':
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
          <LogIn className="w-3 h-3" />
          {action}
        </span>
      );
    case 'LOGOUT':
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-stone-100 text-stone-600 border border-stone-200">
          <LogOut className="w-3 h-3" />
          {action}
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-700 border border-gray-200">
          {action}
        </span>
      );
  }
}

function formatDetailsSummary(details?: Record<string, any> | null): string {
  if (!details) return '—';
  if (typeof details === 'string') return details;
  if (typeof details === 'object') {
    if (details.summary) return String(details.summary);
    if (details.message) return String(details.message);
    // Compact formatting of key-values
    const entries = Object.entries(details)
      .filter(([k]) => k !== 'message' && k !== 'summary')
      .slice(0, 4)
      .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`);
    return entries.length > 0 ? entries.join('; ') : JSON.stringify(details);
  }
  return String(details);
}

export const AuditTrail: React.FC = () => {
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [moduleFilter, setModuleFilter] = useState('');
  const [actionFilter, setActionFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 25;

  const fetchLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await adminAuditApi.getAuditLogs({
        module: moduleFilter || undefined,
        action: actionFilter || undefined,
        date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
        date_to: dateTo ? new Date(dateTo + 'T23:59:59').toISOString() : undefined,
        limit,
        offset,
      });
      setLogs(res.items);
      setTotal(res.total);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch audit trail');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [moduleFilter, actionFilter, dateFrom, dateTo, offset]);

  // Client-side quick filter for search keyword
  const filteredLogs = logs.filter((log) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    const userMatch = log.username.toLowerCase().includes(q);
    const recordMatch = (log.record_id || '').toLowerCase().includes(q);
    const moduleMatch = (log.module || '').toLowerCase().includes(q);
    return userMatch || recordMatch || moduleMatch;
  });

  const handleExportCSV = () => {
    const columns = [
      { header: 'Date & Time', key: 'timestamp_formatted' },
      { header: 'User', key: 'username' },
      { header: 'Action', key: 'action' },
      { header: 'Module', key: 'module' },
      { header: 'Record ID', key: 'record_id' },
      { header: 'Details Summary', key: 'details_str' },
    ];
    const data = filteredLogs.map((l) => ({
      ...l,
      timestamp_formatted: formatAuditDateTime(l.timestamp),
      details_str: formatDetailsSummary(l.changes_summary),
    }));
    downloadCSV(columns, data, 'knl_audit_trail');
  };

  const handleExportExcel = () => {
    const columns = [
      { header: 'Date & Time', key: 'timestamp_formatted' },
      { header: 'User', key: 'username' },
      { header: 'Action', key: 'action' },
      { header: 'Module', key: 'module' },
      { header: 'Record ID', key: 'record_id' },
      { header: 'Details Summary', key: 'details_str' },
    ];
    const data = filteredLogs.map((l) => ({
      ...l,
      timestamp_formatted: formatAuditDateTime(l.timestamp),
      details_str: formatDetailsSummary(l.changes_summary),
    }));
    downloadExcel(columns, data, 'knl_audit_trail');
  };

  return (
    <div className="space-y-6">
      {/* Main Ledger Card */}
      <div className="bg-white rounded-xl shadow-md border border-erp-dark-vanilla/30 overflow-hidden">
        {/* Header & Controls Bar */}
        <div className="p-4 sm:p-5 border-b border-erp-dark-vanilla/20 space-y-4 bg-erp-vanilla/20">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <History className="w-5 h-5 text-erp-tenne" />
              <h2 className="text-base font-bold text-erp-chocolate">Immutable Audit Activity Ledger</h2>
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-erp-vanilla text-erp-tenne border border-erp-dark-vanilla/40">
                {total} Events
              </span>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleExportCSV}
                disabled={filteredLogs.length === 0}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-erp-orange hover:bg-erp-tenne text-white transition-all shadow-xs disabled:opacity-50"
              >
                <Download className="w-3.5 h-3.5" /> Export CSV
              </button>
              <button
                onClick={handleExportExcel}
                disabled={filteredLogs.length === 0}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-white border border-erp-orange text-erp-tenne hover:bg-erp-vanilla/30 transition-all shadow-xs disabled:opacity-50"
              >
                <FileSpreadsheet className="w-3.5 h-3.5" /> Export Excel
              </button>
              <button
                onClick={fetchLogs}
                disabled={loading}
                title="Refresh"
                className="p-1.5 text-erp-chocolate/70 hover:text-erp-tenne hover:bg-white rounded-lg border border-erp-dark-vanilla/30 transition-colors"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {/* Filter Inputs Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3 pt-2">
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-erp-chocolate/70 mb-1">
                Filter Module
              </label>
              <select
                value={moduleFilter}
                onChange={(e) => {
                  setModuleFilter(e.target.value);
                  setOffset(0);
                }}
                className="w-full px-3 py-1.5 text-xs font-medium rounded-lg border border-erp-dark-vanilla/40 bg-white text-erp-chocolate focus:outline-none focus:ring-2 focus:ring-erp-orange"
              >
                {MODULE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-erp-chocolate/70 mb-1">
                Filter Action
              </label>
              <select
                value={actionFilter}
                onChange={(e) => {
                  setActionFilter(e.target.value);
                  setOffset(0);
                }}
                className="w-full px-3 py-1.5 text-xs font-medium rounded-lg border border-erp-dark-vanilla/40 bg-white text-erp-chocolate focus:outline-none focus:ring-2 focus:ring-erp-orange"
              >
                {ACTION_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-erp-chocolate/70 mb-1">
                Date From
              </label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => {
                  setDateFrom(e.target.value);
                  setOffset(0);
                }}
                className="w-full px-3 py-1.5 text-xs font-medium rounded-lg border border-erp-dark-vanilla/40 bg-white text-erp-chocolate focus:outline-none focus:ring-2 focus:ring-erp-orange"
              />
            </div>

            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-erp-chocolate/70 mb-1">
                Date To
              </label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => {
                  setDateTo(e.target.value);
                  setOffset(0);
                }}
                className="w-full px-3 py-1.5 text-xs font-medium rounded-lg border border-erp-dark-vanilla/40 bg-white text-erp-chocolate focus:outline-none focus:ring-2 focus:ring-erp-orange"
              />
            </div>

            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-erp-chocolate/70 mb-1">
                Quick Search
              </label>
              <div className="relative">
                <input
                  type="text"
                  placeholder="User, Record ID..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 text-xs font-medium rounded-lg border border-erp-dark-vanilla/40 bg-white text-erp-chocolate focus:outline-none focus:ring-2 focus:ring-erp-orange placeholder:text-erp-chocolate/40"
                />
                <Search className="w-3.5 h-3.5 text-erp-chocolate/50 absolute left-2.5 top-2.5" />
              </div>
            </div>
          </div>
        </div>

        {error && (
          <div className="p-4 m-4 bg-rose-50 border border-rose-200 text-rose-700 rounded-lg text-sm">
            {error}
          </div>
        )}

        {/* Ledger Table */}
        <div className="overflow-x-auto">
          {loading ? (
            <div className="p-4">
              <TableSkeleton columns={6} rows={6} />
            </div>
          ) : (
            <table className="w-full text-left text-sm text-erp-chocolate/80">
              <thead className="bg-erp-vanilla/40 text-erp-chocolate border-b border-erp-dark-vanilla/20 uppercase text-[11px] font-bold tracking-wider">
                <tr>
                  <th className="py-3.5 px-5">Date & Time</th>
                  <th className="py-3.5 px-4">User</th>
                  <th className="py-3.5 px-4">Action</th>
                  <th className="py-3.5 px-4">Module Affected</th>
                  <th className="py-3.5 px-4">Record ID</th>
                  <th className="py-3.5 px-5">Details Summary</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-erp-dark-vanilla/15">
                {filteredLogs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-12 text-erp-chocolate/40">
                      No audit log records match the applied criteria.
                    </td>
                  </tr>
                ) : (
                  filteredLogs.map((log) => {
                    return (
                      <tr key={log.id} className="hover:bg-erp-vanilla/20 transition-colors">
                        <td className="py-3.5 px-5 text-xs text-erp-chocolate font-medium whitespace-nowrap">
                          {formatAuditDateTime(log.timestamp)}
                        </td>

                        <td className="py-3.5 px-4">
                          <div className="flex items-center gap-2">
                            <div className="w-7 h-7 rounded-full bg-erp-vanilla flex items-center justify-center text-erp-tenne font-bold text-xs flex-shrink-0">
                              {log.username ? log.username[0].toUpperCase() : 'U'}
                            </div>
                            <span className="font-semibold text-xs text-erp-chocolate">
                              {log.username}
                            </span>
                          </div>
                        </td>

                        <td className="py-3.5 px-4 whitespace-nowrap">
                          {renderActionBadge(log.action)}
                        </td>

                        <td className="py-3.5 px-4">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-erp-vanilla/80 text-erp-chocolate border border-erp-dark-vanilla/30">
                            <Layers className="w-3 h-3 text-erp-tenne" />
                            {log.module || 'General'}
                          </span>
                        </td>

                        <td className="py-3.5 px-4 font-mono text-xs text-erp-chocolate/70">
                          {log.record_id ? (
                            <span className="bg-gray-100 px-1.5 py-0.5 rounded text-[11px] text-gray-700">
                              {log.record_id}
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>

                        <td className="py-3.5 px-5 text-xs text-erp-chocolate/80 max-w-md truncate" title={formatDetailsSummary(log.changes_summary)}>
                          {formatDetailsSummary(log.changes_summary)}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination Bar */}
        {total > limit && (
          <div className="p-4 border-t border-erp-dark-vanilla/20 flex items-center justify-between text-xs text-erp-chocolate/70 bg-erp-vanilla/10">
            <span>
              Showing {Math.min(offset + 1, total)} to {Math.min(offset + limit, total)} of {total} records
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - limit))}
                className="px-3 py-1 rounded border border-erp-dark-vanilla/30 bg-white hover:bg-erp-vanilla/30 disabled:opacity-40 transition-colors"
              >
                Previous
              </button>
              <button
                disabled={offset + limit >= total}
                onClick={() => setOffset(offset + limit)}
                className="px-3 py-1 rounded border border-erp-dark-vanilla/30 bg-white hover:bg-erp-vanilla/30 disabled:opacity-40 transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
