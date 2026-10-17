import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { apiClient } from '../api/client';
import PageBoundary from '../components/PageBoundary';
import { AuthContext } from '../features/auth/context';
import PurchaseApprovals from '../features/purchasing/PurchaseApprovals';

const version = {id:'october-version',planning_period:'2026-10',revision_label:'R0',status:'CALCULATED_WITH_ERRORS',is_latest:true,source_filename:'sample.xlsx'};
const plan = {plan_metadata:{has_plan:true,plan_id:version.id,planning_period:'2026-10',planning_month:10,planning_year:2026,
  source_workflow:'BASIC_CENTRAL_V1',status:version.status,revision_label:'R0',record_count:1},records:[{
  id:'sample-drill',plan_id:version.id,revision:'R0',consumable_code:'TEST-001',consumable_name:'Sample drill',unit:'PCS',
  required_qty:'230.0000',stock_qty:null,po_pending_qty:null,shortage_qty:null,system_recommended_qty:null,
  supplier_code:null,supplier_name:null,approval_status:null,source_row_count:1,status:'REQUIREMENT_REVIEW_REQUIRED',remarks:'Review requirements.',
}],notice:'Review central requirements before purchase assessment.'};

function CurrentRoute() {
  const location=useLocation();
  return <output aria-label="Current route">{location.pathname+location.search}</output>;
}

function show(superAdmin = true) {
  return render(<AuthContext.Provider value={{user:{id:'sample-user',username:'sample-user',roles:[],permissions:[],
    is_super_admin:superAdmin,purchase_read:true,purchase_update:false},login:vi.fn(),logout:vi.fn()}}>
    <MemoryRouter initialEntries={['/purchase']}><CurrentRoute/><PageBoundary><PurchaseApprovals currentUserId="sample-user"/></PageBoundary></MemoryRouter>
  </AuthContext.Provider>);
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

test('the complete Purchase page opens for Super Admin and navigates to the selected plan review', async () => {
  const get = vi.spyOn(apiClient,'get').mockImplementation(async path => {
    if (path.includes('/purchasing/workspace')) return plan as never;
    throw new Error(`Unexpected page read: ${path}`);
  });
  const post = vi.spyOn(apiClient,'post');
  show();
  await screen.findByRole('cell',{name:'TEST-001'});
  expect(screen.getByRole('cell',{name:'230.0000'})).toBeInTheDocument();
  expect(get).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('button',{name:'Central purchase assessment'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Review central requirements'}));
  expect(screen.getByLabelText('Current route')).toHaveTextContent('/requirements?period=2026-10');
  expect(screen.queryByRole('heading',{name:'Central basic requirement plan'})).not.toBeInTheDocument();
  expect(screen.queryByText(/This page could not load/)).not.toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
});

test('read-only Purchase users can open the plan, queue and handoff without a central page crash', async () => {
  const get = vi.spyOn(apiClient,'get').mockImplementation(async path => path.includes('/purchasing/workspace') ? plan as never : [] as never);
  show(false);
  await screen.findByRole('cell',{name:'TEST-001'});
  fireEvent.click(screen.getByRole('button',{name:'Approval Queue'}));
  await waitFor(() => expect(get).toHaveBeenCalledWith('/api/v1/purchasing/approvals?status=PENDING'));
  fireEvent.click(screen.getByRole('button',{name:'Approved Handoff (PO Ready)'}));
  await waitFor(() => expect(get).toHaveBeenCalledWith('/api/v1/purchasing/approvals/approved-handoff'));
  expect(screen.getByRole('heading',{name:/Purchase Planning & Approvals/})).toBeInTheDocument();
  expect(screen.queryByText(/This page could not load/)).not.toBeInTheDocument();
  expect(get.mock.calls.some(([path]) => path.includes('/requirements/basic/'))).toBe(false);
});

test('approved plans open Requirement rather than restoring a central Purchase tab', async () => {
  const get = vi.spyOn(apiClient,'get').mockResolvedValue({...plan,plan_metadata:{...plan.plan_metadata,status:'APPROVED'},
    notice:'Complete the inventory and supplier assessment.'});
  show();
  await screen.findByRole('cell',{name:'TEST-001'});
  fireEvent.click(screen.getByRole('button',{name:'View requirements'}));
  expect(screen.getByLabelText('Current route')).toHaveTextContent('/requirements?period=2026-10');
  expect(screen.queryByRole('button',{name:'Central purchase assessment'})).not.toBeInTheDocument();
  expect(screen.queryByText(/This page could not load/)).not.toBeInTheDocument();
  expect(get.mock.calls.some(([path])=>path.includes('/requirements/basic/'))).toBe(false);
});
