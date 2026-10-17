import {act,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,expect,test,vi} from 'vitest';
import {apiClient} from '../api/client';
import {AuthContext} from '../features/auth/context';
import PRDPlanning from '../features/prd/PRDPlanning';
import PurchaseWorkspace from '../features/purchasing/PurchaseWorkspace';
import Requirements from '../features/requirements/Requirements';

const metadata={has_plan:false,planning_period:'2026-10',record_count:0};
const cases=[
  {name:'production',component:<PRDPlanning/>,response:[]},
  {name:'purchase',component:<PurchaseWorkspace canCreate/>,response:{records:[],plan_metadata:metadata}},
  {name:'monthly requirements',component:<Requirements defaultTab="mrp"/>,response:{records:[],plan_metadata:metadata}},
];
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks();});

function show(component:React.ReactNode){
  render(<AuthContext.Provider value={{user:{id:'synthetic',username:'synthetic',roles:[],permissions:[],is_super_admin:true},login:vi.fn(),logout:vi.fn()}}>{component}</AuthContext.Provider>);
}

test.each(cases)('$name searches issue one request after typing settles',async({component,response})=>{
  vi.useFakeTimers();
  const get=vi.spyOn(apiClient,'get').mockResolvedValue(response);
  await act(async()=>{show(component);});
  expect(get).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByRole('textbox',{name:'Search records'}),{target:{value:'D'}});
  fireEvent.change(screen.getByRole('textbox',{name:'Search records'}),{target:{value:'DRILL'}});
  await act(async()=>{await vi.advanceTimersByTimeAsync(299);});
  expect(get).toHaveBeenCalledTimes(1);
  await act(async()=>{await vi.advanceTimersByTimeAsync(1);});
  expect(get).toHaveBeenCalledTimes(2);
  expect(String(get.mock.calls[1][0])).toContain('search=DRILL');
});

test.each(cases)('$name ignores errors from an obsolete search request',async({component,response})=>{
  vi.useFakeTimers();
  let rejectOld!:(error:Error)=>void;
  const get=vi.spyOn(apiClient,'get').mockResolvedValueOnce(response)
    .mockImplementationOnce(()=>new Promise((_resolve,reject)=>{rejectOld=reject;}))
    .mockResolvedValue(response);
  await act(async()=>{show(component);});
  fireEvent.change(screen.getByRole('textbox',{name:'Search records'}),{target:{value:'old'}});
  await act(async()=>{await vi.advanceTimersByTimeAsync(300);});
  fireEvent.change(screen.getByRole('textbox',{name:'Search records'}),{target:{value:'current'}});
  await act(async()=>{await vi.advanceTimersByTimeAsync(300);});
  expect(get).toHaveBeenCalledTimes(3);
  await act(async()=>{rejectOld(new Error('Obsolete request failed'));});
  expect(screen.queryByText('Obsolete request failed')).not.toBeInTheDocument();
});
