from datetime import datetime
from dataclasses import dataclass


status_compliance = {
    'not_started': 'Не начато',
    'in_progress': 'В процессе',
    'pending': 'Ожидает проверки',
    'complete': 'Завершено',
    'passed': 'Пройдено',
    'accepted': 'Принято',
    'incomplete': 'Не завершено',
    'failed': 'Не пройдено',
    'declined': 'Отклонено'
}

@dataclass
class Folder:
    id: str
    type: str
    title: str
    parent_id: str | None = None
    items: list[LearningTrack | Course] | None = None


@dataclass
class LearningTrack:
    id: str
    title: str
    type: str
    added_date: str
    view_url: str
    parent_id: str
    courses: list[Course] = None

    def __post_init__(self):
        self.added_date = datetime.fromisoformat(self.added_date).strftime('%d.%m.%Y')

@dataclass
class Course:
    id: str
    title: str
    type: str
    added_date: str
    view_url: str
    parent_id: str
    modules: list[Module] = None

    def __post_init__(self):
        self.added_date = datetime.fromisoformat(self.added_date).strftime('%d.%m.%Y')

@dataclass
class Module:
    id: str
    title: str
    result_users: list[UserResults]

@dataclass
class UserResults:
    user_id: str
    fio: str
    completion_status: str
    progress: float | int | None
    awarded_score: float | int | None  # только в дз
    passing_score: float | int | None  # только в дз

    def __post_init__(self):
        self.completion_status = status_compliance.get(self.completion_status, '')







