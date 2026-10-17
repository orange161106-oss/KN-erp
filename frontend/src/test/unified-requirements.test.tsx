import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import {apiClient} from '../api/client';
import {AuthContext} from '../features/auth/context';
import Requirements from '../features/requirements/Requirements';

const version={id:'october',planning_period:'2026-10',revision_label:'R1',status:'CALCULATED',is_latest:true,source_filename:'sample.xlsx'};
const row={id:'line-1',planning_period:'2026-10',part_name:'Sample product',part_number:'PART-A',consumable_code:'DRILL-A',consumable_name:'Sample drill',
  process_name:'Drilling',production_order_qty:'100',scheduled_consumable_qty:'200',required_qty:'200',unit:'PCS',plant:'Central',process:'Drilling',
  description:'Sample drill',part_thickness:'0',process_count:2,stock_qty:'Unavailable',shortage_qty:'Unavailable',po_pending_qty:'Unavailable',
  msl:'Unavailable',status:'Calculated',remarks:null};
let status:string;
let issues:{id:string;product_code:string;error_code:string;error_message:string}[];
function monthly(november=false) {
  return {records:[row],plan_metadata:{has_plan:true,plan_id:november?'november':'october',planning_period:november?'2026-11':'2026-10',
    planning_month:november?11:10,planning_year:2026,revision_label:'R1',status,record_count:1,issue_count:1,source_workflow:'BASIC_CENTRAL_V1'}};
}
function fixture() {
  return vi.spyOn(apiClient,'get').mockImplementation(async path=>{
    const november=path.includes('month=11')||path.includes('planning_version_id=november');
    const selected={...version,id:november?'november':'october',planning_period:november?'2026-11':'2026-10',status};
    if(path.includes('/requirements/basic/workspace'))return {versions:[selected],selected_version_id:selected.id,
      results:{calculations:[{id:row.id}],errors:issues,summary:[]}} as never;
    if(path.includes('/workspace/view'))return monthly(november) as never;
    throw new Error(`Unexpected read ${path}`);
  });
}
function show(admin=true) {
  return render(<AuthContext.Provider value={{user:{id:'sample',username:'sample',roles:[],permissions:[],is_super_admin:admin,
    requirements_read:true,requirements_update:admin,plant_ids:[]},login:vi.fn(),logout:vi.fn()}}><Requirements/></AuthContext.Provider>);
}
async function ready(){await screen.findByRole('cell',{name:'DRILL-A'});}
async function openApproval(){
  fireEvent.click(screen.getByLabelText('Requirement plan actions'));
  fireEvent.click(screen.getByRole('button',{name:'Approve plan'}));
  await screen.findByRole('dialog',{name:'Approve requirement plan'});
  await waitFor(()=>expect(screen.queryByText('Loading plan…')).not.toBeInTheDocument());
}
beforeEach(()=>{localStorage.clear();status='CALCULATED';issues=[];window.history.replaceState({},'','/requirements');});
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();window.history.replaceState({},'','/requirements');});

test('compact MRP loads one workspace with issues and no central review panel; recalculation uses the reviewer date without approval',async()=>{
  const get=fixture();const post=vi.spyOn(apiClient,'post').mockResolvedValue({...monthly(),message:'Requirements recalculated.'});
  show();await ready();
  expect(get).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/1 issue:/)).toBeInTheDocument();
  expect(screen.queryByRole('heading',{name:'Central review and approval'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Preview matching'})).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Calculation date')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:/Recalculate$/}));
  fireEvent.change(screen.getByLabelText('Calculation date'),{target:{value:'2026-10-18'}});
  fireEvent.click(screen.getByRole('button',{name:'Recalculate requirements'}));
  await screen.findByText('Requirements recalculated.');
  expect(post).toHaveBeenCalledWith('/api/v1/requirements/workspace/recalculate?month=10&year=2026&as_of_date=2026-10-18',{});
  expect(post.mock.calls.some(([path])=>path.endsWith('/approve'))).toBe(false);
  expect(screen.getByRole('cell',{name:'DRILL-A'})).toBeInTheDocument();
});

test('pending recalculation locks the period and the next month recalculates its own saved plan',async()=>{
  fixture();let finish!:(value:unknown)=>void;
  const post=vi.spyOn(apiClient,'post').mockReturnValue(new Promise(resolve=>{finish=resolve;}) as never);
  show();await ready();
  fireEvent.click(screen.getByRole('button',{name:/Recalculate$/}));
  fireEvent.click(screen.getByRole('button',{name:'Recalculate requirements'}));
  expect(screen.getByLabelText('Planning Month')).toBeDisabled();
  expect(screen.getByLabelText('Planning Year')).toBeDisabled();
  finish(monthly());await waitFor(()=>expect(screen.getByLabelText('Planning Month')).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Planning Month'),{target:{value:'11'}});await ready();
  fireEvent.click(screen.getByRole('button',{name:/Recalculate$/}));
  fireEvent.click(screen.getByRole('button',{name:'Recalculate requirements'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith(expect.stringContaining('month=11&year=2026&as_of_date='),{}));
});

test('approval is loaded on demand and remains separate from recalculation',async()=>{
  const get=fixture();const post=vi.spyOn(apiClient,'post').mockImplementation(async()=>{status='APPROVED';return {} as never;});
  show();await ready();await openApproval();
  expect(get).toHaveBeenCalledWith('/api/v1/requirements/basic/workspace?planning_version_id=october',60000);
  fireEvent.click(screen.getByRole('button',{name:'Confirm approval'}));
  await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(post).toHaveBeenCalledWith('/api/v1/requirements/planning-versions/october/approve',{});
  expect(screen.getByRole('button',{name:/Recalculate$/})).toBeDisabled();
});

test('missing norms require acknowledgement and hard errors still block approval',async()=>{
  issues=[{id:'missing',product_code:'PART-B',error_code:'NO_CONSUMPTION_NORM',error_message:'Configure a consumption norm.'}];
  fixture();const post=vi.spyOn(apiClient,'post').mockResolvedValue({});
  show();await ready();await openApproval();
  expect(screen.getByRole('button',{name:'Confirm approval'})).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox',{name:/I understand/}));
  fireEvent.click(screen.getByRole('button',{name:'Confirm approval'}));
  await waitFor(()=>expect(post).toHaveBeenCalledWith('/api/v1/requirements/planning-versions/october/approve',{acknowledge_missing_norms:true}));
  issues=[{id:'hard',product_code:'PART-A',error_code:'PRODUCTION_UNIT_CHANGED',error_message:'Resolve stock unit.'}];
  await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  await openApproval();
  expect(screen.getByRole('button',{name:'Confirm approval'})).toBeDisabled();
  expect(screen.getByText('Resolve calculation errors before approving this plan.')).toBeInTheDocument();
});

test('read-only users keep the grid and reports without recalculation or plan approval actions',async()=>{
  fixture();show(false);await ready();
  expect(screen.queryByRole('button',{name:/Recalculate$/})).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Requirement plan actions')).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:/Download issues list/})).toBeInTheDocument();
});

test('a Purchase review link opens the requested month rather than the default October plan',async()=>{
  window.history.replaceState({},'','/requirements?period=2026-11');
  const get=fixture();show();await ready();
  expect(screen.getByLabelText('Planning Month')).toHaveValue('11');
  expect(get).toHaveBeenCalledWith('/api/v1/requirements/workspace/view?month=11&year=2026',60000);
});

test('the compact MRP Excel export uses the authenticated binary client for the selected period',async()=>{
  fixture();const blob=new Blob(['sample workbook']);const download=vi.spyOn(apiClient,'getBlob').mockResolvedValue(blob);
  const revoked=vi.fn();vi.stubGlobal('URL',class extends URL {static createObjectURL=vi.fn(()=>'blob:requirements');static revokeObjectURL=revoked;});
  const names:string[]=[];vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(function(this:HTMLAnchorElement){names.push(this.download);});
  show();await ready();fireEvent.click(screen.getByRole('button',{name:/Export Excel ▾/}));
  await screen.findByText('Requirements Excel download started.');
  expect(download).toHaveBeenCalledWith('/api/v1/requirements/workspace/export?month=10&year=2026');
  expect(names).toEqual(['consumable_requirements_2026_10.xlsx']);expect(revoked).toHaveBeenCalledWith('blob:requirements');
});
