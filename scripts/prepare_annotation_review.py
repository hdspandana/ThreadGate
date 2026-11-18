"""Rebuild a small label/prediction-blinded semantic review packet; standard library only."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SELECTION=('AS-dev-05-1','AS-dev-05-2','AS-hel-05-1')
REPLACEMENTS={'50100234559821':'ACCOUNT-A','50100234554455':'ACCOUNT-B',
              'accounts@synthetic.example':'sender@review.invalid'}


def build(root=ROOT):
    sources={}
    for split in ('development','heldout'):
        path=root/'data/assurance'/f'{split}.json'
        raw=path.read_bytes()
        for case in json.loads(raw)['cases']:
            if case['id'] in SELECTION:
                sources[case['id']]=(case,path.relative_to(root).as_posix(),hashlib.sha256(raw).hexdigest())
    packet={'version':'active-request-review-v1','status':'AWAITING_INDEPENDENT_HUMAN_REVIEW',
            'purpose':'Semantic role adjudication only; sanitized account aliases are not format-validation inputs.',
            'cases':[]}
    coordinator={'version':packet['version'],'original_labels_modified':False,'mapping':[]}
    for i,source_id in enumerate(SELECTION,1):
        case,path,digest=sources[source_id]; review_id=f'R{i:02}'
        # Whitelist email fields: never serialize annotations, decisions or predictions.
        email={k:case['email'][k] for k in ('from','reply_to','subject','body')}
        for key,text in email.items():
            for old,new in REPLACEMENTS.items():text=text.replace(old,new)
            email[key]=text
        packet['cases'].append({'review_id':review_id,'email':email})
        coordinator['mapping'].append({'review_id':review_id,'source_id':source_id,
          'source_path':path,'source_sha256':digest,
          'original_email_sha256':hashlib.sha256(json.dumps(case['email'],sort_keys=True).encode()).hexdigest()})
    return packet,coordinator


def main():
    packet,coordinator=build();out=ROOT/'docs/adjudication-v1'
    out.mkdir(exist_ok=True)
    for filename,content in [('review-input.json',packet),('COORDINATOR-ONLY.json',coordinator)]:
        (out/filename).write_text(json.dumps(content,indent=2)+'\n')
    print('Prepared 3 sanitized cases; no human review or label updates performed.')


if __name__=='__main__':main()
