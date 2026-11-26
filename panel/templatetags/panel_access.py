# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/templatetags/panel_access.py
"""
The sidebar menu, without the links the user may not open.

---

S163 (26/11): el menú lateral sin los enlaces a áreas a las que el
usuario no puede entrar (con la puerta por áreas encendida). Apagada,
el menú sale exactamente igual que antes.
"""
from django import template
from django.utils.safestring import mark_safe

from panel.access_rules import filter_menu_html

register = template.Library()


@register.simple_tag(takes_context=True)
def panel_nav(context):
    """
    Render panel/_nav_items.html and drop denied links.

    ---

    Pinta el menú (panel/_nav_items.html) y quita los enlaces a áreas
    sin permiso.
    """
    nav = context.template.engine.get_template("panel/_nav_items.html")
    html = nav.render(context)
    company_user = context.get("company_user")
    if company_user is None:
        return mark_safe(html)
    return mark_safe(filter_menu_html(html, company_user))
