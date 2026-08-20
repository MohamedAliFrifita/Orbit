import asyncio, json
from pathlib import Path
from orbit.tools.classify_exhibitor import classify_exhibitor_batch
from orbit.schemas.exhibitor import ExhibitorInput
from orbit.schemas.run import ICPContext

async def main():
    eval_data = json.loads(Path("eval/classifier_eval_v1.json").read_text())
    icp = ICPContext(**eval_data["icp"])
    exhibitors = [ExhibitorInput(**item["exhibitor"]) for item in eval_data["items"]]
    expected_list = [item["expected"] for item in eval_data["items"]]

    results = await classify_exhibitor_batch(exhibitors, icp)

    passed = failed = 0
    for res, exp, item in zip(results, expected_list, eval_data["items"]):
        ok_cat = res.category == exp["category"]
        ok_score = exp["potential_score_range"][0] <= res.potential_score <= exp["potential_score_range"][1]
        ok_rationale = all(kw in res.rationale for kw in exp.get("rationale_must_mention", []))
        ok_sources = all(s in res.sources_used for s in exp.get("sources_used_must_include", []))

        ok = ok_cat and ok_score and ok_rationale and ok_sources
        status = "✅" if ok else "❌"
        details = []
        if not ok_cat: details.append(f"catégorie={res.category}≠{exp['category']}")
        if not ok_score: details.append(f"score={res.potential_score:.2f} hors [{exp['potential_score_range'][0]},{exp['potential_score_range'][1]}]")
        if not ok_rationale: details.append(f"rationale manque: {exp.get('rationale_must_mention')}")
        if not ok_sources: details.append(f"sources manque: {exp.get('sources_used_must_include')}")

        print(f"{status} [{item['data_quality']}] {item['exhibitor']['name']} — {', '.join(details) or 'OK'}")
        if ok: passed += 1
        else: failed += 1

    print(f"\nScore : {passed}/{passed+failed}")
    print(f"Dont cas 'name_only' : filtrer par data_quality pour voir la performance sur inférences")

asyncio.run(main())