from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime

from django.template.loader import render_to_string

status_compliance = {
    'not_started': 'Не начато',
    'in_progress': 'В процессе',
    'pending': 'Ожидает проверки',
    'complete': 'Завершено',
    'passed': 'Пройдено',
    'accepted': 'Принято',
    'incomplete': 'Не завершено',
    'failed': 'Не пройдено',
    'declined': 'Отклонено',
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
        self.added_date = datetime.fromisoformat(self.added_date).strftime(
            '%d.%m.%Y'
        )


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
        self.added_date = datetime.fromisoformat(self.added_date).strftime(
            '%d.%m.%Y'
        )


@dataclass
class Module:
    id: str
    title: str
    course_id: str
    result_users: list[UserResults] = None


@dataclass
class UserResults:
    user_id: str
    fio: str
    completion_status: str
    progress: float | int | None
    awarded_score: float | int | None  # только в дз
    passing_score: float | int | None  # только в дз

    def __post_init__(self):
        self.completion_status = status_compliance.get(
            self.completion_status, ''
        )


@dataclass
class Cell:
    value: str
    colspan: int = 1
    rowspan: int = 1
    skip: bool = False
    css: str = ''


class Table:
    """
    Превращает LearningTrack в структуры для HTML-таблицы:
      - header_top    : list[list[Cell]]   — верхняя строка шапки (курсы)
      - header_bottom : list[Cell]   — нижняя строка шапки (модули × заглушки)
      - rows          : list[list[Cell]]   — строки данных
    """

    MODULE_STUB_FIELDS: list[str] = ['Лекция', 'Время', 'ДЗ']

    def __init__(
        self,
        learning_track: LearningTrack,
        stub_fields: list[str] | None = None,
    ):
        self._track = learning_track
        self._stub = (
            list(stub_fields)
            if stub_fields is not None
            else list(self.MODULE_STUB_FIELDS)
        )

    @property
    def header_top(self) -> list[list[Cell]]:
        return self._build_header_top()

    @property
    def header_bottom(self) -> list[Cell]:
        return self._build_header_bottom()

    @property
    def rows(self) -> list[list[Cell]]:
        return self._build_rows()

    def to_html(self) -> str:

        return render_to_string(
            'order/partials/_track_table.html',
            {
                'header_top': self.header_top,
                'header_bottom': self.header_bottom,
                'rows': self.rows,
            },
        )

    def _build_header_top(self) -> list[list[Cell]]:
        """
        Верхний уровень шапки:
          [№(rowspan=2), ФИО(rowspan=2), Course1(colspan=N1)]
        """
        header: list[Cell] = [
            Cell(value='№', rowspan=2, css='corner'),
            Cell(value='ФИО', rowspan=2, css='corner'),
        ]

        for course in self._track.courses:
            # Сколько колонок займёт курс:
            # сумма колонок-заглушек по всем модулям курса.
            colspan = sum(len(self._stub) for _ in course.modules)
            # Если модулей нет — 1 пустая колонка, чтобы курс не «схлопнулся».
            colspan = max(colspan, 1)
            header.append(
                Cell(value=course.title, colspan=colspan, css='course')
            )

        return [header]

    def _build_header_bottom(self) -> list[Cell]:
        """
        Нижний уровень шапки: для каждого модуля — len(stub) колонок.
        """
        header: list[Cell] = []
        for course in self._track.courses:
            if not course.modules:
                # Пустой курс — пустая ячейка в нижней шапке.
                header.append(Cell(value='', css='module-empty'))
                continue
            for module in course.modules:
                for sf in self._stub:
                    label = (
                        f'{module.title}'
                        if not sf
                        else f'{module.title} — {sf}'
                    )
                    header.append(Cell(value=label, css='module'))
        return header

    def _collect_users(self) -> 'OrderedDict[str, UserResults]':
        """
        Все пользователи из всех модулей в порядке первого появления.
        """
        users: OrderedDict[str, UserResults] = OrderedDict()
        for course in self._track.courses:
            for module in course.modules:
                for ur in module.result_users:
                    users.setdefault(ur.user_id, ur)
        return users

    def _build_rows(self) -> list[list[Cell]]:
        users = self._collect_users()
        rows: list[list[Cell]] = []

        for idx, (user_id, ur) in enumerate(users.items(), start=1):
            row: list[Cell] = [
                Cell(value=str(idx), css='num'),
                Cell(value=(ur.fio or '').strip(), css='fio'),
            ]

            for course in self._track.courses:
                if not course.modules:
                    row.append(Cell(value='', css='empty'))
                    continue

                for module in course.modules:
                    match = self._find_result(module, user_id)
                    for sf in self._stub:
                        row.append(self._make_cell(sf, match))

            rows.append(row)

        return rows

    @staticmethod
    def _find_result(module: Module, user_id: str) -> UserResults | None:
        for r in module.result_users:
            if r.user_id == user_id:
                return r
        return None

    @staticmethod
    def _make_cell(stub_field: str, ur: UserResults | None) -> Cell:
        """
        Заглушка: здесь вы подставите свои поля.
        Пока — грубый маппинг на progress / awarded_score.
        """
        if ur is None:
            return Cell(value='—', css='empty')

        if stub_field == 'Лекция':
            return Cell(value=Table._fmt(ur.progress))
        if stub_field == 'Время':
            return Cell(value='—')  # TODO: вставить своё поле
        if stub_field == 'ДЗ':
            return Cell(value=Table._fmt(ur.awarded_score))
        return Cell(value='—')

    @staticmethod
    def _fmt(value) -> str:
        if value is None:
            return '—'
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
