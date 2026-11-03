from .models import MenuCabecalho

def menus_cabecalho(request):
    """Injeta os menus ativos do cabeçalho globalmente em todos os templates."""
    menus = MenuCabecalho.objects.filter(ativo=True).order_by('ordem', 'id')
    return {
        'menus_globais': menus
    }