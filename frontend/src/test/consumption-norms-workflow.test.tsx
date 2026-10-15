import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { apiClient } from '../api/client';
import { AuthContext } from '../features/auth/context';
import ConsumptionNorms from '../features/rules/ConsumptionNorms';
import NormSetup from '../features/rules/NormSetup';
import NormImportWorkspace from '../features/rules/NormImportWorkspace';
import type { ConsumptionNorm, NormImportPreview } from '../features/rules/types';

const endpoint = '/api/v1/consumption-norms';
const norm: ConsumptionNorm = {
  id: 'norm-1', product_id: 'product-1', process_id: 'process-1', consumable_id: 'material-1', plant_id: null,
  product_code: 'ITEM-1', product_name: 'Synthetic Part', product_part_number: 'PART-1', consumable_code: 'MAT-1',
  consumable_name: 'Synthetic Material', process_name: 'Drilling', rule_type: 'PRODUCTION_RATE', version: 1,
  parameters: { rate: '2', scrap_factor: '0' }, unit_id: 'unit-1', unit_code: 'PCS', rounding_policy: 'NONE',
  rounding_precision: 4, effective_from: '2026-10-01', is_active: true, created_at: '', updated_at: '',
  reference_data: { part_number: 'BASE-1', used_part_number: 'USED-1', part_name: 'Synthetic Part', process_count: '2', thickness: '9.8' },
};
const preview: NormImportPreview = {
  filename: 'norms.xlsx', source_sha256: 'a'.repeat(64), review_token: 'b'.repeat(64), sheet_name: 'Plan',
  row_count: 1, valid_count: 1, invalid_count: 0, duplicate_count: 0, existing_count: 0, conflict_count: 0,
  rows: [{ row_number: 4, part_number: 'BASE-1', part_name: 'Synthetic Part', used_part_number: 'USED-1',
    consumable_code: 'MAT-1', consumable_name: 'Synthetic Material', process_name: 'Drilling', thickness: '9.8', process_count: '2',
    reference_production_qty: '1', reference_schedule_qty: '2', product_id: 'product-1', process_id: 'process-1', consumable_id: 'material-1',
    unit_id: 'unit-1', unit_code: 'PCS', action: 'CREATE', errors: [] }],
};
const onImported = vi.fn(async () => undefined);
const onClose = vi.fn();
function page(write = true) {
  return render(<AuthContext.Provider value={{ user: { id: 'operator', username: 'operator', roles: [], permissions: ['requirements.calculate'],
    consumption_norms_read: true, consumption_norms_create: write, consumption_norms_update: write }, login: vi.fn(), logout: vi.fn() }}><ConsumptionNorms/></AuthContext.Provider>);
}
function importPage(canUpdate = true) { return render(<NormImportWorkspace canUpdate={canUpdate} onClose={onClose} onImported={onImported}/>); }
async function chooseFile(name = 'norms.xlsx') {
  fireEvent.change(screen.getByLabelText('Consumption norms file'), { target: { files: [new File(['synthetic'], name)] } });
  await screen.findByText(/1 rows ·/);
}
function reviewOptions() {
  fireEvent.change(screen.getByLabelText('Approved formula'), { target: { value: 'PRODUCTION_RATE_FROM_PROCESS_COUNT' } });
  fireEvent.change(screen.getByLabelText('Effective from'), { target: { value: '2026-10-01' } });
  fireEvent.change(screen.getByLabelText('Rounding', { exact: true }), { target: { value: 'NONE' } });
  fireEvent.change(screen.getByLabelText('Import reason'), { target: { value: 'Reviewed synthetic example' } });
}
beforeEach(() => { localStorage.clear(); onClose.mockClear(); onImported.mockClear(); });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test('manual norm selects canonical masters and stock unit without plant or route mappings', async () => {
  const get = vi.spyOn(apiClient, 'get').mockImplementation(async path => {
    if (path === '/api/v1/masters/products') return [{ id: 'product-1', code: 'ITEM-1', name: 'Synthetic Part', is_active: true }] as never;
    if (path.startsWith('/api/v1/processes?')) return [{ id: 'process-1', name: 'Drilling', is_active: true }] as never;
    const items = path.includes('/consumables?') ? [{ id: 'material-1', code: 'MAT-1', name: 'Synthetic Material', unit_id: 'unit-1', is_active: true }]
      : [{ id: 'unit-1', code: 'PCS', is_active: true }];
    return { items, total: 1 } as never;
  });
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue(norm);
  const created = vi.fn(async () => undefined);
  render(<NormSetup onCreated={created}/>);
  await screen.findByRole('option', { name: 'ITEM-1 — Synthetic Part' });
  fireEvent.change(screen.getByLabelText('Product'), { target: { value: 'product-1' } });
  fireEvent.change(screen.getByLabelText('Process', { exact: true }), { target: { value: 'process-1' } });
  fireEvent.change(screen.getByLabelText('Consumable', { exact: true }), { target: { value: 'material-1' } });
  expect(screen.getByLabelText('Output unit')).toHaveValue('PCS');
  expect(screen.getByLabelText('Output unit')).toHaveAttribute('readonly');
  expect(screen.queryByLabelText(/plant/i)).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Formula type'), { target: { value: 'PRODUCTION_RATE' } });
  expect(screen.getByLabelText('Rate per production unit')).toHaveValue(null);
  fireEvent.change(screen.getByLabelText('Rate per production unit'), { target: { value: '2' } });
  fireEvent.change(screen.getByLabelText('Approved scrap factor (enter 0 for none)'), { target: { value: '0' } });
  fireEvent.change(screen.getByLabelText('Rounding policy'), { target: { value: 'NONE' } });
  fireEvent.change(screen.getByLabelText('Effective from'), { target: { value: '2026-10-01' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save norm' }));
  await waitFor(() => expect(created).toHaveBeenCalledWith('norm-1'));
  expect(post).toHaveBeenCalledWith(endpoint, expect.objectContaining({ plant_id: null, product_id: 'product-1', process_id: 'process-1', unit_id: 'unit-1', parameters: { rate: '2', scrap_factor: '0' } }));
  expect(get.mock.calls.some(([path]) => path.includes('/mappings/'))).toBe(false);
});

test('Excel preview never persists; explicit confirm sends approved formula and review token', async () => {
  const post = vi.spyOn(apiClient, 'postFormData').mockImplementation(async path => (path.endsWith('/import-preview') ? preview : { created_count: 1, skipped_count: 0, superseded_count: 0, message: 'One reviewed norm saved.' }) as never);
  importPage(); await chooseFile();
  expect(post).toHaveBeenCalledTimes(1);
  expect(onImported).not.toHaveBeenCalled();
  reviewOptions();
  fireEvent.click(screen.getByRole('button', { name: 'Confirm import' }));
  await waitFor(() => expect(onImported).toHaveBeenCalledWith('One reviewed norm saved.'));
  const review = JSON.parse(String(post.mock.calls[1][1].get('review')));
  expect(review).toMatchObject({ source_sha256: preview.source_sha256, review_token: preview.review_token, formula_choice: 'PRODUCTION_RATE_FROM_PROCESS_COUNT', rounding_policy: 'NONE', effective_from: '2026-10-01' });
  expect(review.rows[0]).not.toHaveProperty('product_id');
  expect(review.rows[0]).not.toHaveProperty('errors');
  expect(review.rows[0].reference_schedule_qty).toBe('2');
  expect(onClose).toHaveBeenCalledOnce();
});

test('invalid CSV rows are editable and require revalidation before confirmation', async () => {
  const invalid = { ...preview, invalid_count: 1, valid_count: 0, rows: [{ ...preview.rows[0], process_count: '-2', action: 'INVALID', errors: [{ field: 'process_count', code: 'INVALID_QUANTITY', message: 'Enter a positive process count.' }] }] };
  const post = vi.spyOn(apiClient, 'postFormData').mockResolvedValueOnce(invalid as never).mockResolvedValueOnce(preview as never);
  importPage(); await chooseFile('norms.csv');
  expect(screen.getByRole('button', { name: 'Confirm import' })).toBeDisabled();
  expect(screen.getByText(/Enter a positive process count/)).toBeInTheDocument();
  fireEvent.doubleClick(screen.getByRole('cell', { name: '-2' }));
  const editor = screen.getByLabelText('Edit No. of Process');
  fireEvent.change(editor, { target: { value: '2' } }); fireEvent.blur(editor);
  expect(screen.getByText(/Changes need validation/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Validate reviewed rows' }));
  await waitFor(() => expect(screen.queryByText(/Changes need validation/)).not.toBeInTheDocument());
  expect(JSON.parse(String(post.mock.calls[1][1].get('review'))).rows[0].process_count).toBe('2');
  expect(screen.getByRole('button', { name: 'Confirm import' })).toBeEnabled();
  expect(onImported).not.toHaveBeenCalled();
});

test('existing conflicts require explicit supersede permission and import failures never report success', async () => {
  const conflict = { ...preview, conflict_count: 1, existing_count: 1, rows: [{ ...preview.rows[0], action: 'CONFLICT', errors: [] }] };
  vi.spyOn(apiClient, 'postFormData').mockResolvedValueOnce(conflict as never).mockRejectedValueOnce(new Error('The reviewed database state changed. Revalidate.'));
  importPage(); await chooseFile(); reviewOptions();
  expect(screen.getByRole('button', { name: 'Confirm import' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Existing records'), { target: { value: 'SUPERSEDE' } });
  fireEvent.click(screen.getByRole('button', { name: 'Confirm import' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Revalidate');
  expect(onImported).not.toHaveBeenCalled(); expect(onClose).not.toHaveBeenCalled();
});

test('norm table supports product and consumable searches and process filter', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue([norm, { ...norm, id: 'norm-2', consumable_code: 'MAT-2', consumable_name: 'Oil', process_name: 'Painting', reference_data: { part_number: 'BASE-2', used_part_number: 'USED-2' } }]);
  page(); await screen.findByRole('cell', { name: 'MAT-1' });
  fireEvent.change(screen.getByLabelText('Search consumption norms'), { target: { value: 'used-2' } });
  expect(screen.queryByRole('cell', { name: 'MAT-1' })).not.toBeInTheDocument();
  expect(screen.getByRole('cell', { name: 'Oil' })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Search consumption norms'), { target: { value: '' } });
  fireEvent.change(screen.getByLabelText('Filter process'), { target: { value: 'Drilling' } });
  expect(screen.getByRole('cell', { name: 'MAT-1' })).toBeInTheDocument(); expect(screen.queryByRole('cell', { name: 'Oil' })).not.toBeInTheDocument();
});

test('saving edited process count uses atomic version update and does not send a conflicting unchanged rate', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue([norm]);
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ updated_count: 1, records: [norm] });
  page(); await screen.findByRole('cell', { name: 'MAT-1' });
  const count = screen.getAllByRole('cell', { name: '2' })[0];
  fireEvent.doubleClick(count);
  const editor = screen.getByLabelText('Edit No. of Process');
  fireEvent.change(editor, { target: { value: '3' } }); fireEvent.blur(editor);
  fireEvent.change(screen.getByLabelText('Change reason'), { target: { value: 'Approved revised process count' } });
  fireEvent.click(screen.getAllByRole('button', { name: 'Save changes' })[0]);
  await screen.findByText(/1 norms saved as reviewed versions/);
  expect(post).toHaveBeenCalledWith(endpoint + '/bulk-update', { reason: 'Approved revised process count', updates: [expect.objectContaining({ norm_id: 'norm-1', expected_version: 1, reference_data: expect.objectContaining({ process_count: '3' }) })] });
  const body = post.mock.calls[0][1] as { updates: Record<string, unknown>[] };
  expect(body.updates[0]).not.toHaveProperty('parameters');
});

test('cancel edits restores values without persistence and read-only access hides mutation actions', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue([norm]);
  const post = vi.spyOn(apiClient, 'post');
  const view = page(); await screen.findByRole('cell', { name: 'BASE-1' });
  fireEvent.doubleClick(screen.getByRole('cell', { name: 'BASE-1' }));
  const editor = screen.getByRole('textbox', { name: 'Edit Part No.' });
  fireEvent.change(editor, { target: { value: 'REFERENCE-REVIEW' } }); fireEvent.blur(editor);
  fireEvent.click(screen.getByRole('button', { name: 'Cancel edits' }));
  expect(screen.getByRole('cell', { name: 'BASE-1' })).toBeInTheDocument(); expect(post).not.toHaveBeenCalled();
  view.unmount(); page(false); await screen.findByRole('cell', { name: 'BASE-1' });
  expect(screen.queryByRole('button', { name: 'Upload Excel / CSV' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Add new norm' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument();
});

test('download errors are visible and do not create a false successful export', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue([norm]);
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: 'Export access denied.' }), { status: 403, headers: { 'Content-Type': 'application/json' } }));
  vi.stubGlobal('fetch', fetch);
  page(); await screen.findByRole('cell', { name: 'MAT-1' });
  fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Export access denied.');
  expect(fetch.mock.calls[0][0]).toContain(endpoint + '/export?format=csv');
});

test('simulator sends canonical scoped inputs and displays backend calculation evidence', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue([norm]);
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ norm_id: 'norm-1', calculation: { rule_type: 'PRODUCTION_RATE', rule_version: 1, parameters: norm.parameters,
    source_production_qty: '100', raw_requirement: '200', final_calculated_requirement: '200', unit: 'PCS', rounding_policy: 'NONE', rounding_precision: 4,
    calculation_steps: [{ step_number: 1, description: 'Approved production-rate rule', formula: '100 × 2', result: '200' }] } });
  page(); await screen.findByRole('cell', { name: 'MAT-1' });
  fireEvent.change(screen.getByLabelText('Production quantity'), { target: { value: '100' } });
  fireEvent.change(screen.getByLabelText('Calculation date'), { target: { value: '2026-10-15' } });
  fireEvent.click(screen.getByRole('button', { name: 'Run Calculation' }));
  expect(await screen.findByText('Calculated Output: 200 PCS')).toBeInTheDocument();
  expect(post).toHaveBeenCalledWith(endpoint + '/evaluate', expect.objectContaining({ production_quantity: '100', plant_id: null, product_id: 'product-1', process_id: 'process-1' }));
  expect(within(screen.getByRole('list')).getByText(/100 × 2/)).toBeInTheDocument();
});
