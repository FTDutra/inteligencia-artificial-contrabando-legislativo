from django.contrib.auth.forms import AuthenticationForm
from django import forms


class LoginDuplaSenhaForm(AuthenticationForm):
    segunda_senha = forms.CharField(
        label="Segunda Senha (Auditoria)",
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
        required=True
    )

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        segunda_senha = self.cleaned_data.get('segunda_senha')

        if username and password and segunda_senha:
            from django.contrib.auth import authenticate
            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password,
                segunda_senha=segunda_senha
            )
            if self.user_cache is None:
                raise forms.ValidationError(
                    "Credenciais inválidas (verifique usuário, senha principal ou segunda senha)."
                )
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data