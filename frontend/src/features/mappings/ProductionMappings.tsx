import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../../api/client';
import type {
  MappingValidationReport,
  MasterOption,
  ProductPlant,
  ProductProcessConsumable,
  ProductResolutionResponse,
} from './types';

export default function ProductionMappings() {
  const [activeTab, setActiveTab] = useState<'traceability' | 'productPlants' | 'processConsumables' | 'validation'>('traceability');
  const [products, setProducts] = useState<MasterOption[]>([]);
  const [consumables, setConsumables] = useState<MasterOption[]>([]);
  const loadedTabs = useRef(new Set<string>());
  const resolutionRequest = useRef(0);
  const [lookupLoading, setLookupLoading] = useState(true);
  const [lookupError, setLookupError] = useState('');

  // Traceability State
  const [selectedProductId, setSelectedProductId] = useState<string>('');
  const [resolution, setResolution] = useState<ProductResolutionResponse | null>(null);
  const [resolutionLoading, setResolutionLoading] = useState(false);
  const [resolutionError, setResolutionError] = useState('');

  // Product-Plant State
  const [productPlants, setProductPlants] = useState<ProductPlant[]>([]);
  const [ppLoading, setPpLoading] = useState(false);
  const [ppLoaded, setPpLoaded] = useState(false);
  const [ppError, setPpError] = useState('');
  const [showAddPp, setShowAddPp] = useState(false);
  const [newPpProduct, setNewPpProduct] = useState('');
  const [newPpPlant, setNewPpPlant] = useState('');
  const [newPpRoute, setNewPpRoute] = useState('');
  const [newPpPrimary, setNewPpPrimary] = useState(true);

  // PPC State
  const [ppcList, setPpcList] = useState<ProductProcessConsumable[]>([]);
  const [ppcLoading, setPpcLoading] = useState(false);
  const [ppcLoaded, setPpcLoaded] = useState(false);
  const [ppcError, setPpcError] = useState('');
  const [showAddPpc, setShowAddPpc] = useState(false);
  const [newPpcProduct, setNewPpcProduct] = useState('');
  const [newPpcProcess, setNewPpcProcess] = useState('');
  const [newPpcConsumable, setNewPpcConsumable] = useState('');

  // Validation State
  const [validationReport, setValidationReport] = useState<MappingValidationReport | null>(null);
  const [valLoading, setValLoading] = useState(false);
  const [valError, setValError] = useState('');

  // Initial Data Load
  useEffect(() => {
    void loadMasterLookups();
  }, []);

  // Hidden tabs should not compete with the screen the user is opening.
  useEffect(() => {
    if (loadedTabs.current.has(activeTab)) return;
    loadedTabs.current.add(activeTab);
    if (activeTab === 'productPlants') void loadProductPlants();
    if (activeTab === 'processConsumables') {
      void loadPpcList();
      void loadConsumables();
    }
  }, [activeTab]);

  async function loadMasterLookups() {
    setLookupLoading(true);
    setLookupError('');
    try {
      const prods = await apiClient.get<Array<{ id: string; code: string; name: string }>>('/api/v1/masters/products');
      if (Array.isArray(prods)) {
        setProducts(prods.map(p => ({ id: p.id, code: p.code, name: `${p.code} - ${p.name}` })));
        if (prods.length > 0) setSelectedProductId(current => current || prods[0].id);
      }
    } catch (error) {
      setLookupError(error instanceof Error ? error.message : 'Failed to load products');
    } finally { setLookupLoading(false); }
  }

  async function loadConsumables() {
    try {
      const cons = await apiClient.get<{ items: Array<{ id: string; code: string; name: string }> }>('/api/v1/masters/consumables?limit=100');
      if (cons && Array.isArray(cons.items)) {
        setConsumables(cons.items.map(c => ({ id: c.id, code: c.code, name: `${c.code} - ${c.name}` })));
      }
    } catch (error) {
      loadedTabs.current.delete('processConsumables');
      setPpcError(error instanceof Error ? error.message : 'Failed to load consumable choices');
    }
  }

  async function loadProductPlants() {
    setPpLoading(true);
    setPpError('');
    try {
      const res = await apiClient.get<ProductPlant[]>('/api/v1/mappings/product-plants');
      setProductPlants(res);
      setPpLoaded(true);
    } catch (err: unknown) {
      loadedTabs.current.delete('productPlants');
      setPpError(err instanceof Error ? err.message : 'Failed to load product plants');
    } finally {
      setPpLoading(false);
    }
  }

  async function loadPpcList() {
    setPpcLoading(true);
    setPpcError('');
    try {
      const res = await apiClient.get<ProductProcessConsumable[]>('/api/v1/mappings/product-process-consumables');
      setPpcList(res);
      setPpcLoaded(true);
    } catch (err: unknown) {
      loadedTabs.current.delete('processConsumables');
      setPpcError(err instanceof Error ? err.message : 'Failed to load consumable mappings');
    } finally {
      setPpcLoading(false);
    }
  }

  // Load Resolution Tree when selectedProductId changes
  useEffect(() => {
    if (!selectedProductId || activeTab !== 'traceability') return;
    void loadResolution(selectedProductId);
    return () => { resolutionRequest.current += 1; };
  }, [selectedProductId, activeTab]);

  async function loadResolution(productId: string) {
    const attempt = ++resolutionRequest.current;
    setResolutionLoading(true);
    setResolutionError('');
    try {
      const data = await apiClient.get<ProductResolutionResponse>(`/api/v1/mappings/resolve/${productId}`);
      if (attempt === resolutionRequest.current) setResolution(data);
    } catch (err: unknown) {
      if (attempt === resolutionRequest.current) {
        setResolutionError(err instanceof Error ? err.message : 'Failed to load resolution tree');
        setResolution(null);
      }
    } finally {
      if (attempt === resolutionRequest.current) setResolutionLoading(false);
    }
  }

  async function runValidation() {
    setValLoading(true);
    setValError('');
    try {
      const data = await apiClient.get<MappingValidationReport>('/api/v1/mappings/validate');
      setValidationReport(data);
    } catch (err: unknown) {
      setValError(err instanceof Error ? err.message : 'Failed to run mapping validation');
    } finally {
      setValLoading(false);
    }
  }

  async function handleCreatePp(e: React.FormEvent) {
    e.preventDefault();
    if (!newPpProduct || !newPpPlant || !newPpRoute) return;
    try {
      await apiClient.post('/api/v1/mappings/product-plants', {
        product_id: newPpProduct,
        plant_id: newPpPlant,
        route_id: newPpRoute,
        is_primary: newPpPrimary,
      });
      setShowAddPp(false);
      loadProductPlants();
      if (selectedProductId === newPpProduct) loadResolution(newPpProduct);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Error adding product plant mapping');
    }
  }

  async function handleTogglePpActive(mapping: ProductPlant) {
    try {
      await apiClient.put(`/api/v1/mappings/product-plants/${mapping.id}`, {
        is_active: !mapping.is_active,
      });
      loadProductPlants();
      if (selectedProductId === mapping.product_id) loadResolution(mapping.product_id);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Error updating mapping');
    }
  }

  async function handleCreatePpc(e: React.FormEvent) {
    e.preventDefault();
    if (!newPpcProduct || !newPpcProcess || !newPpcConsumable) return;
    try {
      await apiClient.post('/api/v1/mappings/product-process-consumables', {
        product_id: newPpcProduct,
        process_id: newPpcProcess,
        consumable_id: newPpcConsumable,
      });
      setShowAddPpc(false);
      loadPpcList();
      if (selectedProductId === newPpcProduct) loadResolution(newPpcProduct);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Error adding consumable mapping');
    }
  }

  async function handleTogglePpcActive(mapping: ProductProcessConsumable) {
    try {
      await apiClient.put(`/api/v1/mappings/product-process-consumables/${mapping.id}`, {
        is_active: !mapping.is_active,
      });
      loadPpcList();
      if (selectedProductId === mapping.product_id) loadResolution(mapping.product_id);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Error updating mapping');
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Production Mappings</h2>
          <p className="text-sm text-gray-500 mt-1">
            M2.4 Architecture: Product → Plant → Route → Process → Consumable Structural Backbone
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('traceability')}
            className={`py-3 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'traceability'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Phase 2 Gate Traceability
          </button>
          <button
            onClick={() => setActiveTab('productPlants')}
            className={`py-3 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'productPlants'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Product-Plant Routes{ppLoaded ? ` (${productPlants.length})` : ''}
          </button>
          <button
            onClick={() => setActiveTab('processConsumables')}
            className={`py-3 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'processConsumables'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Process Consumables{ppcLoaded ? ` (${ppcList.length})` : ''}
          </button>
          <button
            onClick={() => {
              setActiveTab('validation');
              if (!validationReport) runValidation();
            }}
            className={`py-3 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'validation'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Mapping Integrity Audit
          </button>
        </nav>
      </div>

      {lookupLoading && <p role="status">Loading product choices…</p>}
      {lookupError && <div role="alert" className="text-red-700">{lookupError} <button className="underline" onClick={() => void loadMasterLookups()}>Retry products</button></div>}

      {/* TAB 1: Traceability & Resolution (Gate Demonstration) */}
      {activeTab === 'traceability' && (
        <div className="space-y-6">
          <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
            <div>
              <label htmlFor="productSelect" className="block text-xs font-semibold uppercase tracking-wider text-gray-600 mb-1">
                Select PRD Product to Resolve Chain:
              </label>
              <select
                id="productSelect"
                value={selectedProductId}
                onChange={e => setSelectedProductId(e.target.value)}
                className="border border-gray-300 rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {products.length === 0 ? (
                  <option value="">No products loaded</option>
                ) : (
                  products.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))
                )}
              </select>
            </div>

            <div className="text-right">
              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                Phase 2 Gate Ready
              </span>
            </div>
          </div>

          {resolutionLoading && <div className="text-gray-500 py-8 text-center">Tracing structural tree…</div>}
          {resolutionError && (
            <div className="bg-red-50 text-red-700 p-4 rounded-md border border-red-200">
              {resolutionError}
            </div>
          )}

          {resolution && !resolutionLoading && (
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden p-6 space-y-6">
              {/* Product Header */}
              <div className="border-b pb-4">
                <span className="text-xs font-bold uppercase tracking-wider text-indigo-600">Product Root</span>
                <h3 className="text-xl font-bold text-gray-900 mt-1">
                  {resolution.product_code} — {resolution.product_name}
                </h3>
                <span className="text-xs text-gray-500">Default UOM: {resolution.uom}</span>
              </div>

              {/* Plants */}
              {resolution.plant_mappings.length === 0 ? (
                <div className="p-4 bg-amber-50 text-amber-800 rounded-md border border-amber-200 text-sm">
                  ⚠️ No active plant or route mappings found for this product. Use the "Product-Plant Routes" tab to configure.
                </div>
              ) : (
                <div className="space-y-6">
                  {resolution.plant_mappings.map(plant => (
                    <div key={plant.plant_id} className="border border-indigo-100 bg-indigo-50/20 rounded-lg p-5 space-y-4">
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-blue-100 text-blue-800">
                              Manufacturing Plant
                            </span>
                            {plant.is_primary && (
                              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">
                                Primary Plant
                              </span>
                            )}
                          </div>
                          <h4 className="text-lg font-semibold text-gray-900 mt-1">{plant.plant_name}</h4>
                          {plant.location && <p className="text-xs text-gray-500">{plant.location}</p>}
                        </div>
                        <div className="text-right">
                          <span className="text-xs text-gray-500 block">Assigned Route:</span>
                          <span className="text-sm font-medium text-gray-800">{plant.route_name}</span>
                        </div>
                      </div>

                      {/* Process Steps */}
                      <div className="mt-4 pl-4 border-l-2 border-indigo-300 space-y-4">
                        <span className="text-xs font-bold uppercase tracking-wider text-gray-500">
                          Route Process Steps ({plant.steps.length})
                        </span>

                        {plant.steps.length === 0 ? (
                          <p className="text-sm text-gray-500 italic">No steps defined for this route.</p>
                        ) : (
                          plant.steps.map(step => (
                            <div key={step.process_id} className="bg-white rounded border border-gray-200 p-4 shadow-xs">
                              <div className="flex items-center gap-3">
                                <span className="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold">
                                  {step.sequence_order}
                                </span>
                                <div>
                                  <h5 className="font-semibold text-gray-900">{step.process_name}</h5>
                                  {step.process_description && (
                                    <p className="text-xs text-gray-500">{step.process_description}</p>
                                  )}
                                </div>
                              </div>

                              {/* Consumables mapped to this step */}
                              <div className="mt-3 pl-9">
                                <span className="text-xs font-medium text-gray-500 block mb-1.5">
                                  Required Consumables:
                                </span>
                                {step.consumables.length === 0 ? (
                                  <span className="text-xs text-amber-700 bg-amber-50 px-2 py-1 rounded inline-block">
                                    No consumables mapped to this step
                                  </span>
                                ) : (
                                  <div className="flex flex-wrap gap-2">
                                    {step.consumables.map(c => (
                                      <span
                                        key={c.id}
                                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200"
                                      >
                                        <span className="font-semibold">{c.code}</span>
                                        <span>— {c.name}</span>
                                        <span className="text-emerald-600 font-mono">({c.unit})</span>
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: Product-Plant Routes */}
      {activeTab === 'productPlants' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold text-gray-800">Product Plant Assignments</h3>
            <button
              onClick={() => setShowAddPp(!showAddPp)}
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded shadow-sm"
            >
              {showAddPp ? 'Cancel' : '+ Map Product to Plant'}
            </button>
          </div>

          {showAddPp && (
            <form onSubmit={handleCreatePp} className="bg-white p-5 rounded-lg border border-indigo-200 shadow-sm space-y-4">
              <h4 className="text-sm font-bold text-indigo-900 uppercase">New Product-Plant Route</h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Product</label>
                  <select
                    value={newPpProduct}
                    onChange={e => setNewPpProduct(e.target.value)}
                    required
                    className="w-full border border-gray-300 rounded px-2.5 py-1.5 text-sm"
                  >
                    <option value="">Select product...</option>
                    {products.map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Plant ID</label>
                  <input
                    type="text"
                    placeholder="Enter Plant UUID"
                    value={newPpPlant}
                    onChange={e => setNewPpPlant(e.target.value)}
                    required
                    className="w-full border border-gray-300 rounded px-2.5 py-1.5 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Route ID</label>
                  <input
                    type="text"
                    placeholder="Enter Route UUID"
                    value={newPpRoute}
                    onChange={e => setNewPpRoute(e.target.value)}
                    required
                    className="w-full border border-gray-300 rounded px-2.5 py-1.5 text-sm"
                  />
                </div>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="primaryCheck"
                  checked={newPpPrimary}
                  onChange={e => setNewPpPrimary(e.target.checked)}
                />
                <label htmlFor="primaryCheck" className="text-sm text-gray-700">Set as Primary Plant for this product</label>
              </div>

              <button type="submit" className="px-4 py-2 bg-indigo-600 text-white rounded text-sm font-medium hover:bg-indigo-700">
                Save Assignment
              </button>
            </form>
          )}

          {ppLoading && <div className="text-gray-500 py-4 text-center">Loading product plant mappings…</div>}
          {ppError && <div role="alert" className="text-red-700 p-3 bg-red-50 rounded border border-red-200">{ppError} <button className="underline" onClick={() => void loadProductPlants()}>Retry mappings</button></div>}

          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold text-gray-700">Product</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-700">Plant</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-700">Route</th>
                  <th className="px-4 py-3 text-center font-semibold text-gray-700">Primary</th>
                  <th className="px-4 py-3 text-center font-semibold text-gray-700">Status</th>
                  <th className="px-4 py-3 text-right font-semibold text-gray-700">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {productPlants.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-center text-gray-500">
                      No product-plant mappings found.
                    </td>
                  </tr>
                ) : (
                  productPlants.map(pp => (
                    <tr key={pp.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-900">
                        {pp.product_code || pp.product_id}
                        {pp.product_name && <span className="block text-xs text-gray-500 font-normal">{pp.product_name}</span>}
                      </td>
                      <td className="px-4 py-3 text-gray-700">{pp.plant_name || pp.plant_id}</td>
                      <td className="px-4 py-3 text-gray-700">{pp.route_name || pp.route_id}</td>
                      <td className="px-4 py-3 text-center">
                        {pp.is_primary ? (
                          <span className="px-2 py-0.5 text-xs font-semibold rounded bg-green-100 text-green-800">Primary</span>
                        ) : (
                          <span className="px-2 py-0.5 text-xs text-gray-500">Secondary</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`px-2 py-0.5 text-xs font-semibold rounded ${pp.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-600'}`}>
                          {pp.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleTogglePpActive(pp)}
                          className="text-xs text-indigo-600 hover:text-indigo-900 underline font-medium"
                        >
                          {pp.is_active ? 'Deactivate' : 'Reactivate'}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 3: Process Consumables */}
      {activeTab === 'processConsumables' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold text-gray-800">Product-Process Consumables</h3>
            <button
              onClick={() => setShowAddPpc(!showAddPpc)}
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded shadow-sm"
            >
              {showAddPpc ? 'Cancel' : '+ Map Consumable to Process'}
            </button>
          </div>

          {showAddPpc && (
            <form onSubmit={handleCreatePpc} className="bg-white p-5 rounded-lg border border-indigo-200 shadow-sm space-y-4">
              <h4 className="text-sm font-bold text-indigo-900 uppercase">New Process Consumable Mapping</h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Product</label>
                  <select
                    value={newPpcProduct}
                    onChange={e => setNewPpcProduct(e.target.value)}
                    required
                    className="w-full border border-gray-300 rounded px-2.5 py-1.5 text-sm"
                  >
                    <option value="">Select product...</option>
                    {products.map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Process ID</label>
                  <input
                    type="text"
                    placeholder="Enter Process UUID"
                    value={newPpcProcess}
                    onChange={e => setNewPpcProcess(e.target.value)}
                    required
                    className="w-full border border-gray-300 rounded px-2.5 py-1.5 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Consumable</label>
                  <select
                    value={newPpcConsumable}
                    onChange={e => setNewPpcConsumable(e.target.value)}
                    required
                    className="w-full border border-gray-300 rounded px-2.5 py-1.5 text-sm"
                  >
                    <option value="">Select consumable...</option>
                    {consumables.map(c => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <button type="submit" className="px-4 py-2 bg-indigo-600 text-white rounded text-sm font-medium hover:bg-indigo-700">
                Save Consumable Mapping
              </button>
            </form>
          )}

          {ppcLoading && <div className="text-gray-500 py-4 text-center">Loading consumable mappings…</div>}
          {ppcError && <div role="alert" className="text-red-700 p-3 bg-red-50 rounded border border-red-200">{ppcError} <button className="underline" onClick={() => { void loadPpcList(); void loadConsumables(); }}>Retry consumables</button></div>}

          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold text-gray-700">Product</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-700">Process</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-700">Consumable</th>
                  <th className="px-4 py-3 text-center font-semibold text-gray-700">UOM</th>
                  <th className="px-4 py-3 text-center font-semibold text-gray-700">Status</th>
                  <th className="px-4 py-3 text-right font-semibold text-gray-700">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {ppcList.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-center text-gray-500">
                      No process consumable mappings found.
                    </td>
                  </tr>
                ) : (
                  ppcList.map(item => (
                    <tr key={item.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-900">
                        {item.product_code || item.product_id}
                        {item.product_name && <span className="block text-xs text-gray-500 font-normal">{item.product_name}</span>}
                      </td>
                      <td className="px-4 py-3 text-gray-700">{item.process_name || item.process_id}</td>
                      <td className="px-4 py-3 text-gray-700">
                        <span className="font-semibold">{item.consumable_code || item.consumable_id}</span>
                        {item.consumable_name && <span className="block text-xs text-gray-500">{item.consumable_name}</span>}
                      </td>
                      <td className="px-4 py-3 text-center font-mono text-xs text-gray-600">{item.unit || '—'}</td>
                      <td className="px-4 py-3 text-center">
                        <span className={`px-2 py-0.5 text-xs font-semibold rounded ${item.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-600'}`}>
                          {item.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleTogglePpcActive(item)}
                          className="text-xs text-indigo-600 hover:text-indigo-900 underline font-medium"
                        >
                          {item.is_active ? 'Deactivate' : 'Reactivate'}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 4: Mapping Integrity & Validation Audit */}
      {activeTab === 'validation' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h3 className="text-lg font-semibold text-gray-800">Mapping Integrity Audit</h3>
              <p className="text-xs text-gray-500">Detects unmapped products, process steps missing consumables, and inactive entities in active chains.</p>
            </div>
            <button
              onClick={runValidation}
              disabled={valLoading}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded shadow-sm disabled:opacity-50"
            >
              {valLoading ? 'Auditing…' : 'Re-run Audit'}
            </button>
          </div>

          {valLoading && <div className="text-gray-500 py-6 text-center">Auditing all master records and chains…</div>}
          {valError && <div className="text-red-700 p-3 bg-red-50 rounded border border-red-200">{valError}</div>}

          {validationReport && !valLoading && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
                  <span className="text-xs text-gray-500 uppercase font-semibold">Integrity Status</span>
                  <div className="mt-1 flex items-center gap-2">
                    <span className={`w-3 h-3 rounded-full ${validationReport.is_valid ? 'bg-green-500' : 'bg-amber-500'}`} />
                    <span className="text-lg font-bold text-gray-900">
                      {validationReport.is_valid ? 'Passed (100% Valid)' : 'Issues Detected'}
                    </span>
                  </div>
                </div>

                <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
                  <span className="text-xs text-gray-500 uppercase font-semibold">Products Checked</span>
                  <div className="mt-1 text-2xl font-bold text-gray-900">
                    {validationReport.total_products_checked}
                  </div>
                </div>

                <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
                  <span className="text-xs text-gray-500 uppercase font-semibold">Unmapped Products</span>
                  <div className={`mt-1 text-2xl font-bold ${validationReport.unmapped_products_count > 0 ? 'text-red-600' : 'text-green-600'}`}>
                    {validationReport.unmapped_products_count}
                  </div>
                </div>
              </div>

              <div className="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
                <div className="p-4 border-b bg-gray-50">
                  <h4 className="text-sm font-semibold text-gray-800">
                    Audit Issues Log ({validationReport.issues.length})
                  </h4>
                </div>
                {validationReport.issues.length === 0 ? (
                  <div className="p-8 text-center text-green-700 font-medium">
                    ✓ All active products have valid and complete structural mapping chains!
                  </div>
                ) : (
                  <ul className="divide-y divide-gray-100 text-sm">
                    {validationReport.issues.map((issue, idx) => (
                      <li key={idx} className="p-4 flex items-start gap-3">
                        <span
                          className={`mt-0.5 px-2 py-0.5 rounded text-xs font-bold ${
                            issue.severity === 'ERROR'
                              ? 'bg-red-100 text-red-800'
                              : 'bg-amber-100 text-amber-800'
                          }`}
                        >
                          {issue.severity}
                        </span>
                        <div>
                          <span className="font-semibold text-gray-900">{issue.issue_type}</span>
                          {issue.product_code && (
                            <span className="text-xs text-gray-500 ml-2 font-mono">[{issue.product_code}]</span>
                          )}
                          <p className="text-gray-600 text-xs mt-0.5">{issue.message}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
