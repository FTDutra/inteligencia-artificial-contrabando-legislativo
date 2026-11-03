from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    """Permite acessar valores de um dicionário dinamicamente no template do Django."""
    if dictionary and isinstance(dictionary, dict):
        return dictionary.get(str(key), dictionary.get(key, ""))
    return ""