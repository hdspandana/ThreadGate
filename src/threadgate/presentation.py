"""Escaped, accessible comparison rendering. Masking is not a full PII scrubber."""
import html
import re
from difflib import SequenceMatcher
from .normalize import normalize_text
from .tokens import find_tokens

SENSITIVE={'account_number','iban','ifsc','swift','beneficiary_name','remittance_email','contact_phone'}


def mask_value(value):
    if value is None:return 'Not provided'
    value=str(value)
    return '•••• '+value[-4:] if len(value)>4 else '••••'


def masked_text(text):
    nt=normalize_text(text)
    spans=[]
    for token in find_tokens(nt):
        if token.kind in {'account','iban','ifsc','swift'}:
            spans.append(nt.to_raw_span(token.start,token.end))
    # Also mask malformed account-labelled values that the token scanner cannot read.
    spans.extend(m.span(1) for m in re.finditer(r'(?i)account(?:\s+number)?\s*[:=]\s*([A-Za-z0-9]{8,34})',text))
    spans.extend(m.span() for m in re.finditer(r"(?<!\w)\d[\d .()\-]{6,}\d(?!\w)",text))
    spans.extend(m.span() for m in re.finditer(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",text))
    # Union overlaps before redacting: a shorter first match must not leave the
    # suffix of a longer sensitive identifier exposed.
    merged=[]
    for start,end in sorted(spans):
        if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(merged[-1][1],end))
        else:merged.append((start,end))
    spans=merged
    output=[];cursor=0
    for start,end in spans:
        if start<cursor:continue
        output.extend([text[cursor:start],mask_value(text[start:end])]);cursor=end
    return ''.join(output)+text[cursor:]


def comparison_html(result,reveal=False):
    rows=[]
    for diff in result.decision.diffs:
        old,new=diff.old_value,diff.new_value
        if not reveal and diff.field in SENSITIVE:old,new=mask_value(old),mask_value(new)
        status='Different — verify out of band' if diff.changed else 'Matches record — not payment approval'
        def cell(value):return html.escape(str(value if value is not None else 'Not provided'))
        old_html,new_html=cell(old),cell(new)
        if diff.changed and reveal:
            old_parts=[];new_parts=[]
            for tag,a,b,c,d in SequenceMatcher(a=str(old or ''),b=str(new or '')).get_opcodes():
                before,after=cell(str(old or '')[a:b]),cell(str(new or '')[c:d])
                old_parts.append(before if tag=='equal' else '<del>'+before+'</del>')
                new_parts.append(after if tag=='equal' else '<mark>'+after+'</mark>')
            old_html,new_html=''.join(old_parts),''.join(new_parts)
        rows.append('<tr><th scope="row">'+cell(diff.field)+'</th><td>'+old_html+'</td><td'+
            (' style="border-left:3px solid #ffca76"' if diff.changed else '')+'>'+new_html+'</td><td>'+cell(status)+'</td></tr>')
    if not rows:return '<p>No validated field comparison. This does not mean the request is safe.</p>'
    return ('<div style="overflow-x:auto"><table class="comparison"><caption>Trusted record compared with requested values</caption>'
        '<thead><tr><th scope="col">Field</th><th scope="col">Trusted record</th><th scope="col">Requested</th><th scope="col">Next action</th></tr></thead>'
        '<tbody>'+''.join(rows)+'</tbody></table></div>')


def decision_banner_html(decision):
    """Render only a known gate state; never interpolate email/model content."""
    explanations = {
        'CLEAR': ('No change identified by this prototype.',
                  'Not a guarantee of safety, payment approval, or proof that the sender is genuine.'),
        'REVIEW': ('A human must review and attest before proceeding.',
                   'A familiar destination does not remove the verification requirement. No payment is authorised.'),
        'HOLD': ('Stop and verify out of band using the trusted record.',
                 'Do not use replacement contact details from the request. This is not an accusation of fraud.'),
    }
    title,detail=explanations[decision]
    return ('<div class="panel decision-banner '+decision.lower()+'" role="status" aria-label="'+decision+
            ' gate decision"><strong>'+decision+'</strong><div><p>'+title+'</p><small>'+detail+'</small></div></div>')
