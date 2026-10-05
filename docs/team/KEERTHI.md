# Keerthi — Plant Workflow, Approvals & Alerts

## Mission
Own plant-facing workflows so every exception/change is permission-controlled, approved and visible.

## Owned areas
- plants
- routes/workflow coordination
- plant confirmation
- additional/exception requests
- approvals
- plant scope/access
- alerts
- dashboard workflow visibility

## Conditional
Do not implement plant floor stock or inter-plant transfers until KNL confirms they are official controlled processes.

## Inputs
Yathish: calculated plant/material requirements
Munees: stock/MSL/reorder/PO-delay events

## Outputs
Munees: approved final requirement/adjustments
Audit/reporting: workflow and approval history

## AI boundary
Do not invent approval authority or directly change calculated quantities.
