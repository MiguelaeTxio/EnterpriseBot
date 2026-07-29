# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/context_processors.py
"""
Context available to every panel template.

WHY THIS EXISTS

`panel/_nav_items.html` gates almost every sidebar entry on bare
`company_user`, not on `request.user.company_user`. Until now nothing
provided that variable globally: each view had to inject it by hand,
and 23 places in `panel/` do. Any view that forgot silently lost most
of the sidebar -- the conditions simply evaluated false, with no error
anywhere. That is the recurring "se pierden opciones en la sidebar"
Miguel Angel reported in S037, and it was set to happen again with
every new view added to the project.

Providing it here fixes every past, present and future view at once.
Views that already set `company_user` in their own context keep
winning: Django gives the view's context precedence over a context
processor, so nothing that works today changes behaviour.

---

Contexto disponible en todas las plantillas del panel.

POR QUE EXISTE

`panel/_nav_items.html` condiciona casi todas las entradas de la
sidebar a `company_user` a secas, no a `request.user.company_user`.
Hasta ahora nada proveia esa variable de forma global: cada vista
tenia que inyectarla a mano, y 23 sitios de `panel/` lo hacen. La
vista que se olvidara perdia en silencio media sidebar -- las
condiciones daban falso sin ningun error por ninguna parte. Es el
"se pierden opciones en la sidebar" recurrente que reporto Miguel
Angel en S037, y estaba condenado a repetirse con cada vista nueva.

Proveerlo aqui repara de golpe todas las vistas, pasadas, presentes y
futuras. Las que ya ponen `company_user` en su propio contexto siguen
mandando: Django da precedencia al contexto de la vista sobre el de un
procesador, asi que nada de lo que hoy funciona cambia de
comportamiento.
"""


def company_context(request):
    """
    Expose the active CompanyUser and its Company to every template.

    Returns an empty dict for anonymous or non-linked users, so login
    and error pages render exactly as before.

    ---

    Expone el CompanyUser activo y su Company a todas las plantillas.

    Devuelve un diccionario vacio para usuarios anonimos o sin
    CompanyUser vinculado, de modo que el login y las paginas de error
    se renderizan igual que antes.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    company_user = getattr(user, "company_user", None)
    if company_user is None:
        return {}

    return {
        "company_user": company_user,
        "company": company_user.company,
    }
