"""Provider-side shape constraints; the server validates exact evidence IDs."""
from .dac_rules import definition, STATES


def obj(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def array(items):
    return {'type':'array','items':items}


def question_schema(qid, evidence_ids, pdm_ids=None):
    string={'type':'string'}
    # Avoid repeating a large enum at eight nested paths: Gemini rejects that
    # schema as INVALID_ARGUMENT. The prompt contains only this question's IDs;
    # refs_for independently enforces exact membership for every returned ID.
    refs=array(string) if evidence_ids else {**array(string),'maxItems':0}
    condition=obj({'status':{'type':'string','enum':['met','not_met','unverified','conflicted']},
                   'finding':string,'evidence_ids':refs})
    measurement=obj({'table_row_id':string,'metric':string,'target':{'type':'number'},'actual':{'type':'number'},
        'unit':string,'period':string,'population':string,
        'direction':{'type':'string','enum':['higher','lower','budget','duration']},
        'comparable':{'type':'boolean'},'due':{'type':'boolean'},
        'target_evidence_ids':refs,'actual_evidence_ids':refs,
        'justification':{'type':'string','enum':['verified','asserted','none']},'justification_evidence_ids':refs})
    check=obj({'indicator_id':{'type':'string','enum':[c['id'] for c in definition(qid)['checks']]},
        'state':{'type':'string','enum':list(STATES)},'finding':string,'evidence_ids':refs,
        'negative_fact_quote':{'type':'string','description':'negative일 때만 직접적인 미실행·미달·피해 사실의 원문 단문. 단순 자료 부재는 부정 사실이 아니며 나머지는 빈 문자열.'},
        # Use numeric bounds for grades and explicit strings for discrete quality.
        'quality':obj({'source_grade':{'type':'integer','minimum':1,'maximum':4},
            'directness':{'type':'string','enum':['0','0.5','1']},
            'recency':{'type':'string','enum':['0','0.5','1']},'rationale':string}),
        'source_families':array(obj({'name':string,'provenance':string,'evidence_ids':refs})),
        'measurements':array(measurement)})
    question=obj({'question_id':{'type':'string','enum':[qid]},'finding':string,
        'positive_evidence':array(string),'limitations':array(string),'action_items':array(string),
        'table_row_reviews':array(obj({'evidence_id':string,'decision':{'type':'string','enum':['included','excluded']},'reason':string,
            'unit':string,'period':string,'population':string,'direction':{'type':'string','enum':['higher','lower']},
            'comparable':{'type':'boolean'},'due':{'type':'boolean'}})),
        'pdm_indicator_ids':array({'type':'string','enum':sorted(pdm_ids)}) if pdm_ids else {**array(string),'maxItems':0},
        'indicators':{**array(check),'minItems':5,'maxItems':5},
        'four_point_gate':condition,'specific_cap':condition,'red_flag':condition})
    return obj({'question_assessments':{**array(question),'minItems':1,'maxItems':1}})
