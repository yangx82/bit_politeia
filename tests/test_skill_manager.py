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

def test_get_skill_index(skill_manager):
    skill_manager.load_skills()
    index = skill_manager.get_skill_index()
    assert "## AVAILABLE AGENT SKILLS" in index
    assert "- pdf-reader: Extracts text from PDF files for analysis. Use when user wants to read a PDF, summarize a document, or extract content from a research paper." in index

def test_get_skill_instruction(skill_manager):
    skill_manager.load_skills()
    instruction = skill_manager.get_skill_instruction("pdf-reader")
    assert "# GUIDE FOR SKILL: pdf-reader" in instruction
    assert "Extracts text from PDF files from PDF files" not in instruction # Check for duplicates
    assert "## Core Workflow" in instruction
