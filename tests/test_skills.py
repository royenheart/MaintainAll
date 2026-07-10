from pathlib import Path
from MaintainAll.skills.loader import load_skills, load_skill_body

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


def test_load_skills_index():
    skills = load_skills(FIXTURES)
    assert len(skills) == 1
    assert skills[0].name == "sample"
    assert "unit tests" in skills[0].description


def test_load_skill_body():
    body = load_skill_body(FIXTURES / "sample")
    assert "Do the sample thing" in body
