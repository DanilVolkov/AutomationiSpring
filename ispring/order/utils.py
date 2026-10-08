from collections import OrderedDict, defaultdict
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


@dataclass
class Cell:
    value: str
    module_id: str = None
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
        header_bottom, course_headers = self._build_header_bottom()
        header_top = self._build_header_top(course_headers)
        rows = self._build_rows(course_headers)

        return render_to_string(
            'order/partials/_track_table.html',
            {
                'header_top': header_top,
                'header_bottom': header_bottom,
                'rows': rows,
            },
        )

    def _build_header_top(self, course_headers) -> list[Cell]:
        header: list[Cell] = [
            Cell(value='№', rowspan=2, css='corner'),
            Cell(value='ФИО', rowspan=2, css='corner'),
        ]

        for course in self._track.courses:
            header.append(
                Cell(value=course.title, colspan=len(course_headers[course.id]), css='course')
            )

        return header

    def _get_type_item(self, module: Module) -> str:
        if module.title.endswith(self.item_extensions):
            return 'video'

        if module.result_users is not None and len(module.result_users) > 0:
            is_hw = any(map(
                lambda x: True if (
                        x.passing_score is not None and
                        x.awarded_score is not None
                ) else False,
                module.result_users
            ))
            if is_hw:
                return 'hw'

        return 'other'

    def _build_header_bottom(self) -> tuple[list[Cell], dict[str, list[Cell]]]:
        header: list[Cell] = []
        course_headers: dict[str, list] = defaultdict(list)
        lecture_headers = tuple(map(lambda x: Cell(value=x, css='module'), self.module_stub_fields[:3]))
        hw_headers = tuple(map(lambda x: Cell(value=x, css='module'), self.module_stub_fields[3:]))
        for course in self._track.courses:
            if not course.modules:
                # Пустой курс — пустая ячейка в нижней шапке.
                header.append(Cell(value='', css='module-empty'))
                course_headers[course.id].append(Cell(value='', css='module-empty'))
                continue

            lecture = []
            hw = []
            others = []
            for module in course.modules:
                module_type = self._get_type_item(module)
                if module_type == 'video' and len(lecture) == 0:
                    for c in lecture_headers:
                        lecture.append(Cell(module_id=module.id, value=c.value, css=c.css))
                elif module_type == 'hw' and len(hw) == 0:
                    for c in hw_headers:
                        hw.append(Cell(module_id=module.id, value=c.value, css=c.css))
                else:
                    others.append(Cell(module_id=module.id, value=module.title, css='module'))

            if len(lecture) > 0:
                header.extend(lecture)
                course_headers[course.id].extend(lecture)
            if len(hw) > 0:
                header.extend(hw)
                course_headers[course.id].extend(hw)
            if len(others) > 0:
                header.extend(others)
                course_headers[course.id].extend(others)

        return header, course_headers

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

    def _build_rows(self, course_headers: dict[str, list[Cell]]) -> list[list[Cell]]:
        users = self._collect_users()
        rows: list[list[Cell]] = []

        for idx, (user_id, ur) in enumerate(users.items(), start=1):
            row: list[Cell] = [
                Cell(value=str(idx), css='num'),
                Cell(value=(ur.fio or ''), css='fio'),
            ]

            for course in self._track.courses:
                if not course.modules:
                    row.append(Cell(value='', css='empty'))
                    continue

                for header in course_headers[course.id]:
                    module: Module | None = None

                    if header.module_id is None:
                        row.append(Cell(value='', css='empty'))
                        continue

                    for m in course.modules:
                        if header.module_id == m.id:
                            module = m
                            break

                    if module is None:
                        row.append(Cell(value='', css='empty'))
                        continue

                    user_results = self._find_user_results_in_module(
                        module,
                        user_id
                    )
                    row.append(self._make_cell(header.value, user_results))



                # for module in course.modules:
                #     user_results = self._find_user_results_in_module(module, user_id)
                #     for header in course_headers[course.id]:
                #         row.append(self._make_cell(header.value, user_results))
            print(row)
            rows.append(row)
        print(rows)
        return rows

    @staticmethod
    def _find_user_results_in_module(module: Module, user_id: str) -> UserResults | None:
        for r in module.result_users:
            if r.user_id == user_id:
                return r
        return None

    @staticmethod
    def _make_cell(header: str, ur: UserResults | None) -> Cell:
        if ur is None:
            return Cell(value='Нет результата', css='empty')

        match header:
            case 'Лекция iSpring':
                return Cell(value=Table._format_value(ur.progress))
            case 'Лекция IVA':
                return Cell(value='', css='empty')
            case 'Лекция итог':
                result = False
                # TODO: запрос в БД для данных IVA
                user_iva = None
                # TODO: сопоставление пользователя из IVA с текущим пользователем
                if user_iva is None and ur.progress is not None and ur.progress >= 75.0:
                    result = True
                return Cell(value=str(int(result)))
            case 'ДЗ порог':
                return Cell(value=Table._format_value(ur.passing_score))
            case 'ДЗ прогресс':
                result = ur.progress
                if (
                    (ur.progress is None and ur.awarded_score is not None) or
                    (ur.progress is not None and ur.awarded_score is not None
                    and ur.progress != ur.awarded_score)
                ):
                    result = ur.awarded_score
                return Cell(value=Table._format_value(result))
            case 'ДЗ итог':
                result = ''
                if ur.completion_status is not None:
                    result = ur.completion_status
                else:
                    ps = Table._format_value(ur.passing_score)
                    p = Table._format_value(ur.progress)
                    if ps != '' and p != '':
                        if ur.progress >= ur.passing_score:
                            result = 'Принято'
                        else:
                            result = 'Отклонено'

                return Cell(value=result)

        return Cell(value=Table._format_value(ur.progress))


    @staticmethod
    def _format_value(value) -> str:
        if value is None:
            return ''
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
