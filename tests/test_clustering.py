from hr_agent.clustering import complete_link, similarity


def test_geography_does_not_change_similarity():
    a = {"hard_skills": ["python"], "tasks": ["api"], "industry": ["it"], "level": "senior", "soft_skills": ["communication"], "city": "Moscow"}
    b = {**a, "city": "Saint Petersburg"}
    assert similarity(a, b) == 1
    assert complete_link([(1, a), (2, b)]) == [[1, 2]]


def test_complete_link_rejects_weak_pair():
    a = {"hard_skills": ["a"], "tasks": ["x"], "industry": ["it"], "level": "middle", "soft_skills": []}
    b = {**a, "hard_skills": ["a", "b"]}
    c = {**a, "hard_skills": ["b"]}
    groups = complete_link([(1, a), (2, b), (3, c)], threshold=.8)
    assert not any(1 in group and 3 in group for group in groups)
