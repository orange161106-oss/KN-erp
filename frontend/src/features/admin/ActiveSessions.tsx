import React, { useState, useEffect } from 'react';
import { RefreshCw, Download, FileSpreadsheet, Activity, ShieldCheck, CheckCircle2, Clock, Globe } from 'lucide-react';
import { adminAuditApi, type UserSessionItem } from '../../api/adminAudit';
import { downloadCSV, downloadExcel } from '../reports/exportUtils';
import { TableSkeleton } from '../../components/ui/Skeleton';

export function formatAuditDateTime(dateStr?: string | null): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    const day = String(d.getDate()).padStart(2, '0');
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = months[d.getMonth()];
    const year = d.getFullYear();
    let hours = d.getHours();
    const minutes = String(d.getMinutes()).padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12;
    hours = hours ? hours : 12;
    const strHours = String(hours).padStart(2, '0');
    return `${day} ${month} ${year}, ${strHours}:${minutes} ${ampm}`;
  } catch {
    return dateStr;
  }
}

export const ActiveSessions: React.FC = () => {
  const [sessions, setSessions] = useState<UserSessionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [offset, setOffset] = useState(0);
  const limit = 25;

  const fetchSessions = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await adminAuditApi.getActiveSessions({
        status: statusFilter || undefined,
        limit,
        offset,
      });
      setSessions(res.items);
      setTotal(res.total);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch sessions');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, [statusFilter, offset]);

  const activeCount = sessions.filter((s) => s.status.toUpperCase() === 'ACTIVE').length;
  const loggedOutCount = sessions.filter((s) => s.status.toUpperCase() === 'LOGGED_OUT').length;

  const handleExportCSV = () => {
    const columns = [
      { header: 'Username', key: 'username' },
      { header: 'Employee Name', key: 'full_name' },
      { header: 'Employee ID', key: 'employee_id' },
      { header: 'Role', key: 'role' },
      { header: 'IP Address', key: 'ip_address' },
      { header: 'Login Time', key: 'login_formatted' },
      { header: 'Logout Time', key: 'logout_formatted' },
      { header: 'Status', key: 'status' },
    ];
    const data = sessions.map((s) => ({
      ...s,
      login_formatted: formatAuditDateTime(s.login_at),
      logout_formatted: formatAuditDateTime(s.logout_at),
    }));
    downloadCSV(columns, data, 'knl_active_sessions');
  };

  const handleExportExcel = () => {
    const columns = [
      { header: 'Username', key: 'username' },
      { header: 'Employee Name', key: 'full_name' },
      { header: 'Employee ID', key: 'employee_id' },
      { header: 'Role', key: 'role' },
      { header: 'IP Address', key: 'ip_address' },
      { header: 'Login Time', key: 'login_formatted' },
      { header: 'Logout Time', key: 'logout_formatted' },
      { header: 'Status', key: 'status' },
    ];
    const data = sessions.map((s) => ({
      ...s,
      login_formatted: formatAuditDateTime(s.login_at),
      logout_formatted: formatAuditDateTime(s.logout_at),
    }));
    downloadExcel(columns, data, 'knl_active_sessions');
  };

  return (
    <div className="space-y-6">
      {/* Top Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl shadow-md border border-erp-dark-vanilla/30 p-5 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-erp-chocolate/70">Total Monitored</p>
            <p className="text-2xl font-bold text-erp-chocolate mt-1">{total}</p>
          </div>
          <div className="w-11 h-11 rounded-lg bg-erp-vanilla flex items-center justify-center text-erp-tenne">
            <Activity className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-md border border-erp-dark-vanilla/30 p-5 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-emerald-700">Active Now</p>
            <p className="text-2xl font-bold text-emerald-800 mt-1">{activeCount}</p>
          </div>
          <div className="w-11 h-11 rounded-lg bg-emerald-50 flex items-center justify-center text-emerald-600">
            <CheckCircle2 className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-md border border-erp-dark-vanilla/30 p-5 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-stone-600">Logged Out</p>
            <p className="text-2xl font-bold text-stone-800 mt-1">{loggedOutCount}</p>
          </div>
          <div className="w-11 h-11 rounded-lg bg-stone-100 flex items-center justify-center text-stone-600">
            <Clock className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Main Table Card */}
      <div className="bg-white rounded-xl shadow-md border border-erp-dark-vanilla/30 overflow-hidden">
        {/* Controls Bar */}
        <div className="p-4 sm:p-5 border-b border-erp-dark-vanilla/20 flex flex-wrap items-center justify-between gap-4 bg-erp-vanilla/20">
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold text-erp-chocolate uppercase tracking-wider">Filter Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setOffset(0);
              }}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border border-erp-dark-vanilla/40 bg-white text-erp-chocolate focus:outline-none focus:ring-2 focus:ring-erp-orange"
            >
              <option value="">All Statuses</option>
              <option value="ACTIVE">Active Now</option>
              <option value="LOGGED_OUT">Logged Out</option>
            </select>
            <button
              onClick={fetchSessions}
              disabled={loading}
              title="Refresh"
              className="p-1.5 text-erp-chocolate/70 hover:text-erp-tenne hover:bg-white rounded-lg border border-erp-dark-vanilla/30 transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleExportCSV}
              disabled={sessions.length === 0}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-erp-orange hover:bg-erp-tenne text-white transition-all shadow-xs disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
            <button
              onClick={handleExportExcel}
              disabled={sessions.length === 0}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-white border border-erp-orange text-erp-tenne hover:bg-erp-vanilla/30 transition-all shadow-xs disabled:opacity-50"
            >
              <FileSpreadsheet className="w-3.5 h-3.5" /> Export Excel
            </button>
          </div>
        </div>

        {error && (
          <div className="p-4 m-4 bg-rose-50 border border-rose-200 text-rose-700 rounded-lg text-sm">
            {error}
          </div>
        )}

        {/* Sessions Table */}
        <div className="overflow-x-auto">
          {loading ? (
            <div className="p-4">
              <TableSkeleton columns={7} rows={6} />
            </div>
          ) : (
            <table className="w-full text-left text-sm text-erp-chocolate/80">
              <thead className="bg-erp-vanilla/40 text-erp-chocolate border-b border-erp-dark-vanilla/20 uppercase text-[11px] font-bold tracking-wider">
                <tr>
                  <th className="py-3.5 px-5">Employee / Username</th>
                  <th className="py-3.5 px-4">Employee ID</th>
                  <th className="py-3.5 px-4">Role</th>
                  <th className="py-3.5 px-4">IP Address</th>
                  <th className="py-3.5 px-4">Login Time</th>
                  <th className="py-3.5 px-4">Logout Time</th>
                  <th className="py-3.5 px-5 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-erp-dark-vanilla/15">
                {sessions.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-12 text-erp-chocolate/40">
                      No user sessions found for the selected filter.
                    </td>
                  </tr>
                ) : (
                  sessions.map((s) => {
                    const isActive = s.status.toUpperCase() === 'ACTIVE';
                    return (
                      <tr key={s.id} className="hover:bg-erp-vanilla/20 transition-colors">
                        <td className="py-3.5 px-5">
                          <div className="flex items-center gap-2.5">
                            <div className="w-8 h-8 rounded-full bg-erp-vanilla flex items-center justify-center text-erp-tenne font-bold text-xs flex-shrink-0">
                              {s.username ? s.username[0].toUpperCase() : 'U'}
                            </div>
                            <div>
                              <div className="font-semibold text-erp-chocolate flex items-center gap-1.5">
                                {s.username}
                              </div>
                              <div className="text-xs text-erp-chocolate/60">
                                {s.full_name || 'No Name Provided'}
                              </div>
                            </div>
                          </div>
                        </td>

                        <td className="py-3.5 px-4 text-xs font-mono text-erp-chocolate/70">
                          {s.employee_id || '—'}
                        </td>

                        <td className="py-3.5 px-4">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-erp-orange/15 text-erp-topaz border border-erp-orange/30">
                            <ShieldCheck className="w-3 h-3" />
                            {s.role}
                          </span>
                        </td>

                        <td className="py-3.5 px-4">
                          <div className="flex items-center gap-1 text-xs font-mono text-erp-chocolate/70">
                            <Globe className="w-3 h-3 text-erp-dark-vanilla" />
                            {s.ip_address || 'Internal / Proxy'}
                          </div>
                        </td>

                        <td className="py-3.5 px-4 text-xs text-erp-chocolate font-medium">
                          {formatAuditDateTime(s.login_at)}
                        </td>

                        <td className="py-3.5 px-4 text-xs text-erp-chocolate/70">
                          {formatAuditDateTime(s.logout_at)}
                        </td>

                        <td className="py-3.5 px-5 text-right">
                          {isActive ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                              Active Now
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-stone-100 text-stone-600 border border-stone-200">
                              Logged Out
                            </span>
                          )}
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
              Showing {Math.min(offset + 1, total)} to {Math.min(offset + limit, total)} of {total} sessions
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
