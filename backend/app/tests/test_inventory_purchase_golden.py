from copy import deepcopy
import hashlib
import json

import pytest
from pydantic import ValidationError

from app.tests import inventory_purchase_golden as golden

TECHNICAL = golden.load_cases(golden.DATA / 'technical_cases.json')
COMPANY = golden.load_cases(golden.DATA / 'company_cases.json')


@pytest.mark.parametrize('case', TECHNICAL.cases, ids=lambda case: case.case_id)
def test_technical_case_matches_independent_expected_results(case):
    with golden.isolated_session() as session:
        actual = golden.replay(case, session)
    differences = golden.compare(case.expected, actual)
    assert not differences, json.dumps(differences, indent=2)


@pytest.mark.company_golden
@pytest.mark.parametrize('case', COMPANY.cases or [None], ids=lambda case: case.case_id if case else 'awaiting-KNL-examples')
def test_knl_approved_inventory_purchase_golden(case):
    if case is None:
        pytest.skip('M7.2 KNL acceptance PENDING: no complete company-approved numeric cases supplied')
    with golden.isolated_session() as session:
        actual = golden.replay(case, session)
    differences = golden.compare(case.expected, actual)
    assert not differences, json.dumps(differences, indent=2)


def test_technical_evidence_matches_independent_hand_calculation_source():
    # Canonical UTF-8/LF hash avoids platform checkout newline differences.
    source = (golden.DATA / 'technical_expected_results.md').read_text(encoding='utf-8').encode('utf-8')
    digest = hashlib.sha256(source).hexdigest()
    assert all(case.evidence.source_sha256 == digest for case in TECHNICAL.cases)
    assert all(case.evidence.kind == 'SYNTHETIC' and case.evidence.approved_by is None for case in TECHNICAL.cases)


def test_all_differences_are_recorded_including_missing_null_and_wrong_bool_type():
    expected = {'purchase': {'recommended_quantity': '60', 'target_stock': None},
                'reorder': {'reorder_required': True}}
    actual = {'purchase': {'recommended_quantity': '61'}, 'reorder': {'reorder_required': 1}}
    differences = golden.compare(expected, actual)
    assert [row['field'] for row in differences] == ['purchase.recommended_quantity', 'purchase.target_stock', 'reorder.reorder_required']
    assert differences[1]['actual_field_present'] is False
    assert all(row['investigation'] == 'OPEN' for row in differences)


def test_decimal_format_and_timezone_offsets_do_not_create_false_differences():
    assert not golden.compare({'stock': {'usable_quantity': '0.3003', 'as_of': '2020-01-02T05:30:00+05:30'}},
                              {'stock': {'usable_quantity': '0.300300', 'as_of': '2020-01-02T00:00:00Z'}})


def test_timeline_comparison_keeps_event_order_and_exact_decimals():
    expected = {'projection': {'timeline': [{'at': '2020-01-04T00:00:00Z', 'balance_after': '130'},
                                           {'at': '2020-01-05T00:00:00Z', 'balance_after': '70'}]}}
    actual = {'projection': {'timeline': [{'at': '2020-01-04T05:30:00+05:30', 'balance_after': '130.0000'},
                                         {'at': '2020-01-05T00:00:00Z', 'balance_after': '70.0000'}]}}
    assert not golden.compare(expected, actual)
    actual['projection']['timeline'][0]['balance_after'] = '100.0000'
    actual['projection']['timeline'][1]['balance_after'] = '40.0000'
    assert [row['field'] for row in golden.compare(expected, actual)] == [
        'projection.timeline[0].balance_after', 'projection.timeline[1].balance_after']


def test_an_extra_timeline_event_is_a_difference():
    assert golden.compare({'projection': {'timeline': []}}, {'projection': {'timeline': [{'at': '2020-01-04T00:00:00Z'}]}})[0]['field'] == 'projection.timeline.length'


def test_synthetic_cases_cannot_silently_pass_company_acceptance():
    data = TECHNICAL.model_dump(mode='json')
    data['suite'] = 'KNL_APPROVED'
    with pytest.raises(ValidationError, match='Synthetic cases'):
        golden.CaseSet.model_validate(data)


@pytest.mark.parametrize('field', ['approved_by', 'approved_at'])
def test_company_case_requires_actual_approval_metadata(field):
    data = TECHNICAL.cases[0].model_dump(mode='json')
    data['evidence'].update(kind='KNL_APPROVED', approved_by='Fixture approver', approved_at='2020-01-01T00:00:00Z')
    data['evidence'][field] = None
    with pytest.raises(ValidationError, match='KNL approver'):
        golden.GoldenCase.model_validate(data)


@pytest.mark.parametrize('scope,field', [('stock', 'usable_quantity'), ('purchase', 'recommended_quantity'), ('reorder', 'latest_safe_order_at')])
def test_expected_results_cannot_be_omitted(scope, field):
    data = TECHNICAL.cases[0].model_dump(mode='json')
    data['expected'][scope].pop(field)
    with pytest.raises(ValidationError, match='Missing independent expectations'):
        golden.GoldenCase.model_validate(data)


@pytest.mark.parametrize('value', [0.1, '0.00001', 'NaN'])
def test_input_decimal_validation_is_shared_with_domain_contract(value):
    data = TECHNICAL.cases[0].model_dump(mode='json')
    data['stock_imports'][0]['snapshots'][0]['usable_quantity'] = value
    with pytest.raises(ValidationError):
        golden.GoldenCase.model_validate(data)


@pytest.mark.parametrize('value', [1, False, 'true'])
def test_fixture_stock_requires_source_confirmed_usable_exclusions(value):
    data = TECHNICAL.cases[0].model_dump(mode='json')
    data['stock_imports'][0]['snapshots'][0]['nonusable_excluded'] = value
    with pytest.raises(ValidationError):
        golden.GoldenCase.model_validate(data)


def test_duplicate_case_ids_and_plants_are_rejected():
    data = TECHNICAL.model_dump(mode='json')
    data['cases'].append(deepcopy(data['cases'][0]))
    with pytest.raises(ValidationError, match='Duplicate case identities'):
        golden.CaseSet.model_validate(data)
    case = TECHNICAL.cases[0].model_dump(mode='json')
    case['demand'] *= 2
    with pytest.raises(ValidationError, match='each plant'):
        golden.GoldenCase.model_validate(case)


@pytest.mark.parametrize('text,reason', [('{"value":0.1}', 'binary float'), ('{"value":1,"value":2}', 'Duplicate JSON key')])
def test_case_file_cannot_silently_change_exact_inputs(tmp_path, text, reason):
    path = tmp_path / 'bad.json'
    path.write_text(text, encoding='utf-8')
    with pytest.raises(ValueError, match=reason):
        golden.load_cases(path)


def test_empty_company_suite_reports_pending_and_returns_nonzero(tmp_path):
    report = tmp_path / 'report.json'
    assert golden.main(['--report', str(report)]) == 2
    result = json.loads(report.read_text(encoding='utf-8'))
    assert result['status'] == 'NOT_READY' and result['company_acceptance'] == 'PENDING'
    assert result['case_count'] == result['difference_count'] == result['replay_error_count'] == 0


def test_replay_failure_is_recorded_and_other_cases_are_still_compared(monkeypatch):
    original = golden.replay
    def fail_first(case, session):
        if case.case_id == 'T01':
            raise ValueError('Deliberate fixture failure')
        return original(case, session)
    monkeypatch.setattr(golden, 'replay', fail_first)
    result = golden.evaluate(golden.CaseSet(schema_version='M7.2_V1', suite='SYNTHETIC', cases=TECHNICAL.cases[:2]))
    assert result['status'] == 'DIFFERENCE' and result['company_acceptance'] == 'PENDING'
    assert result['replay_error_count'] == 1
    assert result['cases'][0]['investigation'] == 'OPEN' and result['cases'][1]['status'] == 'MATCH'
