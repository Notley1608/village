import json


def _job_context(job):
    parts = [f"Client: {job['client_name']}", f"Target role: {job['target_role']}"]
    if job["contact"]:
        parts.append(f"Contact: {job['contact']}")
    if job["answers"]:
        try:
            answers = json.loads(job["answers"])
            for key, value in answers.items():
                parts.append(f"{key}: {value}")
        except (ValueError, AttributeError):
            parts.append(f"Client answers: {job['answers']}")
    return "\n".join(parts)


def _common_instructions():
    return (
        "Output a complete, ready-to-ship deliverable in plain markdown. "
        "Use strong action verbs and concrete outcomes where supportable. "
        "Never invent employers, degrees, certificates, dates, or facts "
        "that are not in the resume or the client's answers."
    )


def build_resume_rewrite(job):
    return (
        "You are a professional resume writer preparing a client for an interview loop.\n"
        "Rewrite the client's resume for the target role. Tailor skills and "
        "achievements to what hiring managers in that role actually look for.\n"
        f"{_common_instructions()}\n\n"
        f"--- CLIENT CONTEXT ---\n{_job_context(job)}\n\n"
        f"--- CURRENT RESUME ---\n{job['resume_text']}"
    )


def build_linkedin_summary(job):
    return (
        "You are a LinkedIn profile strategist.\n"
        "Write a first-person LinkedIn 'About' section (120-180 words) that "
        "tells a career story aimed at the target role, plus 3 headline "
        "options under 220 characters each.\n"
        f"{_common_instructions()}\n\n"
        f"--- CLIENT CONTEXT ---\n{_job_context(job)}\n\n"
        f"--- CURRENT RESUME (source material) ---\n{job['resume_text']}"
    )


def build_cover_letter(job):
    return (
        "You are a cover-letter writer.\n"
        "Write a concise, confident cover letter (300-380 words) for the "
        "target role. Reference the client's most relevant achievements and "
        "show why they fit. Address it to an unnamed hiring manager.\n"
        f"{_common_instructions()}\n\n"
        f"--- CLIENT CONTEXT ---\n{_job_context(job)}\n\n"
        f"--- CURRENT RESUME (source material) ---\n{job['resume_text']}"
    )