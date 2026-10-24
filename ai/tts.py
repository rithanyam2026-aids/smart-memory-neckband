"""
Offline Text-to-Speech Engine for Python AI Service.
Generates reminder audio, past conversation recall, and daily summaries
to stream to the neckband speaker or phone earpiece.
"""

from __future__ import annotations
from typing import List, Optional
from ai.models import Reminder


class OfflineTTS:
    @staticmethod
    def speak_reminder(reminder: Reminder) -> str:
        speech = f"Reminder: {reminder.title}."
        if reminder.description:
            speech += f" {reminder.description}."
        return speech

    @staticmethod
    def speak_person_encounter(person_label: str, relationship: Optional[str], last_topic: Optional[str]) -> str:
        if relationship:
            speech = f"This is your {relationship}, {person_label}."
        else:
            speech = f"This is {person_label}."

        if last_topic:
            speech += f" You last spoke about: {last_topic}."
        return speech

    @staticmethod
    def generate_daily_summary(
        people_met: List[str],
        reminders_remaining: List[Reminder],
        important_notes: List[str]
    ) -> str:
        parts = ["Here is your daily summary."]
        if people_met:
            unique_people = list(dict.fromkeys(people_met))
            parts.append(f"Today you met {', '.join(unique_people)}.")
        else:
            parts.append("You have not had any visitors yet today.")

        if reminders_remaining:
            titles = [f"{r.title} at {r.scheduled_time}" for r in reminders_remaining]
            parts.append(f"You have {len(reminders_remaining)} scheduled reminders: {', '.join(titles)}.")
        else:
            parts.append("You have completed all reminders for today.")

        if important_notes:
            parts.append(f"Key note: {important_notes[0]}.")

        return " ".join(parts)
