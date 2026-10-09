"""Business Understanding › One-line Answers: short answers about the business.

Each ``OneLineAnswers`` field's description is the question, which the wizard
page also shows as the label.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.ai_tools.task import AiTask


class Answer(BaseModel):
    answer: str = Field(description="The answer, in one line.")
    justification: str = Field(
        description="A few sentences of reasoning, grounded in the filings."
    )
    source: str = Field(
        description='The 10-K section(s) relied on, e.g. "FY2025 10-K, Item 1 (Business)".'
    )


class OneLineAnswers(BaseModel):
    industry: Answer = Field(description="What industry do they operate in?")
    industry_structure: Answer = Field(
        description="What is the structure of the industry?"
    )
    partners: Answer = Field(
        description=(
            "Who are their biggest partners (e.g. manufacturers, distributors, "
            "customers, etc.)?"
        )
    )
    core_competency: Answer = Field(description="What is their core competency?")
    value_chain: Answer = Field(
        description=(
            "What part of the value chain / risk do they own? What part of the "
            "value chain / risk do they not own?"
        )
    )
    competitors: Answer = Field(description="Who are their competitors?")
    commodity: Answer = Field(description="Is it a commodity business?")


ONE_LINE_ANSWERS_TASK = AiTask(
    name="one_line_answers",
    instructions=(
        "Answer each question in the result schema (the field descriptions) "
        "about this company, using its annual reports in the workspace. Read "
        "all the years; prefer the latest report for current facts. Keep each "
        "answer to one line; for the commodity question, start with yes or "
        "no and explain briefly within that line. Ground each justification "
        "in what the filings say. In each source, cite the fiscal year and Item, e.g. "
        '"FY2025 10-K, Item 1 (Business)".'
    ),
    result_model=OneLineAnswers,
)
