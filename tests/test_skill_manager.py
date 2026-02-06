import os
import sys
import pytest
# Add backend directory to path so we can import 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.agent.skill_manager import SkillManager

@pytest.fixture
def skill_manager():
    # Use the actual skills directory
    skills_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend/skills'))
    return SkillManager(skills_dir)

def test_load_skills(skill_manager):
    skill_manager.load_skills()
    assert "pdf-reader" in skill_manager.loaded_skills
    
    skill = skill_manager.loaded_skills["pdf-reader"]
    assert skill["name"] == "pdf-reader"
    assert "Extracts text from PDF files" in skill["description"]

def test_get_skill_tools(skill_manager):
    skill_manager.load_skills()
    tools = skill_manager.get_skill_tools()
    
    # Locate the pdf-reader tool
    pdf_tool = next((t for t in tools if "pdf-reader_read_pdf" in t.name), None)
    assert pdf_tool is not None
    assert "Extracts text from PDF files" in str(skill_manager.loaded_skills["pdf-reader"]["description"])

def test_get_skill_prompts(skill_manager):
    skill_manager.load_skills()
    prompts = skill_manager.get_skill_prompts()
    assert "## ENABLED AGENT SKILLS" in prompts
    assert "### Skill: pdf-reader" in prompts
