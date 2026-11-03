from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.hashers import check_password
from .models import PerfilUsuario


class DuplaSenhaBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, segunda_senha=None, **kwargs):
        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user is not None:
            # Se o usuário passou na primeira senha, valida a segunda
            try:
                perfil = user.perfil
                if segunda_senha and check_password(segunda_senha, perfil.segunda_senha):
                    return user
            except PerfilUsuario.DoesNotExist:
                # Se o usuário não possui perfil de segunda senha cadastrado, permitimos ou bloqueamos conforme regra.
                # Aqui exigimos que o perfil exista e a segunda senha bata.
                pass
        return None