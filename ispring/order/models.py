from django.db import models


class User(models.Model):
    user_id = models.UUIDField(verbose_name='ID пользователя')
    first_name = models.CharField(
        max_length=255, verbose_name='Имя', blank=True
    )
    last_name = models.CharField(
        max_length=255, verbose_name='Фамилия', blank=True
    )
    patronymic = models.CharField(
        max_length=255, verbose_name='Отчество', blank=True
    )

    class Meta:
        ordering = ['last_name', 'first_name', 'patronymic']

    def __str__(self):
        return (
            f'{self.user_id} '
            f'({self.first_name} {self.last_name} {self.patronymic})'
        )
#
# class IvaUser(models.Model):
#     course_id
#     course_name
#     lesson_id
#     lesson_name
#     first_name
#     last_name
#     patronymic
#     other
#     email
#     phone
#     entry_time
#     exit_time
#     duration
#     device
#     user_type
#     ip_address
