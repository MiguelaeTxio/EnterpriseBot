"""
budgets/management/commands/geocode_toll_segments.py

Management command — geocodifica los TollSegment que no tienen coordenadas.
Llama a la Geocoding API de Google para cada punto de peaje (origen y destino)
que aún no tenga lat/lng y persiste el resultado en la BD.

Uso:
    python manage.py geocode_toll_segments [--dry-run] [--road ROAD_CODE]
                                           [--batch-size N] [--force]

Opciones:
    --dry-run       Mostrar qué se geocodificaría sin escribir en la BD.
    --road          Filtrar por código de vía (ej: AP-7, AP-46).
    --batch-size    Número de segmentos a procesar por lote (default: 50).
    --force         Regeocódificar incluso los que ya tienen coordenadas.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from budgets.models import TollSegment


class Command(BaseCommand):
    help = "Geocodifica los TollSegment sin coordenadas vía la Geocoding API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Mostrar qué se geocodificaría sin escribir en la BD.",
        )
        parser.add_argument(
            "--road",
            type=str,
            default=None,
            help="Filtrar por código de vía (ej: AP-7).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Número de segmentos por lote (default: 50).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Regeocódificar aunque ya tengan coordenadas.",
        )

    def handle(self, *args, **options):
        import os
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
        if not api_key:
            raise CommandError(
                "GOOGLE_MAPS_API_KEY no está configurada en el entorno."
            )

        dry_run    = options["dry_run"]
        road       = options["road"]
        batch_size = options["batch_size"]
        force      = options["force"]

        qs = TollSegment.objects.all()
        if road:
            qs = qs.filter(road_code__iexact=road)
        if not force:
            qs = qs.filter(origin_lat__isnull=True)

        total = qs.count()
        self.stdout.write(
            self.style.NOTICE(
                f"Segmentos a geocodificar: {total}"
                + (" (dry-run)" if dry_run else "")
            )
        )
        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nada que hacer."))
            return

        ok = 0
        errors = 0

        for i in range(0, total, batch_size):
            batch = list(qs[i : i + batch_size])
            for seg in batch:
                try:
                    o_lat, o_lng = self._geocode(
                        seg.origin_name, seg.road_code, api_key
                    )
                    d_lat, d_lng = self._geocode(
                        seg.dest_name, seg.road_code, api_key
                    )
                except _GeoError as exc:
                    self.stderr.write(
                        f"  ERROR [{seg.road_code}] "
                        f"{seg.origin_name} → {seg.dest_name}: {exc}"
                    )
                    errors += 1
                    continue

                self.stdout.write(
                    f"  OK  [{seg.road_code}] "
                    f"{seg.origin_name} ({o_lat:.5f},{o_lng:.5f}) → "
                    f"{seg.dest_name} ({d_lat:.5f},{d_lng:.5f})"
                )

                if not dry_run:
                    seg.origin_lat = o_lat
                    seg.origin_lng = o_lng
                    seg.dest_lat   = d_lat
                    seg.dest_lng   = d_lng
                    seg.save(update_fields=[
                        "origin_lat", "origin_lng",
                        "dest_lat", "dest_lng",
                    ])
                ok += 1
                # Throttle: Geocoding API free tier ~50 req/s.
                time.sleep(0.05)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nGeocódificados: {ok} | Errores: {errors}"
                + (" (dry-run — nada guardado)" if dry_run else "")
            )
        )


class _GeoError(Exception):
    pass


def _geocode_query(name: str, road_code: str) -> str:
    """
    Build a search query for a toll point name on a specific road.
    """
    name_clean = name.strip()
    road_clean = road_code.strip().upper()
    # Try: "PEAJE MALAGA AP-7 España"
    return f"{name_clean} {road_clean} España"


def _geocode(name: str, road_code: str, api_key: str) -> tuple[float, float]:
    """
    Geocode a toll point name + road code via the Google Geocoding API.
    Returns (lat, lng) or raises _GeoError.
    """
    query = _geocode_query(name, road_code)
    params = urllib.parse.urlencode({
        "address":  query,
        "key":      api_key,
        "language": "es",
        "region":   "es",
    })
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise _GeoError(f"Red: {exc}") from exc

    status = data.get("status")
    if status == "ZERO_RESULTS":
        raise _GeoError(f"Sin resultados para: {query!r}")
    if status != "OK":
        raise _GeoError(f"API status={status} para: {query!r}")

    loc = data["results"][0]["geometry"]["location"]
    return float(loc["lat"]), float(loc["lng"])


# Patch the method onto Command so it is accessible as self._geocode
Command._geocode = staticmethod(_geocode)
