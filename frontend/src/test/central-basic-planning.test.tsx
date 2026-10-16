import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import {apiClient} from '../api/client';
import {AuthContext} from '../features/auth/context';
import CentralProductionImport from '../features/prd/CentralProductionImport';
import Requirements from '../features/requirements/Requirements';
import CentralPurchaseAssessment from '../features/purchasing/CentralPurchaseAssessment';

const endpoint='/api/v1/requirements/basic';
const version={id:'version-1',planning_period:'2026-10',revision_label:'R3',status:'VALIDATED',is_latest:true,source_filename:'source.xlsx'};
const material={consumable_id:'mat-1',consumable_code:'DRILL',consumable_name:'Synthetic drill',uom:'PCS',final_required_qty:'230',is_fully_confirmed:true};
const sourcePreview={sheet_name:'Prd. Order',planning_period:'2026-10',revision_label:'R3',as_of_date:'2026-10-01',review_token:'reviewed-token',
  rows:[{source_row_number:5,part_number:'PART-A',item_id:'ITEM-A',product_code:'PROD-A',product_name:'Synthetic part',quantity:'100',unit:'PCS',norm_count:1,errors:[],norm_errors:[]}],errors:[],can_confirm:true,norm_ready:true};

function authorized(component:React.ReactNode,superAdmin=true){
  return render(
    <AuthContext.Provider value={{user:{id:'operator',username:'operator',roles:[],permissions:[],is_super_admin:superAdmin,requirements_read:true,requirements_update:superAdmin,plant_ids:[]},login:vi.fn(),logout:vi.fn()}}>
      {component}
    </AuthContext.Provider>
  );
}

beforeEach(()=>{localStorage.clear();});
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();});

test('production upload previews before confirmation and submits the exact reviewed revision',async()=>{
  const imported=vi.fn();const close=vi.fn();const post=vi.spyOn(apiClient,'postFormData').mockResolvedValueOnce(sourcePreview).mockResolvedValueOnce({imported_count:1});
  authorized(<CentralProductionImport isOpen onClose={close} onImportSuccess={imported}/>);
  fireEvent.change(screen.getByLabelText('Production file'),{target:{files:[new File(['synthetic'],'source.xlsx')]}});
  fireEvent.change(screen.getByLabelText('Planning month'),{target:{value:'2026-10'}});
  fireEvent.change(screen.getByLabelText('Norm effective date'),{target:{value:'2026-10-01'}});
  fireEvent.submit(screen.getByRole('button',{name:'Preview and validate'}).closest('form')!);
  await screen.findByText('1 production rows · 2026-10 · R3. Preview does not save data.');
  expect(post).toHaveBeenCalledTimes(1);expect(imported).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Confirm production import'}));
  await waitFor(()=>expect(imported).toHaveBeenCalledWith(1,'Prd. Order'));
  expect(post.mock.calls[1][0]).toBe(endpoint+'/production-confirm');
  expect(post.mock.calls[1][1].get('review_token')).toBe('reviewed-token');expect(post.mock.calls[1][1].get('revision_label')).toBe('R3');
  expect(close).toHaveBeenCalled();
});

test('unmatched product errors block confirming the entire production upload',async()=>{
  vi.spyOn(apiClient,'postFormData').mockResolvedValue({...sourcePreview,can_confirm:false,rows:[{...sourcePreview.rows[0],product_code:'UNKNOWN',errors:[{message:'Review Product Master identity.'}]}]});
  authorized(<CentralProductionImport isOpen onClose={vi.fn()} onImportSuccess={vi.fn()}/>);
  fireEvent.change(screen.getByLabelText('Production file'),{target:{files:[new File(['synthetic'],'source.csv')]}});
  fireEvent.change(screen.getByLabelText('Planning month'),{target:{value:'2026-10'}});fireEvent.change(screen.getByLabelText('Norm effective date'),{target:{value:'2026-10-01'}});
  fireEvent.submit(screen.getByRole('button',{name:'Preview and validate'}).closest('form')!);await screen.findByText('Review Product Master identity.');
  expect(screen.getByRole('button',{name:'Confirm production import'})).toBeDisabled();
});

test('monthly consumable planning displays production-based quantities directly without tabs', async () => {
  const metadata = {has_plan:true,plan_id:version.id,planning_period:'2026-10',status:'CALCULATED',revision_label:'R3',record_count:1,source_workflow:'BASIC_CENTRAL_V1'};
  const row = {id:'calc-1',part_name:'Synthetic part',part_number:'PART-A',consumable_code:'DRILL',consumable_name:'Synthetic drill',process_name:'Drilling',
    production_order_qty:'100',scheduled_consumable_qty:'200',required_qty:'200',unit:'PCS',plant:'Central / unassigned',process:'Drilling',description:'Synthetic drill',
    part_thickness:'0',process_count:2,stock_qty:'Unavailable',shortage_qty:'Unavailable',po_pending_qty:'Unavailable',msl:'Unavailable',status:'Calculated',remarks:null};
  vi.spyOn(apiClient,'get').mockImplementation(async path => {
    if(path.includes('/requirements/workspace/view')) return {records:[row],plan_metadata:metadata} as never;
    return {} as never;
  });
  const post=vi.spyOn(apiClient,'post').mockResolvedValue({message:'Production-based requirements updated.',records:[row],plan_metadata:metadata});
  authorized(<Requirements />);
  await screen.findByText(/Production-based requirements calculated deterministically/);
  expect(screen.getByRole('cell',{name:'DRILL'})).toBeInTheDocument();
  expect(screen.getAllByRole('cell',{name:'200'}).length).toBeGreaterThan(0);
  expect(screen.queryByRole('button',{name:/Upload Excel/})).not.toBeInTheDocument();
  expect(screen.queryByText('Central requirement plan')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:/Recalculate$/}));
  await waitFor(()=>expect(post).toHaveBeenCalledWith('/api/v1/requirements/workspace/recalculate?month=10&year=2026',{}));
});

test('purchase assessment never copies gross demand or treats missing inventory as zero',async()=>{
  vi.spyOn(apiClient,'get').mockImplementation(async path=>{
    if(path.includes('/sources?'))return [] as never;
    if(path.includes('/supplier-consumables?'))return {items:[{supplier_id:'supplier-1'}],total:1} as never;
    if(path.includes('/suppliers?'))return {items:[{id:'supplier-1',code:'SUP-A',name:'Synthetic supplier'}],total:1} as never;
    return {unit_id:'unit-1'} as never;
  });
  const post=vi.spyOn(apiClient,'post').mockResolvedValue({status:'INCOMPLETE',final_requirement:'230',current_stock:null,confirmed_incoming_before_receipt:null,raw_quantity:null,recommended_quantity:null,
    explanation:'Verified projection required.',request:{},limitations:[{message:'Projection incomplete.'}],projection:{stock_as_of:null,current_msl_condition:'UNKNOWN',projected_msl_condition:'UNKNOWN',limitations:[{message:'Stock not imported.'}]},steps:[]});
  authorized(<CentralPurchaseAssessment versionId="version-1" material={material}/>);
  await screen.findByRole('option',{name:'SUP-A — Synthetic supplier'});
  fireEvent.change(screen.getByLabelText('Mapped supplier'),{target:{value:'supplier-1'}});
  for(const [label,value] of [['Order initiated at','2026-10-15T10:00'],['Material usable at','2026-10-17T10:00'],['Policy valid from','2026-10-01T00:00'],['Policy valid until','2026-11-01T00:00']])fireEvent.change(screen.getByLabelText(label),{target:{value}});
  fireEvent.click(screen.getByRole('button',{name:'Assess stock and purchase need'}));await screen.findByText('Stock not imported.');
  expect(screen.getByText('INCOMPLETE')).toBeInTheDocument();expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0);
  expect(post).toHaveBeenCalledWith('/api/v1/purchasing/recommendations/assess',expect.objectContaining({source_set_id:null,target:null,lead_time:null,constraints:expect.objectContaining({moq:{state:'UNKNOWN'}})}));
  expect(screen.queryByRole('button',{name:'Submit traced demand for approval'})).not.toBeInTheDocument();
});
