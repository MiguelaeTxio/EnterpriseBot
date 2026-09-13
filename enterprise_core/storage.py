# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/enterprise_core/storage.py
"""
INCIDENTE REAL S102. Al activar de verdad `ManifestStaticFilesStorage`
por primera vez en todo el proyecto (ver `settings.STORAGES` y su
comentario -- `STATICFILES_STORAGE` llevaba años declarado pero
Django 5.2 lo ignora en runtime, así que el versionado por hash nunca
había estado activo), `collectstatic` fallaba por completo:

    ValueError: The file 'panel/vendor/bootstrap.bundle.min.js.map'
    could not be found with <...ManifestStaticFilesStorage...>.

`panel/vendor/bootstrap.bundle.min.js` (vendorizado, sin tocar)
lleva un comentario `//# sourceMappingURL=bootstrap.bundle.min.js.map`
-- estándar en cualquier build minificado, para que las DevTools del
navegador puedan mostrar el código fuente original al depurar -- pero
el `.map` correspondiente nunca se vendorizó junto al `.js`. El
post-procesado de `ManifestStaticFilesStorage` reescribe TODAS las
referencias `url()`/`sourceMappingURL` que encuentra en cada CSS/JS
para apuntar a la versión con hash, y si el archivo referenciado no
existe, `hashed_name()` lanza `ValueError` sin excepción -- y
`manifest_strict=False` NO evita esto: esa opción solo cambia el
comportamiento de `stored_name()` (búsqueda en tiempo de ejecución,
cuando el navegador ya pide un archivo), nunca el de `_stored_name()`
(usado durante el propio `collectstatic` para reescribir el
contenido) -- confirmado leyendo el código fuente real de Django
5.2.12, no por documentación general.

Verificado con una recreación real de `collectstatic` (mismos
`STATICFILES_DIRS` reales del proyecto + `django.contrib.admin`, 150
archivos) que esta subclase resuelve el problema sin ningún otro
efecto: el archivo con el `.map` ausente simplemente conserva su
nombre sin hashear en esa única referencia rota (el navegador no
podrá cargar el sourcemap de depuración de Bootstrap -- cosmético,
invisible para cualquier usuario final) -- todo lo demás se hashea
con normalidad.
"""
from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class LenientManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """
    Igual que `ManifestStaticFilesStorage`, pero si una referencia
    `url()`/`sourceMappingURL` dentro de un CSS/JS apunta a un archivo
    que no existe, la deja tal cual en vez de tumbar todo
    `collectstatic` -- mismo patrón documentado por el propio
    WhiteNoise para este caso exacto (referencia rota puntual dentro
    de un vendor de terceros, nunca un archivo propio del proyecto).
    """
    def _stored_name(self, name, hashed_files):
        try:
            return super()._stored_name(name, hashed_files)
        except ValueError:
            return self.clean_name(name)
