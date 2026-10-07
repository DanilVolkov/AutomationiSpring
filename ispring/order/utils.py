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
    note: str = ''


class Table:
    module_stub_fields: list[str] = [
        'Лекция iSpring',
        'Лекция IVA',
        'Лекция итог',
        'ДЗ порог',
        'ДЗ прогресс',
        'ДЗ итог'
    ]

    item_extensions = (
        ".mp4",
        ".avi",
        ".mkv",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",
        ".mpg",
        ".mpeg",
        ".3gp",
        ".3g2",
        ".ogv",
        ".ts",
        ".mts",
        ".m2ts",
        ".vob",
        ".rm",
        ".rmvb",
        ".asf",
        ".divx",
        ".f4v",
        ".swf"
    )

    def __init__(
            self,
            learning_track: LearningTrack,
    ):
        self._track = learning_track


    def to_html(self) -> str:
        header_bottom, course_cols_nums = self._build_header_bottom()
        header_top = self._build_header_top(course_cols_nums)
        rows = self._build_rows()

        return render_to_string(
            'order/partials/_track_table.html',
            {
                'header_top': header_top,
                'header_bottom': header_bottom,
                'rows': rows,
            },
        )

    def _build_header_top(self, course_cols_nums) -> list[Cell]:
        header: list[Cell] = [
            Cell(value='№', rowspan=2, css='corner'),
            Cell(value='ФИО', rowspan=2, css='corner'),
        ]

        for course in self._track.courses:
            header.append(
                Cell(value=course.title, colspan=course_cols_nums[course.id], css='course')
            )

        return header

    def _get_type_item(self, module: Module) -> str:
        if module.title.endswith(self.item_extensions):
            return 'video'

        if (
            module.result_users is not None and
            len(module.result_users) > 0 and
            'passing_score' in module.result_users[0] and
            'awarded_score' in module.result_users[0]
        ):
            return 'hw'

        return 'other'


    def _build_header_bottom(self) -> tuple[list[Cell], dict[str, int]]:
        header: list[Cell] = []
        course_cols_nums = {}
        for course in self._track.courses:
            course_cols_nums[course.id] = 0
            if not course.modules:
                # Пустой курс — пустая ячейка в нижней шапке.
                header.append(Cell(value='', css='module-empty'))
                course_cols_nums[course.id] = 1
                continue

            is_lecture = False
            is_hw = False
            others = []
            for module in course.modules:
                module_type = self._get_type_item(module)
                if module_type == 'video' and not is_lecture:
                    is_lecture = True
                elif module_type == 'hw' and not is_hw:
                    is_hw = True
                else:
                    others.append(Cell(value=module.title, css='module'))

            if is_lecture:
                header.extend(self.item_extensions[:3])
                course_cols_nums[course.id] += 3
            if is_hw:
                header.extend(self.item_extensions[3:])
                course_cols_nums[course.id] += 3
            if others:
                header.extend(others)
                course_cols_nums[course.id] += len(others)

        return header, course_cols_nums

    def _collect_users(self) -> dict[str, UserResults]:
        users: dict[str, UserResults] = dict()
        for course in self._track.courses:
            for module in course.modules:
                for user in module.result_users:
                    if user.user_id not in users:
                        users[user.user_id] = user
        return dict(sorted(
            users.items(), key=lambda item: (item[1].fio or '').lower()
        ))

    def _build_rows(self) -> list[list[Cell]]:
        users = self._collect_users()
        rows: list[list[Cell]] = []

        for idx, user_id, ur in enumerate(users.items(), start=1):
            row: list[Cell] = [
                Cell(value=str(idx), css='num'),
                Cell(value=(ur.fio or ''), css='fio'),
            ]

            for course in self._track.courses:
                if not course.modules:
                    row.append(Cell(value='', css='empty'))
                    continue

                for module in course.modules:
                    match = self._find_result(module, user_id)
                    # нужно как-то понять, какие столбцы для какого курса сформированы
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
