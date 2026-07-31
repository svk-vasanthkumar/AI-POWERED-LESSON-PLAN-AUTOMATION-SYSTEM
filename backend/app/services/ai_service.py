from groq import Groq

from app.config.settings import settings

client = Groq(api_key=settings.GROQ_API_KEY)


async def generate_lesson_plan(text: str):
    prompt = f"""
You are an experienced college professor.

Based on the syllabus below, generate a professional lesson plan.

Include:

1. Course Title
2. Course Objectives
3. Learning Outcomes
4. Bloom's Taxonomy Levels
5. Teaching Methods
6. Weekly Lesson Plan
7. Assessment Methods
8. Required Resources

Syllabus:

{text}
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0.5,
    )

    return response.choices[0].message.content