import { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import type { ConsumptionNorm, EvaluationResult } from './types';

export default function ConsumptionNorms() {
  const [norms, setNorms] = useState<ConsumptionNorm[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Evaluation Simulator State
  const [evalNormId, setEvalNormId] = useState('');
  const [evalQty, setEvalQty] = useState('1000');
  const [evalResult, setEvalResult] = useState<EvaluationResult | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalError, setEvalError] = useState('');

  useEffect(() => {
    loadNorms();
  }, []);

  async function loadNorms() {
    setLoading(true);
    setError('');
    try {
      const data = await apiClient.get<ConsumptionNorm[]>('/api/v1/consumption-norms');
      setNorms(data);
      if (data.length > 0 && !evalNormId) {
        setEvalNormId(data[0].id);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load consumption norms');
    } finally {
      setLoading(false);
    }
  }

  async function handleSimulateEvaluation(e: React.FormEvent) {
    e.preventDefault();
    const selectedNorm = norms.find(n => n.id === evalNormId);
    if (!selectedNorm) return;

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
      });
      setEvalResult(res);
    } catch (err: unknown) {
      setEvalError(err instanceof Error ? err.message : 'Evaluation failed');
    } finally {
      setEvalLoading(false);
    }
  }

  async function handleToggleActive(norm: ConsumptionNorm) {
    try {
      await apiClient.put(`/api/v1/consumption-norms/${norm.id}`, {
        is_active: !norm.is_active,
      });
      loadNorms();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to update norm');
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Consumption Rules & Norms</h2>
          <p className="text-sm text-gray-500 mt-1">
            M3.1 Requirement Calculation Framework: Deterministic Strategy per Rule Type
          </p>
        </div>
      </div>

      {/* Evaluation Simulator Card */}
      <div className="bg-white p-6 rounded-lg border border-indigo-200 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-indigo-950 uppercase tracking-wide">
              Deterministic Calculation Simulator
            </h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Simulate explainable requirement calculations with step-by-step audit trails.
            </p>
          </div>
          <span className="text-xs bg-indigo-100 text-indigo-800 font-semibold px-2.5 py-1 rounded-full">
            Pure Domain Engine
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
                norms.map(n => (
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
              value={evalQty}
              onChange={e => setEvalQty(e.target.value)}
              required
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              placeholder="e.g. 1000"
            />
          </div>

          <div>
            <button
              type="submit"
              disabled={evalLoading || !evalNormId}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2 px-4 rounded text-sm disabled:opacity-50"
            >
              {evalLoading ? 'Calculating…' : 'Run Calculation'}
            </button>
          </div>
        </form>

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
        <h3 className="text-lg font-semibold text-gray-800">Active & Historical Norms</h3>

        {loading && <div className="text-gray-500 py-4 text-center">Loading consumption norms…</div>}
        {error && <div className="text-red-700 p-3 bg-red-50 rounded border border-red-200">{error}</div>}

        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-semibold text-gray-700">Consumable</th>
                <th className="px-4 py-3 text-left font-semibold text-gray-700">Rule Type</th>
                <th className="px-4 py-3 text-center font-semibold text-gray-700">Version</th>
                <th className="px-4 py-3 text-left font-semibold text-gray-700">Scope</th>
                <th className="px-4 py-3 text-left font-semibold text-gray-700">Parameters</th>
                <th className="px-4 py-3 text-center font-semibold text-gray-700">Rounding</th>
                <th className="px-4 py-3 text-center font-semibold text-gray-700">Status</th>
                <th className="px-4 py-3 text-right font-semibold text-gray-700">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {norms.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-gray-500">
                    No consumption norms configured.
                  </td>
                </tr>
              ) : (
                norms.map(norm => (
                  <tr key={norm.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {norm.consumable_code || norm.consumable_id}
                      {norm.consumable_name && (
                        <span className="block text-xs text-gray-500 font-normal">{norm.consumable_name}</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-indigo-100 text-indigo-800">
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
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleToggleActive(norm)}
                        className="text-xs text-indigo-600 hover:text-indigo-900 underline font-medium"
                      >
                        {norm.is_active ? 'Deactivate' : 'Reactivate'}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
