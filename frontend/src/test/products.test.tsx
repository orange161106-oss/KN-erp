import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { AuthContext } from '../features/auth/context';
import Products from '../features/masters/Products';

afterEach(() => vi.unstubAllGlobals());

test('product upload displays server rejection beside the upload control', async () => {
  vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation(async input => {
    if (String(input).endsWith('/products/preview')) return new Response(JSON.stringify({
      code: 'SHEET_NOT_FOUND', message: 'Select the production-order sheet.',
    }), { status: 422 });
    return new Response('[]', { status: 200 });
  }));
  render(<AuthContext.Provider value={{ user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true }, login: vi.fn(), logout: vi.fn() }}><Products /></AuthContext.Provider>);
  fireEvent.change(screen.getByLabelText('Preview product workbook'), { target: { files: [new File(['synthetic'], 'source.xlsx')] } });
  expect(await screen.findByRole('alert')).toHaveTextContent('Select the production-order sheet.');
  expect(screen.queryByText('Save reviewed products')).not.toBeInTheDocument();
});

test('source description conflict cannot be saved until reviewed', async () => {
  const calls = vi.fn<typeof fetch>().mockImplementation(async input => {
    const data = String(input).endsWith('/products/preview') ? {
      filename: 'source.xlsx', sheet: 'Prd. Order', sha256: 'synthetic', message: 'Preview only.',
      products: [{ item_id: 'ITEM1', part_number: 'PART1', code: '', name: '', uom: 'PCS',
        source_rows: [531, 540], description_options: ['Assembly SFG', 'Assembly'] }],
    } : [];
    return new Response(JSON.stringify(data), { status: 200 });
  });
  vi.stubGlobal('fetch', calls);
  render(<AuthContext.Provider value={{ user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true }, login: vi.fn(), logout: vi.fn() }}><Products /></AuthContext.Provider>);
  fireEvent.change(screen.getByLabelText('Preview product workbook'), { target: { files: [new File(['synthetic'], 'source.xlsx')] } });
  await screen.findByLabelText('Product 1 description choice');
  await userEvent.selectOptions(screen.getByLabelText('Product code source'), 'item_id');
  await userEvent.click(screen.getByText('Save reviewed products'));
  expect(await screen.findByRole('alert')).toHaveTextContent('review every product');
  expect(calls.mock.calls.some(([input]) => String(input).endsWith('/products/reviewed'))).toBe(false);
  await userEvent.selectOptions(screen.getByLabelText('Product 1 description choice'), 'Assembly');
  await userEvent.click(screen.getByText('Save reviewed products'));
  await waitFor(() => expect(calls.mock.calls.some(([input]) => String(input).endsWith('/products/reviewed'))).toBe(true));
});

test('product workbook requires reviewed identifier and unit before master creation', async () => {
  const calls = vi.fn<typeof fetch>().mockImplementation(async (input, init) => {
    const url = String(input);
    let data: unknown = [];
    if (url.endsWith('/products/preview')) data = { filename: 'source.xlsx', sheet: 'Prd. Order', sha256: 'synthetic-hash',
      message: 'Preview only.', products: [{ item_id: 'ITEM1', part_number: 'PART1', code: '', name: 'Product one', uom: '', source_rows: [6] }] };
    if (url.endsWith('/products/reviewed') && init?.method === 'POST') data = [];
    return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', calls);
  render(<AuthContext.Provider value={{ user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true }, login: vi.fn(), logout: vi.fn() }}><Products /></AuthContext.Provider>);
  fireEvent.change(screen.getByLabelText('Preview product workbook'), { target: { files: [new File(['synthetic'], 'source.xlsx')] } });
  expect(await screen.findByText('Preview only.')).toBeInTheDocument();
  expect(screen.getByRole('option', { name: 'Product Code (not present in this workbook)' })).toBeDisabled();
  await userEvent.selectOptions(screen.getByLabelText('Product code source'), 'item_id');
  await userEvent.click(screen.getByText('Save reviewed products'));
  expect(calls.mock.calls.some(([input]) => String(input).endsWith('/products/reviewed'))).toBe(false);
  await userEvent.type(screen.getByLabelText('Product 1 uom'), 'PCS');
  await userEvent.click(screen.getByText('Save reviewed products'));
  await waitFor(() => expect(calls.mock.calls.some(([input]) => String(input).endsWith('/products/reviewed'))).toBe(true));
  const call = calls.mock.calls.find(([input]) => String(input).endsWith('/products/reviewed'));
  expect(JSON.parse(String(call?.[1]?.body)).products[0]).toMatchObject({ code: 'ITEM1', item_id: 'ITEM1', part_number: 'PART1', uom: 'PCS' });
});
