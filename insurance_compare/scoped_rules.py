"""Conservative, clause-scoped comparisons for hospitalization terms.

Only recognizable policy layouts are interpreted. Unknown layouts remain unclear.
"""
import re


def compact(value):
    return "".join(value.split())


def unclear(note):
    return {
        "left_status": "unclear", "right_status": "unclear",
        "left_claims": [], "right_claims": [],
        "comparison_status": "unclear", "comparison": "",
    }, [note]


def claim(page, quote, fact):
    return {"page": page, "quote": quote[:1200], "fact": fact}


def page_for(document, predicate):
    for page in document["pages"]:
        if predicate(compact(page["text"])):
            return page
    return None


def old_deductible(document):
    page = page_for(document, lambda t: "자기부담금을차감하는담보" in t and
                    ("표준형상해입원실손의료비" in t or
                     "상해유병력자실손의료비(상해입원형)" in t))
    if page is None:
        return None
    text = compact(page["text"])
    values = []
    for label, anchor, pattern in (
        ("표준형", "표준형상해입원실손의료비", r"입원수술비:보상대상의료비의(\d+)%에해당하는금액"),
        ("선택형Ⅱ", "선택형Ⅱ상해입원실손의료비", r"입원수술비:보상대상의료비의급여(\d+)%해당액과비급여(\d+)%해당액의합산액"),
        ("유병력자 상해입원형", "상해유병력자실손의료비(상해입원형)", r"입원수술비:(\d+만원)과보상대상의료비의(\d+)%중큰금액"),
    ):
        pos = text.find(anchor)
        if pos < 0:
            continue
        row = text[pos:text.find("상해통원", pos) if "상해통원" in text[pos:] else pos + 230]
        match = re.search(pattern, row)
        if match:
            values.append((label, match.groups()))
    if not values:
        return None
    facts = []
    for label, amounts in values:
        if label == "표준형":
            facts.append(f"{label} 상해입원: 보상대상의료비의 {amounts[0]}%를 자기부담합니다.")
        elif label == "선택형Ⅱ":
            facts.append(f"{label} 상해입원: 급여 {amounts[0]}% 해당액과 비급여 {amounts[1]}% 해당액을 합산해 자기부담합니다.")
        else:
            facts.append(f"{label}: {amounts[0]}과 보상대상의료비의 {amounts[1]}% 중 큰 금액을 자기부담합니다.")
    return {
        "signature": tuple(values),
        "claims": [claim(page["page"], page["text"], " ".join(facts))],
        "summary": " ".join(facts),
        "scope": "구형 상해입원",
    }


def new_deductible(document):
    # Fourth-generation clauses use benefit percentages. The reimbursement
    # percentages are stated; the corresponding out-of-pocket shares are derived.
    injury = page_for(document, lambda t: "(1)상해급여" in t and "입원(입원실료" in t)
    noncovered = page_for(document, lambda t: "(1)상해비급여" in t and "입원(입원실료" in t)
    if injury is None or noncovered is None:
        return None
    pages = document["pages"]
    i = injury["page"] - 1
    benefit = compact(pages[i]["text"] + pages[i + 1]["text"] if i + 1 < len(pages) else pages[i]["text"])
    benefit = benefit[benefit.find("(1)상해급여"):]
    section = benefit[benefit.find("입원(입원실료"):]
    section = section[:section.find("통원(") if "통원(" in section else 900]
    benefit_match = re.search(r"의(\d+)%에해당하는금액", section)
    noncovered_text = compact(noncovered["text"])
    noncovered_section = noncovered_text[noncovered_text.find("(1)상해비급여"):]
    noncovered_section = noncovered_section[noncovered_section.find("입원(입원실료"):]
    noncovered_section = noncovered_section[:noncovered_section.find("상급병실료차액")]
    noncovered_match = re.search(r"의(\d+)%에해당하는금액", noncovered_section)
    if not benefit_match or not noncovered_match:
        return None
    paid_benefit = int(benefit_match.group(1))
    paid_noncovered = int(noncovered_match.group(1))
    if not (0 < paid_benefit < 100 and 0 < paid_noncovered < 100):
        return None
    fact_benefit = (f"상해급여 입원: 본인부담금의 {paid_benefit}%를 보상하므로 "
                    f"해당 금액의 {100-paid_benefit}%가 자기부담입니다.")
    fact_noncovered = (f"상해비급여 입원: 비급여 의료비의 {paid_noncovered}%를 보상하므로 "
                       f"해당 금액의 {100-paid_noncovered}%가 자기부담입니다.")
    return {
        "signature": (("상해급여", paid_benefit), ("상해비급여", paid_noncovered)),
        "claims": [
            claim(f"{injury['page']}~{injury['page']+1}",
                  section[:180] + " … " +
                  section[max(0, benefit_match.start()-180):benefit_match.end()+25],
                  fact_benefit),
            claim(noncovered["page"], noncovered["text"], fact_noncovered),
        ],
        "summary": fact_benefit + " " + fact_noncovered,
        "scope": "상해급여·상해비급여 입원",
    }


def deductible(document):
    return old_deductible(document) or new_deductible(document)


def exclusion(document):
    old = page_for(document, lambda t: "(1)상해입원" in t and
                   "4.피보험자가임신,출산" in t and
                   "회사가보상하는상해로인하여입원한경우에는보상합니다" in t)
    if old is not None:
        text = compact(old["text"])
        clause = re.search(r"4\.피보험자가임신,출산.*?5\.전쟁", text)
        if clause:
            fact = "상해입원: 임신·출산·산후기로 입원한 경우는 원칙적으로 보상하지 않지만, 회사가 보상하는 상해로 입원한 경우에는 보상합니다."
            return {"signature": "상해입원 예외", "claims": [claim(old["page"], clause.group()[:-4], fact)],
                    "summary": fact, "scope": "구형 상해입원"}
    found = []
    for label in ("상해급여", "상해비급여"):
        page = page_for(document, lambda t: f"(1){label}" in t and
                        "4.피보험자가임신,출산" in t and
                        "회사가보상하는상해로인하여입원또는통원한경우에는보상합니다" in t)
        if page is None:
            return None
        text = compact(page["text"])
        start = text.find(f"(1){label}")
        clause = re.search(r"4\.피보험자가임신,출산.*?5\.전쟁", text[start:])
        if not clause:
            return None
        fact = f"{label}: 임신·출산·산후기로 입원 또는 통원한 경우는 원칙적으로 보상하지 않지만, 회사가 보상하는 상해로 인한 경우에는 보상합니다."
        found.append(claim(page["page"], clause.group()[:-4], fact))
    return {"signature": "상해급여·상해비급여 예외", "claims": found,
            "summary": "상해급여·상해비급여 모두 임신·출산·산후기를 원칙적으로 제외하며, 회사가 보상하는 상해는 예외입니다.",
            "scope": "상해급여·상해비급여"}


def compare_scoped(topic, documents):
    parser = deductible if topic == "deductible" else exclusion
    sides = {side: parser(documents[side]) for side in ("left", "right")}
    if not all(sides.values()):
        return unclear("입원 조항과 일치하는 근거를 양쪽 PDF에서 확인하지 못했습니다.")
    left, right = sides["left"], sides["right"]
    if left["scope"] != right["scope"]:
        return unclear("약관의 보장 유형이 달라 동일한 기준의 직접 비교를 보류했습니다.")
    status = "same" if left["signature"] == right["signature"] else "different"
    if topic == "deductible":
        comparison = (
            "상해입원 자기부담 방식이 동일하게 기재되어 있습니다." if status == "same"
            else "상해입원 자기부담 방식이 다르게 기재되어 있습니다. " +
                 "첫 PDF: " + left["summary"] + " 두 번째 PDF: " + right["summary"]
        )
        comparison += " 실제 가입 유형 확인이 필요합니다."
    else:
        comparison = (
            "비교한 상해 보장 조항의 임신·출산·산후기 보상 제외와 상해 예외가 동일합니다."
            if status == "same" else
            "비교한 상해 보장 조항의 보상 제외 또는 예외가 다릅니다."
        )
        comparison += " 실제 사고의 적용 여부는 가입 약관과 사고 내용을 확인해야 합니다."
    return {
        "left_status": "found", "right_status": "found",
        "left_claims": left["claims"], "right_claims": right["claims"],
        "comparison_status": status, "comparison": comparison,
    }, []


def compare_old_therapy(documents):
    left = page_for(documents["left"], lambda t:
        "비급여도수치료·체외충격파치료·증식치료실손의료비특별약관" in t and
        "보상하는내용" in t and "도수치료·체외충격파치료·증식치료" in t)
    right = page_for(documents["right"], lambda t:
        "(1)상해입원" in t and "도수치료·체외충격파치료·증식치료로인하여발생한비급여의료비" in t)
    # The exclusion may continue onto the following page after the section heading.
    if right is None:
        for page in documents["right"]["pages"]:
            t = compact(page["text"])
            if "11.도수치료·체외충격파치료·증식치료로인하여발생한비급여의료비" in t and "(2)상해통원" in t:
                right = page
                break
    if left is None or right is None:
        return None
    left_fact = "비급여 도수치료·체외충격파치료·증식치료 특별약관에 보상 조항이 있습니다. 실제 적용에는 특약 가입 확인이 필요합니다."
    right_fact = "상해입원 보통약관의 보상 제외 항목에 도수치료·체외충격파치료·증식치료로 인한 비급여 의료비가 기재되어 있습니다."
    return {
        "left_status": "found", "right_status": "found",
        "left_claims": [claim(left["page"], left["text"], left_fact)],
        "right_claims": [claim(right["page"], right["text"], right_fact)],
        "comparison_status": "different",
        "comparison": "첫 PDF에는 해당 특별약관의 보상 조항이 있고, 두 번째 PDF의 상해입원 보통약관에는 해당 비급여 의료비가 보상 제외로 기재되어 있습니다. 실제 적용 여부는 가입한 특약을 확인해야 합니다.",
    }, []


def compare_old_limit(documents):
    found = {}
    for side in ("left", "right"):
        page = page_for(documents[side], lambda t:
            "(1)상해입원" in t and "하나의상해당보험가입금액(5천만원" in t)
        if page is None:
            return None
        text = compact(page["text"])
        start = text.find("(1)상해입원")
        clause = text[start:start + 350]
        selectable = "5천만원이내에서계약시계약자가정한금액" in clause
        fixed = "보험가입금액(5천만원)한도" in clause
        if not (selectable or fixed):
            return None
        fact = ("하나의 상해당 5천만원 이내에서 계약자가 정한 보험가입금액 한도입니다."
                if selectable else "하나의 상해당 보험가입금액 5천만원 한도입니다.")
        found[side] = (selectable, claim(page["page"], clause, fact))
    same = found["left"][0] == found["right"][0]
    comparison = (
        "두 PDF의 하나의 상해당 보장 한도 문구가 동일합니다."
        if same else
        "첫 PDF는 5천만원 이내에서 계약자가 정한 금액을 한도로 하고, 두 번째 PDF는 5천만원 한도로 기재합니다. 실제 가입금액은 보험증권 확인이 필요합니다."
    )
    return {
        "left_status": "found", "right_status": "found",
        "left_claims": [found["left"][1]], "right_claims": [found["right"][1]],
        "comparison_status": "same" if same else "different",
        "comparison": comparison,
    }, []
