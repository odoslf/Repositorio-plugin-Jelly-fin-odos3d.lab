# Repositorio unificado Odos3d.Lab para Jellyfin

Este repositorio agrega automáticamente los catálogos de plugins de ODOS3D para que Jellyfin necesite una sola dirección de repositorio.

## Dirección para Jellyfin

`https://raw.githubusercontent.com/odoslf/Repositorio-plugin-Jelly-fin-odos3d.lab/main/manifest.json`

Actualmente agrega:

- Jellyfin Community
- JellyPremiere
- JellyLiveNow

## Sincronización automática

El workflow `Sync unified Jellyfin repository` consulta cada 15 minutos los manifiestos definidos en `sources.json`, valida su estructura, evita GUID duplicados y actualiza `manifest.json` solo cuando algún catálogo de origen cambia.

Para añadir otro plugin en el futuro basta con añadir la URL de su manifiesto a `sources.json`.
