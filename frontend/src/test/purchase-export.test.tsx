import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { apiClient, getAccessToken, setAccessToken, setUnauthorizedHandler } from '../api/client';
import { AuthContext } from '../features/auth/context';
import PurchaseWorkspace from '../features/purchasing/PurchaseWorkspace';

const metadata = {has_plan:true,plan_id:'sample-version',planning_period:'2026-10',planning_month:10,planning_year:2026,
  source_workflow:'BASIC_CENTRAL_V1',status:'CALCULATED',revision_label:'R0',record_count:2};
const records = ['sample-version:material-a:unit','sample-version:material-b:unit'].map((id,index) => ({
  id,plan_id:metadata.plan_id,revision:'R0',consumable_code:`TEST-00${index+1}`,consumable_name:`Sample drill ${index+1}`,unit:'PCS',
  required_qty:'230.0000',stock_qty:null,po_pending_qty:null,shortage_qty:null,system_recommended_qty:null,
  supplier_code:null,supplier_name:null,approval_status:null,source_row_count:1,status:'REQUIREMENT_REVIEW_REQUIRED',
}));

function setup(response: Promise<Response>) {
  vi.spyOn(apiClient,'get').mockResolvedValue({plan_metadata:metadata,records});
  const fetchMock = vi.fn<typeof fetch>().mockReturnValue(response);
  vi.stubGlobal('fetch',fetchMock);
  const createUrl=vi.fn((_blob:Blob)=>'blob:sample-workbook');
  const revokeUrl=vi.fn();
  vi.stubGlobal('URL',class extends URL { static createObjectURL=createUrl; static revokeObjectURL=revokeUrl; });
  const downloads: {filename:string;url:string;attached:boolean}[]=[];
  vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(function(this: HTMLAnchorElement) {
    downloads.push({filename:this.download,url:this.href,attached:this.isConnected});
  });
  const open=vi.spyOn(window,'open').mockImplementation(()=>null);
  setAccessToken('synthetic-export-session');
  render(<AuthContext.Provider value={{user:{id:'sample-user',username:'sample-user',roles:[],permissions:[],is_super_admin:true},login:vi.fn(),logout:vi.fn()}}>
    <PurchaseWorkspace canCreate/>
  </AuthContext.Provider>);
  return {fetchMock,downloads,createUrl,revokeUrl,open};
}

afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();});

test.each(['ALL','SELECTED','FILTERED'] as const)('authenticated %s export downloads Excel with the exact row/filter scope', async mode=>{
  const result=setup(Promise.resolve(new Response('sample workbook',{headers:{'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}})));
  await screen.findByRole('cell',{name:'TEST-001'});
  if(mode==='SELECTED') {
    fireEvent.click(screen.getByLabelText('Select row 1'));
    fireEvent.click(screen.getByLabelText('Select row 2'));
  }
  if(mode==='FILTERED') {
    fireEvent.change(screen.getByLabelText('Search records'),{target:{value:'Drill & tap'}});
    fireEvent.change(screen.getByLabelText('Status'),{target:{value:'REQUIREMENT_REVIEW_REQUIRED'}});
  }
  fireEvent.click(screen.getByRole('button',{name:mode==='FILTERED'?'Export Filtered':'Export Excel'}));
  await screen.findByText('Excel download started.');
  expect(result.fetchMock).toHaveBeenCalledOnce();
  const [path,options]=result.fetchMock.mock.calls[0];
  expect(options).toMatchObject({method:'GET',headers:{Authorization:'Bearer synthetic-export-session'}});
  const url=new URL(String(path),'http://localhost');
  expect(url.pathname).toBe('/api/v1/purchasing/workspace/export');
  expect(url.searchParams.get('month')).toBe('10');
  expect(url.searchParams.get('year')).toBe('2026');
  expect(url.searchParams.getAll('record_ids')).toEqual(mode==='SELECTED'?records.map(row=>row.id):[]);
  expect(url.searchParams.get('search')).toBe(mode==='FILTERED'?'Drill & tap':null);
  expect(url.searchParams.get('status')).toBe(mode==='FILTERED'?'REQUIREMENT_REVIEW_REQUIRED':null);
  expect(String(path)).not.toContain('synthetic-export-session');
  expect(result.downloads).toEqual([{filename:'purchase_recommendations_2026_10.xlsx',url:'blob:sample-workbook',attached:true}]);
  expect(result.createUrl.mock.calls[0][0]).toBeInstanceOf(Blob);
  expect(result.revokeUrl).toHaveBeenCalledWith('blob:sample-workbook');
  expect(result.open).not.toHaveBeenCalled();
});

test('a failed export shows the server error, creates no JSON workbook and can be retried', async ()=>{
  const result=setup(Promise.resolve(new Response(JSON.stringify({code:'DATABASE_UNAVAILABLE',message:'Database unavailable. Try again.'}),{status:503})));
  await screen.findByRole('cell',{name:'TEST-001'});
  fireEvent.click(screen.getByRole('button',{name:'Export Excel'}));
  await screen.findByText('Database unavailable. Try again.');
  expect(result.downloads).toEqual([]);
  expect(result.createUrl).not.toHaveBeenCalled();
  expect(screen.getByRole('button',{name:'Export Excel'})).toBeEnabled();
});

test('an expired export session uses the normal sign-in handler without downloading an error page', async ()=>{
  const result=setup(Promise.resolve(new Response(JSON.stringify({code:'NOT_AUTHENTICATED',message:'Valid authentication is required.'}),{status:401})));
  const expired=vi.fn();setUnauthorizedHandler(expired);
  await screen.findByRole('cell',{name:'TEST-001'});
  fireEvent.click(screen.getByRole('button',{name:'Export Excel'}));
  await waitFor(()=>expect(expired).toHaveBeenCalledOnce());
  expect(getAccessToken()).toBeNull();
  expect(result.downloads).toEqual([]);
  expect(result.open).not.toHaveBeenCalled();
});

test('repeated clicks during an export start only one authenticated download', async ()=>{
  let finish!: (value:Response)=>void;
  const result=setup(new Promise(resolve=>{finish=resolve;}));
  await screen.findByRole('cell',{name:'TEST-001'});
  fireEvent.click(screen.getByRole('button',{name:'Export Excel'}));
  expect(screen.getByRole('button',{name:'Exporting…'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Export Filtered'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Export Filtered'}));
  expect(result.fetchMock).toHaveBeenCalledOnce();
  finish(new Response('sample workbook'));
  await screen.findByText('Excel download started.');
  expect(result.downloads).toHaveLength(1);
});
