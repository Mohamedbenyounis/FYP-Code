"""
Repository pattern for database access.
"""

from typing import List, Optional
from pathlib import Path

from app.core.models import EnrolledPerson


class InMemoryPersonRepository:
    """In-memory person repository for Iteration 1."""

    def __init__(self) -> None:
        self._persons: List[EnrolledPerson] = []

    def get_all(self) -> List[EnrolledPerson]:
        """Get all enrolled persons."""
        return self._persons.copy()

    def get_by_id(self, person_id: int) -> Optional[EnrolledPerson]:
        """Get person by ID."""
        # TODO: Implement
        return None

    def get_by_name(self, name: str) -> Optional[EnrolledPerson]:
        """Get person by name."""
        # TODO: Implement
        return None

    def add_person(self, person: EnrolledPerson) -> None:
        """Add an enrolled person."""
        self._persons.append(person)

    def clear(self) -> None:
        """Clear all persons."""
        self._persons.clear()


class SQLitePersonRepository:
    """SQLite person repository. Stub for Iteration 2."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        # TODO: Implement in Iteration 2

    def get_all(self) -> List[EnrolledPerson]:
        """Get all enrolled persons."""
        raise NotImplementedError("SQLite repository not implemented yet")
