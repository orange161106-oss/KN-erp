import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { apiClient } from '../api/client';
import PurchaseWorkspace from '../features/purchasing/PurchaseWorkspace';
import { AuthContext } from '../features/auth/context';

const metadata = {has_plan:true,plan_id:'october-version',planning_period:'2026-10',planning_month:10,planning_year:2026,
  source_workflow:'BASIC_CENTRAL_V1',status:'CALCULATED_WITH_ERRORS',revision_label:'R0',record_count:224};
const row = {id:'central-drill',plan_id:'october-version',revision:'R0',consumable_code:'DRILL-A',consumable_name:'Drill',unit:'PCS',
  required_qty:'230.0000',stock_qty:null,po_pending_qty:null,shortage_qty:null,system_recommended_qty:null,
  master_unit:'PCS',draft_version:0,requested_purchase_qty:null,purchase_notes:null,
  supplier_code:null,supplier_name:null,approval_status:null,source_row_count:2,status:'REQUIREMENT_REVIEW_REQUIRED',remarks:'Review central requirements.'};
function show(component: React.ReactNode) {
  return render(<AuthContext.Provider value={{user:{id:'synthetic',username:'synthetic',roles:[],permissions:[],is_super_admin:true},login:vi.fn(),logout:vi.fn()}}>{component}</AuthContext.Provider>);
}
afterEach(() => vi.restoreAllMocks());

test('Purchase Plan shows central demand and offers review without enabling purchase submission', async () => {
  vi.spyOn(apiClient,'get').mockResolvedValue({plan_metadata:metadata,records:[row],notice:'159 requirement configuration issues need review. Approve the central plan before purchase assessment.'});
  const open = vi.fn();
  const post = vi.spyOn(apiClient,'post');
  show(<PurchaseWorkspace canCreate onOpenCentral={open}/>);
  await screen.findByRole('cell',{name:'DRILL-A'});
  expect(screen.getByRole('cell',{name:'230.0000'})).toBeInTheDocument();
  expect(screen.getAllByText('Unavailable')).toHaveLength(4);
  expect(screen.queryByText(/No purchase recommendations found/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('cell',{name:'DRILL-A'}));
  expect(screen.getByRole('button',{name:'Submit to Approval'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Review central requirements'}));
  expect(open).toHaveBeenCalledWith('october-version',true);
  expect(post).not.toHaveBeenCalled();
});

test('approved requirements open the matching central assessment and preserve the blocked status filter', async () => {
  vi.spyOn(apiClient,'get').mockResolvedValue({plan_metadata:{...metadata,status:'APPROVED'},records:[{...row,status:'ASSESSMENT_REQUIRED'}],notice:'Complete the central inventory and supplier assessment.'});
  const open = vi.fn();
  show(<PurchaseWorkspace canCreate onOpenCentral={open}/>);
  await screen.findByRole('cell',{name:'DRILL-A'});
  fireEvent.click(screen.getByRole('button',{name:'Open central purchase assessment'}));
  expect(open).toHaveBeenCalledWith('october-version',false);
  fireEvent.change(screen.getByLabelText('Status'),{target:{value:'ASSESSMENT_REQUIRED'}});
  await waitFor(()=>expect(apiClient.get).toHaveBeenLastCalledWith(expect.stringContaining('status=ASSESSMENT_REQUIRED')));
});

test('loaded purchase rows have no false unsaved changes, and a cell edit saves an exact requested quantity', async () => {
  vi.spyOn(apiClient,'get').mockResolvedValue({plan_metadata:metadata,records:[row]});
  const post=vi.spyOn(apiClient,'post').mockResolvedValue({plan_metadata:metadata,records:[{...row,requested_purchase_qty:'12.3456',requested_purchase_unit:'PCS',draft_version:1}]});
  const {container}=show(<PurchaseWorkspace canCreate/>);
  await screen.findByRole('cell',{name:'DRILL-A'});
  expect(screen.queryByText(/\d+ unsaved/)).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:/Save Changes/})).toBeDisabled();
  const target=container.querySelector('td[data-column-key="requested_purchase_qty"]')!;
  fireEvent.doubleClick(target);
  const input=screen.getByRole('textbox',{name:'Edit Requested Purchase Qty'});
  fireEvent.change(input,{target:{value:'12.3456'}});fireEvent.blur(input);
  expect(screen.getByLabelText('Planning Month')).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:/Save Changes/}));
  await screen.findByText(/Purchase Plan changes saved/);
  expect(post).toHaveBeenCalledWith('/api/v1/purchasing/workspace/save?month=10&year=2026',expect.objectContaining({
    edits:[expect.objectContaining({record_id:row.id,expected_draft_version:0,requested_purchase_qty:'12.3456'})],
  }));
  expect(screen.getByRole('cell',{name:'12.3456 PCS'})).toBeInTheDocument();
});

test('right-click row editing saves master name and purchase remarks without redirecting', async () => {
  vi.spyOn(apiClient,'get').mockResolvedValue({plan_metadata:metadata,records:[row]});
  const post=vi.spyOn(apiClient,'post').mockResolvedValue({plan_metadata:metadata,records:[{...row,consumable_name:'Reviewed drill',purchase_notes:'Review supplier',draft_version:1}]});
  show(<PurchaseWorkspace canCreate/>);
  fireEvent.contextMenu(await screen.findByRole('cell',{name:'Drill'}));
  fireEvent.click(screen.getByRole('button',{name:'Edit row…'}));
  fireEvent.change(screen.getByLabelText('Consumable Name'),{target:{value:'Reviewed drill'}});
  fireEvent.change(screen.getByLabelText('Remarks'),{target:{value:'Review supplier'}});
  expect(screen.queryByRole('textbox',{name:'Requirement Qty'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Save'}));
  await screen.findByText(/Purchase Plan changes saved/);
  expect(post).toHaveBeenCalledWith(expect.stringContaining('/workspace/save'),expect.objectContaining({
    edits:[expect.objectContaining({consumable_name:'Reviewed drill',purchase_notes:'Review supplier'})],
  }));
  expect(screen.getByRole('cell',{name:'Reviewed drill'})).toBeInTheDocument();
});

test('a rejected save retains edits and can explicitly reload the latest plan', async () => {
  const get = vi.spyOn(apiClient,'get').mockResolvedValue({plan_metadata:metadata,records:[row]});
  vi.spyOn(apiClient,'post').mockRejectedValue(new Error('This row changed. Reload before editing again.'));
  const {container}=show(<PurchaseWorkspace canCreate/>);
  await screen.findByRole('cell',{name:'DRILL-A'});
  fireEvent.doubleClick(container.querySelector('td[data-column-key="purchase_notes"]')!);
  const input=screen.getByRole('textbox',{name:'Edit Remarks'});
  fireEvent.change(input,{target:{value:'Keep this correction'}});fireEvent.blur(input);
  fireEvent.click(screen.getByRole('button',{name:/Save Changes/}));
  await screen.findByText('This row changed. Reload before editing again.');
  expect(screen.getByRole('cell',{name:'Keep this correction'})).toBeInTheDocument();
  get.mockResolvedValue({plan_metadata:metadata,records:[{...row,purchase_notes:'Other saved correction',draft_version:1}]});
  fireEvent.click(screen.getByRole('button',{name:'Discard changes and reload'}));
  await screen.findByRole('cell',{name:'Other saved correction'});
  expect(screen.getByLabelText('Planning Month')).toBeEnabled();
  expect(screen.queryByText('This row changed. Reload before editing again.')).not.toBeInTheDocument();
});
