# Librerías de terceros del visor de clases

Se sirven desde la propia app (`/static/vendor/…`) en vez de un CDN: la cabecera CSP del servidor solo
permite scripts propios, la app tiene que funcionar sin conexión, y el saneado del visor no debe depender
de un script remoto. Son las compilaciones minificadas publicadas en npm, sin modificar.

| Archivo | Paquete y versión | Origen dentro del paquete | Licencia | SHA-256 |
|---|---|---|---|---|
| `marked.min.js` | `marked@12.0.2` | `marked.min.js` | MIT (`LICENSE-marked.md`) | `15fabce5b65898b32b03f5ed25e9f891a729ad4c0d6d877110a7744aa847a894` |
| `purify.min.js` | `dompurify@3.4.16` | `dist/purify.min.js` | MPL-2.0 o Apache-2.0 (`LICENSE-dompurify`) | `2c90a9b46d6463f26038a29b686e82bc91de01fdac9d5229e7cfe3b360134ea2` |
| `mermaid.min.js` | `mermaid@10.9.8` | `dist/mermaid.min.js` | MIT (el paquete no trae archivo de licencia) | `8d607d7ef1d077a8aa202e18e62212bfa992c68bfeabc5cf45d51a128fe6675d` |

## Actualizar una librería

1. `npm pack <paquete>@<versión> --ignore-scripts` en una carpeta vacía fuera del repo.
2. Extraer el `.tgz`, copiar solo el archivo de la tabla y recalcular su `sha256sum`.
3. Actualizar esta tabla y subir la versión de `app.js?v=` en `index.html`.
4. Probar el visor en el navegador con una clase que tenga tabla, bloque `mermaid`, bloque `svg` y un `<img onerror>`.

`.gitattributes` marca esta carpeta con `-text` para que git no altere los bytes de los archivos.
