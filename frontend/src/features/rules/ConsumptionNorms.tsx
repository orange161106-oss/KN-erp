import { useEffect, useState, useContext } from 'react';
import { apiClient } from '../../api/client';
import type { ConsumptionNorm, EvaluationResult } from './types';
import { AuthContext } from '../auth/context';
import NormSetup from './NormSetup';
import { TableSkeleton } from '../../components/ui/Skeleton';

const RULE_TYPES = [
  'PRODUCTION_RATE',
  'AREA_COVERAGE',
  'PACKING_RATIO',
  'TOOL_LIFE',
  'FIXED_QUANTITY',
  'PLANT_REQUEST',
  'MAINTENANCE',
  'MIN_MAX',
] as const;

const ROUNDING_POLICIES = [
  'NONE',
  'ROUND',
  'ROUNDUP',
  'ROUNDDOWN',
  'CEILING',
  'FLOOR',
  'ROUND_HALF_UP',
] as const;

interface MasterItem {
  id: string;
  code: string;
  name?: string;
}

export default function ConsumptionNorms() {
  const auth = useContext(AuthContext);
  const user = auth?.user ?? null;
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const hasModernFlags = user && (
    'consumption_norms_read' in user ||
    'consumption_norms_create' in user ||
    'consumption_norms_update' in user ||
    'consumption_norms_delete' in user
  );
  const canRead = Boolean(isSuperAdmin || (hasModernFlags ? user?.consumption_norms_read : true));
  const canCreate = Boolean(isSuperAdmin || (hasModernFlags ? user?.consumption_norms_create : user?.permissions?.includes('masters.write')));
  const canUpdate = Boolean(isSuperAdmin || (hasModernFlags ? user?.consumption_norms_update : user?.permissions?.includes('masters.write')));
  const canDelete = Boolean(isSuperAdmin || (hasModernFlags ? user?.consumption_norms_delete : user?.permissions?.includes('masters.write')));
  const canEdit = Boolean(isSuperAdmin || canUpdate || canDelete);
  const hasActions = Boolean(isSuperAdmin || canUpdate || canDelete);
  const canCalculate = Boolean(isSuperAdmin || user?.permissions?.includes('requirements.calculate'));
  const [norms, setNorms] = useState<ConsumptionNorm[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Filtering
  const [selectedRuleTypeFilter, setSelectedRuleTypeFilter] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  // Evaluation Simulator State
  const [evalNormId, setEvalNormId] = useState('');
  const [evalQty, setEvalQty] = useState('1000');
  const [evalResult, setEvalResult] = useState<EvaluationResult | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalError, setEvalError] = useState('');
  const [evalDate, setEvalDate] = useState('');
  const [requestedQty, setRequestedQty] = useState('');

  // Create Norm Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [consumablesList, setConsumablesList] = useState<MasterItem[]>([]);
  const [unitsList, setUnitsList] = useState<MasterItem[]>([]);
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState('');

  // Form State
  const [formRuleType, setFormRuleType] = useState<string>('PRODUCTION_RATE');
  const [formConsumableId, setFormConsumableId] = useState('');
  const [formUnitId, setFormUnitId] = useState('');
  const [formRoundingPolicy, setFormRoundingPolicy] = useState('NONE');
  const [formRoundingPrecision, setFormRoundingPrecision] = useState(2);
  const [formEffectiveFrom, setFormEffectiveFrom] = useState(
    new Date().toISOString().split('T')[0]
  );

  // Dynamic Parameter Form State
  const [paramRate, setParamRate] = useState('0.005');
  const [paramScrapFactor, setParamScrapFactor] = useState('0');
  const [paramAreaPerUnit, setParamAreaPerUnit] = useState('2.5');
  const [paramCoverage, setParamCoverage] = useState('100');
  const [paramLossFactor, setParamLossFactor] = useState('0');
  const [paramUnitsPerPack, setParamUnitsPerPack] = useState('24');
  const [paramMaterialPerPack, setParamMaterialPerPack] = useState('1');
  const [paramOpsPerUnit, setParamOpsPerUnit] = useState('1');
  const [paramToolLife, setParamToolLife] = useState('2000');
  const [paramQuantity, setParamQuantity] = useState('50');
  const [paramDefaultQty, setParamDefaultQty] = useState('100');
  const [paramFixedAmount, setParamFixedAmount] = useState('20');
  const [paramVariableRate, setParamVariableRate] = useState('0.002');
  const [paramMslDays, setParamMslDays] = useState('10');
  const [paramWorkingDays, setParamWorkingDays] = useState('26');
  const [paramLeadTimeDays, setParamLeadTimeDays] = useState('0');
  const [paramMoq, setParamMoq] = useState('675');
  const [paramOrderMultiple, setParamOrderMultiple] = useState('0');

  useEffect(() => {
    loadNorms();
    loadMasters();
  }, []);

  async function loadNorms(preferredId?: string) {
    setLoading(true);
    setError('');
    try {
      const data = await apiClient.get<ConsumptionNorm[]>('/api/v1/consumption-norms');
      setNorms(data);
      setEvalNormId(previous => data.find(n => n.id === (preferredId || previous) && n.is_active)?.id || data.find(n => n.is_active)?.id || '');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load consumption norms');
    } finally {
      setLoading(false);
    }
  }

  async function loadMasters() {
    try {
      const consRes = await apiClient.get<{ items: MasterItem[] }>('/api/v1/masters/consumables?limit=100');
      if (consRes?.items) setConsumablesList(consRes.items);
    } catch {
      // Non-blocking if permissions restrict master access
    }

    try {
      const unitRes = await apiClient.get<{ items: MasterItem[] }>('/api/v1/masters/units?limit=100');
      if (unitRes?.items) {
        setUnitsList(unitRes.items);
        if (unitRes.items.length > 0) setFormUnitId(unitRes.items[0].id);
      }
    } catch {
      // Non-blocking
    }
  }

  async function handleSimulateEvaluation(e: React.FormEvent) {
    e.preventDefault();
    const selectedNorm = norms.find(n => n.id === evalNormId);
    if (!selectedNorm || !canCalculate) return;

    setEvalLoading(true);
    setEvalError('');
    setEvalResult(null);
    try {
      const res = await apiClient.post<EvaluationResult>('/api/v1/consumption-norms/evaluate', {
        consumable_id: selectedNorm.consumable_id,
        product_id: selectedNorm.product_id || null,
        process_id: selectedNorm.process_id || null,
        plant_id: selectedNorm.plant_id || null,
        production_quantity: evalQty,
        as_of_date: evalDate,
        requested_quantity: requestedQty || null,
      });
      setEvalResult(res);
    } catch (err: unknown) {
      setEvalError(err instanceof Error ? err.message : 'Evaluation failed');
    } finally {
      setEvalLoading(false);
    }
  }

  async function handleToggleActive(norm: ConsumptionNorm) {
    if (!canEdit) return;
    try {
      await apiClient.put(`/api/v1/consumption-norms/${norm.id}`, {
        is_active: !norm.is_active,
      });
      loadNorms();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update norm');
    }
  }

  function buildParameters(): Record<string, any> {
    switch (formRuleType) {
      case 'PRODUCTION_RATE':
        return { rate: paramRate, scrap_factor: paramScrapFactor };
      case 'AREA_COVERAGE':
        return {
          area_per_unit: paramAreaPerUnit,
          coverage: paramCoverage,
          loss_factor: paramLossFactor,
        };
      case 'PACKING_RATIO':
        return {
          units_per_pack: paramUnitsPerPack,
          material_per_pack: paramMaterialPerPack,
        };
      case 'TOOL_LIFE':
        return {
          operations_per_unit: paramOpsPerUnit,
          tool_life: paramToolLife,
        };
      case 'FIXED_QUANTITY':
        return { quantity: paramQuantity };
      case 'PLANT_REQUEST':
        return { default_quantity: paramDefaultQty };
      case 'MAINTENANCE':
        return {
          fixed_amount: paramFixedAmount,
          variable_rate: paramVariableRate,
        };
      case 'MIN_MAX':
        return {
          msl_days: paramMslDays,
          working_days: paramWorkingDays,
          lead_time_days: paramLeadTimeDays,
          moq: paramMoq,
          order_multiple: paramOrderMultiple,
        };
      default:
        return {};
    }
  }

  async function handleCreateNorm(e: React.FormEvent) {
    e.preventDefault();
    if (!formConsumableId) {
      setCreateError('Please select a consumable.');
      return;
    }
    if (!formUnitId) {
      setCreateError('Please select a measurement unit.');
      return;
    }

    setCreateLoading(true);
    setCreateError('');
    try {
      const payload = {
        rule_type: formRuleType,
        consumable_id: formConsumableId,
        unit_id: formUnitId,
        parameters: buildParameters(),
        rounding_policy: formRoundingPolicy,
        rounding_precision: formRoundingPrecision,
        effective_from: formEffectiveFrom,
      };

      await apiClient.post('/api/v1/consumption-norms', payload);
      setShowCreateModal(false);
      await loadNorms();
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create consumption norm');
    } finally {
      setCreateLoading(false);
    }
  }

  const filteredNorms = norms.filter(n => {
    if (selectedRuleTypeFilter !== 'ALL' && n.rule_type !== selectedRuleTypeFilter) {
      return false;
    }
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      const code = (n.consumable_code || '').toLowerCase();
      const name = (n.consumable_name || '').toLowerCase();
      if (!code.includes(term) && !name.includes(term)) return false;
    }
    return true;
  });

  if (!canRead) {
    return <p role="alert" className="text-red-700">You do not have permission to view consumption norms.</p>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
  <h2 className="text-2xl font-bold text-gray-900 tracking-tight">
    Consumption Rules & Norms
  </h2>
  <p className="text-sm text-gray-500 mt-0.5">
    KNL-Verified Consumable Calculation Engine: 8 Deterministic Rule Families with Full Traceability
  </p>
</div>
        {canCreate && (
          <button
            type="button"
            onClick={() => {
              setShowCreateModal(true);
              setCreateError('');
            }}
            className="px-4 py-2 bg-burnt-orange hover:bg-burnt-orange-dark text-white rounded text-sm font-semibold shadow-xs flex items-center gap-1.5 transition-colors"
          >
            <span>＋</span> New Consumption Norm
          </button>
        )}
      </div>

      {canCreate && <NormSetup onCreated={async id => { await loadNorms(id); setEvalResult(null); setEvalError(''); }} />}
      {!canCreate && <p className="text-sm text-gray-600">You have read-only access. A Super Admin or an employee with Create permission can configure norms.</p>}

      {/* Evaluation Simulator Card */}
      <div className="bg-white p-6 rounded-lg border border-ink-text/15 shadow-2xs space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-indigo-950 uppercase tracking-wide">
              Test a consumption norm
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Simulate explainable requirement calculations with step-by-step audit trails.
            </p>
          </div>
          <span className="text-xs bg-indigo-100 text-indigo-800 font-semibold px-2.5 py-1 rounded-full">
            Calculation preview
          </span>
        </div>

        <form onSubmit={handleSimulateEvaluation} className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-end">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Select Norm to Evaluate</label>
            <select
              value={evalNormId}
              onChange={e => setEvalNormId(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm bg-white"
            >
              {norms.length === 0 ? (
                <option value="">No norms configured</option>
              ) : (
                norms.filter(n => n.is_active).map(n => (
                  <option key={n.id} value={n.id}>
                    {n.consumable_code || n.consumable_id} [{n.rule_type} v{n.version}]
                  </option>
                ))
              )}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Production Quantity</label>
            <input
              type="number"
              step="any"
              min="0"
              value={evalQty}
              onChange={e => setEvalQty(e.target.value)}
              required
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              placeholder="e.g. 1000"
            />
          </div>

          <label className="block text-xs font-medium">Calculation date
            <input required type="date" className="block w-full border rounded px-3 py-2" value={evalDate} onChange={e => setEvalDate(e.target.value)} />
          </label>
          {norms.find(n => n.id === evalNormId)?.rule_type === 'PLANT_REQUEST' && <label className="block text-xs font-medium">Explicit requested quantity (optional)
            <input type="number" min="0" step="any" className="block w-full border rounded px-3 py-2" value={requestedQty} onChange={e => setRequestedQty(e.target.value)} />
          </label>}

          <div>
            <button
              type="submit"
              disabled={evalLoading || !evalNormId || !canCalculate}
              className="w-full bg-burnt-orange hover:bg-burnt-orange-dark text-white font-medium py-2 px-4 rounded text-sm disabled:opacity-50 transition-colors shadow-xs"
            >
              {evalLoading ? 'Calculating…' : 'Run Calculation'}
            </button>
          </div>
        </form>
        <p className="text-sm text-gray-600">This preview does not approve demand, create a purchase order or change stock.</p>

        {evalError && (
          <div className="bg-red-50 text-red-700 p-3 rounded text-sm border border-red-200">
            {evalError}
          </div>
        )}

        {evalResult && (
          <div className="mt-4 p-5 bg-indigo-50/50 rounded-lg border border-indigo-100 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-indigo-100 pb-3">
              <div>
                <span className="text-xs uppercase font-bold text-indigo-700">Calculated Output</span>
                <div className="text-2xl font-bold text-gray-900 mt-1">
                  {evalResult.calculation.final_calculated_requirement}{' '}
                  <span className="text-sm font-normal text-gray-600">{evalResult.calculation.unit}</span>
                </div>
              </div>

              <div className="text-right text-xs text-gray-500">
                <div>Raw Value: <span className="font-mono text-gray-800">{evalResult.calculation.raw_requirement}</span></div>
                <div>Rounding: <span className="font-semibold text-gray-800">{evalResult.calculation.rounding_policy}</span> (prec {evalResult.calculation.rounding_precision})</div>
              </div>
            </div>

            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-gray-600 block mb-2">
                Explainable Audit Steps:
              </span>
              <ul className="space-y-2 text-xs">
                {evalResult.calculation.calculation_steps.map((step, idx) => (
                  <li key={idx} className="bg-white p-3 rounded border border-gray-200 shadow-2xs">
                    <span className="font-bold text-indigo-600 mr-2">Step {step.step_number}:</span>
                    <span className="text-gray-800">{step.description}</span>
                    <div className="mt-1 font-mono text-indigo-900 bg-indigo-50/60 p-1.5 rounded text-2xs">
                      Formula: {step.formula} ⇒ <span className="font-bold">{step.result}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>

      {/* Norms Directory Table */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
          <h3 className="text-lg font-semibold text-gray-800">Rule Master Registry ({filteredNorms.length})</h3>

          <div className="flex items-center gap-3 w-full sm:w-auto">
            <input
              type="text"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              placeholder="🔍 Search consumable..."
              className="border border-gray-300 rounded px-3 py-1.5 text-xs bg-white w-full sm:w-48"
            />
          </div>
        </div>

        {/* Rule Type Filter Tabs */}
        <div className="flex flex-wrap gap-1 border-b border-gray-200 pb-2">
          <button
            type="button"
            onClick={() => setSelectedRuleTypeFilter('ALL')}
            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
              selectedRuleTypeFilter === 'ALL'
                ? 'bg-indigo-600 text-white font-bold'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            All Rules ({norms.length})
          </button>
          {RULE_TYPES.map(rt => {
            const count = norms.filter(n => n.rule_type === rt).length;
            return (
              <button
                key={rt}
                type="button"
                onClick={() => setSelectedRuleTypeFilter(rt)}
                className={`px-2.5 py-1 rounded text-2xs font-semibold transition-colors ${
                  selectedRuleTypeFilter === rt
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {rt} ({count})
              </button>
            );
          })}
        </div>

        {loading && <div className="mb-4"><TableSkeleton columns={7 + (hasActions ? 1 : 0)} rows={5} /></div>}
        {error && <div className="text-red-700 p-3 bg-red-50 rounded border border-red-200">{error}</div>}

        <div className="bg-white rounded-lg border border-ink-text/10 overflow-hidden shadow-2xs">
          <table className="min-w-full divide-y divide-ink-text/10 text-sm">
            <thead className="bg-vanilla-surface border-b border-ink-text/10 text-ink-text">
              <tr>
                <th className="px-4 py-3 text-left font-semibold text-ink-text">Consumable</th>
                <th className="px-4 py-3 text-left font-semibold text-ink-text">Rule Type</th>
                <th className="px-4 py-3 text-center font-semibold text-ink-text">Version</th>
                <th className="px-4 py-3 text-left font-semibold text-ink-text">Scope</th>
                <th className="px-4 py-3 text-left font-semibold text-ink-text">Parameters</th>
                <th className="px-4 py-3 text-center font-semibold text-ink-text">Rounding</th>
                <th className="px-4 py-3 text-center font-semibold text-ink-text">Status</th>
                {hasActions && <th className="px-4 py-3 text-right font-semibold text-ink-text">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-text/10">
              {filteredNorms.length === 0 ? (
                <tr>
                  <td colSpan={7 + (hasActions ? 1 : 0)} className="px-4 py-6 text-center text-gray-500">
                    No consumption norms match the selected filter.
                  </td>
                </tr>
              ) : (
                filteredNorms.map(norm => (
                  <tr key={norm.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {norm.consumable_code || norm.consumable_id}
                      {norm.consumable_name && (
                        <span className="block text-xs text-gray-500 font-normal">{norm.consumable_name}</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded text-2xs font-semibold bg-indigo-100 text-indigo-800">
                        {norm.rule_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center font-bold text-gray-700">v{norm.version}</td>
                    <td className="px-4 py-3 text-xs text-gray-600">
                      <div>Product: {norm.product_code || (norm.product_id ? 'Yes' : 'Global')}</div>
                      <div>Process: {norm.process_name || (norm.process_id ? 'Yes' : 'Global')}</div>
                    </td>
                    <td className="px-4 py-3 text-xs font-mono text-gray-700">
                      {JSON.stringify(norm.parameters)}
                    </td>
                    <td className="px-4 py-3 text-center text-xs text-gray-600">
                      {norm.rounding_policy} ({norm.rounding_precision})
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className={`px-2 py-0.5 text-xs font-semibold rounded ${
                          norm.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {norm.is_active ? 'Active' : 'Superseded'}
                      </span>
                    </td>
                    {hasActions && (
                      <td className="px-4 py-3 text-right">
                        {canDelete && (
                          <button
                            onClick={() => handleToggleActive(norm)}
                            className="text-xs text-indigo-600 hover:text-indigo-900 underline font-medium"
                          >
                            {norm.is_active ? 'Deactivate' : 'Reactivate'}
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create Consumption Norm Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-lg shadow-xl border border-gray-200 max-w-xl w-full max-h-[90vh] overflow-y-auto">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between bg-gray-50/70">
              <div>
                <h3 className="text-base font-bold text-gray-900">Define New Consumption Norm</h3>
                <p className="text-xs text-gray-500">
                  Versioned deterministic business rule foundation
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="text-gray-400 hover:text-gray-600 font-bold text-lg p-1"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateNorm} className="p-6 space-y-4 text-xs">
              {createError && (
                <div className="p-3 bg-red-50 text-red-700 rounded border border-red-200">
                  {createError}
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-medium text-gray-700 mb-1">Rule Type *</label>
                  <select
                    value={formRuleType}
                    onChange={e => setFormRuleType(e.target.value)}
                    className="w-full border border-gray-300 rounded px-2.5 py-1.5 text-xs bg-white font-medium text-indigo-950"
                  >
                    {RULE_TYPES.map(rt => (
                      <option key={rt} value={rt}>{rt}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block font-medium text-gray-700 mb-1">Measurement Unit *</label>
                  {unitsList.length > 0 ? (
                    <select
                      value={formUnitId}
                      onChange={e => setFormUnitId(e.target.value)}
                      className="w-full border border-gray-300 rounded px-2.5 py-1.5 text-xs bg-white"
                      required
                    >
                      <option value="">Select Unit</option>
                      {unitsList.map(u => (
                        <option key={u.id} value={u.id}>{u.code} {u.name ? `(${u.name})` : ''}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={formUnitId}
                      onChange={e => setFormUnitId(e.target.value)}
                      placeholder="Unit ID or Code"
                      required
                      className="w-full border border-gray-300 rounded px-2.5 py-1.5 text-xs"
                    />
                  )}
                </div>
              </div>

              <div>
                <label className="block font-medium text-gray-700 mb-1">Consumable *</label>
                {consumablesList.length > 0 ? (
                  <select
                    value={formConsumableId}
                    onChange={e => setFormConsumableId(e.target.value)}
                    className="w-full border border-gray-300 rounded px-2.5 py-1.5 text-xs bg-white"
                    required
                  >
                    <option value="">Select Consumable</option>
                    {consumablesList.map(c => (
                      <option key={c.id} value={c.id}>{c.code} - {c.name || 'Consumable'}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={formConsumableId}
                    onChange={e => setFormConsumableId(e.target.value)}
                    placeholder="Consumable UUID"
                    required
                    className="w-full border border-gray-300 rounded px-2.5 py-1.5 text-xs"
                  />
                )}
              </div>

              {/* Dynamic Parameter Fields */}
              <div className="p-3.5 bg-gray-50 border border-gray-200 rounded-md space-y-3">
                <div className="font-bold text-indigo-900 uppercase tracking-wide text-2xs">
                  {formRuleType} Parameters
                </div>

                {formRuleType === 'PRODUCTION_RATE' && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-gray-600 mb-0.5">Consumption Rate *</label>
                      <input
                        type="number"
                        step="any"
                        value={paramRate}
                        onChange={e => setParamRate(e.target.value)}
                        required
                        className="w-full border border-gray-300 rounded px-2.5 py-1 text-xs"
                        placeholder="e.g. 0.005"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-600 mb-0.5">Scrap Factor (e.g. 0.05)</label>
                      <input
                        type="number"
                        step="any"
                        value={paramScrapFactor}
                        onChange={e => setParamScrapFactor(e.target.value)}
                        className="w-full border border-gray-300 rounded px-2.5 py-1 text-xs"
                      />
                    </div>
                  </div>
                )}

                {formRuleType === 'AREA_COVERAGE' && (
                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <label className="block text-gray-600 mb-0.5">Area / Unit (Sq.ft)</label>
                      <input
                        type="number"
                        step="any"
                        value={paramAreaPerUnit}
                        onChange={e => setParamAreaPerUnit(e.target.value)}
                        required
                        className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-600 mb-0.5">Coverage (Sq.ft/kg) *</label>
                      <input
                        type="number"
                        step="any"
                        value={paramCoverage}
                        onChange={e => setParamCoverage(e.target.value)}
                        required
                        className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-600 mb-0.5">Loss Factor</label>
                      <input
                        type="number"
                        step="any"
                        value={paramLossFactor}
                        onChange={e => setParamLossFactor(e.target.value)}
                        className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                      />
                    </div>
                  </div>
                )}

                {formRuleType === 'PACKING_RATIO' && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-gray-600 mb-0.5">Pieces Per Pack *</label>
                      <input
                        type="number"
                        step="any"
                        value={paramUnitsPerPack}
                        onChange={e => setParamUnitsPerPack(e.target.value)}
                        required
                        className="w-full border border-gray-300 rounded px-2.5 py-1 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-600 mb-0.5">Material Factor / Pack</label>
                      <input
                        type="number"
                        step="any"
                        value={paramMaterialPerPack}
                        onChange={e => setParamMaterialPerPack(e.target.value)}
                        className="w-full border border-gray-300 rounded px-2.5 py-1 text-xs"
                      />
                    </div>
                  </div>
                )}

                {formRuleType === 'TOOL_LIFE' && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-gray-600 mb-0.5">Operations Per Part</label>
                      <input
                        type="number"
                        step="any"
                        value={paramOpsPerUnit}
                        onChange={e => setParamOpsPerUnit(e.target.value)}
                        required
                        className="w-full border border-gray-300 rounded px-2.5 py-1 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-600 mb-0.5">Rated Tool Life (Operations) *</label>
                      <input
                        type="number"
                        step="any"
                        value={paramToolLife}
                        onChange={e => setParamToolLife(e.target.value)}
                        required
                        className="w-full border border-gray-300 rounded px-2.5 py-1 text-xs"
                      />
                    </div>
                  </div>
                )}

                {formRuleType === 'FIXED_QUANTITY' && (
                  <div>
                    <label className="block text-gray-600 mb-0.5">Fixed Periodic Quantity *</label>
                    <input
                      type="number"
                      step="any"
                      value={paramQuantity}
                      onChange={e => setParamQuantity(e.target.value)}
                      required
                      className="w-full border border-gray-300 rounded px-2.5 py-1 text-xs"
                    />
                  </div>
                )}

                {formRuleType === 'PLANT_REQUEST' && (
                  <div>
                    <label className="block text-gray-600 mb-0.5">Default Fallback Quantity</label>
                    <input
                      type="number"
                      step="any"
                      value={paramDefaultQty}
                      onChange={e => setParamDefaultQty(e.target.value)}
                      required
                      className="w-full border border-gray-300 rounded px-2.5 py-1 text-xs"
                    />
                  </div>
                )}

                {formRuleType === 'MAINTENANCE' && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-gray-600 mb-0.5">Fixed Baseline Amount</label>
                      <input
                        type="number"
                        step="any"
                        value={paramFixedAmount}
                        onChange={e => setParamFixedAmount(e.target.value)}
                        className="w-full border border-gray-300 rounded px-2.5 py-1 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-600 mb-0.5">Variable Wear Rate</label>
                      <input
                        type="number"
                        step="any"
                        value={paramVariableRate}
                        onChange={e => setParamVariableRate(e.target.value)}
                        className="w-full border border-gray-300 rounded px-2.5 py-1 text-xs"
                      />
                    </div>
                  </div>
                )}

                {formRuleType === 'MIN_MAX' && (
                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <label className="block text-gray-600 mb-0.5">MSL Days (e.g. 10)</label>
                      <input
                        type="number"
                        step="any"
                        value={paramMslDays}
                        onChange={e => setParamMslDays(e.target.value)}
                        className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-600 mb-0.5">Working Days (26)</label>
                      <input
                        type="number"
                        step="any"
                        value={paramWorkingDays}
                        onChange={e => setParamWorkingDays(e.target.value)}
                        className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-600 mb-0.5">MOQ</label>
                      <input
                        type="number"
                        step="any"
                        value={paramMoq}
                        onChange={e => setParamMoq(e.target.value)}
                        className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-600 mb-0.5">Lead Time Days</label>
                      <input
                        type="number"
                        step="any"
                        value={paramLeadTimeDays}
                        onChange={e => setParamLeadTimeDays(e.target.value)}
                        className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-600 mb-0.5">Pack Multiple</label>
                      <input
                        type="number"
                        step="any"
                        value={paramOrderMultiple}
                        onChange={e => setParamOrderMultiple(e.target.value)}
                        className="w-full border border-gray-300 rounded px-2 py-1 text-xs"
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Rounding & Effective Date */}
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block font-medium text-gray-700 mb-1">Rounding Policy</label>
                  <select
                    value={formRoundingPolicy}
                    onChange={e => setFormRoundingPolicy(e.target.value)}
                    className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs bg-white"
                  >
                    {ROUNDING_POLICIES.map(rp => (
                      <option key={rp} value={rp}>{rp}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block font-medium text-gray-700 mb-1">Precision</label>
                  <input
                    type="number"
                    min="0"
                    max="6"
                    value={formRoundingPrecision}
                    onChange={e => setFormRoundingPrecision(Number(e.target.value))}
                    className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs"
                  />
                </div>

                <div>
                  <label className="block font-medium text-gray-700 mb-1">Effective Date</label>
                  <input
                    type="date"
                    value={formEffectiveFrom}
                    onChange={e => setFormEffectiveFrom(e.target.value)}
                    required
                    className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs"
                  />
                </div>
              </div>

              <div className="pt-3 border-t border-gray-200 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-3.5 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded font-medium text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createLoading}
                  className="px-4 py-1.5 bg-burnt-orange hover:bg-burnt-orange-dark text-white rounded font-medium text-xs disabled:opacity-50 transition-colors shadow-xs"
                >
                  {createLoading ? 'Creating…' : 'Save & Publish Norm'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
