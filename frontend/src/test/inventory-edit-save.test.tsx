import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import {AuthContext} from '../features/auth/context';
import {apiClient} from '../api/client';
import Statement from '../features/inventory/StockStatementWorkspace';
import Management from '../features/inventory/StockManagementWorkspace';
const user={id:'user',username:'operator',roles:[],permissions:[],inventory_read:true,inventory_update:true};
beforeEach(()=>vi.restoreAllMocks());
for (const module of ['statement','management'] as const) {
 test(`${module} saves exact decimal edits through its API`,async()=>{
  let value='10';const id='00000000-0000-4000-8000-000000000001';const batch='00000000-0000-4000-8000-000000000002';
  vi.spyOn(apiClient,'get').mockImplementation(async endpoint=>{
   const query=new URL(endpoint,'http://localhost').searchParams;const month=Number(query.get('month'));const year=Number(query.get('year'));
   return {metadata:{batch_id:batch,month,year,statement_month:month,statement_year:year,has_statement:true,has_parameters:true,row_count:1},
    summary:{item_count:1,warning_rows_count:0,missing_limits_count:0,min_exceeds_max_count:0},
    records:[{id,item_id:'TEST-MATERIAL',description:'Test',item_description:'Test',opening_qty:value,min_stock_level:value,warning_codes:[]}]} as never;
  });
  const field=module==='statement'?'opening_qty':'min_stock_level';
  const update=vi.spyOn(apiClient,'patch').mockImplementation(async(_,body)=>{
   value=(body as {updates:Record<string,string>[]} ).updates[0][field];return {} as never;
  });
  render(<AuthContext.Provider value={{user,login:vi.fn(),logout:vi.fn()}}>{module==='statement'?<Statement/>:<Management/>}</AuthContext.Provider>);
  await screen.findByText('TEST-MATERIAL');
  const initialCell=screen.getByRole('cell',{name:module==='statement'?'10.00':'10'});
  fireEvent.doubleClick(initialCell);
  const editor=screen.getByRole('textbox',{name:module==='statement'?'Edit Opening Qty.':'Edit Min. Stock Level'});
  fireEvent.change(editor,{target:{value:'0.1234'}});fireEvent.blur(editor);
  const changed=screen.getByRole('cell',{name:'0.1234'});changed.focus();fireEvent.keyDown(changed,{key:'z',ctrlKey:true});
  expect(screen.getByRole('button',{name:module==='statement'?'Save changes':'Save'})).toBeDisabled();
  fireEvent.doubleClick(screen.getByRole('cell',{name:module==='statement'?'10.00':'10'}));
  fireEvent.change(screen.getByRole('textbox',{name:module==='statement'?'Edit Opening Qty.':'Edit Min. Stock Level'}),{target:{value:'0.1234'}});
  // Ctrl+S commits the active cell first and saves on the following render.
  fireEvent.keyDown(screen.getByRole('textbox',{name:module==='statement'?'Edit Opening Qty.':'Edit Min. Stock Level'}),{key:'s',ctrlKey:true});
  await waitFor(()=>expect(update).toHaveBeenCalledOnce());
  const payload=update.mock.calls[0][1] as {batch_id:string;updates:Record<string,unknown>[]};
  expect(payload.batch_id).toBe(batch);expect(payload.updates).toEqual([{id,[field]:'0.1234'}]);
 });
}


for (const module of ['statement','management'] as const) {
 test(`${module} enables Item Description Edit cell, undo, redo and audited save payload`,async()=>{
  let description='Rework Tag';const id='00000000-0000-4000-8000-000000000001';const batch='00000000-0000-4000-8000-000000000002';
  vi.spyOn(apiClient,'get').mockImplementation(async endpoint=>{
   const query=new URL(endpoint,'http://localhost').searchParams;const month=Number(query.get('month'));const year=Number(query.get('year'));
   return {metadata:{batch_id:batch,month,year,statement_month:month,statement_year:year,has_statement:true,has_parameters:true,row_count:1},
    summary:{item_count:1,warning_rows_count:0,missing_limits_count:0,min_exceeds_max_count:0},
    records:[{id,item_id:'TEST-MATERIAL',description,item_description:description,warning_codes:[]}]} as never;
  });
  const field=module==='statement'?'item_description':'description';
  const update=vi.spyOn(apiClient,'patch').mockImplementation(async(_,body)=>{
   description=(body as {updates:Record<string,string>[]}).updates[0][field];return {} as never;
  });
  render(<AuthContext.Provider value={{user,login:vi.fn(),logout:vi.fn()}}>{module==='statement'?<Statement/>:<Management/>}</AuthContext.Provider>);
  await screen.findByText('TEST-MATERIAL');
  fireEvent.contextMenu(screen.getByRole('cell',{name:'Rework Tag'}));
  const edit=screen.getByRole('button',{name:/^Edit cell/});expect(edit).toBeEnabled();fireEvent.click(edit);
  const editor=screen.getByRole('textbox',{name:module==='statement'?'Edit Item Description':'Edit Description'});
  fireEvent.change(editor,{target:{value:'Rework Tag, approved'}});fireEvent.keyDown(editor,{key:'Enter'});
  fireEvent.keyDown(document.body,{key:'z',ctrlKey:true});
  expect(screen.getByRole('cell',{name:'Rework Tag'})).toBeInTheDocument();
  fireEvent.keyDown(document.body,{key:'y',ctrlKey:true});
  expect(screen.getByText('Rework Tag, approved')).toBeInTheDocument();
  fireEvent.keyDown(document.body,{key:'s',ctrlKey:true});
  await waitFor(()=>expect(update).toHaveBeenCalledOnce());
  expect((update.mock.calls[0][1] as {updates:unknown[]}).updates).toEqual([{id,[field]:'Rework Tag, approved'}]);
 });
}
