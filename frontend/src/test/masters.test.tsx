import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { apiClient, setAccessToken, setUnauthorizedHandler } from '../api/client';
import { AuthContext } from '../features/auth/context';
import type { CurrentUser } from '../features/auth/context';
import MasterPage from '../features/masters/MasterPage';
import MasterForm from '../features/masters/MasterForm';
import type { Master } from '../features/masters/types';

const unit: Master = { id: 'unit-1', code: 'KG', name: 'Kilogram', is_active: true, created_at: '', updated_at: '' };
const supplier: Master = { ...unit, id: 'supplier-1', code: 'S1', name: 'Supplier' };
const consumable: Master = { ...unit, id: 'consumable-1', code: 'C1', name: 'Material', unit_id: unit.id };
const permissions = ['units', 'consumables', 'suppliers', 'supplier_consumables'].flatMap(resource => [`masters.${resource}.read`, `masters.${resource}.write`]);
const identity: CurrentUser = { id: 'user-1', username: 'operator', roles: ['ADMIN'], permissions };
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 25, offset: 0 });
const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  window.history.replaceState({}, '', '/'); setAccessToken(null); vi.stubGlobal('fetch', fetchMock);
  // Node's experimental storage is independent of a browser's storage implementation.
  vi.stubGlobal('localStorage', { setItem: vi.fn(), getItem: vi.fn(() => null), removeItem: vi.fn(), clear: vi.fn(), length: 0 });
});
afterEach(() => { setAccessToken(null); setUnauthorizedHandler(null); vi.unstubAllGlobals(); });

function context(children: React.ReactNode, user = identity) {
  return <AuthContext.Provider value={{ user, login: vi.fn(), logout: vi.fn() }}><MemoryRouter>{children}</MemoryRouter></AuthContext.Provider>;
}
async function signIn() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Username'), 'operator');
  await user.type(screen.getByLabelText('Password'), 'synthetic password');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
  return user;
}
function authenticate(user = identity, other?: (url: string, init?: RequestInit) => Response) {
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith('/auth/login')) return response({ access_token: 'synthetic-token' });
    if (url.endsWith('/auth/me')) return response(user);
    return other ? other(url, init) : response(page([]));
  });
}

test('invalid credentials show an error and clear the password', async () => {
  fetchMock.mockResolvedValue(response({ code: 'INVALID_CREDENTIALS', message: 'Invalid username or password.' }, 401));
  render(<App />); await signIn();
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password.');
  expect(screen.getByLabelText('Password')).toHaveValue('');
  expect(screen.queryByText('Select Persona')).not.toBeInTheDocument();
});

test('real login loads current user with bearer credentials and logout clears authentication', async () => {
  authenticate(); render(<App />); const user = await signIn();
  expect(await screen.findByText('operator')).toBeInTheDocument();
  const me = fetchMock.mock.calls.find(([input]) => String(input).endsWith('/auth/me'));
  expect(me?.[1]?.headers).toMatchObject({ Authorization: 'Bearer synthetic-token' });
  expect(localStorage.setItem).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Logout' }));
  expect(screen.getByLabelText('Username')).toBeInTheDocument();
  await apiClient.get('/api/v1/health');
  expect(fetchMock.mock.calls.at(-1)?.[1]?.headers).not.toHaveProperty('Authorization');
});

test('ADMIN without explicit grants cannot navigate directly to masters', async () => {
  window.history.replaceState({}, '', '/masters/units');
  authenticate({ ...identity, permissions: [] }); render(<App />); await signIn();
  expect(await screen.findByRole('alert')).toHaveTextContent('do not have permission');
  expect(screen.queryByRole('link', { name: 'Masters' })).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/masters/units'))).toBe(false);
});

test('read-only users can list units but cannot see mutation controls', async () => {
  fetchMock.mockResolvedValue(response(page([unit])));
  render(context(<MasterPage resource="units" />, { ...identity, permissions: ['masters.units.read'] }));
  expect(await screen.findByText('Kilogram')).toBeInTheDocument();
  expect(screen.getByText('You have read-only access.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Add unit' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Deactivate' })).not.toBeInTheDocument();
});

test('create unit submits its reason and refreshes the list', async () => {
  let created = false;
  fetchMock.mockImplementation(async (_url, init) => {
    if (init?.method === 'POST') { created = true; return response(unit, 201); }
    return response(page(created ? [unit] : []));
  });
  render(context(<MasterPage resource="units" />)); const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Add unit' }));
  await user.type(screen.getByLabelText('Code'), 'KG'); await user.type(screen.getByLabelText('Name'), 'Kilogram');
  await user.type(screen.getByLabelText('Reason for change'), 'Approved unit setup');
  await user.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Kilogram')).toBeInTheDocument();
  const posted = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
  expect(JSON.parse(String(posted?.[1]?.body))).toEqual({ code: 'KG', name: 'Kilogram', change_reason: 'Approved unit setup' });
  expect(screen.queryByLabelText('Reason for change')).not.toBeInTheDocument();
});

test('validation errors keep the form open and identify invalid fields', async () => {
  fetchMock.mockResolvedValue(response({ code: 'VALIDATION_ERROR', message: 'Request validation failed.', details: { errors: [{ location: ['body', 'code'] }] } }, 422));
  const saved = vi.fn(); render(<MasterForm resource="units" onSaved={saved} onCancel={vi.fn()} />);
  fireEvent.change(screen.getByLabelText('Code'), { target: { value: 'KG' } });
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Kilogram' } });
  fireEvent.change(screen.getByLabelText('Reason for change'), { target: { value: 'Test' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Check these fields: code.');
  expect(saved).not.toHaveBeenCalled();
});

test('consumable form loads active units and sends unit id without speculative quantities', async () => {
  fetchMock.mockImplementation(async (_url, init) => response(init?.method === 'POST' ? consumable : page([unit])));
  const saved = vi.fn(); render(<MasterForm resource="consumables" onSaved={saved} onCancel={vi.fn()} />);
  expect(await screen.findByRole('option', { name: 'KG — Kilogram' })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Code'), { target: { value: 'C1' } });
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Material' } });
  fireEvent.change(screen.getByLabelText('Unit', { exact: true }), { target: { value: unit.id } });
  fireEvent.change(screen.getByLabelText('Reason for change'), { target: { value: 'Approved material' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(saved).toHaveBeenCalled());
  expect(String(fetchMock.mock.calls[0][0])).toContain('is_active=true');
  const payload = JSON.parse(String(fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')?.[1]?.body));
  expect(payload.unit_id).toBe(unit.id); expect(payload).not.toHaveProperty('moq');
});

test('deactivation requires a reason and uses status API, not deletion', async () => {
  let active = true;
  fetchMock.mockImplementation(async (_url, init) => {
    if (init?.method === 'PATCH') { active = false; return response({ ...unit, is_active: false }); }
    return response(page(active ? [unit] : []));
  });
  render(context(<MasterPage resource="units" />)); const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Deactivate' }));
  await user.type(screen.getByLabelText('Reason for change'), 'Retired unit');
  await user.click(screen.getByRole('button', { name: 'Confirm deactivate' }));
  expect(await screen.findByText('No matching units.')).toBeInTheDocument();
  const changed = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH');
  expect(String(changed?.[0]).endsWith('/status')).toBe(true);
  expect(JSON.parse(String(changed?.[1]?.body))).toEqual({ is_active: false, change_reason: 'Retired unit' });
});

test('supplier details create an association with the selected consumable and reason', async () => {
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === 'POST') return response({ id: 'mapping-1', supplier_id: supplier.id, consumable_id: consumable.id, is_active: true }, 201);
    if (url.includes('/supplier-consumables')) return response(page([]));
    if (url.includes('/consumables')) return response(page([consumable]));
    return response(page([supplier]));
  });
  render(context(<MasterPage resource="suppliers" />)); const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Consumable mappings' }));
  await user.click(screen.getByRole('button', { name: 'Add mapping' }));
  await screen.findByRole('option', { name: 'C1 — Material' });
  await user.selectOptions(screen.getByLabelText('Consumable', { exact: true }), consumable.id);
  await user.type(screen.getByLabelText('Reason for change'), 'Approved supplier association');
  await user.click(screen.getByRole('button', { name: 'Save mapping' }));
  await waitFor(() => expect(screen.queryByRole('form', { name: 'Create supplier mapping' })).not.toBeInTheDocument());
  const posted = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
  expect(JSON.parse(String(posted?.[1]?.body))).toEqual({ supplier_id: supplier.id, consumable_id: consumable.id, change_reason: 'Approved supplier association' });
});

test('401 on a protected request clears the session and returns to login', async () => {
  authenticate(identity, () => response({ code: 'NOT_AUTHENTICATED', message: 'Valid authentication is required.' }, 401));
  render(<App />); const user = await signIn();
  await user.click(await screen.findByRole('link', { name: 'Masters' }));
  expect(await screen.findByLabelText('Username')).toBeInTheDocument();
});

test('403 is shown without silently enabling access', async () => {
  fetchMock.mockResolvedValue(response({ code: 'PERMISSION_DENIED', message: 'Required permission is missing.' }, 403));
  render(context(<MasterPage resource="units" />, { ...identity, permissions: ['masters.units.read'] }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Required permission is missing.');
  expect(screen.queryByRole('button', { name: 'Add unit' })).not.toBeInTheDocument();
});

test('network failures produce a useful error without exposing diagnostics', async () => {
  fetchMock.mockRejectedValue(new Error('private diagnostic'));
  await expect(apiClient.get('/api/v1/health')).rejects.toThrow('Cannot reach the server.');
});

test('edit unit retains its identifier and sends the updated name', async () => {
  fetchMock.mockResolvedValue(response({ ...unit, name: 'Updated label' }));
  const saved = vi.fn(); render(<MasterForm resource="units" record={unit} onSaved={saved} onCancel={vi.fn()} />);
  expect(screen.getByLabelText('Code')).toHaveValue('KG');
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Updated label' } });
  fireEvent.change(screen.getByLabelText('Reason for change'), { target: { value: 'Correct label' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(saved).toHaveBeenCalled());
  expect(String(fetchMock.mock.calls[0][0])).toBe('/api/v1/masters/units/unit-1');
  expect(fetchMock.mock.calls[0][1]?.method).toBe('PATCH');
  expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body)).name).toBe('Updated label');
});

test('inactive filter exposes reactivation with a required reason', async () => {
  fetchMock.mockImplementation(async (input, init) => {
    if (init?.method === 'PATCH') return response(unit);
    return response(page(String(input).includes('is_active=false') ? [{ ...unit, is_active: false }] : []));
  });
  render(context(<MasterPage resource="units" />)); const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText('Status', { exact: true }), 'false');
  await user.click(await screen.findByRole('button', { name: 'Reactivate' }));
  await user.type(screen.getByLabelText('Reason for change'), 'Restore approved unit');
  await user.click(screen.getByRole('button', { name: 'Confirm reactivate' }));
  await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(true));
  const updated = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH');
  expect(JSON.parse(String(updated?.[1]?.body)).is_active).toBe(true);
});

test('consumable list resolves unit names for users with unit read access', async () => {
  fetchMock.mockImplementation(async input => response(String(input).endsWith('/units/unit-1') ? unit : page([consumable])));
  render(context(<MasterPage resource="consumables" />));
  expect(await screen.findByText('KG — Kilogram')).toBeInTheDocument();
});
