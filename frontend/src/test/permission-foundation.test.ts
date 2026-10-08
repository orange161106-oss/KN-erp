import { expect, test } from 'vitest';
import { canOpen, canPerform } from '../core/rbac';

test('base ADMIN role never grants a feature or employee administration', () => {
  const user = { roles: ['ADMIN'], permissions: [] };
  expect(canPerform(user, 'prd', 'create')).toBe(false);
  expect(canOpen(user, '/admin')).toBe(false);
  expect(canOpen(user, '/masters')).toBe(false);
});

test('GRN permissions cannot grant unrelated PRD or purchase-order access', () => {
  const user = { roles: [], permissions: ['purchase.grns.create'] };
  expect(canPerform(user, 'prd', 'create')).toBe(false);
  expect(canPerform(user, 'purchase_orders', 'create')).toBe(false);
  expect(canPerform(user, 'grns', 'create')).toBe(true);
});

test('effective planning permissions distinguish read and write', () => {
  const user = { roles: [], permissions: ['planning.read'] };
  expect(canOpen(user, '/prd')).toBe(true);
  expect(canPerform(user, 'prd', 'create')).toBe(false);
  expect(canPerform({ ...user, permissions: ['planning.read', 'planning.write'] }, 'prd', 'create')).toBe(true);
});

test('Super Admin can open protected setup pages without role templates', () => {
  const user = { roles: [], permissions: [], is_super_admin: true };
  expect(canOpen(user, '/admin')).toBe(true);
  expect(canOpen(user, '/masters')).toBe(true);
  expect(canPerform(user, 'prd', 'import')).toBe(true);
});
