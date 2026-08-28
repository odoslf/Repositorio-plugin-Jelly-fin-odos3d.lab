# Repositorio unificado ODOS3D para Jellyfin

Este repositorio agrega automáticamente los catálogos de los plugins de ODOS3D para que Jellyfin necesite una sola dirección de repositorio.

## Dirección única para Jellyfin

`https://raw.githubusercontent.com/odoslf/Repositorio-plugin-Jelly-fin-odos3d.lab/main/manifest.json`

Incluye actualmente:

- Community 1.6.0.0
- JellyPremiere 1.0.1.0
- JellyLiveNow 1.0.2.0

Todos apuntan a Jellyfin 10.10.7 (`targetAbi` 10.10.7.0).

## Validación automática

El workflow `Sync and validate unified Jellyfin repository` se ejecuta cada 15 minutos y también puede lanzarse manualmente. Para cada origen:

1. descarga y valida el manifiesto;
2. rechaza GUID o nombres duplicados;
3. comprueba `targetAbi` 10.10.7.0;
4. descarga el ZIP publicado y verifica que sea un paquete ZIP real;
5. verifica que el MD5 del paquete coincida con el checksum anunciado;
6. cuando detecta un cambio, instala juntos los tres paquetes en un Jellyfin 10.10.7 oficial;
7. ejecuta E2E combinado y revisa los logs de los tres plugins;
8. solo si todo lo anterior termina correctamente actualiza `manifest.json`.

Los catálogos de origen están definidos en `sources.json`. Para añadir otro plugin en el futuro basta con añadir su manifiesto y deberá superar la misma validación antes de publicarse en el catálogo unificado.
