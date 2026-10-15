import { useState, useEffect } from 'react';
import { Activity, History, Server, CheckCircle2, AlertTriangle } from 'lucide-react';
import { apiClient } from '../../api/client';
import { ActiveSessions } from '../admin/ActiveSessions';
import { AuditTrail } from '../admin/AuditTrail';

type HealthStatus = {
  status: string;
};

export default function SystemStatus() {
  const [activeTab, setActiveTab] = useState<'sessions' | 'audit'>('sessions');
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [loadingHealth, setLoadingHealth] = useState(true);

  useEffect(() => {
    apiClient.get<HealthStatus>('/api/v1/health')
      .then((data) => {
        setHealth(data);
        setLoadingHealth(false);
      })
      .catch((err) => {
        setHealthError(err.message || 'Backend unreachable');
        setLoadingHealth(false);
      });
  }, []);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Top Header Card */}
      <div className="flex flex-wrap justify-between items-center bg-white p-6 rounded-xl shadow-md border border-erp-dark-vanilla/30 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-erp-chocolate flex items-center gap-2">
            <Activity className="w-7 h-7 text-erp-orange" />
            System Status & Audit Hub
          </h1>
          <p className="text-sm text-erp-chocolate/70 mt-1">
            Live user session tracking, immutable audit ledger, and infrastructure monitoring.
          </p>
        </div>

        {/* Backend Health Badge */}
        <div className="flex items-center gap-3 bg-erp-vanilla/40 px-4 py-2 rounded-xl border border-erp-dark-vanilla/30">
          <Server className="w-4 h-4 text-erp-chocolate/70" />
          <span className="text-xs font-semibold text-erp-chocolate">Backend:</span>
          {loadingHealth ? (
            <span className="text-xs text-erp-chocolate/60 animate-pulse font-medium">Checking...</span>
          ) : healthError ? (
            <span className="inline-flex items-center gap-1 text-xs font-bold text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full border border-rose-200">
              <AlertTriangle className="w-3 h-3" /> Degraded
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
              <CheckCircle2 className="w-3 h-3" /> {health?.status?.toUpperCase() || 'HEALTHY'}
            </span>
          )}
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-erp-dark-vanilla/30 bg-white rounded-xl shadow-xs p-1.5 gap-2">
        <button
          onClick={() => setActiveTab('sessions')}
          aria-label="Live Sessions"
          title="Active Users & Sessions"
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all ${
            activeTab === 'sessions'
              ? 'bg-erp-orange text-white shadow-xs'
              : 'text-erp-chocolate/70 hover:text-erp-chocolate hover:bg-erp-vanilla/40'
          }`}
        >
          <Activity className="w-4 h-4" /> Live Sessions
          <span className="hidden sm:inline text-[11px] opacity-80 font-normal ml-0.5">(Active Users & Sessions)</span>
        </button>
        <button
          onClick={() => setActiveTab('audit')}
          aria-label="Audit Ledger"
          title="System Audit Trail"
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-all ${
            activeTab === 'audit'
              ? 'bg-erp-orange text-white shadow-xs'
              : 'text-erp-chocolate/70 hover:text-erp-chocolate hover:bg-erp-vanilla/40'
          }`}
        >
          <History className="w-4 h-4" /> Audit Ledger
          <span className="hidden sm:inline text-[11px] opacity-80 font-normal ml-0.5">(System Audit Trail)</span>
        </button>
      </div>

      {/* Tab Panels */}
      {activeTab === 'sessions' && <ActiveSessions />}
      {activeTab === 'audit' && <AuditTrail />}
    </div>
  );
}

export { SystemStatus };
