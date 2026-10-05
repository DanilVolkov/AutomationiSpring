from django.db import models


class User(models.Model):
    user_id = models.UUIDField(verbose_name='ID пользователя')
    first_name = models.CharField(max_length=255, verbose_name='Имя', blank=True)
    last_name = models.CharField(max_length=255, verbose_name='Фамилия', blank=True)
    patronymic = models.CharField(max_length=255, verbose_name='Отчество', blank=True)
    email = models.CharField(max_length=255, verbose_name='Почта', blank=True)

    def __str__(self):
        return (
            f'{self.user_id} '
            f'({self.first_name} {self.last_name} {self.patronymic})'
        )

    class Meta:
        ordering = ['last_name', 'first_name', 'patronymic']
