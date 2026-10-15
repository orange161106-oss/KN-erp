import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { apiClient } from '../api/client';
import { AuthContext } from '../features/auth/context';
import MasterBulkWorkspace from '../features/masters/MasterBulkWorkspace';

const endpoint = '/api/v1/masters/product-master/consumables/workspace';
const record = { id: 'row-1', item_id: 'TEST-MAT-1', description: 'Synthetic material', output_unit: 'PCS', rate: '12.3456' };
const empty = { category: 'consumables', review_token: 'a'.repeat(64), row_count: 0, filename: null, report: {}, records: [] };
const saved = { ...empty, review_token: 'b'.repeat(64), row_count: 1, filename: 'synthetic.xlsx', records: [record] };
const preview = { ...saved, review_token: empty.review_token };
const changed = vi.fn();

function page(write = true) {
  return render(<AuthContext.Provider value={{ user: { id: 'operator', username: 'operator', roles: [], permissions: [],
    masters_read: true, masters_create: write, masters_update: write, masters_delete: write }, login: vi.fn(), logout: vi.fn() }}>
    <MasterBulkWorkspace category="consumables" label="List of Consumables" onClose={vi.fn()} onChanged={changed}/>
  </AuthContext.Provider>);
}
async function chooseFile() {
  await waitFor(() => expect(screen.getByRole('button', { name: 'Upload data' })).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Master Excel file'), { target: { files: [new File(['synthetic'], 'synthetic.xlsx')] } });
  await screen.findByText(/unique items ready for review/);
}

beforeEach(() => { changed.mockReset(); vi.spyOn(apiClient, 'get').mockResolvedValue(empty); });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test('upload only previews; Save changes commits even without a cell edit and needs no dates', async () => {
  const post = vi.spyOn(apiClient, 'postFormData').mockImplementation(async url => (url.endsWith('/preview') ? preview : saved) as never);
  page();
  expect(screen.queryByLabelText('Upload month')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Upload year')).not.toBeInTheDocument();
  await chooseFile();
  expect(post).toHaveBeenCalledTimes(1);
  expect(post).toHaveBeenCalledWith(endpoint + '/preview', expect.any(FormData));
  expect(changed).not.toHaveBeenCalled();
  expect(screen.getByText('Not saved yet')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled();
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByText('1 items saved successfully.')).toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(2);
  expect(post.mock.calls[1][0]).toBe(endpoint);
  expect(JSON.parse(String(post.mock.calls[1][1].get('review')))).toEqual({ review_token: empty.review_token, updates: [] });
  expect(changed).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
  expect(screen.getByText('Saved · 1 items')).toBeInTheDocument();
});

test('already saved catalog displays Saved; edits persist through the catalog API', async () => {
  vi.mocked(apiClient.get).mockResolvedValue(saved);
  const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({ ...saved, records: [{ ...record, description: 'Reviewed material' }] });
  page();
  const cell = await screen.findByRole('cell', { name: 'Synthetic material' });
  expect(screen.getByText('Saved · 1 items')).toBeInTheDocument();
  fireEvent.doubleClick(cell);
  const editor = screen.getByRole('textbox', { name: 'Edit Description' });
  fireEvent.change(editor, { target: { value: 'Reviewed material' } });
  fireEvent.blur(editor);
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(patch).toHaveBeenCalledExactlyOnceWith(endpoint, {
    review_token: saved.review_token, updates: [{ id: 'row-1', changes: { description: 'Reviewed material' } }],
  }));
});

test('delete reviews the entire selected tab and enables replacement upload', async () => {
  vi.mocked(apiClient.get).mockResolvedValue(saved);
  const remove = vi.spyOn(apiClient, 'delete').mockResolvedValue(empty);
  page();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Delete data' })).toBeEnabled());
  expect(screen.getByRole('button', { name: 'Upload data' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Delete data' }));
  const dialog = screen.getByRole('dialog', { name: 'Delete List of Consumables data?' });
  expect(within(dialog).getByRole('button', { name: 'Delete data' })).toBeDisabled();
  fireEvent.change(within(dialog).getByLabelText('Deletion reason'), { target: { value: 'Replace workbook' } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Delete data' }));
  await waitFor(() => expect(remove).toHaveBeenCalledExactlyOnceWith(endpoint, { review_token: saved.review_token, reason: 'Replace workbook' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Upload data' })).toBeEnabled());
});

test('numeric output quantities require reviewed unit labels before Save changes', async () => {
  const post = vi.spyOn(apiClient, 'postFormData').mockImplementation(async url => (url.endsWith('/preview')
    ? { ...preview, records: [{ ...record, output_unit: '2000' }] } : saved) as never);
  page(); await chooseFile();
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(screen.getByRole('alert')).toHaveTextContent('1 rows need a valid stock unit');
  expect(post).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByLabelText('Reviewed stock unit'), { target: { value: 'PCS' } });
  fireEvent.click(screen.getByRole('button', { name: 'Apply to unresolved units' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByText('1 items saved successfully.')).toBeInTheDocument();
  expect(JSON.parse(String(post.mock.calls[1][1].get('review'))).updates).toEqual([{ id: 'row-1', changes: { output_unit: 'PCS' } }]);
});

test('discarding an upload does not persist or delete master data', async () => {
  const post = vi.spyOn(apiClient, 'postFormData').mockResolvedValue(preview);
  const remove = vi.spyOn(apiClient, 'delete');
  page(); await chooseFile();
  fireEvent.click(screen.getByRole('button', { name: 'Discard upload' }));
  expect(screen.queryByRole('cell', { name: 'Synthetic material' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Upload data' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
  expect(post).toHaveBeenCalledTimes(1); expect(remove).not.toHaveBeenCalled(); expect(changed).not.toHaveBeenCalled();
});

test('readers export the undated catalog and cannot edit or remove rows', async () => {
  vi.mocked(apiClient.get).mockResolvedValue(saved);
  const fetchFile = vi.fn().mockResolvedValue(new Response(new Blob(['synthetic-xlsx'])));
  vi.stubGlobal('fetch', fetchFile);
  const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:synthetic');
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  page(false);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Export Excel' })).toBeEnabled());
  expect(screen.getByRole('button', { name: 'Upload data' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Delete data' })).toBeDisabled();
  fireEvent.doubleClick(screen.getByRole('cell', { name: 'Synthetic material' }));
  expect(screen.queryByRole('textbox', { name: 'Edit Description' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Export Excel' }));
  await waitFor(() => expect(create).toHaveBeenCalled());
  expect(String(fetchFile.mock.calls[0][0])).toContain(endpoint + '/export');
});
